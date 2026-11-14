"""Fenêtre Windows de Celodata.

L'écran est une page HTML chargée directement dans la fenêtre : aucun serveur, aucun port ouvert.
"""

import argparse
import os
from pathlib import Path

ECRAN = Path(__file__).parent / "ecran.html"


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

    from celodata.appli.api import Api

    webview.create_window(
        "Celodata",
        html=ECRAN.read_text(encoding="utf-8"),
        js_api=Api(args.table),
        width=1180,
        height=860,
        min_size=(820, 600),
        text_select=True,
    )
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
