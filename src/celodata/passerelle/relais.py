"""Filtrage d'une demande et restauration d'une réponse au format OpenAI (`chat/completions`).

Rien ici ne parle au réseau : ce module transforme des dictionnaires. Le serveur est dans `serveur.py`.
"""

import hashlib
import json
from collections import OrderedDict
from collections.abc import Callable

import regex

from celodata import journal
from celodata.detection.base import Detecteur, Detection
from celodata.moteur import Restauration, analyser, pseudonymiser, restaurer, texte_motif_jetons
from celodata.table import Table

TEXTES_GARDES = 2000
# Un jeton coupé entre deux morceaux d'une réponse en flux tient largement dans cette longueur.
LONGUEUR_RETENUE = 80


class DemandeRefusee(Exception):
    """La demande contient quelque chose que la passerelle ne sait pas filtrer. Elle n'est pas transmise."""


class Session:
    """Ce que la passerelle garde en mémoire pour un utilisateur : sa table ouverte et les textes déjà filtrés."""

    def __init__(self, table: Table) -> None:
        self.table = table
        # Une discussion renvoie tout son historique à chaque message : on ne le réanalyse pas.
        # Seuls l'empreinte du texte et son résultat filtré sont gardés.
        self.deja: OrderedDict[bytes, str] = OrderedDict()


def _dans_json(texte: str, transformer: Callable[[str], str]) -> str:
    """Applique `transformer` aux chaînes d'un texte JSON, en gardant un JSON valide."""
    try:
        donnees = json.loads(texte)
    except ValueError:
        return transformer(texte)

    def parcourir(v):
        if isinstance(v, str):
            return transformer(v)
        if isinstance(v, list):
            return [parcourir(x) for x in v]
        if isinstance(v, dict):
            return {k: parcourir(x) for k, x in v.items()}
        return v

    return json.dumps(parcourir(donnees), ensure_ascii=False)


# ---------- demande ----------


def _filtrer_texte(texte: str, session: Session, detecteur: Detecteur, nouvelles: list[Detection]) -> str:
    if not texte.strip():
        return texte
    cle = hashlib.sha256(texte.encode("utf-8")).digest()
    if cle in session.deja:
        session.deja.move_to_end(cle)
        return session.deja[cle]
    detections = analyser(texte, detecteur, session.table)
    filtre = pseudonymiser(texte, detections, session.table).texte
    nouvelles.extend(detections)
    session.deja[cle] = filtre
    if len(session.deja) > TEXTES_GARDES:
        session.deja.popitem(last=False)
    return filtre


def filtrer_demande(corps: dict, session: Session, detecteur: Detecteur) -> dict:
    """Rend la demande à transmettre à l'IA : tous les textes des messages sont filtrés."""
    if not isinstance(corps, dict) or not isinstance(corps.get("messages"), list):
        raise DemandeRefusee("La demande doit contenir une liste « messages ».")
    nouvelles: list[Detection] = []
    filtrer = lambda t: _filtrer_texte(t, session, detecteur, nouvelles)  # noqa: E731

    # Ces champs peuvent identifier la personne et ne servent pas à la réponse.
    sortie = {k: v for k, v in corps.items() if k not in ("user", "metadata", "safety_identifier")}
    messages = []
    for message in corps["messages"]:
        if not isinstance(message, dict):
            raise DemandeRefusee("Message mal formé.")
        m = dict(message)
        if m.get("role") not in ("tool", "function"):
            m.pop("name", None)
        contenu = m.get("content")
        if isinstance(contenu, str):
            m["content"] = filtrer(contenu)
        elif isinstance(contenu, list):
            parties = []
            for partie in contenu:
                if not (isinstance(partie, dict) and partie.get("type") == "text" and isinstance(partie.get("text"), str)):
                    raise DemandeRefusee(
                        "La passerelle ne filtre que le texte : les images et les fichiers joints sont refusés."
                    )
                parties.append({**partie, "text": filtrer(partie["text"])})
            m["content"] = parties
        elif contenu is not None:
            raise DemandeRefusee("Contenu de message non pris en charge.")
        if m.get("tool_calls"):
            appels = []
            for appel in m["tool_calls"]:
                fonction = dict(appel.get("function") or {})
                if isinstance(fonction.get("arguments"), str):
                    fonction["arguments"] = _dans_json(fonction["arguments"], filtrer)
                appels.append({**appel, "function": fonction})
            m["tool_calls"] = appels
        messages.append(m)
    sortie["messages"] = messages
    if nouvelles:
        journal.filtrage(session.table, nouvelles, mode="passerelle", detecteur=detecteur.nom)
    return sortie


# ---------- réponse entière ----------


def _cumuler(bilan: Restauration, r: Restauration) -> str:
    bilan.inconnus += [j for j in r.inconnus if j not in bilan.inconnus]
    bilan.approximatifs += r.approximatifs
    return r.texte


def restaurer_reponse(corps: dict, session: Session) -> dict:
    """Remet les vraies valeurs dans une réponse non diffusée en flux."""
    bilan = Restauration("")
    rendre = lambda t: _cumuler(bilan, restaurer(t, session.table))  # noqa: E731
    for choix in corps.get("choices") or []:
        message = choix.get("message") or {}
        if isinstance(message.get("content"), str):
            message["content"] = rendre(message["content"])
        for appel in message.get("tool_calls") or []:
            fonction = appel.get("function") or {}
            if isinstance(fonction.get("arguments"), str):
                fonction["arguments"] = _dans_json(fonction["arguments"], rendre)
    journal.restauration(session.table, bilan)
    return corps


# ---------- réponse en flux ----------


class FluxRestaure:
    """Restaure une réponse qui arrive par morceaux.

    Un jeton peut être coupé entre deux morceaux (« PERSON », « NE_1 », « 2 »). La fin d'un morceau
    est donc retenue tant qu'elle peut être le début d'un jeton, et rendue avec le morceau suivant.
    """

    def __init__(self, session: Session) -> None:
        self._table = session.table
        texte = texte_motif_jetons(session.table.types())
        self._motif = regex.compile(texte, regex.IGNORECASE) if texte else None
        self._contenus: dict[int, str] = {}
        self._arguments: dict[tuple[int, int], str] = {}
        self._enveloppe: dict = {}
        self.bilan = Restauration("")

    def _coupe(self, tampon: str) -> int:
        """Position à partir de laquelle la fin du tampon peut encore devenir un jeton."""
        if self._motif:
            for debut in range(max(0, len(tampon) - LONGUEUR_RETENUE), len(tampon)):
                if self._motif.fullmatch(tampon, debut, partial=True):
                    return debut
        return len(tampon)

    def _rendre(self, texte: str) -> str:
        return _cumuler(self.bilan, restaurer(texte, self._table)) if texte else texte

    def morceau(self, donnees: dict) -> dict:
        self._enveloppe = {k: v for k, v in donnees.items() if k not in ("choices", "usage")}
        for choix in donnees.get("choices") or []:
            i = choix.get("index", 0)
            delta = choix.get("delta") or {}
            fin = choix.get("finish_reason") is not None
            if isinstance(delta.get("content"), str) or (fin and self._contenus.get(i)):
                tampon = self._contenus.get(i, "") + (delta.get("content") or "")
                coupe = len(tampon) if fin else self._coupe(tampon)
                delta["content"] = self._rendre(tampon[:coupe])
                self._contenus[i] = tampon[coupe:]
            # Les arguments d'un appel d'outil sont rendus d'un bloc à la fin, pour rester un JSON valide.
            for appel in delta.get("tool_calls") or []:
                fonction = appel.get("function") or {}
                if isinstance(fonction.get("arguments"), str):
                    cle = (i, appel.get("index", 0))
                    self._arguments[cle] = self._arguments.get(cle, "") + fonction["arguments"]
                    fonction["arguments"] = ""
            if fin:
                for (j, outil), arguments in sorted(self._arguments.items()):
                    if j == i and arguments:
                        delta.setdefault("tool_calls", []).append(
                            {"index": outil, "function": {"arguments": _dans_json(arguments, self._rendre)}}
                        )
                        self._arguments[(j, outil)] = ""
            choix["delta"] = delta
        return donnees

    def reste(self) -> dict | None:
        """Ce qui est encore retenu quand le flux se termine sans prévenir."""
        choix = [
            {"index": i, "delta": {"content": self._rendre(tampon)}, "finish_reason": None}
            for i, tampon in sorted(self._contenus.items())
            if tampon
        ]
        for (i, outil), arguments in sorted(self._arguments.items()):
            if arguments:
                appel = {"index": outil, "function": {"arguments": _dans_json(arguments, self._rendre)}}
                choix.append({"index": i, "delta": {"tool_calls": [appel]}, "finish_reason": None})
        self._contenus.clear()
        self._arguments.clear()
        return {**self._enveloppe, "choices": choix} if choix else None
