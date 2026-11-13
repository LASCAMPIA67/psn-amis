"""Exporte les ajouts et les retraits d'amis de journal.txt dans un fichier CSV.

Le fichier s'ouvre directement dans Excel ou LibreOffice Calc (séparateur « ; »,
accents conservés). Il contient des pseudos de joueurs : il n'est jamais publié
(export-*.csv est exclu du dépôt).

Depuis le dossier du projet :

    uv run outils/exporter_journal.py                       tout le journal
    uv run outils/exporter_journal.py --depuis 2026-11-01   à partir d'une date
    uv run outils/exporter_journal.py --sortie mon.csv      autre nom de fichier
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

import moteur  # noqa: E402


def lignes_du_journal(depuis: datetime) -> list[tuple[datetime, str, str]]:
    """(moment, événement, pseudo) pour chaque ajout et chaque retrait, dans l'ordre."""
    ajouts = moteur._dans_journal(moteur.MOTIF_AJOUT, depuis)
    retraits = moteur._dans_journal(moteur.MOTIF_RETRAIT, depuis)
    lignes = [(a.moment, "ajout", a.pseudo) for a in ajouts]
    lignes += [(r.moment, "retrait", r.pseudo) for r in retraits]
    return sorted(lignes, key=lambda ligne: ligne[0])


def exporter(chemin: Path, depuis: datetime) -> int:
    """Écrit le fichier CSV ; renvoie le nombre de lignes exportées."""
    lignes = lignes_du_journal(depuis)
    # « utf-8-sig » : Excel reconnaît alors les accents.
    with chemin.open("w", encoding="utf-8-sig", newline="") as fichier:
        ecriture = csv.writer(fichier, delimiter=";")
        ecriture.writerow(["date", "heure", "événement", "pseudo"])
        for moment, evenement, pseudo in lignes:
            ecriture.writerow(
                [
                    moment.strftime("%d/%m/%Y"),
                    moment.strftime("%H:%M:%S"),
                    evenement,
                    pseudo,
                ]
            )
    return len(lignes)


def main() -> int:
    parametres = argparse.ArgumentParser(
        description="Exporte les ajouts et retraits d'amis du journal en CSV."
    )
    parametres.add_argument(
        "--depuis",
        type=date.fromisoformat,
        default=date.min,
        help="première date exportée, au format AAAA-MM-JJ",
    )
    parametres.add_argument(
        "--sortie",
        type=Path,
        default=RACINE / f"export-journal-{date.today():%Y-%m-%d}.csv",
        help="fichier CSV à écrire",
    )
    options = parametres.parse_args()
    depuis = datetime.combine(options.depuis, datetime.min.time())
    nombre = exporter(options.sortie, depuis)
    print(f"{nombre} ligne(s) exportée(s) dans {options.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
