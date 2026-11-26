"""Table liée au poste, Windows Hello et « Déplacer la table »."""

import os
import sqlite3
import sys

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from celodata import poste
from celodata.appli.api import AUTRE_POSTE, Api
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.regles import DetecteurRegles
from celodata.table import _SCHEMA, _TEMOIN, MotDePasseIncorrect, Table, TableDunAutrePoste, _deriver

LEGER = {"memoire_kio": 64, "iterations": 1}
SECRET = os.urandom(32)


def regles_seules():
    return DetecteurCompose("regles", [DetecteurRegles()]), False


class FauxPoste:
    """Remplace DPAPI : le secret est rangé en clair, et `autre` simule un autre poste."""

    def __init__(self):
        self.autre = False

    def lire(self, chemin):
        f = poste.fichier(chemin)
        if not f.exists():
            return None
        if self.autre:
            raise poste.PosteInconnu("autre poste")
        return f.read_bytes()

    def creer(self, chemin):
        secret = os.urandom(32)
        poste.fichier(chemin).write_bytes(secret)
        return secret


# --- Table ---------------------------------------------------------------------------------


def test_table_liee_ne_s_ouvre_pas_sans_son_secret(tmp_path):
    chemin = tmp_path / "p.celodata"
    with Table.ouvrir(chemin, "juste", secret_poste=SECRET, **LEGER) as t:
        assert t.est_liee()
        t.jeton("PERSONNE", "Rose Petit")
    assert Table.liee_au_poste(chemin)
    with pytest.raises(TableDunAutrePoste):
        Table.ouvrir(chemin, "juste", **LEGER)
    with pytest.raises(MotDePasseIncorrect):
        Table.ouvrir(chemin, "juste", secret_poste=os.urandom(32), **LEGER)
    with pytest.raises(MotDePasseIncorrect):
        Table.ouvrir(chemin, "faux", secret_poste=SECRET, **LEGER)
    with Table.ouvrir(chemin, "juste", secret_poste=SECRET, **LEGER) as t:
        assert t.valeur("PERSONNE", 1) == "Rose Petit"


def test_table_non_liee_le_devient_a_l_ouverture(tmp_path):
    chemin = tmp_path / "p.celodata"
    with Table.ouvrir(chemin, "juste", **LEGER) as t:
        assert not t.est_liee()
        t.jeton("PERSONNE", "Rose Petit")
    assert not Table.liee_au_poste(chemin)
    with Table.ouvrir(chemin, "juste", secret_poste=SECRET, **LEGER) as t:
        assert t.est_liee()
    assert Table.liee_au_poste(chemin)
    with pytest.raises(TableDunAutrePoste):
        Table.ouvrir(chemin, "juste", **LEGER)
    with Table.ouvrir(chemin, "juste", secret_poste=SECRET, **LEGER) as t:
        assert t.valeur("PERSONNE", 1) == "Rose Petit"


def _ancienne_table(chemin, mot_de_passe):
    """Fabrique une table au format d'avant l'enveloppe : clés tirées du mot de passe, témoin."""
    db = sqlite3.connect(str(chemin))
    db.executescript(_SCHEMA)
    meta = {"sel": os.urandom(16), "memoire_kio": b"64", "iterations": b"1"}
    cle = _deriver(meta, mot_de_passe, 64)[:32]
    nonce = os.urandom(12)
    meta["temoin"] = nonce + AESGCM(cle).encrypt(nonce, _TEMOIN, b"temoin")
    with db:
        db.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
    db.close()
    return meta["sel"]


def test_ancienne_table_reprise_puis_liee(tmp_path):
    chemin = tmp_path / "ancienne.celodata"
    ancien_sel = _ancienne_table(chemin, "juste")
    with Table.ouvrir(chemin, "juste") as t:
        t.jeton("PERSONNE", "Yann Kerbrat")
    with pytest.raises(MotDePasseIncorrect):
        Table.ouvrir(chemin, "faux")
    with Table.ouvrir(chemin, "juste", secret_poste=SECRET) as t:
        assert t.valeur("PERSONNE", 1) == "Yann Kerbrat"
    # L'ancien sel est effacé : le mot de passe seul ne redonne plus les clés.
    assert ancien_sel not in chemin.read_bytes()
    with pytest.raises(TableDunAutrePoste):
        Table.ouvrir(chemin, "juste")
    with Table.ouvrir(chemin, "juste", secret_poste=SECRET) as t:
        assert t.valeur("PERSONNE", 1) == "Yann Kerbrat"


def test_exporter_donne_une_copie_que_le_mot_de_passe_seul_ouvre(tmp_path):
    chemin, copie = tmp_path / "p.celodata", tmp_path / "copie.celodata"
    with Table.ouvrir(chemin, "juste", secret_poste=SECRET, **LEGER) as t:
        t.jeton("PERSONNE", "Rose Petit")
        with pytest.raises(MotDePasseIncorrect):
            t.exporter(copie, "faux")
        t.exporter(copie, "juste")
    assert not Table.liee_au_poste(copie)
    assert b"Rose Petit" not in copie.read_bytes()
    with Table.ouvrir(copie, "juste") as t:
        assert not t.est_liee()
        assert t.valeur("PERSONNE", 1) == "Rose Petit"
    # L'original, lui, reste lié.
    with pytest.raises(TableDunAutrePoste):
        Table.ouvrir(chemin, "juste")


# --- Appli ---------------------------------------------------------------------------------


def test_appli_lie_la_table_et_refuse_un_autre_poste(tmp_path):
    chemin = tmp_path / "p.celodata"
    faux = FauxPoste()
    a = Api(chemin, regles_seules, LEGER, poste=faux)
    r = a.ouvrir("assez long")
    assert r["ok"] and r["liee"] is True and r["hello"] is False
    assert poste.fichier(chemin).exists()

    faux.autre = True
    assert Api(chemin, regles_seules, LEGER, poste=faux).ouvrir("assez long")["erreur"] == AUTRE_POSTE
    # Fichier du secret absent, table liée : même refus, et aucun nouveau secret n'est créé.
    poste.fichier(chemin).unlink()
    faux.autre = False
    assert Api(chemin, regles_seules, LEGER, poste=faux).ouvrir("assez long")["erreur"] == AUTRE_POSTE
    assert not poste.fichier(chemin).exists()


def test_windows_hello(tmp_path):
    chemin = tmp_path / "p.celodata"
    demandes = []

    def hello(reponse):
        def verifier(message):
            demandes.append(message)
            return reponse

        return verifier

    refus = Api(chemin, regles_seules, LEGER, poste=FauxPoste(), hello=hello(False)).ouvrir("assez long")
    assert refus["ok"] is False and "Windows Hello" in refus["erreur"]
    ok = Api(chemin, regles_seules, LEGER, poste=FauxPoste(), hello=hello(True)).ouvrir("assez long")
    assert ok["ok"] and ok["hello"] is True
    # Le mot de passe est vérifié avant Hello : un mauvais mot de passe ne déclenche pas la demande.
    demandes.clear()
    assert Api(chemin, regles_seules, LEGER, poste=FauxPoste(), hello=hello(True)).ouvrir("mauvais mot")["ok"] is False
    assert demandes == []
    sans = Api(chemin, regles_seules, LEGER, poste=FauxPoste(), hello=hello(None)).ouvrir("assez long")
    assert sans["ok"] and sans["hello"] is False


def test_deplacer_la_table(tmp_path):
    chemin, copie = tmp_path / "p.celodata", tmp_path / "copie.celodata"
    choix = {"chemin": str(copie)}
    a = Api(chemin, regles_seules, LEGER, poste=FauxPoste(), dialogue=lambda *_: choix["chemin"])
    assert a.ouvrir("assez long")["ok"]
    a.filtrer("Appeler le 04 72 99 88 77.", [{"debut": 11, "fin": 25, "type": "TELEPHONE"}], [])

    assert a.deplacer_table("mauvais mot")["erreur"] == "Mot de passe incorrect."
    choix["chemin"] = str(chemin)
    assert a.deplacer_table("assez long")["ok"] is False
    choix["chemin"] = None
    assert a.deplacer_table("assez long") == {"ok": False, "annule": True}
    choix["chemin"] = str(copie)
    assert a.deplacer_table("assez long") == {"ok": True, "chemin": str(copie)}

    # Sur le nouveau poste, la copie s'ouvre avec le mot de passe et se lie à son tour.
    b = Api(copie, regles_seules, LEGER, poste=FauxPoste())
    assert b.ouvrir("assez long")["liee"] is True
    assert b.restaurer("Rappeler TELEPHONE_1.")["texte"] == "Rappeler 04 72 99 88 77."


# --- DPAPI, sur Windows seulement ------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI n'existe que sous Windows")
def test_secret_de_poste_windows(tmp_path):
    chemin = tmp_path / "p.celodata"
    assert poste.lire(chemin) is None
    secret = poste.creer(chemin)
    assert len(secret) == 32
    assert secret not in poste.fichier(chemin).read_bytes()
    assert poste.lire(chemin) == secret
    poste.fichier(chemin).write_bytes(b"pas un secret de ce poste")
    with pytest.raises(poste.PosteInconnu):
        poste.lire(chemin)
