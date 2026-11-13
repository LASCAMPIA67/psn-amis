"""Démarrage de l'application graphique PSN Amis."""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import IO

from PySide6.QtCore import QLibraryInfo, QLocale, QProcess, QTimer, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from psn_amis import chemins, migration, moteur, systeme
from psn_amis.controleur import Controleur
from psn_amis.moteur import journal
from psn_amis.ui.commun import PontJournal, VersInterface

# Pendant une relance, la nouvelle instance attend que l'ancienne ait libéré le verrou.
ATTENTE_RELANCE = 20


def prendre_le_verrou(relance: bool) -> IO[str] | None:
    fin = time.monotonic() + (ATTENTE_RELANCE if relance else 0)
    while True:
        verrou = moteur.verrouiller_instance()
        if verrou is not None or time.monotonic() >= fin:
            return verrou
        time.sleep(0.25)


def icone() -> QIcon:
    from psn_amis.ui.fenetre import chemin_icone

    chemin = chemin_icone()
    return QIcon(str(chemin)) if chemin.exists() else QIcon()


def traduire(application: QApplication) -> None:
    """Boutons et fenêtres standard de Qt en français (Oui, Non, Annuler...)."""
    traducteur = QTranslator(application)
    dossier = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if traducteur.load(QLocale(QLocale.Language.French), "qtbase", "_", dossier):
        application.installTranslator(traducteur)


def main(choix: argparse.Namespace) -> int:
    systeme.declarer_identite()
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName("PSN Amis")
    application.setOrganizationName("LASCAMPIA67")
    application.setApplicationDisplayName("PSN Amis")
    application.setWindowIcon(icone())
    traduire(application)

    verrou = prendre_le_verrou(choix.relance)
    if verrou is None:
        if choix.verifier is None:
            QMessageBox.information(
                None,
                "PSN Amis",
                "PSN Amis est déjà ouvert : cherchez sa fenêtre dans la barre des "
                "tâches ou près de l'horloge.",
            )
        return 1
    if not choix.demo:
        systeme.creer_mutex()

    rapport = None
    if not choix.demo:
        rapport = migration.migrer_si_besoin(chemins.dossier_projet(), moteur.DOSSIER)
    reglages_charges, problemes = moteur.charger_reglages()
    if choix.demo:
        from psn_amis import demo

        demo.brancher()

    pont = PontJournal()
    moteur.configurer_journal(ecran=False, fichier=True, diagnostic=choix.diagnostic)
    vers_interface = VersInterface(pont)
    journal.addHandler(vers_interface)

    suivi = moteur.Suivi(
        moteur.ajouts_recents_dans_journal(), moteur.retraits_recents_dans_journal()
    )
    controleur = Controleur(
        suivi, moteur.FICHIER_REGLAGES, moteur.DOSSIER, reglages_charges
    )
    avertissements = list(problemes)
    if rapport is not None and rapport.copies:
        avertissements.append(
            "Données de l'ancienne version reprises ("
            + ", ".join(rapport.copies)
            + f") dans {moteur.DOSSIER}. Les anciens fichiers n'ont pas été modifiés."
        )
    if rapport is not None and rapport.ancien_npsso:
        avertissements.append(
            f"Un ancien fichier npsso.txt reste dans {rapport.source} : une fois "
            "connecté, supprimez-le (le code est gardé dans le coffre de Windows)."
        )
    if choix.demo:
        avertissements.append(
            "Mode démonstration : faux compte, aucune connexion à Sony, données "
            "temporaires."
        )

    from psn_amis.ui.fenetre import Fenetre

    etat = {"relancer": False}

    def relancer_application() -> None:
        reponse = QMessageBox.question(
            fenetre,
            "Redémarrer l'application",
            "PSN Amis va se fermer proprement puis se rouvrir. Continuer ?",
        )
        if reponse == QMessageBox.StandardButton.Yes:
            etat["relancer"] = True
            fenetre.quitter()

    fenetre = Fenetre(
        controleur, pont, application.windowIcon(), relancer_application, avertissements
    )
    journal.info("=== Démarrage de PSN Amis %s ===", moteur.VERSION)
    for probleme in problemes:
        journal.warning("%s", probleme)
    if choix.reduit or reglages_charges.demarrage_reduit:
        if reglages_charges.zone_notification:
            fenetre.hide()
        else:
            fenetre.showMinimized()
    else:
        fenetre.show()

    premier_lancement = not choix.demo and not moteur.code_present()
    if premier_lancement and choix.verifier is None:
        from psn_amis.ui.assistant import Assistant

        Assistant(controleur.reglages, controleur.appliquer, fenetre).exec()
    controleur.demarrer()
    if reglages_charges.verifier_mises_a_jour and not choix.demo:
        QTimer.singleShot(3000, lambda: fenetre.rechercher_mise_a_jour(manuelle=False))
    if choix.verifier is not None:
        # Vérification d'un exécutable compilé : la fenêtre s'ouvre, le moteur
        # démarre, puis tout se ferme proprement après quelques secondes.
        QTimer.singleShot(int(choix.verifier * 1000), fenetre.quitter)

    code = application.exec()

    # Fermeture : moteur arrêté proprement, ressources libérées.
    journal.removeHandler(vers_interface)
    arrete = controleur.attendre_arret(15)
    journal.info(
        "=== Arrêt de PSN Amis : %d demande(s) acceptée(s) pendant cette session ===",
        suivi.instantane().ajouts_session,
    )
    if choix.demo:
        from psn_amis import demo

        demo.arreter()
    verrou.close()
    moteur.FICHIER_VERROU.unlink(missing_ok=True)
    moteur.nettoyer_fichiers_temporaires()
    if etat["relancer"]:
        commande = systeme.commande_de_lancement("--relance")
        if choix.demo:
            commande.append("--demo")
        if not QProcess.startDetached(commande[0], commande[1:]):
            QMessageBox.warning(
                None,
                "PSN Amis",
                "PSN Amis n'a pas pu se rouvrir : relancez-le depuis le menu Démarrer.",
            )
    if choix.verifier is not None:
        print(f"Vérification : fenêtre ouverte, moteur arrêté={arrete}.")
        return 0 if arrete else 2
    return code


if __name__ == "__main__":  # pragma: no cover
    from psn_amis.__main__ import main as principal

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    sys.exit(principal())
