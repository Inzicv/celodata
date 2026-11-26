"""Étape 5 : la passerelle, essayée contre une fausse IA locale. Aucune connexion sortante."""

import json

import pytest

pytest.importorskip("starlette")
httpx = pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

from celodata.detection.fusion import DetecteurCompose  # noqa: E402
from celodata.detection.regles import DetecteurRegles  # noqa: E402
from celodata.passerelle.relais import FluxRestaure, Session  # noqa: E402
from celodata.passerelle.serveur import Passerelle, Reglages, ajouter_utilisateur  # noqa: E402
from celodata.table import Table  # noqa: E402

OPTIONS = {"memoire_kio": 64, "iterations": 1}
TELEPHONE = "04 72 99 88 77"
MAIL = "s.lemoine@fonderies-exemple.fr"


def regles_seules():
    return DetecteurCompose("regles", [DetecteurRegles()]), False


class FausseIA:
    """Joue le rôle de l'IA : garde ce qu'elle reçoit et répond ce qu'on lui a préparé."""

    def __init__(self) -> None:
        self.recues: list[httpx.Request] = []
        self.reponse: dict | list[str] = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}]}

    def __call__(self, demande: httpx.Request) -> httpx.Response:
        self.recues.append(demande)
        if demande.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "faux-modele"}]})
        if isinstance(self.reponse, list):
            flux = "".join(f"data: {m}\n\n" for m in self.reponse)
            return httpx.Response(200, content=flux.encode(), headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=self.reponse)

    @property
    def derniere(self) -> dict:
        return json.loads(self.recues[-1].content)


@pytest.fixture
def banc(tmp_path):
    ia = FausseIA()
    reglages = Reglages("http://ia.invalid/v1", "cle-de-l-ia-pour-le-test", tmp_path)
    cles = {nom: ajouter_utilisateur(reglages, nom) for nom in ("alice", "bruno")}
    passerelle = Passerelle(reglages, regles_seules, httpx.MockTransport(ia), OPTIONS)
    with TestClient(passerelle.appli) as client:
        yield client, ia, cles, tmp_path


def demander(client, cle, corps):
    return client.post("/v1/chat/completions", json=corps, headers={"Authorization": f"Bearer {cle}"})


def morceau(contenu=None, fin=None, **delta):
    if contenu is not None:
        delta["content"] = contenu
    return json.dumps({"id": "x", "choices": [{"index": 0, "delta": delta, "finish_reason": fin}]})


def test_sans_cle_rien_ne_part(banc):
    client, ia, _, _ = banc
    corps = {"messages": [{"role": "user", "content": "bonjour"}]}
    assert client.post("/v1/chat/completions", json=corps).status_code == 401
    assert demander(client, "celo-inconnue", corps).status_code == 401
    assert client.get("/v1/models").status_code == 401
    assert ia.recues == []


def test_seules_trois_adresses_existent(banc):
    client, ia, cles, _ = banc
    entetes = {"Authorization": f"Bearer {cles['alice']}"}
    assert client.get("/sante").json()["etat"] == "ok"
    assert client.get("/v1/models", headers=entetes).json() == {"data": [{"id": "faux-modele"}]}
    # Ces adresses de l'IA ne sont pas relayées : leur contenu ne serait pas filtré.
    for adresse in ("/v1/embeddings", "/v1/responses", "/v1/completions"):
        assert client.post(adresse, json={"input": TELEPHONE}, headers=entetes).status_code == 404
    assert len(ia.recues) == 1


def test_demande_filtree_et_reponse_restauree(banc):
    client, ia, cles, dossier = banc
    ia.reponse = {"choices": [{"index": 0, "message": {
        "role": "assistant",
        "content": "Rappelez Telephone 1, puis écrivez à MAIL_1 et MAIL_9.",
        "tool_calls": [{"id": "a", "type": "function", "function": {"name": "appeler", "arguments": '{"numero": "TELEPHONE_1"}'}}],
    }}]}
    corps = {
        "model": "faux-modele",
        "user": "alice.martin",
        "metadata": {"poste": "PC-0412"},
        "messages": [
            {"role": "system", "content": "Tu es un assistant."},
            {"role": "user", "name": "Alice Martin", "content": [{"type": "text", "text": f"Appeler le {TELEPHONE} ou {MAIL}."}]},
        ],
    }
    reponse = demander(client, cles["alice"], corps)
    assert reponse.status_code == 200

    transmise = ia.recues[-1].content.decode()
    for valeur in (TELEPHONE, MAIL, "alice.martin", "Alice Martin", "PC-0412", cles["alice"]):
        assert valeur not in transmise
    assert ia.derniere["messages"][1]["content"][0]["text"] == "Appeler le TELEPHONE_1 ou MAIL_1."
    assert ia.derniere["model"] == "faux-modele"
    # L'IA reçoit la clé de l'entreprise, jamais celle de l'utilisateur.
    assert ia.recues[-1].headers["authorization"] == "Bearer cle-de-l-ia-pour-le-test"

    message = reponse.json()["choices"][0]["message"]
    assert message["content"] == f"Rappelez {TELEPHONE}, puis écrivez à {MAIL} et MAIL_9."
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"numero": TELEPHONE}

    with Table.ouvrir(dossier / "alice.celodata", cles["alice"]) as table:
        restauration, filtrage = table.journal()
        assert filtrage["mode"] == "passerelle" and filtrage["par_type"] == {"TELEPHONE": 1, "MAIL": 1}
        assert (restauration["inconnus"], restauration["approximatifs"]) == (1, 1)
    for fichier in dossier.iterdir():
        brut = fichier.read_bytes()
        assert TELEPHONE.encode() not in brut and cles["alice"].encode() not in brut


def test_l_historique_est_refiltre_avec_les_memes_jetons(banc):
    client, ia, cles, _ = banc
    demander(client, cles["alice"], {"messages": [{"role": "user", "content": f"Mon numéro : {TELEPHONE}."}]})
    # L'outil de discussion renvoie l'historique restauré, vraies valeurs comprises.
    demander(client, cles["alice"], {"messages": [
        {"role": "user", "content": f"Mon numéro : {TELEPHONE}."},
        {"role": "assistant", "content": f"Noté : {TELEPHONE}."},
        {"role": "user", "content": "Et le mail ?"},
    ]})
    assert [m["content"] for m in ia.derniere["messages"]] == [
        "Mon numéro : TELEPHONE_1.", "Noté : TELEPHONE_1.", "Et le mail ?",
    ]


def test_une_table_par_utilisateur(banc):
    client, ia, cles, dossier = banc
    demander(client, cles["alice"], {"messages": [{"role": "user", "content": f"Appeler le {TELEPHONE}."}]})
    ia.reponse = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "Voir TELEPHONE_1."}}]}
    # Bruno ne peut pas faire restaurer une valeur d'Alice.
    autre = demander(client, cles["bruno"], {"messages": [{"role": "user", "content": "Bonjour."}]})
    assert autre.json()["choices"][0]["message"]["content"] == "Voir TELEPHONE_1."
    assert {f.name for f in dossier.iterdir()} == {"utilisateurs.json", "alice.celodata", "bruno.celodata"}


def test_images_et_demandes_mal_formees_refusees(banc):
    client, ia, cles, _ = banc
    image = {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}
    assert demander(client, cles["alice"], {"messages": [image]}).status_code == 400
    assert demander(client, cles["alice"], {"messages": "bonjour"}).status_code == 400
    assert ia.recues == []


def test_reponse_en_flux_avec_jeton_coupe(banc):
    client, ia, cles, _ = banc
    ia.reponse = [
        morceau("Rappelez "), morceau("TELE"), morceau("PHONE_"), morceau("1"), morceau(" demain, ou MAIL"),
        morceau(tool_calls=[{"index": 0, "function": {"name": "appeler", "arguments": '{"numero": "TELE'}}]),
        morceau(tool_calls=[{"index": 0, "function": {"arguments": 'PHONE_1"}'}}]),
        morceau("_1", fin="stop"),
        "[DONE]",
    ]
    corps = {"stream": True, "messages": [{"role": "user", "content": f"Appeler le {TELEPHONE} ou {MAIL}."}]}
    reponse = demander(client, cles["alice"], corps)
    assert reponse.headers["content-type"].startswith("text/event-stream")
    lignes = [ligne[6:] for ligne in reponse.text.split("\n") if ligne.startswith("data: ")]
    assert lignes[-1] == "[DONE]"
    deltas = [json.loads(ligne)["choices"][0]["delta"] for ligne in lignes[:-1]]
    textes = [d.get("content", "") for d in deltas]
    assert "".join(textes) == f"Rappelez {TELEPHONE} demain, ou {MAIL}"
    # Aucun morceau de jeton n'est montré à l'utilisateur.
    assert not any("TELE" in t or "PHONE" in t or "MAIL" in t for t in textes)
    arguments = "".join(a["function"].get("arguments", "") for d in deltas for a in d.get("tool_calls", []))
    assert json.loads(arguments) == {"numero": TELEPHONE}


def test_flux_qui_s_arrete_sans_prevenir():
    with Table.ouvrir(":memory:", "mot de passe de test", **OPTIONS) as table:
        table.jeton("DATE_NAISSANCE", "12/03/1984")
        flux = FluxRestaure(Session(table))
        rendus = [flux.morceau(json.loads(morceau(t)))["choices"][0]["delta"]["content"] for t in ("Né le date", " naissance", " 1")]
        assert rendus == ["Né le ", "", ""]
        assert flux.reste()["choices"][0]["delta"]["content"] == "12/03/1984"
        assert flux.reste() is None
        assert flux.bilan.approximatifs == ["date naissance 1"]


def test_session_expire_et_cache_utilisateurs_se_rafraichit(tmp_path):
    ia = FausseIA()
    reglages = Reglages("http://ia.invalid/v1", "cle-ia", tmp_path, ttl_session=60.0)
    cle_alice = ajouter_utilisateur(reglages, "alice")
    passerelle = Passerelle(reglages, regles_seules, httpx.MockTransport(ia), OPTIONS)
    with TestClient(passerelle.appli) as client:
        assert demander(client, cle_alice, {"messages": [{"role": "user", "content": "bonjour"}]}).status_code == 200
        assert "alice" in passerelle._sessions

        # Un utilisateur ajouté à chaud est reconnu sans redémarrer la passerelle.
        cle_chloe = ajouter_utilisateur(reglages, "chloe")
        # Simule l'inactivité d'Alice au-delà du TTL.
        passerelle._sessions["alice"].derniere_activite -= 120.0
        assert demander(client, cle_chloe, {"messages": [{"role": "user", "content": "salut"}]}).status_code == 200
        assert "alice" not in passerelle._sessions and "chloe" in passerelle._sessions
