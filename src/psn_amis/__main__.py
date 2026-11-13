"""Point d'entrée de PSN Amis : `python -m psn_amis` ou l'exécutable installé.

Sans option, la fenêtre de l'application s'ouvre. Les options --console, --test,
--simple et --configurer gardent le mode console des versions 2.x.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from psn_amis import __version__, chemins


def analyser(arguments: list[str] | None = None) -> argparse.Namespace:
    parametres = argparse.ArgumentParser(
        prog="psn-amis",
        description="PSN Amis : accepte et gère les demandes d'amis PlayStation.",
    )
    parametres.add_argument(
        "--version", action="version", version=f"PSN Amis {__version__}"
    )
    mode = parametres.add_mutually_exclusive_group()
    mode.add_argument(
        "--console",
        action="store_true",
        help="tableau de bord en couleur dans la console, au lieu de la fenêtre",
    )
    mode.add_argument(
        "--test",
        action="store_true",
        help="affiche les demandes en attente sans les accepter (console)",
    )
    mode.add_argument(
        "--simple",
        action="store_true",
        help="affichage texte simple, sans tableau de bord (console)",
    )
    mode.add_argument(
        "--configurer",
        action="store_true",
        help="enregistre le code npsso (connecte votre compte), puis s'arrête",
    )
    parametres.add_argument(
        "--diagnostic",
        action="store_true",
        help="écrit aussi diagnostic.txt, avec les détails techniques (code masqué)",
    )
    parametres.add_argument(
        "--demo",
        action="store_true",
        help="démonstration : faux compte PlayStation, aucune connexion à Sony, "
        "données dans un dossier temporaire",
    )
    parametres.add_argument(
        "--reduit", action="store_true", help="ouvre la fenêtre réduite"
    )
    # Options internes (relance de l'application, vérification après compilation).
    parametres.add_argument("--relance", action="store_true", help=argparse.SUPPRESS)
    parametres.add_argument(
        "--verifier", type=float, metavar="SECONDES", help=argparse.SUPPRESS
    )
    # Utilisé par la désinstallation (niveau 3) : retire le code du coffre de Windows.
    parametres.add_argument(
        "--effacer-code", action="store_true", help=argparse.SUPPRESS
    )
    parametres.add_argument("--cible", help=argparse.SUPPRESS)
    return parametres.parse_args(arguments)


def effacer_code(cible: str | None) -> int:
    """Retire du Gestionnaire d'identification l'entrée de PSN Amis, et rien d'autre."""
    from psn_amis import coffre

    cible = cible or coffre.CIBLE
    if cible != coffre.CIBLE and not cible.startswith("PSN Amis/test"):
        print("Entrée refusée : seule celle de PSN Amis peut être retirée.")
        return 2
    return 0 if coffre.effacer(cible) else 1


def mode_console(choix: argparse.Namespace) -> bool:
    if choix.console or choix.test or choix.simple or choix.configurer:
        return True
    # « PSN Amis console.exe » : le même programme, ouvert dans une console.
    return chemins.est_compile() and "console" in Path(sys.executable).stem.lower()


def main(arguments: list[str] | None = None) -> int:
    choix = analyser(arguments)
    if choix.effacer_code:
        return effacer_code(choix.cible)
    if choix.demo:
        from psn_amis import demo

        demo.preparer()
    if mode_console(choix):
        from psn_amis import console

        if choix.demo:
            demo.brancher()
        return console.main(choix)
    try:
        from psn_amis import app
    except ImportError as erreur:
        # Bibliothèque Qt absente (installation partielle) : la console reste possible.
        signaler_plantage(erreur, "Interface graphique indisponible")
        return 1
    try:
        return app.main(choix)
    except Exception as erreur:  # noqa: BLE001 (dernier filet : message lisible)
        signaler_plantage(erreur, "PSN Amis s'est arrêté à cause d'une erreur imprévue")
        return 1


def _masqueur():
    """La fonction qui masque le code npsso ; si le moteur ne se charge pas, une
    fonction qui ne garde que le nom de l'erreur (rien de sensible ne sort)."""
    try:
        from psn_amis.moteur import masquer
    except Exception:  # noqa: BLE001 (le moteur lui-même peut être en cause)
        return None
    return masquer


def signaler_plantage(erreur: BaseException, titre: str) -> Path | None:
    """Écrit le détail (code npsso masqué) dans un fichier et prévient l'utilisateur.

    L'application installée n'a pas de console : sans cela, Windows afficherait une
    trace technique brute.
    """
    import tempfile
    import traceback

    masquer = _masqueur()
    if masquer is None:
        detail = f"{type(erreur).__name__} (détail indisponible)"
        resume = type(erreur).__name__
    else:
        detail = masquer("".join(traceback.format_exception(erreur)))
        resume = masquer(f"{type(erreur).__name__} : {erreur}")
    rapport: Path | None = Path(tempfile.gettempdir()) / "psn-amis-erreur.txt"
    try:
        rapport.write_text(f"PSN Amis {__version__}\n\n{detail}", encoding="utf-8")
    except OSError:
        rapport = None
    texte = (
        f"{titre} :\n{resume}\n\n"
        + (f"Détails enregistrés dans :\n{rapport}\n\n" if rapport else "")
        + "Joignez ce fichier à un signalement sur la page GitHub du projet "
        "(relisez-le avant : il ne contient pas votre code npsso)."
    )
    if sys.stderr is not None:
        print(texte, file=sys.stderr)
    if os.name == "nt" and not os.environ.get("PSN_AMIS_SANS_FENETRE"):
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, texte, "PSN Amis", 0x10)
    return rapport


if __name__ == "__main__":
    sys.exit(main())
