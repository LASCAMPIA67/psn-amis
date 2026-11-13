"""Fenêtre principale de PSN Amis."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from psn_amis import __version__, chemins, migration, mises_a_jour, moteur, systeme
from psn_amis.controleur import Controleur, EtatMoteur
from psn_amis.mises_a_jour import Publication
from psn_amis.reglages import Reglages
from psn_amis.ui import composants, icones, theme
from psn_amis.ui.amis import PageAmis
from psn_amis.ui.apropos import FenetreMiseAJour, PageAPropos
from psn_amis.ui.assistant import FenetreCode
from psn_amis.ui.commun import STATUTS, Message, PontJournal, Tache
from psn_amis.ui.composants import (
    Animations,
    Notifications,
    Pages,
    Pastille,
    etiquette,
)
from psn_amis.ui.console import Console
from psn_amis.ui.demandes import PageDemandes
from psn_amis.ui.reglages import PageReglages
from psn_amis.ui.tableau import TableauDeBord

# (nom, raccourci, icône, sous-titre de l'en-tête)
PAGES = (
    (
        "Tableau de bord",
        "Ctrl+1",
        "tableau",
        "Votre compte et le moteur, en un coup d'œil",
    ),
    ("Activité", "Ctrl+2", "activite", "Tout ce que fait PSN Amis, en temps réel"),
    (
        "Amis",
        "Ctrl+3",
        "amis",
        "Consulter, protéger et faire de la place dans votre liste",
    ),
    ("Demandes", "Ctrl+4", "demandes", "Demandes reçues et règles d'acceptation"),
    (
        "Paramètres",
        "Ctrl+5",
        "parametres",
        "Apparence, moteur, demandes, amis et application",
    ),
    ("À propos", "Ctrl+6", "apropos", "Version, mises à jour et confidentialité"),
)
# Icône de chaque commande (recolorée selon le thème).
ICONES_ACTIONS = {
    "action_demarrer": "jouer",
    "action_arreter": "arreter",
    "action_pause": "pause",
    "action_verifier": "actualiser",
    "action_reconnecter": "lien",
    "action_redemarrer": "redemarrer",
    "action_relancer": "redemarrer",
    "action_quitter": "quitter",
}


class Fenetre(QMainWindow):
    # Réglages changés depuis un autre fil (moteur) : remis au fil de l'interface.
    reglages_modifies = Signal(object)

    def __init__(
        self,
        controleur: Controleur,
        pont: PontJournal,
        icone: QIcon,
        relancer_application: Callable[[], None],
        avertissements_demarrage: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.controleur = controleur
        self._relancer_application = relancer_application
        self._avertissements_demarrage = list(avertissements_demarrage or [])
        self._publication: Publication | None = None
        self._quitter_pour_de_bon = False
        self.setWindowTitle(f"PSN Amis {__version__}")
        self.setWindowIcon(icone)
        self.resize(1240, 800)
        self.setMinimumSize(900, 600)
        self._dernier_toast = 0.0
        nom_theme = controleur.reglages.theme
        palette = theme.palette(nom_theme)

        self.tableau = TableauDeBord(palette)
        self.console = Console(palette)
        self.amis = PageAmis(controleur.gestion, controleur.verifier_maintenant)
        self.demandes = PageDemandes(self._changer_reglage, lambda: self.aller(4))
        verrous = {}
        if not systeme.demarrage_possible():
            verrous["demarrage_windows"] = (
                "Disponible dans l'application installée seulement."
            )
        self.reglages_page = PageReglages(
            controleur.appliquer,
            lambda: controleur.reglages,
            {
                "code": self.changer_code,
                "urgence": self.arret_d_urgence,
                "dossier": self.ouvrir_dossier,
                "migrer": self.reprendre_anciennes_donnees,
            },
            verrous,
            changer_apparence=self._changer_apparence,
        )
        self.apropos = PageAPropos(self.rechercher_mise_a_jour, moteur.DOSSIER)

        self.pages = Pages()
        self._boutons_nav: list[QPushButton] = []
        self._groupe_nav = QButtonGroup(self)
        self._groupe_nav.setExclusive(True)

        laterale = QFrame()
        laterale.setObjectName("laterale")
        laterale.setFixedWidth(236)
        nav = QVBoxLayout(laterale)
        nav.setContentsMargins(14, 18, 14, 14)
        nav.setSpacing(4)
        self.logo = QLabel()
        self.logo.setFixedSize(38, 38)
        self.logo.setAccessibleName("PSN Amis")
        marque = QVBoxLayout()
        marque.setSpacing(0)
        marque.addWidget(etiquette("PSN Amis", "marque"))
        marque.addWidget(etiquette(f"Version {__version__}", "marque_sous"))
        ligne_marque = QHBoxLayout()
        ligne_marque.setContentsMargins(6, 0, 0, 0)
        ligne_marque.setSpacing(10)
        ligne_marque.addWidget(self.logo)
        ligne_marque.addLayout(marque, 1)
        nav.addLayout(ligne_marque)
        nav.addSpacing(18)
        nav.addWidget(etiquette("NAVIGATION", "section_nav"))
        for rang, (nom, raccourci, icone_nom, _) in enumerate(PAGES):
            bouton = composants.bouton(nom, icone_nom, "nav")
            bouton.setCheckable(True)
            bouton.setToolTip(f"{nom} ({raccourci})")
            bouton.setAccessibleName(nom)
            bouton.setIconSize(QSize(18, 18))
            # Focus au clavier seulement : un clic ne laisse pas de cadre en plus.
            bouton.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            self._groupe_nav.addButton(bouton, rang)
            self._boutons_nav.append(bouton)
            nav.addWidget(bouton)
        self._groupe_nav.idClicked.connect(self.aller)
        for page in (
            self.tableau,
            self.console,
            self.amis,
            self.demandes,
            self.reglages_page,
            self.apropos,
        ):
            conteneur = QWidget()
            conteneur.setObjectName("page")
            disposition = QVBoxLayout(conteneur)
            disposition.setContentsMargins(28, 18, 28, 22)
            disposition.addWidget(page)
            self.pages.addWidget(conteneur)
        nav.addStretch(1)
        pied = QFrame()
        pied.setObjectName("pied_nav")
        disposition_pied = QVBoxLayout(pied)
        disposition_pied.setContentsMargins(12, 10, 12, 12)
        disposition_pied.setSpacing(6)
        self.etat_nav = Pastille()
        self.etat_nav.setAccessibleName("État du moteur")
        self.compte_nav = etiquette("Aucun compte connecté", "tertiaire", True)
        disposition_pied.addWidget(self.etat_nav, 0, Qt.AlignmentFlag.AlignLeft)
        disposition_pied.addWidget(self.compte_nav)
        nav.addWidget(pied)

        entete = QFrame()
        entete.setObjectName("entete")
        disposition_entete = QHBoxLayout(entete)
        disposition_entete.setContentsMargins(28, 16, 22, 14)
        disposition_entete.setSpacing(8)
        textes = QVBoxLayout()
        textes.setSpacing(2)
        self.titre_page = etiquette("", "titre_page")
        self.sous_titre_page = etiquette("", "sous_titre_page")
        textes.addWidget(self.titre_page)
        textes.addWidget(self.sous_titre_page)
        disposition_entete.addLayout(textes, 1)
        self.barre_actions = QHBoxLayout()
        self.barre_actions.setSpacing(8)
        disposition_entete.addLayout(self.barre_actions)

        droite = QWidget()
        disposition_droite = QVBoxLayout(droite)
        disposition_droite.setContentsMargins(0, 0, 0, 0)
        disposition_droite.setSpacing(0)
        disposition_droite.addWidget(entete)
        disposition_droite.addWidget(self.pages, 1)

        centre = QWidget()
        centre.setObjectName("centre")
        disposition = QHBoxLayout(centre)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addWidget(laterale)
        disposition.addWidget(droite, 1)
        self.setCentralWidget(centre)
        self.notifications = Notifications(centre)

        self._creer_actions()
        self.etat_barre = QLabel()
        self.statusBar().addWidget(self.etat_barre, 1)
        self.statusBar().addPermanentWidget(QLabel(f"v{__version__}"))

        pont.message.connect(self._message)
        self._tache_maj = Tache(self)
        self._tache_maj.reussie.connect(self._publication_recue)
        self._tache_maj.echouee.connect(lambda e: self._etat_maj(f"échec ({e})"))
        self._manuelle = False

        self.zone: QSystemTrayIcon | None = None
        self.appliquer_reglages(controleur.reglages)
        self.reglages_modifies.connect(self._reglages_modifies)
        controleur.reglages_changes = self.reglages_modifies.emit

        # Thème « Système » : suit Windows quand il passe du clair au sombre.
        QApplication.instance().styleHints().colorSchemeChanged.connect(
            self._schema_windows_change
        )
        self.aller(0)
        # Focus de départ sur le contenu (et non sur un bouton de navigation).
        self.pages.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.pages.setFocus()
        self.minuterie = QTimer(self)
        self.minuterie.setInterval(1000)
        self.minuterie.timeout.connect(self.actualiser)
        self.minuterie.start()
        self.actualiser()

    # ─── Actions ───

    def _action(
        self,
        texte: str,
        raccourci: str | QKeySequence.StandardKey | None,
        aide: str,
        fonction: Callable[[], object],
    ) -> QAction:
        action = QAction(texte, self)
        if raccourci is not None:
            action.setShortcut(QKeySequence(raccourci))
        action.setToolTip(
            f"{aide} ({action.shortcut().toString()})" if raccourci else aide
        )
        action.setStatusTip(aide)
        action.triggered.connect(fonction)
        self.addAction(action)
        return action

    def _creer_actions(self) -> None:
        self.action_demarrer = self._action(
            "Démarrer", "Ctrl+D", "Démarre le moteur", self.controleur.demarrer
        )
        self.action_arreter = self._action(
            "Arrêter",
            "Ctrl+Shift+D",
            "Arrête le moteur après l'opération en cours",
            self.arreter_moteur,
        )
        self.action_pause = self._action(
            "Pause", "Ctrl+P", "Met en pause ou reprend les acceptations", self.pause
        )
        self.action_verifier = self._action(
            "Vérifier maintenant",
            "F5",
            "Vérifie les demandes et recompte les amis tout de suite",
            self.controleur.verifier_maintenant,
        )
        self.action_reconnecter = self._action(
            "Reconnecter",
            "Ctrl+R",
            "Ferme puis rouvre la connexion à Sony",
            self.controleur.reconnecter,
        )
        self.action_redemarrer = self._action(
            "Redémarrer le moteur",
            "Ctrl+Shift+R",
            "Arrête proprement le moteur puis le relance",
            self.controleur.redemarrer,
        )
        self.action_relancer = self._action(
            "Redémarrer l'application",
            None,
            "Ferme PSN Amis proprement et le rouvre",
            self.redemarrer_application,
        )
        self.action_quitter = self._action(
            "Quitter", QKeySequence.StandardKey.Quit, "Ferme PSN Amis", self.quitter
        )
        self.action_quitter.setShortcut(QKeySequence("Ctrl+Q"))
        self._boutons_actions: dict[str, QToolButton] = {}
        for nom in (
            "action_demarrer",
            "action_arreter",
            "action_pause",
            "action_verifier",
        ):
            bouton = QToolButton()
            bouton.setDefaultAction(getattr(self, nom))
            bouton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            bouton.setIconSize(QSize(16, 16))
            bouton.setCursor(Qt.CursorShape.PointingHandCursor)
            self._boutons_actions[nom] = bouton
            self.barre_actions.addWidget(bouton)
        self.menu_plus = QMenu(self)
        self.menu_plus.addAction(self.action_reconnecter)
        self.menu_plus.addAction(self.action_redemarrer)
        self.menu_plus.addAction(self.action_relancer)
        self.menu_plus.addSeparator()
        self.menu_plus.addAction(self.action_quitter)
        self.bouton_plus = QToolButton()
        self.bouton_plus.setText("Plus")
        self.bouton_plus.setToolTip("Reconnecter, redémarrer, quitter")
        self.bouton_plus.setAccessibleName("Plus de commandes")
        self.bouton_plus.setMenu(self.menu_plus)
        self.bouton_plus.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.bouton_plus.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.bouton_plus.setIconSize(QSize(18, 18))
        self.bouton_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.barre_actions.addWidget(self.bouton_plus)
        for rang, (nom, raccourci, _, _) in enumerate(PAGES):
            self._action(nom, raccourci, nom, lambda r=rang: self.aller(r))

    def aller(self, rang: int) -> None:
        self._boutons_nav[rang].setChecked(True)
        nom, _, _, sous_titre = PAGES[rang]
        self.titre_page.setText(nom)
        self.sous_titre_page.setText(sous_titre)
        self.pages.afficher(rang)
        self.actualiser()

    def notifier(
        self, niveau: str, titre: str, texte: str = "", duree_ms: int = 4500
    ) -> None:
        """Notification temporaire dans la fenêtre (rien si elle est cachée)."""
        if self.isVisible():
            self.notifications.afficher(niveau, titre, texte, duree_ms)

    # En dessous de cette largeur, les commandes de l'en-tête n'affichent que leur
    # icône (le libellé reste dans l'infobulle et pour les lecteurs d'écran).
    LARGEUR_COMPACTE = 1180

    def resizeEvent(self, evenement) -> None:
        super().resizeEvent(evenement)
        self.notifications.replacer()
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if self.width() < self.LARGEUR_COMPACTE
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        for bouton in self._boutons_actions.values():
            if bouton.toolButtonStyle() != style:
                bouton.setToolButtonStyle(style)

    def pause(self) -> None:
        self.controleur.basculer_pause()
        self.actualiser()

    def arreter_moteur(self) -> None:
        if self.controleur.gestion.vue().operation is not None:
            reponse = QMessageBox.question(
                self,
                "Arrêter le moteur",
                "Une suppression d'amis est en cours. Le moteur s'arrêtera après l'ami "
                "en cours de traitement. Continuer ?",
            )
            if reponse != QMessageBox.StandardButton.Yes:
                return
        self.controleur.arreter()

    def changer_code(self) -> None:
        dialogue = FenetreCode(self)
        dialogue.exec()
        if dialogue.saisie.enregistre:
            self.controleur.reconnecter()
            moteur.journal.info("Nouveau code npsso enregistré : reconnexion à Sony.")
            self.notifier("succes", "Code enregistré", "Reconnexion à Sony en cours.")

    def arret_d_urgence(self) -> None:
        self.controleur.arret_d_urgence()
        self.reglages_page.recharger()
        self.notifier(
            "attention",
            "Arrêt d'urgence",
            "Suppressions annulées, nettoyage repassé en manuel.",
        )

    def ouvrir_dossier(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(moteur.DOSSIER)))

    def reprendre_anciennes_donnees(self) -> None:
        dossier = QFileDialog.getExistingDirectory(
            self, "Dossier de l'ancienne version de PSN Amis"
        )
        if not dossier:
            return
        source = Path(dossier)
        if not migration.anciennes_donnees(source):
            QMessageBox.information(
                self, "PSN Amis", "Aucune donnée de PSN Amis dans ce dossier."
            )
            return
        rapport = migration.migrer(source, moteur.DOSSIER)
        texte = (
            f"Copiés : {', '.join(rapport.copies) or 'rien'}.\n"
            f"Déjà présents (gardés) : {', '.join(rapport.gardes) or 'aucun'}.\n"
        )
        if rapport.erreurs:
            texte += f"Erreurs : {'; '.join(rapport.erreurs)}\n"
        texte += "Les anciens fichiers n'ont pas été modifiés."
        if rapport.ancien_npsso:
            texte += (
                "\nUn ancien npsso.txt a été trouvé : une fois PSN Amis connecté, "
                "supprimez-le de l'ancien dossier."
            )
        if rapport.copies:
            texte += "\n\nRedémarrez PSN Amis pour utiliser ces données."
        QMessageBox.information(self, "Reprise des anciennes données", texte)

    def redemarrer_application(self) -> None:
        self._relancer_application()

    def quitter(self) -> None:
        self._quitter_pour_de_bon = True
        self.close()

    # ─── Réglages ───

    def _changer_reglage(self, nom: str, valeur: object) -> None:
        from psn_amis import reglages

        nouveaux, problemes = reglages.modifier(
            self.controleur.reglages, **{nom: valeur}
        )
        if problemes:
            QMessageBox.warning(self, "PSN Amis", " ".join(problemes))
            return
        self.controleur.appliquer(nouveaux)
        self.reglages_page.recharger()

    def _reglages_modifies(self, nouveaux: Reglages) -> None:
        self.appliquer_reglages(nouveaux)
        # Changement venu d'ailleurs (arrêt du nettoyage par le moteur...) : le
        # formulaire est remis à jour s'il n'est pas sous les yeux de l'utilisateur.
        if self.pages.currentIndex() != 4:
            self.reglages_page.recharger()

    def _changer_apparence(self, nom: str, valeur: object) -> None:
        """Thème ou animations : enregistrés et appliqués tout de suite."""
        from psn_amis import reglages

        nouveaux, problemes = reglages.modifier(
            self.controleur.reglages, **{nom: valeur}
        )
        if problemes:
            self.notifier("erreur", "Réglage refusé", " ".join(problemes))
            return
        if nouveaux == self.controleur.reglages:
            return
        resultat = self.controleur.appliquer(nouveaux)
        if not resultat.enregistre:
            self.notifier(
                "erreur", "Réglage non enregistré", " ".join(resultat.problemes)
            )
            return
        self.appliquer_reglages(nouveaux)
        if nom == "theme":
            self.notifier(
                "succes", "Thème appliqué", theme.NOMS.get(str(valeur), ""), 2500
            )

    def _dessiner_marque(self, palette: theme.Palette) -> None:
        """La marque PSN Amis : manette blanche sur un carré arrondi à l'accent."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap

        densite = self.devicePixelRatioF() or 1.0
        cote = 38
        image = QPixmap(round(cote * densite), round(cote * densite))
        image.setDevicePixelRatio(densite)
        image.fill(Qt.GlobalColor.transparent)
        peintre = QPainter(image)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        degrade = QLinearGradient(0, 0, cote, cote)
        degrade.setColorAt(0, QColor(palette.accent_survol))
        degrade.setColorAt(1, QColor(palette.accent_presse))
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(degrade)
        peintre.drawRoundedRect(QRectF(0, 0, cote, cote), 11, 11)
        peintre.drawPixmap(
            7, 7, icones.pixmap("manette", palette.sur_accent, 24, densite)
        )
        peintre.end()
        self.logo.setPixmap(image)

    def _schema_windows_change(self, *_: object) -> None:
        if self.controleur.reglages.theme == "systeme":
            self.appliquer_reglages(self.controleur.reglages)

    def appliquer_reglages(self, nouveaux: Reglages) -> None:
        Animations.definir(nouveaux.animations)
        composants.changer_theme_courant(nouveaux.theme)
        palette = theme.appliquer(QApplication.instance(), nouveaux.theme)
        self.tableau.changer_palette(palette)
        self.console.changer_palette(palette)
        composants.recolorer(self)
        for nom, icone_nom in ICONES_ACTIONS.items():
            getattr(self, nom).setIcon(
                icones.icone(icone_nom, palette.texte, 16, desactivee=palette.tertiaire)
            )
        self.bouton_plus.setIcon(icones.icone("plus", palette.texte, 18))
        self._dessiner_marque(palette)
        if systeme.demarrage_possible() and (
            systeme.demarre_avec_windows() != nouveaux.demarrage_windows
        ):
            systeme.demarrage_avec_windows(nouveaux.demarrage_windows)
        self._zone_de_notification(nouveaux.zone_notification)

    def _zone_de_notification(self, active: bool) -> None:
        if not active or not QSystemTrayIcon.isSystemTrayAvailable():
            if self.zone is not None:
                self.zone.hide()
                self.zone = None
            return
        if self.zone is not None:
            return
        self.zone = QSystemTrayIcon(self.windowIcon(), self)
        self.zone.setToolTip("PSN Amis")
        menu = QMenu(self)
        menu.addAction("Ouvrir PSN Amis", self.montrer)
        menu.addAction(self.action_pause)
        menu.addSeparator()
        menu.addAction(self.action_quitter)
        self.zone.setContextMenu(menu)
        self.zone.activated.connect(
            lambda raison: (
                self.montrer()
                if raison == QSystemTrayIcon.ActivationReason.Trigger
                else None
            )
        )
        self.zone.show()

    def montrer(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ─── Mises à jour ───

    def rechercher_mise_a_jour(self, manuelle: bool = True) -> None:
        self._manuelle = manuelle
        if self._tache_maj.lancer(mises_a_jour.derniere_publication):
            self._etat_maj("recherche en cours…")

    def _etat_maj(self, texte: str) -> None:
        self.apropos.etat.setText(f"Mises à jour : {texte}")

    def _publication_recue(self, publication: Publication | None) -> None:
        if publication is None:
            self._etat_maj("GitHub est injoignable pour l'instant.")
            return
        if not mises_a_jour.plus_recente(__version__, publication.version):
            self._etat_maj(f"vous avez la dernière version ({__version__}).")
            return
        self._publication = publication
        self._etat_maj(f"version {publication.version} disponible.")
        moteur.journal.info(
            "Nouvelle version disponible : %s (vous avez la %s).",
            publication.version,
            __version__,
        )
        if self._manuelle or self.isVisible():
            FenetreMiseAJour(publication, self.preparer_fermeture, self).exec()

    def preparer_fermeture(self) -> None:
        """Avant une mise à jour : arrêt propre du moteur, réglages déjà enregistrés."""
        self._quitter_pour_de_bon = True
        self.controleur.attendre_arret(15)

    # ─── Affichage ───

    def _message(self, message: Message) -> None:
        self.console.ajouter(message)
        self.tableau.ajouter_evenement(message)
        # Avertissements et erreurs : aussi en notification (une toutes les 8 s au
        # plus, pour ne jamais submerger l'écran).
        if (
            message.niveau >= logging.WARNING
            and time.monotonic() - self._dernier_toast > 8
        ):
            self._dernier_toast = time.monotonic()
            niveau = "erreur" if message.niveau >= logging.ERROR else "attention"
            titre = "Erreur" if niveau == "erreur" else "Attention"
            texte = (
                message.texte if len(message.texte) < 160 else message.texte[:157] + "…"
            )
            self.notifier(niveau, titre, texte, 6000)

    def avertissements(self, instant: moteur.Instantane) -> list[tuple[str, str]]:
        resultat: list[tuple[str, str]] = [
            ("attention", texte) for texte in self._avertissements_demarrage
        ]
        if instant.probleme_npsso:
            resultat.append(
                (
                    "erreur",
                    f"{instant.probleme_npsso} → Paramètres, « Changer le code npsso ».",
                )
            )
        if instant.statut is moteur.Statut.LISTE_PLEINE:
            resultat.append(
                (
                    "attention",
                    "Liste d'amis pleine : les acceptations reprendront dès qu'il y "
                    "aura de la place (onglet Amis pour en supprimer).",
                )
            )
        vue = self.controleur.gestion.vue()
        if vue.proposition is not None:
            resultat.append(
                (
                    "info",
                    f"Nettoyage proposé : {len(vue.proposition.cibles)} ami(s). "
                    "Confirmez ou ignorez dans l'onglet Amis.",
                )
            )
        if vue.interrompue:
            resultat.append(
                (
                    "attention",
                    "La dernière suppression d'amis a été interrompue ; elle n'a pas "
                    "été reprise (onglet Amis).",
                )
            )
        if self._publication is not None:
            resultat.append(
                (
                    "info",
                    f"PSN Amis {self._publication.version} est disponible "
                    "(onglet À propos).",
                )
            )
        return resultat

    def actualiser(self) -> None:
        instant = self.controleur.suivi.instantane()
        etat = self.controleur.etat()
        en_pause = self.controleur.en_pause()
        reglages = self.controleur.reglages
        self.action_demarrer.setEnabled(etat is EtatMoteur.ARRETE)
        self.action_arreter.setEnabled(etat is EtatMoteur.EN_MARCHE)
        texte_pause = "Reprendre" if en_pause else "Pause"
        if self.action_pause.text() != texte_pause:
            p = composants.palette_courante()
            self.action_pause.setText(texte_pause)
            self.action_pause.setIcon(
                icones.icone("jouer" if en_pause else "pause", p.texte, 16)
            )
        self._boutons_actions["action_demarrer"].setVisible(etat is EtatMoteur.ARRETE)
        self._boutons_actions["action_arreter"].setVisible(
            etat is not EtatMoteur.ARRETE
        )
        self.action_verifier.setEnabled(etat is EtatMoteur.EN_MARCHE)
        self.action_reconnecter.setEnabled(etat is EtatMoteur.EN_MARCHE)
        symbole, cle, libelle = STATUTS[instant.statut]
        if etat is EtatMoteur.EN_MARCHE:
            self.etat_nav.afficher(
                "En pause" if en_pause else libelle, "attention" if en_pause else cle
            )
        else:
            self.etat_nav.afficher(f"Moteur {etat.value}", "discret")
        composants.changer_texte(
            self.compte_nav,
            f"Compte : {instant.pseudo_compte}"
            if instant.pseudo_compte
            else "Aucun compte connecté",
        )
        texte = (
            f"{symbole} {libelle} · {instant.detail}"
            if etat is EtatMoteur.EN_MARCHE
            else f"Moteur {etat.value}"
        )
        if self.etat_barre.text() != texte:
            self.etat_barre.setText(texte)
        if self.zone is not None:
            self.zone.setToolTip(f"PSN Amis · {libelle}")
        page = self.pages.currentIndex()
        if page == 0:
            self.tableau.actualiser(
                instant,
                self.controleur.gestion.vue(),
                etat,
                en_pause,
                reglages.limite_amis,
                reglages.acceptation_auto,
                self.avertissements(instant),
            )
        elif page == 2:
            self.amis.actualiser()
        elif page == 3:
            self.demandes.actualiser(instant, reglages)

    def changeEvent(self, evenement) -> None:
        from PySide6.QtCore import QEvent

        if (
            evenement.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and self.zone is not None
        ):
            # Réduite avec l'icône de notification active : rangée près de l'horloge.
            QTimer.singleShot(0, self.hide)
        super().changeEvent(evenement)

    def closeEvent(self, evenement: QCloseEvent) -> None:
        reglages = self.controleur.reglages
        if (
            not self._quitter_pour_de_bon
            and reglages.fermeture == "reduire"
            and self.zone is not None
        ):
            evenement.ignore()
            self.hide()
            self.zone.showMessage(
                "PSN Amis continue",
                "PSN Amis tourne toujours ici. Clic droit → Quitter pour l'arrêter.",
            )
            return
        if self.controleur.gestion.vue().operation is not None:
            reponse = QMessageBox.question(
                self,
                "Quitter PSN Amis",
                "Une suppression d'amis est en cours : elle s'arrêtera après l'ami en "
                "cours de traitement et ne reprendra pas toute seule. Quitter ?",
            )
            if reponse != QMessageBox.StandardButton.Yes:
                self._quitter_pour_de_bon = False
                evenement.ignore()
                return
        self.minuterie.stop()
        if self.zone is not None:
            self.zone.hide()
        evenement.accept()
        QApplication.instance().quit()


def chemin_icone() -> Path:
    return chemins.dossier_paquet() / "ressources" / "icone.ico"
