from pathlib import Path

import pytest

from celodata.detection import controles
from celodata.detection.base import Detection
from celodata.detection.fusion import propager, regler_chevauchements
from celodata.detection.regles import DetecteurRegles
from celodata.mesure import charger_jeu, evaluer


@pytest.fixture(scope="module")
def regles() -> DetecteurRegles:
    return DetecteurRegles()


def trouve(regles: DetecteurRegles, texte: str) -> set[tuple[str, str]]:
    return {(d.type, texte[d.debut : d.fin]) for d in regles.detecter(texte)}


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("Appelez le 06 12 34 56 78 demain", ("TELEPHONE", "06 12 34 56 78")),
        ("tél : 01.42.68.53.00.", ("TELEPHONE", "01.42.68.53.00")),
        ("mobile +33 6 22 33 44 55", ("TELEPHONE", "+33 6 22 33 44 55")),
        ("écrire à jean.dupont@exemple.fr.", ("MAIL", "jean.dupont@exemple.fr")),
        ("NIR 2 85 07 69 123 456 23", ("NIR", "2 85 07 69 123 456 23")),
        ("IBAN FR76 3000 6000 0112 3456 7890 189", ("IBAN", "FR76 3000 6000 0112 3456 7890 189")),
        ("BIC : AGRIFRPP", ("BIC", "AGRIFRPP")),
        ("SIRET 443 061 841 00013", ("SIRET", "443 061 841 00013")),
        ("TVA FR64443061841", ("TVA", "FR64443061841")),
        ("immatriculé AB-123-CD", ("PLAQUE", "AB-123-CD")),
        ("depuis 192.168.14.27.", ("IP", "192.168.14.27")),
        ("Client: 2001:db8:85a3::8a2e:370:7334", ("IP", "2001:db8:85a3::8a2e:370:7334")),
        ("MAC=00:1A:2B:3C:4D:5E", ("MAC", "00:1A:2B:3C:4D:5E")),
        (r"le partage \\nas-rh-01\paie", ("MACHINE", "nas-rh-01")),
        ("sur sql-prod-03.intra.exemple.fr hier", ("MACHINE", "sql-prod-03.intra.exemple.fr")),
        ("matricule 20418", ("IDENTIFIANT", "20418")),
        ("dossier CLI-2024-00871", ("IDENTIFIANT", "CLI-2024-00871")),
        ("password=Tulipe2024! ok", ("SECRET", "Tulipe2024!")),
        ("née le 14 juillet 1985", ("DATE_NAISSANCE", "14 juillet 1985")),
        ("la directrice du site de Lyon refuse", ("LIEU", "site de Lyon")),
        ("il est adhérent CFDT", ("SYNDICAT", "adhérent CFDT")),
        ("en mi-temps thérapeutique", ("SANTE", "mi-temps thérapeutique")),
        ("habite 14 rue des Lilas, 69003 Lyon.", ("ADRESSE", "14 rue des Lilas, 69003 Lyon")),
    ],
)
def test_regle_detecte(regles, texte, attendu):
    assert attendu in trouve(regles, texte)


@pytest.mark.parametrize(
    ("texte", "type_"),
    [
        ("NIR 2 85 07 69 123 456 24", "NIR"),  # clé fausse
        ("IBAN FR76 3000 6000 0112 3456 7890 188", "IBAN"),  # clé fausse
        ("numéro 443 061 841 00014", "SIRET"),  # clé fausse
        ("le vaccin COVID-19", "MACHINE"),
        ("client chez vous depuis 2015", "IDENTIFIANT"),
        ("réunion à 08:41:17", "IP"),
        ("ROUSSEAU a signé", "BIC"),
    ],
)
def test_regle_ne_detecte_pas(regles, texte, type_):
    assert type_ not in {t for t, _ in trouve(regles, texte)}


def test_cles_de_controle():
    assert controles.nir("1 68 03 63 113 045 66") is True
    assert controles.nir("1680363113045") is None
    assert controles.luhn("53208917400017")
    assert controles.tva("FR64443061841") is True
    assert controles.tva("FR65443061841") is False


def test_les_regles_passent_avant_le_modele():
    modele = Detection(0, 30, "IBAN", 0.99, "modele")
    regle = Detection(5, 30, "IBAN", 1.0, "regles")
    assert regler_chevauchements([modele, regle]) == [regle]


def test_la_plus_longue_l_emporte():
    courte = Detection(0, 5, "PERSONNE", 0.9, "modele")
    longue = Detection(0, 12, "PERSONNE", 0.5, "modele")
    assert regler_chevauchements([courte, longue]) == [longue]


def test_propagation():
    texte = "Rose Petit a appelé. Mme rose petit rappellera. Une rose rouge pour Rose."
    detections = [Detection(0, 10, "PERSONNE", 0.9, "modele"), Detection(68, 72, "PERSONNE", 0.9, "modele")]
    valeurs = [texte[d.debut : d.fin] for d in propager(texte, detections)]
    assert valeurs == ["Rose Petit", "rose petit", "Rose"]


def test_formats_fixes_du_jeu_a_100_pour_cent(regles):
    for nom, texte, attendus in charger_jeu(Path(__file__).parent.parent / "jeu_de_test"):
        bilan = evaluer(nom, texte, attendus, regles.detecter(texte))
        assert bilan.fixe_ok == bilan.fixe_total, bilan.rates


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("conformément au règlement général sur la protection des données du 27 avril 2016", ("DATE_LOI", "27 avril 2016")),
        ("la loi n° 78-17 du 6 janvier 1978 modifiée", ("DATE_LOI", "6 janvier 1978")),
        ("un stage de six mois", ("DUREE", "six mois")),
        ("dans un délai de 48 heures", ("DUREE", "48 heures")),
        ("âgée de 34 ans", ("AGE", "34 ans")),
        ("La stagiaire est suivie par un tuteur", ("ROLE", "stagiaire")),
        ("avec l'équipe pédagogique", ("ROLE", "équipe pédagogique")),
    ],
)
def test_categories_fines(regles, texte, attendu):
    assert attendu in trouve(regles, texte)


def test_une_date_de_contrat_reste_une_date(regles):
    texte = "Le contrat prend effet le 2 mars 2026. La salariée, âgée de 34 ans, signe."
    trouves = regler_chevauchements(regles.detecter(texte))
    types = {(d.type, texte[d.debut : d.fin]) for d in trouves}
    assert ("DATE", "2 mars 2026") in types
    assert ("AGE", "34 ans") in types and not any(t == "DUREE" for t, _ in types)


def test_la_date_d_une_loi_passe_avant_la_date(regles):
    texte = "en application de la loi du 10 juillet 2014 relative aux stages"
    assert [d.type for d in regler_chevauchements(regles.detecter(texte))] == ["DATE_LOI"]


def test_un_terme_generique_est_range_a_part():
    from celodata.detection.fusion import declasser

    texte = "L'organisme de formation Institut Valmont suit le compte svc_backup à grande échelle."

    def modele(valeur, type_):
        debut = texte.index(valeur)
        return Detection(debut, debut + len(valeur), type_, 0.8, "modele")

    recu = [
        modele("L'organisme de formation", "ORGANISATION"),
        modele("Institut Valmont", "ORGANISATION"),
        modele("svc_backup", "ROLE"),
        modele("grande échelle", "VILLE"),
    ]
    assert [d.type for d in declasser(texte, recu)] == ["COMMUN", "ORGANISATION", "LOGIN", "COMMUN"]
    # Dans un texte écrit sans majuscules, un nom en minuscules peut être un vrai nom : rien n'est déclassé.
    minuscules = "bonjour, je suis cliente chez dupont et fils depuis mars."
    debut = minuscules.index("dupont et fils")
    nom = [Detection(debut, debut + 14, "ORGANISATION", 0.8, "modele")]
    assert declasser(minuscules, nom) == nom
