"""Page « Demandes d'amis » : demandes en attente et traitement automatique."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from psn_amis import demandes as types_demandes
from psn_amis.moteur import Instantane
from psn_amis.reglages import Reglages
from psn_amis.ui.commun import date_courte, etiquette

EXPLICATIONS = (
    "Demandes ordinaires : acceptées automatiquement si l'option est cochée "
    "(listes noire et blanche appliquées).\n"
    "Demandes d'ami proche (partage du vrai nom) : jamais acceptées automatiquement. "
    + types_demandes.EXPLICATION_REFUS_AMI_PROCHE
)


class PageDemandes(QWidget):
    def __init__(
        self,
        changer_reglage: Callable[[str, object], None],
        ouvrir_reglages: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._changer = changer_reglage
        self.acceptation = QCheckBox("Accepter automatiquement les demandes d'amis")
        self.acceptation.setToolTip(
            "Décochez pour laisser les demandes en attente sans les accepter."
        )
        self.acceptation.toggled.connect(
            lambda coche: self._changer("acceptation_auto", coche)
        )
        reglages_demandes = QPushButton("Listes noire et blanche…")
        reglages_demandes.setToolTip("Ouvre les paramètres des demandes")
        reglages_demandes.clicked.connect(ouvrir_reglages)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Pseudo", "Envoyée le", "État"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setAccessibleName("Demandes d'amis en attente")
        self.vide = etiquette(
            "Aucune demande en attente pour l'instant.", "discret", retour_ligne=True
        )

        haut = QHBoxLayout()
        haut.addWidget(self.acceptation)
        haut.addStretch(1)
        haut.addWidget(reglages_demandes)

        disposition = QVBoxLayout(self)
        disposition.addWidget(etiquette("Demandes d'amis", "titre"))
        disposition.addLayout(haut)
        disposition.addWidget(etiquette(EXPLICATIONS, "description", retour_ligne=True))
        disposition.addWidget(self.vide)
        disposition.addWidget(self.table, 1)
        self._derniere: tuple = ()

    def actualiser(self, instant: Instantane, reglages: Reglages) -> None:
        if self.acceptation.isChecked() != reglages.acceptation_auto:
            self.acceptation.blockSignals(True)
            self.acceptation.setChecked(reglages.acceptation_auto)
            self.acceptation.blockSignals(False)
        if instant.attentes == self._derniere:
            return
        self._derniere = instant.attentes
        self.vide.setVisible(not instant.attentes)
        self.table.setVisible(bool(instant.attentes))
        self.table.setRowCount(len(instant.attentes))
        for rang, attente in enumerate(instant.attentes):
            depuis = attente.depuis
            valeurs = (
                attente.pseudo,
                date_courte(depuis, "Non disponible")
                if isinstance(depuis, datetime)
                else "Non disponible",
                attente.motif or "sera acceptée à la prochaine vérification",
            )
            for colonne, valeur in enumerate(valeurs):
                self.table.setItem(rang, colonne, QTableWidgetItem(valeur))
        self.table.resizeColumnsToContents()
