"""Table de correspondance chiffrée entre les vraies valeurs et leurs jetons.

Un fichier SQLite par projet, qui ne quitte pas la machine.

- Chaque valeur est chiffrée en AES-GCM. Le fichier ne contient aucune valeur en clair.
- Les clés de la table sont tirées au hasard et rangées dans le fichier sous une enveloppe
  chiffrée. La clé de l'enveloppe est dérivée du mot de passe avec Argon2id. Le mot de passe
  n'est stocké nulle part.
- Avec un secret de poste (appli de bureau), la clé de l'enveloppe dépend aussi de ce secret :
  le fichier copié ailleurs ne s'ouvre pas, même avec le bon mot de passe.
- Une empreinte à clé (HMAC) de chaque valeur permet de retrouver son jeton sans tout déchiffrer.
- Mot de passe perdu ou table détruite : la réidentification devient impossible. C'est voulu.

Restent lisibles dans le fichier : le type de chaque valeur, leur nombre et leur date d'ajout,
ainsi que le journal (dates et décomptes, sans valeur ni nom de fichier).
"""

import hashlib
import hmac
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

_TEMOIN = b"celodata"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS valeurs (
    type TEXT NOT NULL,
    numero INTEGER NOT NULL,
    empreinte BLOB NOT NULL UNIQUE,
    nonce BLOB NOT NULL,
    chiffre BLOB NOT NULL,
    cree_le TEXT NOT NULL,
    PRIMARY KEY (type, numero)
);
CREATE TABLE IF NOT EXISTS ignorees (empreinte BLOB PRIMARY KEY);
CREATE TABLE IF NOT EXISTS regles (id INTEGER PRIMARY KEY, nonce BLOB NOT NULL, chiffre BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    contenu TEXT NOT NULL,
    nonce BLOB,
    chiffre BLOB
);
"""


class MotDePasseIncorrect(Exception):
    pass


class TableDunAutrePoste(Exception):
    """La table est liée à un poste et son secret n'a pas été fourni."""


_ENVELOPPE = ("sel", "memoire_kio", "iterations", "temoin", "cles", "poste")


def _deriver(meta: dict, mot_de_passe: str, longueur: int) -> bytes:
    return Argon2id(
        salt=meta["sel"],
        length=longueur,
        iterations=int(meta["iterations"]),
        lanes=4,
        memory_cost=int(meta["memoire_kio"]),
    ).derive(mot_de_passe.encode("utf-8"))


def _cle_enveloppe(meta: dict, mot_de_passe: str, secret_poste: bytes | None) -> bytes:
    cle = _deriver(meta, mot_de_passe, 32)
    if secret_poste is not None:
        cle = hmac.new(secret_poste, cle, hashlib.sha256).digest()
    return cle


class Table:
    def __init__(
        self,
        connexion: sqlite3.Connection,
        cle_chiffrement: bytes,
        cle_empreinte: bytes,
        secret_poste: bytes | None = None,
    ) -> None:
        self._db = connexion
        self._cle_chiffrement = cle_chiffrement
        self._aes = AESGCM(cle_chiffrement)
        self._cle_empreinte = cle_empreinte
        self._secret_poste = secret_poste

    @classmethod
    def ouvrir(
        cls,
        chemin: Path | str,
        mot_de_passe: str,
        *,
        memoire_kio: int = 65536,
        iterations: int = 3,
        secret_poste: bytes | None = None,
    ) -> "Table":
        """Ouvre la table, ou la crée si le fichier n'existe pas. `:memory:` ne laisse rien sur disque.

        `secret_poste` lie la table au poste. Une table qui ne l'était pas le devient à cette
        ouverture ; une table liée ne s'ouvre plus sans lui.
        """
        # L'appli appelle la table depuis plusieurs fils, un à la fois (verrou côté appli).
        db = sqlite3.connect(str(chemin), check_same_thread=False)
        # Ce qui est effacé est écrasé dans le fichier : une ancienne enveloppe n'y reste pas.
        db.execute("PRAGMA secure_delete = ON")
        db.executescript(_SCHEMA)
        # Tables créées avant l'étape 4 : les valeurs ignorées n'avaient qu'une empreinte.
        if "chiffre" not in {c[1] for c in db.execute("PRAGMA table_info(ignorees)")}:
            db.execute("ALTER TABLE ignorees ADD COLUMN nonce BLOB")
            db.execute("ALTER TABLE ignorees ADD COLUMN chiffre BLOB")
        meta = dict(db.execute("SELECT cle, valeur FROM meta"))
        if "cles" in meta:
            liee = meta.get("poste") == b"1"
            if liee and secret_poste is None:
                db.close()
                raise TableDunAutrePoste("Cette table est liée à un autre poste.")
            enveloppe = AESGCM(_cle_enveloppe(meta, mot_de_passe, secret_poste if liee else None))
            try:
                cles = enveloppe.decrypt(meta["cles"][:12], meta["cles"][12:], b"cles")
            except InvalidTag:
                db.close()
                raise MotDePasseIncorrect("Mot de passe incorrect pour cette table.") from None
            table = cls(db, cles[:32], cles[32:], secret_poste)
            if not liee and secret_poste is not None:
                table._envelopper(mot_de_passe, secret_poste)
        elif "temoin" in meta:
            # Table d'avant l'enveloppe : ses clés sortent directement du mot de passe.
            cles = _deriver(meta, mot_de_passe, 64)
            table = cls(db, cles[:32], cles[32:], secret_poste)
            try:
                table._aes.decrypt(meta["temoin"][:12], meta["temoin"][12:], b"temoin")
            except InvalidTag:
                db.close()
                raise MotDePasseIncorrect("Mot de passe incorrect pour cette table.") from None
            if secret_poste is not None:
                # Les clés sont gardées, mais l'ancien sel est effacé : le mot de passe seul
                # ne permet plus de les retrouver.
                table._envelopper(mot_de_passe, secret_poste)
        else:
            cles = os.urandom(64)
            table = cls(db, cles[:32], cles[32:], secret_poste)
            table._envelopper(mot_de_passe, secret_poste, memoire_kio, iterations)
        return table

    def _envelopper(
        self,
        mot_de_passe: str,
        secret_poste: bytes | None,
        memoire_kio: int | None = None,
        iterations: int | None = None,
    ) -> None:
        """Range les clés de la table sous une enveloppe neuve, liée ou non au poste."""
        ancien = dict(self._db.execute("SELECT cle, valeur FROM meta WHERE cle IN ('memoire_kio', 'iterations')"))
        meta = {
            "sel": os.urandom(16),
            "memoire_kio": str(memoire_kio).encode() if memoire_kio else ancien["memoire_kio"],
            "iterations": str(iterations).encode() if iterations else ancien["iterations"],
            "poste": b"1" if secret_poste is not None else b"0",
        }
        nonce = os.urandom(12)
        cles = self._cle_chiffrement + self._cle_empreinte
        meta["cles"] = nonce + AESGCM(_cle_enveloppe(meta, mot_de_passe, secret_poste)).encrypt(nonce, cles, b"cles")
        with self._db:
            self._db.execute(f"DELETE FROM meta WHERE cle IN ({', '.join('?' * len(_ENVELOPPE))})", _ENVELOPPE)
            self._db.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
        self._secret_poste = secret_poste

    @staticmethod
    def liee_au_poste(chemin: Path | str) -> bool:
        """Dit, sans mot de passe, si le fichier est une table liée à un poste."""
        if str(chemin) == ":memory:" or not Path(chemin).exists():
            return False
        try:
            db = sqlite3.connect(f"{Path(chemin).resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.Error:
            return False
        try:
            ligne = db.execute("SELECT valeur FROM meta WHERE cle = 'poste'").fetchone()
        except sqlite3.Error:
            return False
        finally:
            db.close()
        return bool(ligne) and ligne[0] == b"1"

    def est_liee(self) -> bool:
        return self._secret_poste is not None

    def lier(self, mot_de_passe: str, secret_poste: bytes) -> None:
        """Lie la table ouverte à ce poste, sans toucher aux valeurs déjà chiffrées."""
        self._envelopper(mot_de_passe, secret_poste)

    def _verifier_mot_de_passe(self, mot_de_passe: str) -> None:
        meta = dict(self._db.execute("SELECT cle, valeur FROM meta"))
        try:
            if "cles" in meta:
                enveloppe = AESGCM(_cle_enveloppe(meta, mot_de_passe, self._secret_poste))
                enveloppe.decrypt(meta["cles"][:12], meta["cles"][12:], b"cles")
            else:
                AESGCM(_deriver(meta, mot_de_passe, 64)[:32]).decrypt(
                    meta["temoin"][:12], meta["temoin"][12:], b"temoin"
                )
        except InvalidTag:
            raise MotDePasseIncorrect("Mot de passe incorrect pour cette table.") from None

    def changer_mot_de_passe(self, ancien: str, nouveau: str) -> None:
        """Change le mot de passe qui protège l'enveloppe des clés, sans rechiffrer les valeurs."""
        self._verifier_mot_de_passe(ancien)
        self._envelopper(nouveau, self._secret_poste)

    def exporter(self, destination: Path | str, mot_de_passe: str) -> None:
        """Copie la table dans un fichier que le mot de passe seul ouvre, pour changer de poste.

        Le mot de passe est redemandé : c'est lui, et lui seul, qui protégera la copie.
        """
        self._verifier_mot_de_passe(mot_de_passe)
        copie = sqlite3.connect(str(destination))
        try:
            copie.execute("PRAGMA secure_delete = ON")
            self._db.backup(copie)
            Table(copie, self._cle_chiffrement, self._cle_empreinte)._envelopper(mot_de_passe, None)
            copie.execute("VACUUM")
        finally:
            copie.close()

    def _empreinte(self, valeur: str) -> bytes:
        return hmac.new(self._cle_empreinte, valeur.encode("utf-8"), hashlib.sha256).digest()

    def _chiffrer(self, texte: str, lie_a: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        return nonce, self._aes.encrypt(nonce, texte.encode("utf-8"), lie_a)

    def _dechiffrer(self, nonce: bytes, chiffre: bytes, lie_a: bytes) -> str:
        return self._aes.decrypt(nonce, chiffre, lie_a).decode("utf-8")

    def jeton(self, type_: str, valeur: str) -> str:
        """Rend le jeton de la valeur, en le créant au besoin.

        Une valeur déjà connue garde son jeton, même si un détecteur lui donne un autre type.
        """
        empreinte = self._empreinte(valeur)
        connu = self._db.execute(
            "SELECT type, numero FROM valeurs WHERE empreinte = ?", (empreinte,)
        ).fetchone()
        if connu:
            return f"{connu[0]}_{connu[1]}"
        with self._db:
            (numero,) = self._db.execute(
                "SELECT COALESCE(MAX(numero), 0) + 1 FROM valeurs WHERE type = ?", (type_,)
            ).fetchone()
            jeton = f"{type_}_{numero}"
            nonce = os.urandom(12)
            # Le jeton est lié au chiffré : une ligne déplacée à la main ne se déchiffre plus.
            chiffre = self._aes.encrypt(nonce, valeur.encode("utf-8"), jeton.encode())
            self._db.execute(
                "INSERT INTO valeurs VALUES (?, ?, ?, ?, ?, ?)",
                (type_, numero, empreinte, nonce, chiffre, datetime.now(UTC).isoformat()),
            )
        return jeton

    def valeur(self, type_: str, numero: int) -> str | None:
        ligne = self._db.execute(
            "SELECT nonce, chiffre FROM valeurs WHERE type = ? AND numero = ?", (type_, numero)
        ).fetchone()
        if not ligne:
            return None
        return self._aes.decrypt(ligne[0], ligne[1], f"{type_}_{numero}".encode()).decode("utf-8")

    def valeurs(self) -> list[tuple[str, str]]:
        """Toutes les correspondances déchiffrées (type, valeur), pour les rechercher dans un texte."""
        lignes = self._db.execute("SELECT type, numero, nonce, chiffre FROM valeurs").fetchall()
        return [
            (t, self._aes.decrypt(nonce, chiffre, f"{t}_{n}".encode()).decode("utf-8"))
            for t, n, nonce, chiffre in lignes
        ]

    def ignorer(self, valeur: str) -> None:
        """Retient qu'une valeur ne doit plus être masquée. Elle est gardée chiffrée, pour être listée."""
        nonce, chiffre = self._chiffrer(valeur, b"ignoree")
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO ignorees VALUES (?, ?, ?)", (self._empreinte(valeur), nonce, chiffre)
            )

    def ignorees(self) -> list[str]:
        lignes = self._db.execute("SELECT nonce, chiffre FROM ignorees WHERE chiffre IS NOT NULL")
        return sorted(self._dechiffrer(n, c, b"ignoree") for n, c in lignes)

    def ne_plus_ignorer(self, valeur: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM ignorees WHERE empreinte = ?", (self._empreinte(valeur),))

    def est_ignoree(self, valeur: str) -> bool:
        return (
            self._db.execute(
                "SELECT 1 FROM ignorees WHERE empreinte = ?", (self._empreinte(valeur),)
            ).fetchone()
            is not None
        )

    # Règles du projet : termes toujours masqués et motifs. Chiffrées en entier.

    def ajouter_regle(self, genre: str, texte: str, type_: str) -> int:
        """`genre` : "terme" (texte exact, casse ignorée) ou "motif" (expression régulière)."""
        nonce, chiffre = self._chiffrer(
            json.dumps({"genre": genre, "texte": texte, "type": type_}), b"regle"
        )
        with self._db:
            return self._db.execute(
                "INSERT INTO regles (nonce, chiffre) VALUES (?, ?)", (nonce, chiffre)
            ).lastrowid

    def regles(self) -> list[dict]:
        lignes = self._db.execute("SELECT id, nonce, chiffre FROM regles ORDER BY id").fetchall()
        return [{"id": i, **json.loads(self._dechiffrer(n, c, b"regle"))} for i, n, c in lignes]

    def supprimer_regle(self, identifiant: int) -> None:
        with self._db:
            self._db.execute("DELETE FROM regles WHERE id = ?", (identifiant,))

    # Réglages de l'appli, chiffrés (par exemple le dossier surveillé).

    def regler(self, nom: str, valeur: str | None) -> None:
        """Range un réglage. `None` l'efface."""
        cle = f"reglage:{nom}"
        with self._db:
            self._db.execute("DELETE FROM meta WHERE cle = ?", (cle,))
            if valeur is not None:
                nonce, chiffre = self._chiffrer(valeur, cle.encode())
                self._db.execute("INSERT INTO meta VALUES (?, ?)", (cle, nonce + chiffre))

    def reglage(self, nom: str) -> str | None:
        cle = f"reglage:{nom}"
        ligne = self._db.execute("SELECT valeur FROM meta WHERE cle = ?", (cle,)).fetchone()
        return self._dechiffrer(ligne[0][:12], ligne[0][12:], cle.encode()) if ligne else None

    # Journal : décomptes en clair, nom de fichier chiffré. Jamais de vraie valeur.

    def journaliser(self, contenu: dict, fichier: str | None = None) -> None:
        nonce, chiffre = self._chiffrer(fichier, b"journal") if fichier else (None, None)
        with self._db:
            self._db.execute(
                "INSERT INTO journal (date, contenu, nonce, chiffre) VALUES (?, ?, ?, ?)",
                (datetime.now(UTC).isoformat(timespec="seconds"), json.dumps(contenu), nonce, chiffre),
            )

    def journal(self, limite: int = 200) -> list[dict]:
        """Les dernières lignes du journal, la plus récente d'abord."""
        lignes = self._db.execute(
            "SELECT date, contenu, nonce, chiffre FROM journal ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
        return [
            {"date": d, "fichier": self._dechiffrer(n, c, b"journal") if c else "", **json.loads(contenu)}
            for d, contenu, n, c in lignes
        ]

    def types(self) -> list[str]:
        return [t for (t,) in self._db.execute("SELECT DISTINCT type FROM valeurs")]

    def __len__(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM valeurs").fetchone()[0]

    def purger(self, jours: int) -> int:
        """Supprime les correspondances plus vieilles que `jours`. Leurs jetons deviennent définitifs."""
        limite = (datetime.now(UTC) - timedelta(days=jours)).isoformat()
        with self._db:
            supprimees = self._db.execute("DELETE FROM valeurs WHERE cree_le < ?", (limite,)).rowcount
        self._db.execute("VACUUM")
        return supprimees

    def fermer(self) -> None:
        self._db.close()

    def __enter__(self) -> "Table":
        return self

    def __exit__(self, *_: object) -> None:
        self.fermer()
