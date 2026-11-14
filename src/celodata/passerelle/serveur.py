"""Le serveur de la passerelle.

Il n'expose que trois adresses. Tout le reste est refusé : rien ne part vers l'IA sans être filtré.

- `POST /v1/chat/completions` : filtre la demande, la transmet, restaure la réponse.
- `GET /v1/models` : liste des modèles de l'IA, pour les outils de discussion.
- `GET /sante` : pour vérifier que le serveur tourne.

Chaque utilisateur a une clé d'accès et sa propre table. La clé sert de mot de passe à la table :
le serveur ne garde que l'empreinte de la clé, et ne peut pas ouvrir une table sans son utilisateur.
"""

import argparse
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from celodata import __version__, journal
from celodata.detection.base import Detecteur
from celodata.passerelle.relais import DemandeRefusee, FluxRestaure, Session, filtrer_demande, restaurer_reponse
from celodata.table import MotDePasseIncorrect, Table

NOM_VALIDE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")


@dataclass
class Reglages:
    url_ia: str
    cle_ia: str
    dossier: Path
    hote: str = "127.0.0.1"
    port: int = 8787

    @property
    def fichier_utilisateurs(self) -> Path:
        return self.dossier / "utilisateurs.json"


def lire_reglages(chemin: Path) -> Reglages:
    with open(chemin, "rb") as f:
        brut = tomllib.load(f)
    ia, passerelle = brut.get("ia", {}), brut.get("passerelle", {})
    return Reglages(
        url_ia=ia["url"].rstrip("/"),
        # La clé de l'IA n'est jamais écrite dans le fichier de réglages.
        cle_ia=os.environ.get(ia.get("variable_cle", "CELODATA_CLE_IA"), ""),
        dossier=(chemin.parent / passerelle.get("dossier", "donnees")).resolve(),
        hote=passerelle.get("hote", "127.0.0.1"),
        port=int(passerelle.get("port", 8787)),
    )


# ---------- utilisateurs ----------


def _empreinte(cle: str) -> str:
    # Les clés sont tirées au hasard (256 bits) : une empreinte simple suffit.
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()


def lire_utilisateurs(reglages: Reglages) -> dict[str, str]:
    try:
        return json.loads(reglages.fichier_utilisateurs.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def ajouter_utilisateur(reglages: Reglages, nom: str) -> str:
    """Crée un utilisateur et rend sa clé d'accès. Elle n'est gardée nulle part : à transmettre tout de suite."""
    if not NOM_VALIDE.fullmatch(nom):
        raise ValueError("Nom invalide : lettres minuscules, chiffres, tiret, point ou tiret bas.")
    utilisateurs = lire_utilisateurs(reglages)
    if nom in utilisateurs:
        raise ValueError(f"L'utilisateur « {nom} » existe déjà. Sa table n'est lisible qu'avec sa clé actuelle.")
    cle = "celo-" + secrets.token_urlsafe(32)
    utilisateurs[nom] = _empreinte(cle)
    reglages.dossier.mkdir(parents=True, exist_ok=True)
    reglages.fichier_utilisateurs.write_text(json.dumps(utilisateurs, indent=2), encoding="utf-8")
    return cle


# ---------- serveur ----------


def _detecteur_par_defaut() -> tuple[Detecteur, bool]:
    from celodata.appli.api import detecteur_par_defaut

    return detecteur_par_defaut()


def _erreur(statut: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": "celodata", "code": statut}}, status_code=statut)


class Passerelle:
    def __init__(
        self,
        reglages: Reglages,
        fabrique: Callable[[], tuple[Detecteur, bool]] = _detecteur_par_defaut,
        transport: httpx.AsyncBaseTransport | None = None,
        options_table: dict | None = None,
    ) -> None:
        self.reglages = reglages
        self._fabrique = fabrique
        self._options_table = options_table or {}
        self._detecteur: Detecteur | None = None
        self.avec_modele = False
        self._sessions: dict[str, Session] = {}
        # Le modèle d'entités et les tables ne servent qu'une demande à la fois.
        self._verrou = threading.Lock()
        self._client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(300, connect=15))
        self.appli = Starlette(
            routes=[
                Route("/v1/chat/completions", self.discussion, methods=["POST"]),
                Route("/v1/models", self.modeles, methods=["GET"]),
                Route("/sante", self.sante, methods=["GET"]),
            ],
            lifespan=self._vie,
        )

    @contextlib.asynccontextmanager
    async def _vie(self, appli: Starlette):
        yield
        await self._client.aclose()

    def charger(self) -> None:
        with self._verrou:
            if self._detecteur is None:
                self._detecteur, self.avec_modele = self._fabrique()

    def _identifier(self, request: Request) -> tuple[str, str] | None:
        entete = request.headers.get("authorization", "")
        if not entete.lower().startswith("bearer "):
            return None
        cle = entete[7:].strip()
        empreinte = _empreinte(cle)
        for nom, attendue in lire_utilisateurs(self.reglages).items():
            if hmac.compare_digest(empreinte, attendue):
                return nom, cle
        return None

    def _session(self, nom: str, cle: str) -> Session:
        if nom not in self._sessions:
            self.reglages.dossier.mkdir(parents=True, exist_ok=True)
            table = Table.ouvrir(self.reglages.dossier / f"{nom}.celodata", cle, **self._options_table)
            self._sessions[nom] = Session(table)
        return self._sessions[nom]

    def _preparer(self, nom: str, cle: str, corps: dict) -> tuple[Session, dict, FluxRestaure | None]:
        self.charger()
        with self._verrou:
            session = self._session(nom, cle)
            filtre = filtrer_demande(corps, session, self._detecteur)
            return session, filtre, FluxRestaure(session) if corps.get("stream") else None

    def _sous_verrou(self, fonction, *arguments):
        with self._verrou:
            return fonction(*arguments)

    def _entetes_ia(self) -> dict[str, str]:
        # La clé de l'utilisateur ne sort pas de la passerelle : l'IA reçoit la clé de l'entreprise.
        return {"Authorization": f"Bearer {self.reglages.cle_ia}"}

    # ---------- adresses ----------

    async def sante(self, request: Request) -> JSONResponse:
        return JSONResponse({"etat": "ok", "version": __version__})

    async def modeles(self, request: Request) -> Response:
        if not self._identifier(request):
            return _erreur(401, "Clé d'accès Celodata absente ou inconnue.")
        try:
            reponse = await self._client.get(self.reglages.url_ia + "/models", headers=self._entetes_ia())
        except httpx.HTTPError as e:
            return _erreur(502, f"L'IA ne répond pas ({type(e).__name__}).")
        return Response(reponse.content, reponse.status_code, media_type=reponse.headers.get("content-type"))

    async def discussion(self, request: Request) -> Response:
        identite = self._identifier(request)
        if not identite:
            return _erreur(401, "Clé d'accès Celodata absente ou inconnue.")
        try:
            corps = await request.json()
        except ValueError:
            return _erreur(400, "La demande n'est pas un JSON valide.")
        try:
            session, filtre, flux = await run_in_threadpool(self._preparer, *identite, corps)
        except DemandeRefusee as e:
            return _erreur(400, str(e))
        except MotDePasseIncorrect:
            return _erreur(403, "La table de cet utilisateur a été créée avec une autre clé d'accès.")

        adresse = self.reglages.url_ia + "/chat/completions"
        try:
            if flux is None:
                reponse = await self._client.post(adresse, json=filtre, headers=self._entetes_ia())
            else:
                demande = self._client.build_request("POST", adresse, json=filtre, headers=self._entetes_ia())
                reponse = await self._client.send(demande, stream=True)
        except httpx.HTTPError as e:
            return _erreur(502, f"L'IA ne répond pas ({type(e).__name__}).")

        type_contenu = reponse.headers.get("content-type", "")
        if reponse.status_code != 200:
            # Une erreur de l'IA est rendue telle quelle : elle ne peut contenir que du texte filtré.
            contenu = await reponse.aread()
            await reponse.aclose()
            return Response(contenu, reponse.status_code, media_type=type_contenu or None)
        if flux is None:
            try:
                donnees = reponse.json()
            except ValueError:
                return _erreur(502, "La réponse de l'IA n'est pas un JSON valide.")
            return JSONResponse(await run_in_threadpool(self._sous_verrou, restaurer_reponse, donnees, session))
        return StreamingResponse(self._diffuser(reponse, flux, session), media_type="text/event-stream")

    async def _diffuser(self, reponse: httpx.Response, flux: FluxRestaure, session: Session):
        def ligne(donnees: dict) -> str:
            return f"data: {json.dumps(donnees, ensure_ascii=False)}\n\n"

        try:
            async for recue in reponse.aiter_lines():
                if not recue.startswith("data:"):
                    continue
                charge = recue[5:].strip()
                if charge == "[DONE]":
                    break
                try:
                    donnees = json.loads(charge)
                except ValueError:
                    # Un morceau illisible n'est pas transmis : il ne peut pas être restauré.
                    continue
                yield ligne(await run_in_threadpool(self._sous_verrou, flux.morceau, donnees))
            reste = await run_in_threadpool(self._sous_verrou, flux.reste)
            if reste:
                yield ligne(reste)
            yield "data: [DONE]\n\n"
        finally:
            await reponse.aclose()
            await run_in_threadpool(self._sous_verrou, journal.restauration, session.table, flux.bilan)


# ---------- ligne de commande ----------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Passerelle Celodata : filtre les demandes envoyées à une IA.")
    parser.add_argument("--reglages", type=Path, default=Path("passerelle.toml"), help="fichier de réglages")
    commandes = parser.add_subparsers(dest="commande", required=True)
    commandes.add_parser("servir", help="lance le serveur")
    utilisateur = commandes.add_parser("utilisateur", help="crée un utilisateur et affiche sa clé d'accès")
    utilisateur.add_argument("nom")
    args = parser.parse_args(argv)

    try:
        reglages = lire_reglages(args.reglages)
    except (OSError, KeyError, tomllib.TOMLDecodeError) as e:
        print(f"Réglages illisibles ({args.reglages}) : {e}", file=sys.stderr)
        return 2

    if args.commande == "utilisateur":
        try:
            cle = ajouter_utilisateur(reglages, args.nom)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        print(f"Clé d'accès de {args.nom} (affichée une seule fois, à lui transmettre) :\n{cle}")
        print("Cette clé protège aussi sa table : si elle est perdue, ses anciens textes ne pourront plus être restaurés.")
        return 0

    if not reglages.cle_ia:
        print("La clé de l'IA est absente : renseignez la variable d'environnement indiquée dans les réglages.", file=sys.stderr)
        return 2
    # Le modèle d'entités doit déjà être sur la machine : la passerelle ne parle qu'à l'IA.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    import uvicorn

    passerelle = Passerelle(reglages)
    passerelle.charger()
    if not passerelle.avec_modele:
        print("Attention : modèle d'entités absent, seules les règles tournent (les noms ne sont pas détectés).", file=sys.stderr)
    # Pas de journal des accès : il n'apporterait rien et n'a pas à garder trace des échanges.
    uvicorn.run(passerelle.appli, host=reglages.hote, port=reglages.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
