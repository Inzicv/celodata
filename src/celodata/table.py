"""Table de correspondance chiffrée entre les vraies valeurs et leurs jetons.

Un fichier SQLite par projet, qui ne quitte pas la machine.

- Chaque valeur est chiffrée en AES-GCM. Le fichier ne contient aucune valeur en clair.
- Les clés sont dérivées du mot de passe avec Argon2id. Le mot de passe n'est stocké nulle part.
- Une empreinte à clé (HMAC) de chaque valeur permet de retrouver son jeton sans tout déchiffrer.
- Mot de passe perdu ou table détruite : la réidentification devient impossible. C'est voulu.

Restent lisibles dans le fichier : le type de chaque valeur, leur nombre et leur date d'ajout.
"""

import hashlib
import hmac
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
"""


class MotDePasseIncorrect(Exception):
    pass


class Table:
    def __init__(self, connexion: sqlite3.Connection, cle_chiffrement: bytes, cle_empreinte: bytes) -> None:
        self._db = connexion
        self._aes = AESGCM(cle_chiffrement)
        self._cle_empreinte = cle_empreinte

    @classmethod
    def ouvrir(
        cls,
        chemin: Path | str,
        mot_de_passe: str,
        *,
        memoire_kio: int = 65536,
        iterations: int = 3,
    ) -> "Table":
        """Ouvre la table, ou la crée si le fichier n'existe pas. `:memory:` ne laisse rien sur disque."""
        db = sqlite3.connect(str(chemin))
        db.executescript(_SCHEMA)
        meta = dict(db.execute("SELECT cle, valeur FROM meta"))
        if not meta:
            meta = {
                "sel": os.urandom(16),
                "memoire_kio": str(memoire_kio).encode(),
                "iterations": str(iterations).encode(),
            }
        cles = Argon2id(
            salt=meta["sel"],
            length=64,
            iterations=int(meta["iterations"]),
            lanes=4,
            memory_cost=int(meta["memoire_kio"]),
        ).derive(mot_de_passe.encode("utf-8"))
        table = cls(db, cles[:32], cles[32:])
        if "temoin" in meta:
            # Le témoin est une valeur connue chiffrée à la création : il vérifie le mot de passe.
            try:
                table._aes.decrypt(meta["temoin"][:12], meta["temoin"][12:], b"temoin")
            except InvalidTag:
                db.close()
                raise MotDePasseIncorrect("Mot de passe incorrect pour cette table.") from None
        else:
            nonce = os.urandom(12)
            meta["temoin"] = nonce + table._aes.encrypt(nonce, _TEMOIN, b"temoin")
            with db:
                db.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
        return table

    def _empreinte(self, valeur: str) -> bytes:
        return hmac.new(self._cle_empreinte, valeur.encode("utf-8"), hashlib.sha256).digest()

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
