"""Secret de poste : ce qui lie une table à une session Windows.

Trente-deux octets tirés au hasard, rangés à côté de la table dans un fichier que seul Windows
sait ouvrir, pour ce compte et sur ce poste (DPAPI). Copié ailleurs, le fichier est inutilisable.
Session Windows perdue ou réinstallée : le secret est perdu, et la table avec lui. C'est voulu ;
« Déplacer la table » sert à l'emporter avant.
"""

import ctypes
import os
import sys
from pathlib import Path

_SANS_FENETRE = 0x1
_USAGE = b"celodata"


class PosteInconnu(Exception):
    """Le secret existe mais Windows refuse de l'ouvrir : il vient d'un autre poste ou d'un autre compte."""


class _Bloc(ctypes.Structure):
    _fields_ = [("taille", ctypes.c_uint32), ("donnees", ctypes.POINTER(ctypes.c_char))]


def disponible() -> bool:
    return sys.platform == "win32"


def _dpapi(fonction: str, donnees: bytes) -> bytes | None:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    entree = _Bloc(len(donnees), ctypes.cast(ctypes.create_string_buffer(donnees, len(donnees)), ctypes.POINTER(ctypes.c_char)))
    usage = _Bloc(len(_USAGE), ctypes.cast(ctypes.create_string_buffer(_USAGE, len(_USAGE)), ctypes.POINTER(ctypes.c_char)))
    sortie = _Bloc()
    appel = getattr(crypt32, fonction)
    appel.argtypes = [
        ctypes.POINTER(_Bloc), ctypes.c_void_p, ctypes.POINTER(_Bloc), ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_Bloc),
    ]
    appel.restype = ctypes.c_int
    if not appel(ctypes.byref(entree), None, ctypes.byref(usage), None, None, _SANS_FENETRE, ctypes.byref(sortie)):
        return None
    try:
        return ctypes.string_at(sortie.donnees, sortie.taille)
    finally:
        kernel32.LocalFree(sortie.donnees)


def proteger(donnees: bytes) -> bytes:
    resultat = _dpapi("CryptProtectData", donnees)
    if resultat is None:
        raise OSError("Windows n'a pas pu protéger le secret de poste.")
    return resultat


def reveler(protege: bytes) -> bytes:
    resultat = _dpapi("CryptUnprotectData", protege)
    if resultat is None:
        raise PosteInconnu("Ce secret vient d'un autre poste ou d'un autre compte Windows.")
    return resultat


def fichier(chemin_table: Path | str) -> Path:
    return Path(f"{chemin_table}.poste")


def lire(chemin_table: Path | str) -> bytes | None:
    """Rend le secret de la table, ou `None` s'il n'y en a pas encore."""
    try:
        protege = fichier(chemin_table).read_bytes()
    except FileNotFoundError:
        return None
    return reveler(protege)


def creer(chemin_table: Path | str) -> bytes:
    secret = os.urandom(32)
    fichier(chemin_table).write_bytes(proteger(secret))
    return secret
