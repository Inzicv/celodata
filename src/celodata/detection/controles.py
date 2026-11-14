"""Clés de contrôle des numéros français.

Chaque fonction rend True (clé juste), False (clé fausse : ce n'est pas le numéro attendu)
ou None (pas de clé à vérifier).
"""

import ipaddress
import re

_SEPARATEURS = re.compile(r"[\s.\-]")


def _compact(valeur: str) -> str:
    return _SEPARATEURS.sub("", valeur).upper()


def luhn(valeur: str) -> bool:
    chiffres = _compact(valeur)
    if not chiffres.isdigit():
        return False
    total = 0
    for rang, c in enumerate(reversed(chiffres)):
        n = int(c)
        if rang % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def nir(valeur: str) -> bool | None:
    """Numéro de sécurité sociale : la clé vaut 97 moins le reste de la division par 97."""
    v = _compact(valeur)
    if len(v) == 13:
        return None
    corps = v[:13].replace("2A", "19").replace("2B", "18")
    if not (corps.isdigit() and v[13:].isdigit()):
        return False
    return 97 - int(corps) % 97 == int(v[13:])


def iban(valeur: str) -> bool:
    v = _compact(valeur)
    if not 15 <= len(v) <= 34:
        return False
    deplace = v[4:] + v[:4]
    try:
        return int("".join(str(int(c, 36)) for c in deplace)) % 97 == 1
    except ValueError:
        return False


def tva(valeur: str) -> bool | None:
    """TVA intracommunautaire française : FR + clé sur deux caractères + SIREN."""
    v = _compact(valeur)
    cle, siren = v[2:4], v[4:]
    if not cle.isdigit():
        return None
    return (12 + 3 * (int(siren) % 97)) % 97 == int(cle)


def ipv6(valeur: str) -> bool:
    try:
        ipaddress.IPv6Address(valeur)
    except ValueError:
        return False
    return True
