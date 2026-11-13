"""Page « Tableau de bord » : l'essentiel en un coup d'œil."""

from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from psn_amis.controleur import EtatMoteur
from psn_amis.gestion import Vue
from psn_amis.moteur import Instantane, en_amis
from psn_amis.ui.commun import STATUTS, carte, date_courte, etiquette
from psn_amis.ui.theme import Palette


def il_y_a(moment: datetime | None, maintenant: datetime) -> str:
    if moment is None:
        return "jamais"
    secondes = int((maintenant - moment).total_seconds())
    if secondes < 60:
        return "à l'instant"
    if secondes < 3600:
        return f"il y a {secondes // 60} min"
    return f"il y a {secondes // 3600} h {secondes % 3600 // 60:02d}"


class TableauDeBord(QWidget):
    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self.statut = etiquette("◌ Démarrage", "grand")
        self.detail = etiquette("", "discret", retour_ligne=True)
        self.compte = etiquette("Compte : pas encore connecté")
        self.automatisation = etiquette("")
        self.amis = etiquette("—", "grand")
        self.capacite = QProgressBar()
        self.capacite.setTextVisible(True)
        self.capacite_texte = etiquette("", "discret")
        self.en_attente = etiquette("—", "grand")
        self.acceptees = etiquette("0", "grand")
        self.acceptees_detail = etiquette("", "discret")
        self.supprimes = etiquette("0", "grand")
        self.supprimes_detail = etiquette("", "discret")
        self.synchro = etiquette("", "discret", retour_ligne=True)
        self.prochaine = etiquette("", "discret", retour_ligne=True)
        self.avertissements = QVBoxLayout()
        self.recents = QListWidget()
        self.recents.setAccessibleName("Derniers amis acceptés")
        self.recents.setMaximumHeight(220)
        self._avertissements_actuels: tuple[tuple[str, str], ...] = ()

        haut = QVBoxLayout()
        haut.addWidget(self.statut)
        haut.addWidget(self.detail)
        haut.addWidget(self.compte)
        haut.addWidget(self.automatisation)
        cadre_haut = carte("État", *[])
        cadre_haut.layout().addLayout(haut)

        grille = QGridLayout()
        grille.setSpacing(10)
        grille.addWidget(cadre_haut, 0, 0, 1, 2)
        grille.addWidget(
            carte("Amis", self.amis, self.capacite, self.capacite_texte), 0, 2, 1, 2
        )
        grille.addWidget(carte("Demandes en attente", self.en_attente), 1, 0)
        grille.addWidget(
            carte("Demandes acceptées", self.acceptees, self.acceptees_detail), 1, 1
        )
        grille.addWidget(
            carte("Amis supprimés par PSN Amis", self.supprimes, self.supprimes_detail),
            1,
            2,
        )
        grille.addWidget(carte("Synchronisation", self.synchro, self.prochaine), 1, 3)
        for colonne in range(4):
            grille.setColumnStretch(colonne, 1)

        bas = QHBoxLayout()
        bas.addWidget(carte("Derniers ajouts", self.recents), 1)

        disposition = QVBoxLayout(self)
        titre = etiquette("Tableau de bord", "titre")
        disposition.addWidget(titre)
        disposition.addLayout(self.avertissements)
        disposition.addLayout(grille)
        disposition.addLayout(bas)
        disposition.addStretch(1)
        self._derniers: tuple = ()

    def changer_palette(self, palette: Palette) -> None:
        self._palette = palette

    def actualiser(
        self,
        instant: Instantane,
        vue: Vue,
        etat_moteur: EtatMoteur,
        en_pause: bool,
        limite: int,
        acceptation_auto: bool,
        avertissements: list[tuple[str, str]],
    ) -> None:
        maintenant = datetime.now()
        if etat_moteur is EtatMoteur.EN_MARCHE:
            symbole, cle, libelle = STATUTS[instant.statut]
        elif etat_moteur is EtatMoteur.ARRET_EN_COURS:
            symbole, cle, libelle = "◌", "attention", "Arrêt en cours"
        else:
            symbole, cle, libelle = "■", "discret", "Moteur arrêté"
        couleur = getattr(self._palette, cle)
        self._texte(self.statut, f"{symbole} {libelle}")
        self.statut.setStyleSheet(f"color: {couleur};")
        self._texte(
            self.detail,
            instant.detail if etat_moteur is EtatMoteur.EN_MARCHE else "",
        )
        self._texte(
            self.compte,
            f"Compte PSN : {instant.pseudo_compte}"
            if instant.pseudo_compte
            else "Compte PSN : pas encore connecté",
        )
        if en_pause:
            automatisation = "Automatisation : en pause (les demandes attendent)"
        elif not acceptation_auto:
            automatisation = "Automatisation : acceptation automatique coupée"
        else:
            automatisation = "Automatisation : acceptation automatique active"
        self._texte(self.automatisation, automatisation)

        if instant.nombre_amis is None:
            self._texte(self.amis, "—")
            self.capacite.setRange(0, max(1, limite))
            self.capacite.setValue(0)
            self._texte(self.capacite_texte, "Nombre d'amis pas encore connu")
        else:
            self._texte(self.amis, f"{instant.nombre_amis} / {limite}")
            self.capacite.setRange(0, max(1, limite))
            self.capacite.setValue(min(instant.nombre_amis, limite))
            reste = limite - instant.nombre_amis
            self._texte(
                self.capacite_texte,
                f"{en_amis(max(reste, 0))} de place"
                if reste > 0
                else "Liste pleine : retirez des amis",
            )
        self._texte(
            self.en_attente,
            "—"
            if instant.demandes_en_attente is None
            else str(instant.demandes_en_attente),
        )
        self._texte(self.acceptees, str(instant.ajouts_jour))
        self._texte(
            self.acceptees_detail,
            f"aujourd'hui · {instant.ajouts_session} depuis le lancement",
        )
        self._texte(self.supprimes, str(instant.supprimes_jour))
        self._texte(
            self.supprimes_detail,
            f"aujourd'hui · {instant.retraits_jour} ami(s) parti(s) d'eux-mêmes",
        )
        self._texte(
            self.synchro,
            f"Dernière vérification : {il_y_a(instant.derniere_verification, maintenant)}"
            + (
                f" · liste reçue le {date_courte(vue.synchronise_le)}"
                if vue.synchronise_le
                else ""
            ),
        )
        if instant.prochaine_verification is not None and not en_pause:
            reste = max(0, int(instant.prochaine_verification - time.monotonic()))
            self._texte(self.prochaine, f"Prochaine vérification dans {reste} s")
        else:
            self._texte(self.prochaine, "Prochaine vérification : —")

        if instant.derniers_ajouts[:10] != self._derniers:
            self._derniers = instant.derniers_ajouts[:10]
            self.recents.clear()
            if not self._derniers:
                self.recents.addItem("Aucun ajout pour l'instant.")
            for ajout in self._derniers:
                self.recents.addItem(f"+ {ajout.moment:%d/%m %H:%M}  {ajout.pseudo}")
        self._afficher_avertissements(tuple(avertissements))

    def _afficher_avertissements(
        self, avertissements: tuple[tuple[str, str], ...]
    ) -> None:
        if avertissements == self._avertissements_actuels:
            return
        self._avertissements_actuels = avertissements
        while self.avertissements.count():
            element = self.avertissements.takeAt(0)
            if element.widget():
                element.widget().deleteLater()
        for niveau, texte in avertissements:
            bandeau = QLabel(texte)
            bandeau.setWordWrap(True)
            bandeau.setObjectName(f"bandeau_{niveau}")
            bandeau.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.avertissements.addWidget(bandeau)

    @staticmethod
    def _texte(label: QLabel, texte: str) -> None:
        # Ne redessine que si le texte change : pas de rafraîchissement inutile.
        if label.text() != texte:
            label.setText(texte)
