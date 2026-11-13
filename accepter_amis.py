"""PSN Amis : accepte automatiquement les demandes d'amis PlayStation Network.

Le plus simple : double-cliquez sur « Lancer PSN Amis.cmd ».

En ligne de commande, depuis ce dossier :
    .venv\\Scripts\\python.exe accepter_amis.py               tableau de bord en couleur
    .venv\\Scripts\\python.exe accepter_amis.py --test        demandes en attente, sans
                                                              rien accepter
    .venv\\Scripts\\python.exe accepter_amis.py --simple      affichage texte simple
    .venv\\Scripts\\python.exe accepter_amis.py --configurer  enregistrer le code npsso
                                                              (connecter son compte)
    Ajoutez --diagnostic pour écrire aussi diagnostic.txt (détails techniques, code
    npsso toujours masqué), à joindre à un signalement de problème.

Au premier lancement, sans code enregistré, l'assistant demande le code avant d'ouvrir
le tableau de bord. Les réglages (intervalle de vérification, thème, notifications...)
sont dans reglages.toml, créé au premier lancement.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import os
import sys
import threading
from collections.abc import Callable
from typing import IO

import moteur
from moteur import Commandes, Suivi, journal

# Gardé en mémoire : Windows l'appelle quand la fenêtre se ferme.
_gestionnaire_fermeture: object | None = None


class Fin:
    """Termine la session une seule fois : ligne d'arrêt dans le journal, rangement."""

    def __init__(
        self, suivi: Suivi, commandes: Commandes, verrou: IO[str], noter: bool
    ) -> None:
        self._suivi = suivi
        self._commandes = commandes
        self._verrou = verrou
        self._noter = noter
        self._faite = False
        self._protection = threading.Lock()

    def __call__(self, raison: str) -> None:
        with self._protection:
            if self._faite:
                return
            self._faite = True
        self._commandes.arreter()
        if self._noter:
            journal.info(
                "=== Arrêt (%s) : %d demande(s) acceptée(s) pendant cette session ===",
                raison,
                self._suivi.instantane().ajouts_session,
            )
        self._verrou.close()
        moteur.FICHIER_VERROU.unlink(missing_ok=True)
        moteur.nettoyer_fichiers_temporaires()


def surveiller_fermeture_fenetre(fin: Callable[[str], None]) -> None:
    """Note l'arrêt dans le journal même si la fenêtre est fermée avec la croix."""
    global _gestionnaire_fermeture
    if os.name != "nt":
        return
    raisons = {
        2: "fenêtre fermée",
        5: "fermeture de la session Windows",
        6: "arrêt de Windows",
    }
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint32)

    def gestionnaire(evenement: int) -> int:
        if evenement not in raisons:
            # Ctrl+C et Ctrl+Pause restent gérés normalement par Python.
            return 0
        # Appelé directement par Windows : aucune erreur ne doit en sortir.
        with contextlib.suppress(Exception):
            fin(raisons[evenement])
        return 1

    _gestionnaire_fermeture = prototype(gestionnaire)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetConsoleCtrlHandler.argtypes = (prototype, ctypes.c_int)
    kernel32.SetConsoleCtrlHandler(_gestionnaire_fermeture, 1)


def demarrer_moteur(suivi: Suivi, commandes: Commandes) -> threading.Thread:
    fil = threading.Thread(
        target=moteur.tourner_en_continu,
        args=(moteur.Etat(), suivi, commandes),
        name="moteur-psn-amis",
        daemon=True,
    )
    fil.start()
    return fil


def console_interactive() -> bool:
    return all(flux is not None and flux.isatty() for flux in (sys.stdin, sys.stdout))


def main() -> int:
    parametres = argparse.ArgumentParser(
        prog="accepter_amis",
        description="Accepte automatiquement les demandes d'amis PSN.",
    )
    mode = parametres.add_mutually_exclusive_group()
    mode.add_argument(
        "--test",
        action="store_true",
        help="affiche les demandes en attente sans les accepter",
    )
    mode.add_argument(
        "--simple",
        action="store_true",
        help="affichage texte simple, sans tableau de bord",
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
    choix = parametres.parse_args()

    # Les réglages d'abord : ils disent notamment où ranger le code npsso.
    _, problemes_reglages = moteur.charger_reglages()
    if choix.configurer:
        return 0 if moteur.assistant_npsso() else 1

    tableau_de_bord = None
    if not choix.test and not choix.simple and console_interactive():
        try:
            # Rich n'est chargé que pour le tableau de bord.
            import tableau_de_bord
        except ImportError:
            tableau_de_bord = None
        # Premier lancement : on demande le code avant d'ouvrir le tableau de bord.
        if tableau_de_bord is not None and not moteur.code_present():
            moteur.assistant_npsso()

    moteur.configurer_journal(
        ecran=tableau_de_bord is None,
        fichier=not choix.test,
        diagnostic=choix.diagnostic,
    )
    verrou = moteur.verrouiller_instance()
    if verrou is None:
        print(
            "PSN Amis tourne déjà dans une autre fenêtre : utilisez-la, "
            "ou fermez-la avant de relancer."
        )
        return 1
    moteur.baisser_priorite()
    suivi = moteur.Suivi(
        moteur.ajouts_recents_dans_journal(), moteur.retraits_recents_dans_journal()
    )
    commandes = moteur.Commandes()
    fin = Fin(suivi, commandes, verrou, noter=not choix.test)

    if choix.test:
        try:
            return moteur.tester(suivi, commandes)
        except KeyboardInterrupt:
            journal.info("Test interrompu.")
            return 1
        finally:
            fin("test")

    if tableau_de_bord is not None:
        journal.addHandler(tableau_de_bord.VersTableau(suivi))
    surveiller_fermeture_fenetre(fin)
    journal.info("=== Démarrage de PSN Amis ===")
    for probleme in problemes_reglages:
        journal.warning("%s", probleme)
    if choix.diagnostic:
        journal.info(
            "Mode diagnostic : détails techniques écrits dans %s.",
            moteur.FICHIER_DIAGNOSTIC.name,
        )
    moteur.signaler_nouvelle_version()
    raison = "Ctrl+C"
    try:
        if tableau_de_bord is not None:
            raison = tableau_de_bord.lancer(
                suivi, commandes, lambda: demarrer_moteur(suivi, commandes)
            )
        else:
            moteur.tourner_en_continu(moteur.Etat(), suivi, commandes)
    except KeyboardInterrupt:
        raison = "Ctrl+C"
    finally:
        fin(raison)
    return 0


if __name__ == "__main__":
    sys.exit(main())
