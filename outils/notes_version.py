"""Extrait de CHANGELOG.md les notes d'une version, pour la publication sur GitHub.

Depuis le dossier du projet :

    uv run outils/notes_version.py 2.2.0                   affiche les notes
    uv run outils/notes_version.py v2.2.0 --sortie notes.md  les écrit dans un fichier
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
CHANGELOG = RACINE / "CHANGELOG.md"


def notes_de_version(version: str, changelog: str) -> str:
    """Le texte sous « ## [version] », jusqu'au titre de version suivant."""
    motif = re.compile(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    correspondance = motif.search(changelog)
    if correspondance is None:
        raise SystemExit(f"La version {version} est absente de CHANGELOG.md.")
    return correspondance.group(1).strip() + "\n"


def main() -> int:
    parametres = argparse.ArgumentParser(
        description="Notes de version depuis CHANGELOG.md."
    )
    parametres.add_argument("version", help="par exemple 2.2.0 ou v2.2.0")
    parametres.add_argument(
        "--sortie", type=Path, help="fichier à écrire (sinon : écran)"
    )
    choix = parametres.parse_args()

    version = choix.version.removeprefix("v")
    notes = notes_de_version(version, CHANGELOG.read_text(encoding="utf-8"))
    notes += (
        "\n---\n\nLe détail de toutes les versions est dans le "
        "[journal des modifications](https://github.com/LASCAMPIA67/psn-amis/blob/main/CHANGELOG.md).\n"
    )
    if choix.sortie:
        choix.sortie.write_text(notes, encoding="utf-8")
    else:
        sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
