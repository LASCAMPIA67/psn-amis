"""Assistant de première utilisation et fenêtre « Changer le code npsso ».

Le code npsso est saisi masqué, vérifié (format puis connexion à Sony), rangé dans le
Gestionnaire d'identification de Windows, puis effacé du champ. Il n'est jamais
affiché ni écrit dans le journal.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from psn_amis import moteur, reglages
from psn_amis.reglages import Reglages
from psn_amis.ui import composants, icones
from psn_amis.ui import theme as theme_ui
from psn_amis.ui.apropos import AVERTISSEMENT
from psn_amis.ui.commun import Tache, etiquette

ETAPES = (
    "1. Dans votre navigateur, connectez-vous sur playstation.com avec votre compte.\n"
    "2. Ouvrez ensuite la page du code (bouton ci-dessous) dans le même navigateur.\n"
    "3. Copiez le code de 64 caractères (sans les guillemets) et collez-le ici.\n"
    "Attention : si votre écran est partagé ou enregistré, le code y serait visible."
)


class SaisieCode(QWidget):
    """Champ masqué + vérification du format et de la connexion."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.enregistre = False
        self.pseudo: str | None = None
        self.champ = QLineEdit()
        self.champ.setEchoMode(QLineEdit.EchoMode.Password)
        self.champ.setPlaceholderText("Collez ici votre code npsso (Ctrl+V)")
        self.champ.setAccessibleName("Code npsso")
        connexion = QPushButton("1. Se connecter sur playstation.com")
        connexion.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.playstation.com"))
        )
        page_code = QPushButton("2. Ouvrir la page du code")
        page_code.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(moteur.ADRESSE_CODE_NPSSO))
        )
        self.verifier = QPushButton("Enregistrer et vérifier")
        self.verifier.setObjectName("principal")
        self.verifier.clicked.connect(self.enregistrer)
        self.message = etiquette("", "discret", retour_ligne=True)
        self._tache = Tache(self)
        self._tache.reussie.connect(self._connecte)
        self._tache.echouee.connect(self._refuse)

        boutons = QHBoxLayout()
        boutons.addWidget(connexion)
        boutons.addWidget(page_code)
        boutons.addStretch(1)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addWidget(etiquette(ETAPES, retour_ligne=True))
        disposition.addLayout(boutons)
        ligne = QHBoxLayout()
        ligne.addWidget(self.champ, 1)
        ligne.addWidget(self.verifier)
        disposition.addLayout(ligne)
        disposition.addWidget(self.message)

    def enregistrer(self) -> None:
        saisie = self.champ.text()
        # Le champ est vidé tout de suite : le code ne reste pas à l'écran.
        self.champ.clear()
        if not saisie.strip():
            self.message.setText("Collez d'abord votre code.")
            return
        try:
            rangement = moteur.enregistrer_npsso(saisie)
        except moteur.ProblemeNpsso as probleme:
            self.message.setText(f"Ce n'est pas un code valide : {probleme}")
            return
        self.enregistre = True
        self.message.setText(
            f"Code enregistré dans {rangement}. Vérification auprès de Sony…"
        )
        self.verifier.setEnabled(False)
        self._tache.lancer(_verifier_connexion)

    def _connecte(self, pseudo: str) -> None:
        self.pseudo = pseudo
        self.verifier.setEnabled(True)
        self.message.setText(f"✔ Connexion réussie : compte PSN {pseudo}.")

    def _refuse(self, erreur: object) -> None:
        self.verifier.setEnabled(True)
        if isinstance(erreur, moteur.PSNAWPAuthenticationError):
            texte = "Sony refuse ce code (expiré ou incorrect) : recommencez l'étape 2."
        elif isinstance(erreur, moteur.requests.RequestException):
            texte = (
                "Sony est injoignable pour l'instant (connexion Internet ?). Le code est "
                "enregistré : PSN Amis réessaiera tout seul."
            )
        else:
            texte = f"Vérification impossible ({type(erreur).__name__})."
        self.message.setText(f"✖ {moteur.masquer(texte)}")


def _verifier_connexion() -> str:
    connexion = moteur.ouvrir_connexion(moteur.lire_npsso())
    try:
        return connexion.pseudo
    finally:
        connexion.fermer()


class FenetreCode(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connecter un compte PSN")
        self.resize(660, 360)
        self.saisie = SaisieCode()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(24, 22, 24, 18)
        disposition.setSpacing(12)
        entete = QHBoxLayout()
        entete.setSpacing(12)
        icone = QLabel()
        p = composants.palette_courante()
        icone.setPixmap(icones.pixmap("cle", p.accent, 28))
        icone.setAlignment(Qt.AlignmentFlag.AlignTop)
        textes = QVBoxLayout()
        textes.setSpacing(2)
        textes.addWidget(etiquette("Connecter votre compte PlayStation", "titre_vide"))
        textes.addWidget(
            etiquette(
                "Le code est vérifié auprès de Sony, puis gardé dans le Gestionnaire "
                "d'identification de Windows. Il n'est jamais affiché.",
                "discret",
                retour_ligne=True,
            )
        )
        entete.addWidget(icone)
        entete.addLayout(textes, 1)
        disposition.addLayout(entete)
        disposition.addWidget(self.saisie)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        boutons.button(QDialogButtonBox.StandardButton.Close).setText("Fermer")
        boutons.rejected.connect(self.reject)
        disposition.addWidget(boutons)


class _PageCode(QWizardPage):
    def __init__(self, saisie: SaisieCode) -> None:
        super().__init__()
        self.setTitle("Connexion de votre compte PlayStation")
        self.saisie = saisie
        disposition = QVBoxLayout(self)
        disposition.addWidget(saisie)
        disposition.addWidget(
            etiquette(
                "Vous pourrez aussi le faire plus tard : Paramètres → « Changer le "
                "code npsso ».",
                "description",
                retour_ligne=True,
            )
        )


class _PageAvertissement(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Avant de commencer")
        self.compris = QCheckBox("J'ai compris")
        self.compris.toggled.connect(self.completeChanged)
        disposition = QVBoxLayout(self)
        disposition.addWidget(etiquette(AVERTISSEMENT, retour_ligne=True))
        disposition.addWidget(self.compris)

    def isComplete(self) -> bool:
        return self.compris.isChecked()


class Assistant(QWizard):
    def __init__(
        self,
        actuels: Reglages,
        appliquer: Callable[[Reglages], object],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bienvenue dans PSN Amis")
        # Style classique : pas de flèche de retour dans l'en-tête (elle chevauchait
        # le titre sous Windows) ; « < Précédent » reste en bas.
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.resize(680, 520)
        self.setButtonText(QWizard.WizardButton.NextButton, "Suivant >")
        self.setButtonText(QWizard.WizardButton.BackButton, "< Précédent")
        self.setButtonText(
            QWizard.WizardButton.FinishButton, "Ouvrir le tableau de bord"
        )
        self.setButtonText(QWizard.WizardButton.CancelButton, "Plus tard")
        self._actuels = actuels
        self._appliquer = appliquer

        bienvenue = QWizardPage()
        bienvenue.setTitle("Bienvenue dans PSN Amis")
        disposition_bienvenue = QVBoxLayout(bienvenue)
        disposition_bienvenue.setSpacing(14)
        disposition_bienvenue.addWidget(
            etiquette(
                "PSN Amis accepte automatiquement les demandes d'amis que reçoit votre "
                "compte PlayStation, et vous aide à garder de la place dans votre liste "
                "d'amis (2000 au maximum chez Sony).",
                retour_ligne=True,
            )
        )
        p = composants.palette_courante()
        for icone_nom, titre, texte in (
            (
                "demandes",
                "Acceptation automatique",
                "Les demandes sont vérifiées toutes les 15 secondes et acceptées une par "
                "une.",
            ),
            (
                "bouclier",
                "Vous gardez la main",
                "Aucun ami n'est supprimé sans votre accord, et jamais un ami protégé.",
            ),
            (
                "activite",
                "Tout est visible",
                "Chaque action apparaît dans l'activité, avec son heure.",
            ),
        ):
            carte = composants.Carte(titre, icone_nom)
            carte.ajouter(etiquette(texte, "discret", retour_ligne=True))
            carte.changer_palette(p)
            disposition_bienvenue.addWidget(carte)
        disposition_bienvenue.addStretch(1)
        self.saisie = SaisieCode()
        configuration = QWizardPage()
        configuration.setTitle("Premiers réglages")
        self.acceptation = QCheckBox("Accepter automatiquement les demandes d'amis")
        self.acceptation.setChecked(actuels.acceptation_auto)
        self.notifications = QCheckBox(
            "Notifications Windows pour les événements importants"
        )
        self.notifications.setChecked(actuels.notifications)
        self.mises_a_jour = QCheckBox(
            "Vérifier les mises à jour au lancement (une requête à GitHub, rien d'autre)"
        )
        self.mises_a_jour.setChecked(True)
        self.theme = QComboBox()
        for cle in theme_ui.ORDRE:
            self.theme.addItem(theme_ui.NOMS[cle], cle)
        self.theme.setCurrentIndex(max(0, self.theme.findData(actuels.theme)))
        disposition = QVBoxLayout(configuration)
        for widget in (self.acceptation, self.notifications, self.mises_a_jour):
            disposition.addWidget(widget)
        ligne = QHBoxLayout()
        ligne.addWidget(etiquette("Thème :"))
        ligne.addWidget(self.theme)
        ligne.addStretch(1)
        disposition.addLayout(ligne)
        disposition.addWidget(
            etiquette(
                "Tout se change ensuite dans l'onglet Paramètres. La suppression "
                "automatique d'amis reste désactivée tant que vous ne l'activez pas.",
                "description",
                retour_ligne=True,
            )
        )
        for page in (
            bienvenue,
            _PageAvertissement(),
            _PageCode(self.saisie),
            configuration,
        ):
            self.addPage(page)

    def accept(self) -> None:
        nouveaux, problemes = reglages.modifier(
            self._actuels,
            acceptation_auto=self.acceptation.isChecked(),
            notifications=self.notifications.isChecked(),
            verifier_mises_a_jour=self.mises_a_jour.isChecked(),
            theme=self.theme.currentData(),
        )
        if not problemes:
            self._appliquer(nouveaux)
        super().accept()
