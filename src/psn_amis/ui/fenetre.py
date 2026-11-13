"""Fenêtre principale de PSN Amis."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QSystemTrayIcon,
    QToolBar,
    QWidget,
)

from psn_amis import __version__, chemins, migration, mises_a_jour, moteur, systeme
from psn_amis.controleur import Controleur, EtatMoteur
from psn_amis.mises_a_jour import Publication
from psn_amis.reglages import Reglages
from psn_amis.ui import theme
from psn_amis.ui.amis import PageAmis
from psn_amis.ui.apropos import FenetreMiseAJour, PageAPropos
from psn_amis.ui.assistant import FenetreCode
from psn_amis.ui.commun import STATUTS, Message, PontJournal, Tache
from psn_amis.ui.console import Console
from psn_amis.ui.demandes import PageDemandes
from psn_amis.ui.reglages import PageReglages
from psn_amis.ui.tableau import TableauDeBord

PAGES = (
    ("Tableau de bord", "Ctrl+1"),
    ("Activité", "Ctrl+2"),
    ("Amis", "Ctrl+3"),
    ("Demandes", "Ctrl+4"),
    ("Paramètres", "Ctrl+5"),
    ("À propos", "Ctrl+6"),
)


class Fenetre(QMainWindow):
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
        self.resize(1180, 760)
        self.setMinimumSize(820, 560)
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
        )
        self.apropos = PageAPropos(self.rechercher_mise_a_jour, moteur.DOSSIER)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(190)
        self.navigation.setAccessibleName("Navigation")
        self.pages = QStackedWidget()
        for (nom, raccourci), page in zip(
            PAGES,
            (
                self.tableau,
                self.console,
                self.amis,
                self.demandes,
                self.reglages_page,
                self.apropos,
            ),
            strict=True,
        ):
            self.navigation.addItem(nom)
            element = self.navigation.item(self.navigation.count() - 1)
            element.setToolTip(f"{nom} ({raccourci})")
            conteneur = QWidget()
            disposition = QHBoxLayout(conteneur)
            disposition.setContentsMargins(16, 12, 16, 12)
            disposition.addWidget(page)
            self.pages.addWidget(conteneur)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)

        centre = QWidget()
        disposition = QHBoxLayout(centre)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addWidget(self.navigation)
        disposition.addWidget(self.pages, 1)
        self.setCentralWidget(centre)

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
        controleur.reglages_changes = lambda r: QTimer.singleShot(
            0, lambda: self.appliquer_reglages(r)
        )

        self.navigation.currentRowChanged.connect(lambda _: self.actualiser())
        self.navigation.setCurrentRow(0)
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
        barre = QToolBar("Commandes")
        barre.setMovable(False)
        self.addToolBar(barre)
        self.action_demarrer = self._action(
            "▶ Démarrer", "Ctrl+D", "Démarre le moteur", self.controleur.demarrer
        )
        self.action_arreter = self._action(
            "■ Arrêter",
            "Ctrl+Shift+D",
            "Arrête le moteur après l'opération en cours",
            self.arreter_moteur,
        )
        self.action_pause = self._action(
            "⏸ Pause", "Ctrl+P", "Met en pause ou reprend les acceptations", self.pause
        )
        self.action_verifier = self._action(
            "↻ Vérifier maintenant",
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
        for action in (
            self.action_demarrer,
            self.action_arreter,
            self.action_pause,
            self.action_verifier,
            self.action_reconnecter,
        ):
            barre.addAction(action)
        barre.addSeparator()
        for action in (
            self.action_redemarrer,
            self.action_relancer,
            self.action_quitter,
        ):
            barre.addAction(action)
        for rang, (_, raccourci) in enumerate(PAGES):
            self._action(
                PAGES[rang][0], raccourci, PAGES[rang][0], lambda r=rang: self.aller(r)
            )

    def aller(self, rang: int) -> None:
        self.navigation.setCurrentRow(rang)

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

    def arret_d_urgence(self) -> None:
        self.controleur.arret_d_urgence()
        self.reglages_page.recharger()

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

    def appliquer_reglages(self, nouveaux: Reglages) -> None:
        palette = theme.palette(nouveaux.theme)
        QApplication.instance().setStyleSheet(theme.feuille_de_style(nouveaux.theme))
        self.tableau.changer_palette(palette)
        self.console.changer_palette(palette)
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
        self.action_pause.setText("▶ Reprendre" if en_pause else "⏸ Pause")
        self.action_verifier.setEnabled(etat is EtatMoteur.EN_MARCHE)
        self.action_reconnecter.setEnabled(etat is EtatMoteur.EN_MARCHE)
        symbole, _, libelle = STATUTS[instant.statut]
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
