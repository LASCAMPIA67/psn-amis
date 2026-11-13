"""Dessine les captures d'écran du README avec des données de démonstration.

Les pseudos et les chiffres sont inventés : aucune donnée réelle n'apparaît. L'heure
est figée pour que les images soient identiques d'une fois sur l'autre.

Depuis le dossier du projet :

    uv run outils/captures.py                 écrit dans docs/images/
    uv run outils/captures.py --sortie X      écrit dans le dossier X
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from rich.console import Console

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

import moteur  # noqa: E402
import tableau_de_bord as tb  # noqa: E402

MAINTENANT = datetime(2026, 11, 11, 21, 4, 33)
COMPTE = "MonCompte-PSN"
PSEUDOS = [
    "NightOwl-77",
    "Kyra_Sniper",
    "xX_Pixel_Xx",
    "Tomahawk-77",
    "Lyna-Gamer",
    "ZedRush_",
    "Mika_Quickscope",
    "Bastien-Nuketown",
    "Shaddow_FR",
    "Yuna-Plays",
    "Kevin_du_67",
    "Noa-Hijacked",
]


# Il y a combien d'heures ont eu lieu les ajouts du jour d'avant le lancement.
HEURES_DES_ANCIENS_AJOUTS = (2, 2, 2, 3, 3, 3, 3, 4, 4, 5, 6, 6, 7, 9, 10, 10, 11, 12)
HEURES_DES_ANCIENS_AJOUTS += (12, 13, 13, 14, 16, 17, 18)


class HorlogeFigee(datetime):
    """datetime dont now() renvoie toujours la même heure : captures reproductibles."""

    @classmethod
    def now(cls, tz=None):
        return MAINTENANT


class CalendrierFige(date):
    @classmethod
    def today(cls):
        return MAINTENANT.date()


def figer_le_temps() -> None:
    moteur.datetime = HorlogeFigee
    moteur.date = CalendrierFige
    tb.datetime = HorlogeFigee


def evenement(
    suivi: moteur.Suivi, il_y_a: int, niveau: int, genre: str, texte: str
) -> None:
    suivi.evenement(MAINTENANT - timedelta(seconds=il_y_a), niveau, genre, texte)


def suivi_demo() -> moteur.Suivi:
    """Un tableau de bord en pleine soirée : 37 ajouts, quelques événements variés."""
    # Deux ajouts très récents, puis d'autres espacés de quelques minutes.
    anciens = [
        moteur.Ajout(MAINTENANT - timedelta(seconds=70 * rang), pseudo)
        for rang, pseudo in enumerate(PSEUDOS[1:3], start=1)
    ]
    anciens += [
        moteur.Ajout(MAINTENANT - timedelta(minutes=9 + 6 * rang), pseudo)
        for rang, pseudo in enumerate(PSEUDOS[3:])
    ]
    # Les ajouts du jour « avant le lancement » : relus dans journal.txt au démarrage.
    anciens += [
        moteur.Ajout(
            MAINTENANT - timedelta(hours=heures, minutes=7), f"Joueur-{rang:02d}"
        )
        for rang, heures in enumerate(HEURES_DES_ANCIENS_AJOUTS)
    ]
    # La veille au soir : visibles dans l'histogramme des 24 heures seulement.
    anciens += [
        moteur.Ajout(MAINTENANT - timedelta(hours=heures, minutes=30), f"Veille-{rang}")
        for rang, heures in enumerate((22, 22, 23, 23, 23))
    ]
    suivi = moteur.Suivi(anciens)
    suivi._debut = MAINTENANT - timedelta(hours=1, minutes=24)
    suivi.connecte(COMPTE, 410)
    evenement(suivi, 5100, logging.INFO, "info", "Démarrage de PSN Amis")
    evenement(suivi, 5099, logging.INFO, "info", "Connexion aux serveurs de Sony...")
    evenement(
        suivi,
        5087,
        logging.INFO,
        "info",
        f"Connecté au compte PSN {COMPTE} (410 amis). Vérification toutes les 15 secondes.",
    )
    for rang, pseudo in enumerate(reversed(PSEUDOS[3:7])):
        evenement(
            suivi,
            2400 - 300 * rang,
            logging.INFO,
            moteur.GENRE_AJOUT,
            f"Demande acceptée : {pseudo}",
        )
    evenement(
        suivi,
        1500,
        logging.WARNING,
        "info",
        "Pas d'accès à Internet, ou serveurs Sony injoignables. Nouvel essai dans 30 s.",
    )
    evenement(
        suivi,
        1200,
        logging.INFO,
        "info",
        "Lyna-Gamer (déjà votre ami) demande à partager vos vrais noms : le script n'y "
        "touche pas. Répondez vous-même sur la console si vous le souhaitez.",
    )
    evenement(suivi, 700, logging.INFO, moteur.GENRE_RETRAIT, "Ami retiré : ZedRush_")
    suivi.retrait("ZedRush_")
    for rang, pseudo in enumerate(reversed(PSEUDOS[1:3]), start=1):
        evenement(
            suivi,
            70 * (3 - rang),
            logging.INFO,
            moteur.GENRE_AJOUT,
            f"Demande acceptée : {pseudo}",
        )
    # Le tout dernier ajout, à l'instant : il est surligné en vert.
    suivi.demandes_trouvees(1)
    suivi.ajout(PSEUDOS[0])
    evenement(
        suivi, 0, logging.INFO, moteur.GENRE_AJOUT, f"Demande acceptée : {PSEUDOS[0]}"
    )
    suivi._ajouts_session = 12
    suivi.demandes_trouvees(0)
    suivi.verification_terminee()
    suivi.statut(
        moteur.Statut.EN_MARCHE, "En attente de demandes d'amis", prochaine_dans=9
    )
    return suivi


def suivi_npsso() -> moteur.Suivi:
    suivi = moteur.Suivi()
    evenement(suivi, 20, logging.INFO, "info", "Démarrage de PSN Amis")
    evenement(suivi, 19, logging.INFO, "info", "Connexion aux serveurs de Sony...")
    evenement(
        suivi,
        7,
        logging.ERROR,
        "info",
        "PROBLÈME : Sony refuse le code npsso (il est expiré ou incorrect).",
    )
    suivi.code_a_changer(
        "PROBLÈME : Sony refuse le code npsso (il est expiré ou incorrect)."
    )
    return suivi


def suivi_pause() -> moteur.Suivi:
    """La pause minutée (touche 2), avec les demandes qui attendent."""
    suivi = suivi_demo()
    evenement(
        suivi,
        160,
        logging.INFO,
        "info",
        "Pause de 10 min : reprise automatique à 21:11.",
    )
    suivi.statut(moteur.Statut.PAUSE, "Les demandes attendent · P : reprendre")
    suivi.en_attente(
        [
            moteur.Attente(pseudo, MAINTENANT - timedelta(seconds=secondes), "en pause")
            for pseudo, secondes in (
                ("Riko_Spectre", 25),
                ("Alba-Rush", 74),
                ("Sn1per_Lou", 132),
            )
        ]
    )
    return suivi


def interface_pause() -> tb.EtatInterface:
    return tb.EtatInterface(reprise_a=time.monotonic() + 437, duree_pause=600)


def interface_aide() -> tb.EtatInterface:
    jour = MAINTENANT.date()
    ajouts = (37, 52, 18, 0, 64, 41, 29)
    retraits = (1, 3, 0, 0, 2, 1, 0)
    return tb.EtatInterface(
        aide=True,
        statistiques=[
            (jour - timedelta(days=rang), ajouts[rang], retraits[rang])
            for rang in range(7)
        ],
    )


def dessiner(
    suivi: moteur.Suivi,
    largeur: int,
    hauteur: int,
    chemin: Path,
    interface: tb.EtatInterface | None = None,
    theme: str = "sombre",
) -> None:
    with Path(os.devnull).open("w", encoding="utf-8") as nul:
        console = Console(
            record=True,
            width=largeur,
            height=hauteur,
            force_terminal=True,
            legacy_windows=False,
            color_system="truecolor",
            theme=tb.THEMES[theme],
            file=nul,
        )
        instant = suivi.instantane()
        console.print(
            tb.construire_ecran(
                instant, interface or tb.EtatInterface(), largeur, hauteur
            )
        )
        # Écrit avec des fins de ligne LF, comme le reste du dépôt.
        svg = console.export_svg(title=tb.titre_fenetre(instant))
        chemin.write_text(svg, encoding="utf-8", newline="\n")


def main() -> int:
    parametres = argparse.ArgumentParser(
        description="Dessine les captures d'écran du README."
    )
    parametres.add_argument(
        "--sortie",
        type=Path,
        default=RACINE / "docs" / "images",
        help="dossier des images",
    )
    sortie: Path = parametres.parse_args().sortie
    sortie.mkdir(parents=True, exist_ok=True)
    figer_le_temps()

    demo = suivi_demo()
    captures = {
        "tableau-de-bord.svg": (demo, 132, 36, None, "sombre"),
        "cartes-compactes.svg": (demo, 86, 26, None, "sombre"),
        "resume.svg": (demo, 52, 18, None, "sombre"),
        "code-npsso.svg": (suivi_npsso(), 110, 32, None, "sombre"),
        "pause.svg": (suivi_pause(), 132, 36, interface_pause(), "sombre"),
        "aide.svg": (demo, 132, 40, interface_aide(), "sombre"),
        "theme-daltonien.svg": (demo, 132, 36, None, "daltonien"),
    }
    for nom, (suivi, largeur, hauteur, interface, theme) in captures.items():
        dessiner(suivi, largeur, hauteur, sortie / nom, interface, theme)
        print(f"{nom:<22} {largeur} x {hauteur}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
