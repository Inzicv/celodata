import pytest

from celodata.appli.api import Api
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.regles import DetecteurRegles

TEXTE = (
    "Note pour la DRH. M. Girard (matricule 20418) est en arrêt pour dépression.\n"
    "Le dossier Zéphyr reste confidentiel. Appeler le 04 72 99 88 77. Zéphyr avance."
)


def regles_seules():
    return DetecteurCompose("regles", [DetecteurRegles()]), False


@pytest.fixture
def api():
    a = Api(":memory:", regles_seules, {"memoire_kio": 64, "iterations": 1})
    assert a.ouvrir("mot de passe de test")["ok"]
    return a


def valeurs(resultat, cle="detections"):
    return [TEXTE[d["debut"] : d["fin"]] for d in resultat[cle]]


def test_mot_de_passe(tmp_path):
    a = Api(tmp_path / "sous-dossier" / "p.celodata", regles_seules, {"memoire_kio": 64, "iterations": 1})
    assert a.etat()["table_existe"] is False
    assert a.ouvrir("court")["ok"] is False
    assert a.ouvrir("assez long")["ok"] is True
    b = Api(tmp_path / "sous-dossier" / "p.celodata", regles_seules)
    assert b.etat()["table_existe"] is True
    assert b.ouvrir("mauvais mot")["erreur"] == "Mot de passe incorrect."


def test_boucle_complete(api):
    analyse = api.analyser(TEXTE)
    assert analyse["modele"] is False
    assert valeurs(analyse) == ["20418", "dépression", "04 72 99 88 77"]
    assert valeurs(analyse, "suggestions") == ["DRH"]

    filtre = api.filtrer(TEXTE, analyse["detections"], [])
    assert filtre["ok"] and "20418" not in filtre["texte"] and "IDENTIFIANT_1" in filtre["texte"]
    assert filtre["par_type"] == {"IDENTIFIANT": 1, "SANTE": 1, "TELEPHONE": 1}

    retour = api.restaurer("Rappeler Telephone 1 pour IDENTIFIANT_1 et IDENTIFIANT_8.")
    assert retour["texte"] == "Rappeler 04 72 99 88 77 pour 20418 et IDENTIFIANT_8."
    assert retour["inconnus"] == ["IDENTIFIANT_8"]
    assert retour["approximatifs"] == ["Telephone 1"]


def test_les_corrections_deviennent_la_memoire_du_projet(api):
    analyse = api.analyser(TEXTE)
    gardees = [d for d in analyse["detections"] if TEXTE[d["debut"] : d["fin"]] != "dépression"]
    debut = TEXTE.index("Zéphyr")
    ajout = {"debut": debut, "fin": debut + 6, "type": "PROJET"}
    api.filtrer(TEXTE, [*gardees, ajout], ["dépression"])

    suite = api.analyser(TEXTE)
    # La valeur démasquée n'est plus proposée, la valeur ajoutée est retrouvée partout.
    assert valeurs(suite) == ["20418", "Zéphyr", "04 72 99 88 77", "Zéphyr"]


def test_chevauchement_signale(api):
    r = api.filtrer("abcdef", [{"debut": 0, "fin": 4, "type": "A"}, {"debut": 2, "fin": 6, "type": "A"}], [])
    assert r["ok"] is False


def test_le_theme_choisi_est_retenu(tmp_path):
    a = Api(tmp_path / "p.celodata", regles_seules)
    assert a.etat()["theme"] == ""
    a.choisir_theme("dark")
    # Lu avant l'ouverture de la table : l'écran du mot de passe a déjà le bon thème.
    assert Api(tmp_path / "p.celodata", regles_seules).etat()["theme"] == "dark"
    a.choisir_theme("n'importe quoi")
    assert a.etat()["theme"] == ""


def test_avancement_et_annulation(api):
    from celodata import suivi

    assert api.avancement()["etape"] == ""
    vus = []

    class Lent:
        nom = "lent"

        def detecter(self, texte):
            for numero in suivi.parcourir("analyse", range(5)):
                vus.append(api.avancement())
                if numero == 2:
                    api.annuler()
            return []

    api._detecteur = Lent()
    assert api.analyser("Bonjour") == {"annule": True}
    # Arrêté au bloc qui suit la demande, pas à la fin.
    assert [(a["etape"], a["fait"], a["total"]) for a in vus] == [("analyse", 0, 5), ("analyse", 1, 5), ("analyse", 2, 5)]
    assert api.avancement()["etape"] == ""
    # L'annulation ne vaut que pour le travail en cours : l'analyse suivante va au bout.
    api._detecteur = DetecteurCompose("regles", [DetecteurRegles()])
    assert "detections" in api.analyser("Écrire à jean.dupont@exemple.fr")


CONTRAT = "La stagiaire Maëlle Kervadec (matricule 20418) effectue un stage de six mois. La DRH signe."


def test_un_prereglage_laisse_des_categories_en_clair(api):
    def hors(analyse):
        return {CONTRAT[d["debut"] : d["fin"]]: d["hors"] for d in analyse["detections"]}

    assert api.prereglages()["courant"] == "RH / paie"
    assert hors(api.analyser(CONTRAT)) == {"stagiaire": True, "20418": False, "six mois": True}
    assert api.choisir_prereglage("Tout masquer")["ok"]
    assert hors(api.analyser(CONTRAT)) == {"stagiaire": False, "20418": False, "six mois": False}

    assert api.choisir_prereglage("Contrat / juridique")["ok"]
    analyse = api.analyser(CONTRAT)
    assert hors(analyse) == {"stagiaire": True, "20418": False, "six mois": True}
    assert [CONTRAT[d["debut"] : d["fin"]] for d in analyse["suggestions"]] == ["DRH"]
    assert api.choisir_prereglage("Inconnu")["ok"] is False

    # Un préréglage créé ici, puis choisi : il est retenu dans la table.
    assert api.enregistrer_prereglage("Formation", ["DUREE", "CATEGORIE_INCONNUE"])["ok"]
    assert api.choisir_prereglage("Formation")["ok"]
    assert hors(api.analyser(CONTRAT)) == {"stagiaire": False, "20418": False, "six mois": True}
    formation = next(p for p in api.prereglages()["liste"] if p["nom"] == "Formation")
    assert formation == {"nom": "Formation", "laisses": ["DUREE"], "origine": False, "modifie": False}
    # Supprimé, on revient au préréglage par défaut.
    assert api.supprimer_prereglage("Formation")["ok"]
    assert api.prereglages()["courant"] == "RH / paie"

    # Un préréglage d'origine se modifie, et se remet comme au départ.
    assert api.enregistrer_prereglage("RH / paie", ["DUREE"])["ok"]
    rh = next(p for p in api.prereglages()["liste"] if p["nom"] == "RH / paie")
    assert rh["laisses"] == ["DUREE"] and rh["modifie"]
    api.supprimer_prereglage("RH / paie")
    rh = next(p for p in api.prereglages()["liste"] if p["nom"] == "RH / paie")
    assert not rh["modifie"] and "ROLE" in rh["laisses"]


def test_un_terme_impose_reste_masque_malgre_le_prereglage(api):
    api.choisir_prereglage("Contrat / juridique")
    api.ajouter_regle("terme", "six mois", "DUREE")
    analyse = api.analyser(CONTRAT)
    assert {CONTRAT[d["debut"] : d["fin"]]: d["hors"] for d in analyse["detections"]}["six mois"] is False


def test_un_dossier_suit_le_prereglage(api, tmp_path):
    (tmp_path / "contrat.txt").write_text(CONTRAT, encoding="utf-8")
    api.choisir_prereglage("Contrat / juridique")
    api._dialogue = lambda *_: str(tmp_path)
    resultat = api.filtrer_dossier()
    produit = (tmp_path / "celodata_filtré" / "contrat.txt").read_text(encoding="utf-8")
    assert resultat["fichiers"][0]["masques"] == 1
    assert "six mois" in produit and "stagiaire" in produit and "20418" not in produit


def test_changer_mot_de_passe(tmp_path):
    chemin = tmp_path / "p.celodata"
    a = Api(chemin, regles_seules, {"memoire_kio": 64, "iterations": 1})
    assert a.ouvrir("ancien mot de passe")["ok"]
    a.filtrer("Appeler le 04 72 99 88 77.", [{"debut": 11, "fin": 25, "type": "TELEPHONE"}], [])

    assert a.changer_mot_de_passe("ancien mot de passe", "court")["ok"] is False
    assert a.changer_mot_de_passe("mauvais", "nouveau mot de passe")["ok"] is False
    assert a.changer_mot_de_passe("ancien mot de passe", "nouveau mot de passe")["ok"] is True

    assert Api(chemin, regles_seules).ouvrir("ancien mot de passe")["ok"] is False
    b = Api(chemin, regles_seules)
    assert b.ouvrir("nouveau mot de passe")["ok"] is True
    assert b.restaurer("Rappeler TELEPHONE_1.")["texte"] == "Rappeler 04 72 99 88 77."


def test_purger_table_et_exporter_journal(tmp_path):
    csv_path = tmp_path / "journal.csv"
    a = Api(":memory:", regles_seules, {"memoire_kio": 64, "iterations": 1}, dialogue=lambda *_: str(csv_path))
    assert a.ouvrir("mot de passe de test")["ok"]
    a.filtrer("Appeler le 04 72 99 88 77.", [{"debut": 11, "fin": 25, "type": "TELEPHONE"}], [], fichier="note.txt")

    assert a.purger_table(30) == {"ok": True, "supprimees": 0, "restantes": 1}
    assert a.purger_table(0) == {"ok": True, "supprimees": 1, "restantes": 0}

    export = a.exporter_journal()
    assert export["ok"] and export["lignes"] == 1
    contenu = csv_path.read_text(encoding="utf-8-sig")
    assert "date;action;traitement" in contenu
    assert "note.txt" in contenu and "TELEPHONE:1" in contenu


def test_ecran_assemble_et_syntaxe_js():
    import shutil
    import subprocess

    from celodata.appli.fenetre import DOSSIER_ECRAN, charger_ecran

    html_brut = (DOSSIER_ECRAN / "ecran.html").read_text(encoding="utf-8")
    assert '\\"' not in html_brut
    assemble = charger_ecran()
    assert "<style>" in assemble and "<script>" in assemble
    assert 'href="ecran.css"' not in assemble and 'src="ecran.js"' not in assemble
    js = (DOSSIER_ECRAN / "ecran.js").read_text(encoding="utf-8")
    assert "toast(" not in js
    if shutil.which("node"):
        res = subprocess.run(["node", "--check", str(DOSSIER_ECRAN / "ecran.js")], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
