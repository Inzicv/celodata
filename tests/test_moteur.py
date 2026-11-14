from pathlib import Path

import pytest

from celodata.detection.base import Detection
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.regles import DetecteurRegles
from celodata.mesure import charger_jeu
from celodata.moteur import MARQUE_SECRET, pseudonymiser, restaurer
from celodata.table import MotDePasseIncorrect, Table

# Dérivation de clé allégée pour que les tests restent rapides.
LEGER = {"memoire_kio": 64, "iterations": 1}


@pytest.fixture
def table():
    with Table.ouvrir(":memory:", "mot de passe de test", **LEGER) as t:
        yield t


def detections(texte: str, *valeurs: tuple[str, str]) -> list[Detection]:
    return [Detection(texte.index(v), texte.index(v) + len(v), t, 1.0, "test") for t, v in valeurs]


def test_meme_valeur_meme_jeton(table):
    assert table.jeton("PERSONNE", "Rose Petit") == "PERSONNE_1"
    assert table.jeton("PERSONNE", "Yann Kerbrat") == "PERSONNE_2"
    assert table.jeton("PERSONNE", "Rose Petit") == "PERSONNE_1"
    # Une valeur connue garde son jeton, même vue sous un autre type.
    assert table.jeton("ORGANISATION", "Rose Petit") == "PERSONNE_1"
    assert table.valeur("PERSONNE", 2) == "Yann Kerbrat"
    assert table.valeur("PERSONNE", 9) is None


def test_fichier_sans_valeur_en_clair_et_mot_de_passe_verifie(tmp_path):
    chemin = tmp_path / "projet.celodata"
    with Table.ouvrir(chemin, "juste", **LEGER) as t:
        t.jeton("PERSONNE", "Fatoumata Diallo")
        t.jeton("IBAN", "FR76 3000 6000 0112 3456 7890 189")
    contenu = chemin.read_bytes()
    assert b"Fatoumata" not in contenu and b"Diallo" not in contenu and b"3456 7890" not in contenu
    with pytest.raises(MotDePasseIncorrect):
        Table.ouvrir(chemin, "faux", **LEGER)
    with Table.ouvrir(chemin, "juste", **LEGER) as t:
        assert t.valeur("PERSONNE", 1) == "Fatoumata Diallo"
        assert t.jeton("PERSONNE", "Fatoumata Diallo") == "PERSONNE_1"


def test_purge(table):
    table.jeton("PERSONNE", "Rose Petit")
    assert table.purger(jours=30) == 0
    assert table.purger(jours=-1) == 1
    assert len(table) == 0


def test_aller_retour_simple(table):
    texte = "Rose Petit habite Brest. Appeler Rose Petit au 06 01 02 03 04."
    d = detections(texte, ("PERSONNE", "Rose Petit"), ("VILLE", "Brest"), ("TELEPHONE", "06 01 02 03 04"))
    d.append(Detection(33, 43, "PERSONNE", 1.0, "test"))
    filtre = pseudonymiser(texte, d, table)
    assert filtre.texte == "PERSONNE_1 habite VILLE_1. Appeler PERSONNE_1 au TELEPHONE_1."
    assert filtre.par_type == {"PERSONNE": 2, "VILLE": 1, "TELEPHONE": 1}
    retour = restaurer(filtre.texte, table)
    assert retour.texte == texte
    assert retour.inconnus == [] and retour.approximatifs == []


@pytest.mark.parametrize(
    "forme",
    ["PERSONNE_1", "[PERSONNE_1]", "Personne 1", "PERSONNE-1", "personne_1", "PERSONNE 1", "Personne_01"],
)
def test_jetons_deformes(table, forme):
    table.jeton("PERSONNE", "Inès Belkacem")
    retour = restaurer(f"Bonjour {forme}, **{forme}**. L'avis de {forme}s compte.", table)
    assert retour.texte == "Bonjour Inès Belkacem, **Inès Belkacem**. L'avis de Inès Belkacems compte."


def test_type_en_deux_mots_et_numeros_voisins(table):
    table.jeton("DATE_NAISSANCE", "14 juillet 1985")
    for i in range(12):
        table.jeton("PERSONNE", f"Personne numéro {i}")
    retour = restaurer("Née le Date naissance 1. Vu PERSONNE_1 et PERSONNE_12.", table)
    assert retour.texte == "Née le 14 juillet 1985. Vu Personne numéro 0 et Personne numéro 11."
    assert retour.approximatifs == ["Date naissance 1"]


def test_jeton_inconnu_signale(table):
    table.jeton("PERSONNE", "Rose Petit")
    retour = restaurer("PERSONNE_1 a écrit à PERSONNE_7.", table)
    assert retour.texte == "Rose Petit a écrit à PERSONNE_7."
    assert retour.inconnus == ["PERSONNE_7"]


def test_secret_supprime_pour_de_bon(table):
    texte = "connexion user=clefevre password=Tulipe2024! refusée"
    filtre = pseudonymiser(texte, detections(texte, ("SECRET", "Tulipe2024!")), table)
    assert filtre.texte == f"connexion user=clefevre password={MARQUE_SECRET} refusée"
    assert len(table) == 0
    assert restaurer(filtre.texte, table).texte == filtre.texte


def test_chevauchement_refuse(table):
    with pytest.raises(ValueError):
        pseudonymiser("abcdef", [Detection(0, 4, "A", 1, "t"), Detection(2, 6, "A", 1, "t")], table)


def test_aller_retour_sur_le_jeu_de_test(table):
    """Chaque faux document, filtré puis restauré, redonne l'original (secrets mis à part)."""
    detecteur = DetecteurCompose("regles", [DetecteurRegles()])
    for nom, texte, _ in charger_jeu(Path(__file__).parent.parent / "jeu_de_test"):
        d = detecteur.detecter(texte)
        filtre = pseudonymiser(texte, d, table)
        for x in d:
            if x.type != "SECRET" and len(texte[x.debut : x.fin]) > 5:
                assert texte[x.debut : x.fin] not in filtre.texte, nom
        attendu = pseudonymiser(texte, [x for x in d if x.type == "SECRET"], table).texte
        retour = restaurer(filtre.texte, table)
        assert retour.texte == attendu, nom
        assert retour.inconnus == [], nom
