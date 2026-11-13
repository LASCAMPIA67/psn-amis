"""Vérifie que la version est la même partout : src/psn_amis/__init__.py (la source),
pyproject.toml, CHANGELOG.md, et l'étiquette Git lors d'une publication.

Depuis le dossier du projet :

    uv run outils/verifier_version.py
    uv run outils/verifier_version.py --etiquette v2.2.0
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def version_pyproject() -> str:
    projet = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    return projet["project"]["version"]


def version_code() -> str:
    """La version déclarée dans src/psn_amis/__init__.py (seule source de vérité)."""
    texte = (RACINE / "src" / "psn_amis" / "__init__.py").read_text(encoding="utf-8")
    correspondance = re.search(r'^__version__ = "([^"]+)"', texte, re.MULTILINE)
    if correspondance is None:
        raise SystemExit('__init__.py : la ligne __version__ = "..." est introuvable.')
    version = correspondance.group(1)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"__init__.py : « {version} » n'est pas une version X.Y.Z.")
    return version


def derniere_version_changelog() -> tuple[str, str]:
    """La première version datée du journal : (version, date)."""
    texte = (RACINE / "CHANGELOG.md").read_text(encoding="utf-8")
    if "## [Non publié]" not in texte:
        raise SystemExit("CHANGELOG.md : la partie « ## [Non publié] » manque.")
    correspondance = re.search(
        r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$", texte, re.MULTILINE
    )
    if correspondance is None:
        raise SystemExit(
            "CHANGELOG.md : aucune version datée « ## [X.Y.Z] - AAAA-MM-JJ »."
        )
    return correspondance.group(1), correspondance.group(2)


def main() -> int:
    parametres = argparse.ArgumentParser(
        description="Vérifie la cohérence de la version."
    )
    parametres.add_argument(
        "--etiquette", help="étiquette Git attendue, par exemple v2.2.0"
    )
    choix = parametres.parse_args()

    versions = {
        "__init__.py": version_code(),
        "pyproject.toml": version_pyproject(),
        "CHANGELOG.md": derniere_version_changelog()[0],
    }
    if choix.etiquette:
        versions["étiquette Git"] = choix.etiquette.removeprefix("v")

    if len(set(versions.values())) != 1:
        print("Les versions ne sont pas d'accord :")
        for source, version in versions.items():
            print(f"  {source:<16} {version}")
        return 1
    print(
        f"Version {versions['__init__.py']} : "
        + ", ".join(versions)
        + " sont d'accord."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
