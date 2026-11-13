"""Page « Paramètres » : construite à partir de reglages.py (une seule source de vérité).

Chaque réglage a son libellé, une explication, des bornes et l'effet d'un changement
(immédiat, redémarrage du moteur ou de l'application). Rien n'est enregistré tant que
tout n'est pas valide.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from psn_amis import reglages
from psn_amis.reglages import Effet, Reglages
from psn_amis.ui.commun import etiquette

# Réglages présentés mais pas modifiables, avec la raison.
VERROUILLES: dict[str, str] = {
    "refuser_demandes_ami_proche": "Indisponible : voir l'explication ci-dessous.",
}
LIBELLES_CHOIX = {
    "assiste": "assisté (confirmation demandée)",
    "automatique": "automatique (dans les limites)",
    "manuel": "manuel (désactivé)",
    "laisser": "laisser en attente",
    "accepter": "accepter",
    "quitter": "quitter PSN Amis",
    "reduire": "réduire dans la zone de notification",
    "plus_anciens_acceptes": "les plus anciennement acceptés",
    "premiere_observation": "les premiers vus par PSN Amis",
    "alphabetique": "ordre alphabétique",
}


class PageReglages(QWidget):
    def __init__(
        self,
        appliquer: Callable[[Reglages], Any],
        actuels: Callable[[], Reglages],
        actions: dict[str, Callable[[], None]],
        verrous: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._appliquer = appliquer
        self._actuels = actuels
        self._verrous = {**VERROUILLES, **(verrous or {})}
        self.champs: dict[str, QWidget] = {}

        onglets = QTabWidget()
        groupes: dict[str, QFormLayout] = {}
        for champ in fields(Reglages):
            meta = champ.metadata
            if meta["groupe"] not in groupes:
                page = QWidget()
                formulaire = QFormLayout(page)
                formulaire.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
                defilement = QScrollArea()
                defilement.setWidgetResizable(True)
                defilement.setWidget(page)
                onglets.addTab(defilement, meta["groupe"])
                groupes[meta["groupe"]] = formulaire
            widget = self._creer(champ.name, getattr(Reglages(), champ.name), meta)
            self.champs[champ.name] = widget
            texte = meta["description"]
            if meta["effet"] is not Effet.IMMEDIAT:
                texte += f" (Prend effet après {meta['effet'].value}.)"
            if champ.name in self._verrous:
                widget.setEnabled(False)
                texte = f"{self._verrous[champ.name]} {texte}"
            widget.setToolTip(texte)
            widget.setAccessibleName(meta["libelle"])
            description = etiquette(texte, "description", retour_ligne=True)
            bloc = QWidget()
            disposition = QVBoxLayout(bloc)
            disposition.setContentsMargins(0, 0, 0, 6)
            if isinstance(widget, QSpinBox | QDoubleSpinBox | QComboBox | QLineEdit):
                widget.setMaximumWidth(340)
            disposition.addWidget(widget)
            disposition.addWidget(description)
            if isinstance(widget, QCheckBox):
                # La case porte déjà son libellé.
                groupes[meta["groupe"]].addRow(bloc)
            else:
                groupes[meta["groupe"]].addRow(f"{meta['libelle']} :", bloc)

        self.message = etiquette("", "discret", retour_ligne=True)
        enregistrer = QPushButton("Enregistrer")
        enregistrer.setObjectName("principal")
        enregistrer.setToolTip("Vérifie puis enregistre les réglages (Ctrl+S)")
        enregistrer.setShortcut("Ctrl+S")
        enregistrer.clicked.connect(self.enregistrer)
        annuler = QPushButton("Annuler les modifications")
        annuler.clicked.connect(self.recharger)
        defaut = QPushButton("Valeurs par défaut")
        defaut.setToolTip(
            "Remet les valeurs par défaut dans le formulaire (à enregistrer)"
        )
        defaut.clicked.connect(lambda: self.remplir(Reglages()))
        importer = QPushButton("Importer…")
        importer.clicked.connect(self.importer)
        exporter = QPushButton("Exporter…")
        exporter.setToolTip("Les exports ne contiennent jamais le code npsso")
        exporter.clicked.connect(self.exporter)
        boutons = QHBoxLayout()
        for bouton in (enregistrer, annuler, defaut, importer, exporter):
            boutons.addWidget(bouton)
        boutons.addStretch(1)

        compte = QHBoxLayout()
        for libelle, cle, aide in (
            (
                "Changer le code npsso…",
                "code",
                "Connecte un compte PSN ou renouvelle le code",
            ),
            (
                "Arrêt d'urgence du nettoyage",
                "urgence",
                "Annule toutes les suppressions et repasse le nettoyage en manuel",
            ),
            (
                "Ouvrir le dossier des données",
                "dossier",
                "Réglages, journal, amis connus",
            ),
            (
                "Reprendre les données d'une ancienne version…",
                "migrer",
                "Copie réglages, journal et amis connus d'un dossier PSN Amis 2.x",
            ),
        ):
            if cle in actions:
                bouton = QPushButton(libelle)
                bouton.setToolTip(aide)
                bouton.clicked.connect(actions[cle])
                compte.addWidget(bouton)
        compte.addStretch(1)

        disposition = QVBoxLayout(self)
        disposition.addWidget(etiquette("Paramètres", "titre"))
        disposition.addLayout(compte)
        disposition.addWidget(onglets, 1)
        disposition.addWidget(self.message)
        disposition.addLayout(boutons)
        self.recharger()

    # ─── Widgets ───

    def _creer(self, nom: str, defaut: Any, meta: dict[str, Any]) -> QWidget:
        if isinstance(defaut, bool):
            return QCheckBox(meta["libelle"])
        if meta["choix"]:
            boite = QComboBox()
            for choix in meta["choix"]:
                boite.addItem(LIBELLES_CHOIX.get(choix, choix), choix)
            return boite
        if isinstance(defaut, int) and nom in reglages.ENTIERS:
            boite = QSpinBox()
            minimum, maximum = meta["bornes"]
            boite.setRange(int(minimum), int(maximum))
            if meta["unite"]:
                boite.setSuffix(f" {meta['unite']}")
            return boite
        if isinstance(defaut, int | float):
            boite = QDoubleSpinBox()
            minimum, maximum = meta["bornes"]
            boite.setRange(minimum, maximum)
            boite.setDecimals(1)
            boite.setSingleStep(0.5)
            if meta["unite"]:
                boite.setSuffix(f" {meta['unite']}")
            return boite
        if isinstance(defaut, list):
            zone = QPlainTextEdit()
            zone.setPlaceholderText("Un pseudo (ou identifiant) par ligne")
            zone.setMaximumHeight(110)
            return zone
        return QLineEdit()

    def _valeur(self, nom: str) -> Any:
        widget = self.champs[nom]
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QComboBox):
            return widget.currentData()
        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QDoubleSpinBox):
            return float(widget.value())
        if isinstance(widget, QPlainTextEdit):
            lignes = widget.toPlainText().splitlines()
            return [ligne.strip() for ligne in lignes if ligne.strip()]
        return widget.text() if isinstance(widget, QLineEdit) else None

    def remplir(self, valeurs: Reglages) -> None:
        for nom, widget in self.champs.items():
            valeur = getattr(valeurs, nom)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(valeur))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(valeur)))
            elif isinstance(widget, QSpinBox | QDoubleSpinBox):
                widget.setValue(valeur)
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText("\n".join(valeur))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(valeur))

    def recharger(self) -> None:
        self.remplir(self._actuels())
        self.message.setText("")

    def lire(self) -> tuple[Reglages, list[str]]:
        """Les réglages du formulaire, vérifiés comme ceux du fichier."""
        changements = {
            nom: self._valeur(nom) for nom in self.champs if nom not in self._verrous
        }
        return reglages.modifier(self._actuels(), **changements)

    # ─── Actions ───

    def enregistrer(self) -> bool:
        nouveaux, problemes = self.lire()
        if problemes:
            self._afficher("erreur", "Rien n'a été enregistré : " + " ".join(problemes))
            return False
        resultat = self._appliquer(nouveaux)
        if not resultat.enregistre:
            self._afficher(
                "erreur", "Rien n'a été enregistré : " + " ".join(resultat.problemes)
            )
            return False
        if not resultat.effets:
            self._afficher("info", "✔ Enregistré et appliqué immédiatement.")
        else:
            besoins = " et ".join(sorted(e.value for e in resultat.effets))
            self._afficher(
                "attention",
                f"✔ Enregistré. Certains changements prendront effet après {besoins} "
                "(boutons de la barre d'outils).",
            )
        return True

    def _afficher(self, niveau: str, texte: str) -> None:
        self.message.setObjectName(f"bandeau_{niveau}")
        self.message.setText(texte)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)

    def importer(self) -> None:
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Importer des réglages", "", "Réglages (*.toml)"
        )
        if not chemin:
            return
        lus, problemes = reglages.importer(Path(chemin))
        self.remplir(lus)
        texte = "Réglages importés dans le formulaire : vérifiez puis enregistrez."
        if problemes:
            texte += " Problèmes : " + " ".join(problemes)
        self._afficher("attention", texte)

    def exporter(self) -> None:
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Exporter les réglages", "reglages-psn-amis.toml", "Réglages (*.toml)"
        )
        if chemin:
            try:
                reglages.exporter(self._actuels(), Path(chemin))
            except OSError as erreur:
                QMessageBox.warning(self, "PSN Amis", f"Export impossible : {erreur}")
