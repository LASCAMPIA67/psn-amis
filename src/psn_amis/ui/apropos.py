"""Page « À propos » et fenêtre de mise à jour."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QProgressBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from psn_amis import __version__, chemins, mises_a_jour
from psn_amis.mises_a_jour import ErreurMiseAJour, Publication
from psn_amis.ui import composants
from psn_amis.ui.commun import Tache, etiquette
from psn_amis.ui.composants import Bandeau

DEPOT = f"https://github.com/{mises_a_jour.DEPOT}"
AVERTISSEMENT = (
    "PSN Amis est un projet indépendant, sans lien avec Sony Interactive Entertainment "
    "ni PlayStation. Il utilise PSNAWP, une bibliothèque qui passe par une API "
    "PlayStation non officielle : Sony peut la modifier à tout moment, et une "
    "utilisation intensive pourrait enfreindre ses conditions d'utilisation. Utilisez "
    "PSN Amis à un rythme raisonnable ; aucune garantie de compatibilité ni d'absence "
    "de sanction n'est possible."
)


def ouvrir(adresse: str) -> None:
    QDesktopServices.openUrl(QUrl(adresse))


class FenetreMiseAJour(QDialog):
    """« Mise à jour disponible » : nouveautés, installer, ou plus tard."""

    def __init__(
        self,
        publication: Publication,
        preparer_fermeture: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.publication = publication
        self._preparer_fermeture = preparer_fermeture
        self.setWindowTitle("Mise à jour disponible")
        self.resize(560, 460)
        disposition = QVBoxLayout(self)
        disposition.addWidget(etiquette("Mise à jour disponible", "titre"))
        disposition.addWidget(
            etiquette(
                f"Version installée : {__version__}\n"
                f"Nouvelle version : {publication.version}"
            )
        )
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(publication.notes or "Pas de notes de version.")
        disposition.addWidget(notes, 1)
        self.progression = QProgressBar()
        self.progression.setVisible(False)
        self.message = etiquette("", "discret", retour_ligne=True)
        disposition.addWidget(self.progression)
        disposition.addWidget(self.message)
        boutons = QDialogButtonBox()
        voir = boutons.addButton(
            "Voir les nouveautés", QDialogButtonBox.ButtonRole.HelpRole
        )
        voir.clicked.connect(lambda: ouvrir(publication.page))
        self.installer = boutons.addButton(
            "Installer la mise à jour", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.installer.setObjectName("principal")
        plus_tard = boutons.addButton(
            "Plus tard", QDialogButtonBox.ButtonRole.RejectRole
        )
        plus_tard.clicked.connect(self.reject)
        self.installer.clicked.connect(self._installer)
        disposition.addWidget(boutons)
        if not chemins.est_compile():
            self.installer.setEnabled(False)
            self.message.setText(
                "Lancé depuis le code source : mettez à jour avec Git (git pull)."
            )
        elif publication.installateur is None:
            self.installer.setEnabled(False)
            self.message.setText("Pas d'installateur dans cette publication.")
        self._annule = False
        self._tache = Tache(self)
        self._tache.progression.connect(self._progresser)
        self._tache.reussie.connect(self._telecharge)
        self._tache.echouee.connect(self._echec)

    def _installer(self) -> None:
        self.installer.setEnabled(False)
        self.progression.setVisible(True)
        self.progression.setRange(0, 100)
        self.message.setText("Téléchargement de l'installateur officiel…")
        dossier = chemins.dossier_donnees() / "mises_a_jour"
        self._tache.lancer(
            mises_a_jour.telecharger,
            self.publication,
            dossier,
            lambda faits, total: self._tache.progression.emit((faits, total)),
            lambda: self._annule,
        )

    def _progresser(self, valeur: tuple[int, int]) -> None:
        faits, total = valeur
        self.progression.setValue(int(faits * 100 / max(total, 1)))

    def _telecharge(self, chemin: Path) -> None:
        self.message.setText(
            "Fichier vérifié (taille et empreinte SHA-256). Fermeture de PSN Amis et "
            "lancement de l'installation ; vos données sont conservées."
        )
        try:
            self._preparer_fermeture()
            mises_a_jour.lancer_installateur(chemin)
        except (ErreurMiseAJour, OSError) as erreur:
            self._echec(erreur)
            return
        self.accept()
        from PySide6.QtWidgets import QApplication

        QApplication.quit()

    def _echec(self, erreur: object) -> None:
        self.progression.setVisible(False)
        self.installer.setEnabled(chemins.est_compile())
        self.message.setText(f"Mise à jour impossible : {erreur}. PSN Amis continue.")

    def reject(self) -> None:
        self._annule = True
        super().reject()


class PageAPropos(QWidget):
    def __init__(
        self,
        rechercher: Callable[[], None],
        dossier_donnees: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.etat = etiquette("Mises à jour : pas encore vérifiées.", retour_ligne=True)
        verifier = composants.bouton("Rechercher une mise à jour", "mise_a_jour")
        verifier.setObjectName("principal")
        verifier.clicked.connect(rechercher)
        liens_boutons = []
        for libelle, adresse in (
            ("Page du projet", DEPOT),
            ("Notes de version", f"{DEPOT}/releases"),
            ("Signaler un problème", f"{DEPOT}/issues"),
        ):
            bouton = composants.bouton(libelle, "lien", "plat")
            bouton.clicked.connect(lambda _=False, a=adresse: ouvrir(a))
            liens_boutons.append(bouton)
        donnees = composants.bouton(
            "Dossier des données et du journal", "dossier", "plat"
        )
        donnees.clicked.connect(
            lambda: ouvrir(QUrl.fromLocalFile(str(dossier_donnees)).toString())
        )
        liens_boutons.append(donnees)
        liens = composants.RangeeAdaptative(*liens_boutons)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(12)
        disposition.addWidget(etiquette("PSN Amis", "titre"))
        disposition.addWidget(
            etiquette(
                f"Version {__version__} · Python {sys.version.split()[0]} · "
                f"{'application installée' if chemins.est_compile() else 'code source'}"
            )
        )
        disposition.addWidget(
            etiquette(
                "Accepte automatiquement les demandes d'amis PlayStation Network et "
                "aide à gérer la liste d'amis. Licence MIT.",
                retour_ligne=True,
            )
        )
        disposition.addWidget(Bandeau("attention", AVERTISSEMENT))
        disposition.addWidget(
            etiquette(
                "Confidentialité : aucune télémétrie. PSN Amis ne contacte que les "
                "serveurs de Sony, et GitHub pour les mises à jour si vous l'autorisez. "
                "Le code npsso reste dans le Gestionnaire d'identification de Windows.",
                "description",
                retour_ligne=True,
            )
        )
        ligne = QHBoxLayout()
        ligne.addWidget(verifier)
        ligne.addWidget(self.etat, 1)
        disposition.addLayout(ligne)
        disposition.addWidget(liens)
        disposition.addWidget(
            etiquette(
                f"Données : {dossier_donnees}\nBibliothèques tierces et licences : "
                "fichier LICENCES-TIERS.txt du dossier d'installation.",
                "description",
                retour_ligne=True,
            )
        )
        disposition.addStretch(1)
