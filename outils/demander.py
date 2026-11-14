"""Envoie le contenu d'un fichier texte à la passerelle et affiche la réponse restaurée.

    uv run --extra passerelle python outils/demander.py essais/mail_paie.txt
    uv run --extra passerelle python outils/demander.py essais/mail_paie.txt --flux

La clé d'accès est demandée au clavier (elle ne s'affiche pas), ou lue dans la variable CELODATA_CLE.
"""

import argparse
import getpass
import json
import os
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Pose une question à la passerelle Celodata.")
    parser.add_argument("fichier", type=Path, help="fichier texte à envoyer")
    parser.add_argument("--adresse", default="http://127.0.0.1:8787/v1", help="adresse de la passerelle")
    parser.add_argument("--flux", action="store_true", help="demande une réponse mot à mot")
    args = parser.parse_args()

    cle = os.environ.get("CELODATA_CLE") or getpass.getpass("Clé d'accès Celodata : ")
    corps = {
        "model": "fausse-ia",
        "stream": args.flux,
        "messages": [{"role": "user", "content": args.fichier.read_text(encoding="utf-8")}],
    }
    entetes = {"Authorization": f"Bearer {cle.strip()}"}
    print("=" * 70 + "\nCE QUE VOUS RECEVEZ :\n" + "=" * 70)
    if not args.flux:
        reponse = httpx.post(args.adresse + "/chat/completions", json=corps, headers=entetes, timeout=300)
        if reponse.status_code != 200:
            print(f"Erreur {reponse.status_code} : {reponse.text}")
            return 1
        print(reponse.json()["choices"][0]["message"]["content"])
        return 0
    with httpx.stream("POST", args.adresse + "/chat/completions", json=corps, headers=entetes, timeout=300) as reponse:
        if reponse.status_code != 200:
            print(f"Erreur {reponse.status_code} : {reponse.read().decode()}")
            return 1
        for ligne in reponse.iter_lines():
            if ligne.startswith("data: {"):
                for choix in json.loads(ligne[6:])["choices"]:
                    print(choix["delta"].get("content") or "", end="", flush=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
