"""Fenêtre Windows de Celodata.

L'écran est une page HTML chargée directement dans la fenêtre : aucun serveur, aucun port ouvert.
"""

import argparse
import os
from pathlib import Path

DOSSIER_ECRAN = Path(__file__).parent
ECRAN = DOSSIER_ECRAN / "ecran.html"


def charger_ecran() -> str:
    """Assemble ecran.html avec ses feuilles de style et son script, pour pywebview sans serveur local."""
    html = ECRAN.read_text(encoding="utf-8")
    css = (DOSSIER_ECRAN / "ecran.css").read_text(encoding="utf-8")
    js = (DOSSIER_ECRAN / "ecran.js").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="ecran.css">', f"<style>\n{css}</style>", 1)
    html = html.replace('<script src="ecran.js"></script>', f"<script>\n{js}</script>", 1)
    return html


def chemin_table_par_defaut() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Celodata" / "projet.celodata"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Celodata : filtrer un texte avant de l'envoyer à une IA.")
    parser.add_argument("--table", type=Path, default=chemin_table_par_defaut(), help="fichier de la table chiffrée")
    args = parser.parse_args(argv)

    # Aucune connexion sortante : le modèle doit déjà être sur la machine.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    import webview

    from celodata import poste
    from celodata.appli import hello
    from celodata.appli.api import Api
    from celodata.documents import EXTENSIONS

    def dialogue(genre: str, nom: str = "") -> str | None:
        fenetre = webview.windows[0]
        if genre == "dossier":
            choix = fenetre.create_file_dialog(webview.FileDialog.FOLDER)
        elif genre == "enregistrer":
            choix = fenetre.create_file_dialog(webview.FileDialog.SAVE, save_filename=nom)
            # Selon la version, la boîte rend un chemin ou une liste de chemins.
            return choix if isinstance(choix, str) else (choix[0] if choix else None)
        else:
            motifs = ";".join(f"*{e}" for e in sorted(EXTENSIONS))
            choix = fenetre.create_file_dialog(webview.FileDialog.OPEN, file_types=(f"Documents ({motifs})",))
        return choix[0] if choix else None

    webview.create_window(
        "Celodata",
        html=charger_ecran(),
        js_api=Api(
            args.table,
            dialogue=dialogue,
            poste=poste if poste.disponible() else None,
            hello=hello.verifier,
        ),
        width=1180,
        height=860,
        min_size=(820, 600),
        text_select=True,
    )
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
