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

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
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
from psn_amis.ui import composants, theme
from psn_amis.ui.commun import etiquette
from psn_amis.ui.composants import Interrupteur, palette_courante

# Réglages de l'onglet Apparence (appliqués dès qu'on les choisit).
APPARENCE = ("theme", "animations")
# Réglages présentés mais pas modifiables, avec la raison.
VERROUILLES: dict[str, str] = {
    "refuser_demandes_ami_proche": "Indisponible : voir l'explication ci-dessous.",
}
LIBELLES_CHOIX = {
    "systeme": "comme Windows (Effets d'animation)",
    "activees": "activées (transitions discrètes)",
    "coupees": "coupées (affichage instantané)",
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


class ApercuTheme(QAbstractButton):
    """Miniature d'un thème : navigation, carte, texte et bouton d'accent."""

    def __init__(self, cle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cle = cle
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Thème {theme.NOMS[cle]}")
        self.setToolTip(f"{theme.NOMS[cle]} : {theme.DESCRIPTIONS[cle]}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:
        return QSize(200, 150)

    def _miniature(self, peintre: QPainter, zone: QRectF, cle: str) -> None:
        p = theme.PALETTES[cle]
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(QColor(p.fond))
        peintre.drawRoundedRect(zone, 10, 10)
        laterale = QRectF(zone.left(), zone.top(), zone.width() * 0.28, zone.height())
        peintre.setBrush(QColor(p.fond_lateral))
        peintre.drawRoundedRect(laterale, 10, 10)
        for rang in range(4):
            ligne = QRectF(
                laterale.left() + 8,
                laterale.top() + 14 + rang * 13,
                laterale.width() - 16,
                6,
            )
            peintre.setBrush(QColor(p.accent if rang == 0 else p.surface_active))
            peintre.drawRoundedRect(ligne, 3, 3)
        carte = QRectF(
            laterale.right() + 8,
            zone.top() + 12,
            zone.right() - laterale.right() - 16,
            44,
        )
        peintre.setBrush(QColor(p.surface))
        peintre.setPen(QPen(QColor(p.bordure), 1))
        peintre.drawRoundedRect(carte, 7, 7)
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(QColor(p.texte))
        peintre.drawRoundedRect(QRectF(carte.left() + 8, carte.top() + 9, 50, 7), 3, 3)
        peintre.setBrush(QColor(p.discret))
        peintre.drawRoundedRect(QRectF(carte.left() + 8, carte.top() + 22, 80, 5), 2, 2)
        peintre.setBrush(QColor(p.succes))
        peintre.drawEllipse(QRectF(carte.left() + 8, carte.top() + 32, 6, 6))
        peintre.setBrush(QColor(p.accent))
        bouton = QRectF(carte.left(), carte.bottom() + 10, 54, 16)
        peintre.drawRoundedRect(bouton, 6, 6)
        peintre.setBrush(QColor(p.surface_haute))
        peintre.drawRoundedRect(QRectF(bouton.right() + 6, bouton.top(), 40, 16), 6, 6)

    def paintEvent(self, evenement) -> None:
        courante = palette_courante()
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        cadre = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        peintre.setPen(
            QPen(
                QColor(courante.accent if self.isChecked() else courante.bordure_forte),
                2.5 if self.isChecked() else 1,
            )
        )
        peintre.setBrush(QColor(courante.surface))
        peintre.drawRoundedRect(cadre, 14, 14)
        zone = QRectF(cadre.left() + 10, cadre.top() + 10, cadre.width() - 20, 92)
        if self.cle == "systeme":
            gauche = QRectF(
                zone.left(), zone.top(), zone.width() / 2 - 2, zone.height()
            )
            droite = QRectF(
                zone.center().x() + 2, zone.top(), zone.width() / 2 - 2, zone.height()
            )
            peintre.save()
            peintre.setClipRect(gauche)
            self._miniature(peintre, zone, "graphite")
            peintre.restore()
            peintre.save()
            peintre.setClipRect(droite)
            self._miniature(peintre, zone, "clair")
            peintre.restore()
        else:
            self._miniature(peintre, zone, self.cle)
        peintre.setPen(QColor(courante.texte))
        police = peintre.font()
        police.setBold(True)
        peintre.setFont(police)
        texte = theme.NOMS[self.cle] + ("  ✓" if self.isChecked() else "")
        peintre.drawText(
            QRectF(cadre.left() + 12, zone.bottom() + 8, cadre.width() - 24, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            texte,
        )
        if self.hasFocus():
            peintre.setPen(QPen(QColor(courante.accent), 2, Qt.PenStyle.DashLine))
            peintre.setBrush(Qt.BrushStyle.NoBrush)
            peintre.drawRoundedRect(cadre.adjusted(3, 3, -3, -3), 12, 12)
        peintre.end()


class GalerieThemes(QWidget):
    """Choix du thème par aperçus cliquables (pas de palette libre)."""

    def __init__(
        self, choisi: Callable[[str], None], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._choisi = choisi
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        self.apercus: dict[str, ApercuTheme] = {}
        grille = QGridLayout(self)
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setSpacing(12)
        for rang, cle in enumerate(theme.ORDRE):
            apercu = ApercuTheme(cle)
            apercu.setFixedSize(apercu.sizeHint())
            self._groupe.addButton(apercu)
            self.apercus[cle] = apercu
            apercu.clicked.connect(lambda _=False, c=cle: self._choisi(c))
            grille.addWidget(apercu, rang // 4, rang % 4)
        grille.setColumnStretch(4, 1)

    def valeur(self) -> str:
        for cle, apercu in self.apercus.items():
            if apercu.isChecked():
                return cle
        return "graphite"

    def choisir(self, cle: str) -> None:
        if cle in self.apercus:
            self.apercus[cle].setChecked(True)
        for apercu in self.apercus.values():
            apercu.update()

    def changer_palette(self, _p) -> None:
        for apercu in self.apercus.values():
            apercu.update()


class PageReglages(QWidget):
    def __init__(
        self,
        appliquer: Callable[[Reglages], Any],
        actuels: Callable[[], Reglages],
        actions: dict[str, Callable[[], None]],
        verrous: dict[str, str] | None = None,
        parent: QWidget | None = None,
        changer_apparence: Callable[[str, object], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._appliquer = appliquer
        self._actuels = actuels
        self._changer_apparence = changer_apparence
        self._verrous = {**VERROUILLES, **(verrous or {})}
        self.champs: dict[str, QWidget] = {}

        onglets = QTabWidget()
        onglets.setDocumentMode(True)
        onglets.addTab(self._page_apparence(), "Apparence")
        groupes: dict[str, QFormLayout] = {}
        for champ in fields(Reglages):
            meta = champ.metadata
            if champ.name in APPARENCE:
                continue
            if meta["groupe"] not in groupes:
                page = QWidget()
                page.setObjectName("page")
                formulaire = QFormLayout(page)
                formulaire.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
                formulaire.setContentsMargins(4, 14, 18, 14)
                formulaire.setVerticalSpacing(10)
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
        enregistrer = composants.bouton("Enregistrer", "succes", "principal")
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
        importer = composants.bouton("Importer…", "importer")
        importer.clicked.connect(self.importer)
        exporter = composants.bouton("Exporter…", "exporter")
        exporter.setToolTip("Les exports ne contiennent jamais le code npsso")
        exporter.clicked.connect(self.exporter)
        boutons = QHBoxLayout()
        for bouton in (enregistrer, annuler, defaut, importer, exporter):
            boutons.addWidget(bouton)
        boutons.addStretch(1)

        compte = QHBoxLayout()
        compte.setSpacing(8)
        for libelle, cle, icone_nom, genre, aide in (
            (
                "Changer le code npsso…",
                "code",
                "cle",
                "",
                "Connecte un compte PSN ou renouvelle le code",
            ),
            (
                "Arrêt d'urgence du nettoyage",
                "urgence",
                "urgence",
                "secondaire_danger",
                "Annule toutes les suppressions et repasse le nettoyage en manuel",
            ),
            (
                "Dossier des données",
                "dossier",
                "dossier",
                "",
                "Ouvre le dossier des réglages, du journal et des amis connus",
            ),
            (
                "Reprendre une ancienne version…",
                "migrer",
                "importer",
                "",
                "Copie réglages, journal et amis connus d'un dossier PSN Amis 2.x",
            ),
        ):
            if cle in actions:
                bouton = composants.bouton(
                    libelle, icone_nom, genre, aide, actions[cle]
                )
                compte.addWidget(bouton)
        compte.addStretch(1)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(12)
        disposition.addLayout(compte)
        disposition.addWidget(onglets, 1)
        disposition.addWidget(self.message)
        disposition.addLayout(boutons)
        self.recharger()

    # ─── Apparence ───

    def _page_apparence(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        disposition = QVBoxLayout(page)
        disposition.setContentsMargins(4, 14, 18, 14)
        disposition.setSpacing(10)
        disposition.addWidget(etiquette("Thème", "titre_vide"))
        disposition.addWidget(
            etiquette(
                "Choisissez l'apparence de toute l'application. Le changement est "
                "immédiat et gardé pour les prochains lancements.",
                "description",
                retour_ligne=True,
            )
        )
        self.galerie = GalerieThemes(lambda cle: self._apparence("theme", cle))
        self.champs["theme"] = self.galerie
        disposition.addWidget(self.galerie)
        disposition.addSpacing(10)
        disposition.addWidget(etiquette("Animations", "titre_vide"))
        animations = self._creer("animations", "systeme", reglages.info("animations"))
        animations.setMaximumWidth(340)
        animations.setAccessibleName("Animations")
        animations.setToolTip(reglages.info("animations")["description"])
        self.champs["animations"] = animations
        animations.activated.connect(
            lambda _: self._apparence("animations", animations.currentData())
        )
        disposition.addWidget(animations)
        disposition.addWidget(
            etiquette(
                reglages.info("animations")["description"],
                "description",
                retour_ligne=True,
            )
        )
        disposition.addStretch(1)
        defilement = QScrollArea()
        defilement.setWidgetResizable(True)
        defilement.setWidget(page)
        return defilement

    def _apparence(self, nom: str, valeur: object) -> None:
        """Thème ou animations : enregistrés et appliqués tout de suite."""
        if self._changer_apparence is not None:
            self._changer_apparence(nom, valeur)
        else:
            nouveaux, problemes = reglages.modifier(self._actuels(), **{nom: valeur})
            if not problemes:
                self._appliquer(nouveaux)
        if nom == "theme":
            self.galerie.choisir(str(valeur))

    # ─── Widgets ───

    def _creer(self, nom: str, defaut: Any, meta: dict[str, Any]) -> QWidget:
        if isinstance(defaut, bool):
            return Interrupteur(meta["libelle"])
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
        if isinstance(widget, GalerieThemes):
            return widget.valeur()
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
            if isinstance(widget, GalerieThemes):
                widget.choisir(valeur)
            elif isinstance(widget, QCheckBox):
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
