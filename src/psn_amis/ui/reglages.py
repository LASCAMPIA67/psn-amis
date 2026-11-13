"""Page « Paramètres » : construite à partir de reglages.py (une seule source de vérité).

Chaque réglage a son libellé, une explication, des bornes et l'effet d'un changement
(immédiat, redémarrage du moteur ou de l'application). Rien n'est enregistré tant que
tout n'est pas valide.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, replace
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
    QLineEdit,
    QPlainTextEdit,
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

# Titres courts des onglets (le titre complet est dans l'info-bulle).
TITRES_ONGLETS = {"Gestion des amis": "Amis", "Nettoyage automatique": "Nettoyage"}
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

    LARGEUR = 200

    def __init__(self, cle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cle = cle
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Thème {theme.NOMS[cle]}")
        self.setToolTip(f"{theme.NOMS[cle]} : {theme.DESCRIPTIONS[cle]}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:
        return QSize(self.LARGEUR, 150)

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
        self._grille = grille
        self._colonnes = 0
        for cle in theme.ORDRE:
            apercu = ApercuTheme(cle)
            apercu.setFixedSize(apercu.sizeHint())
            self._groupe.addButton(apercu)
            self.apercus[cle] = apercu
            apercu.clicked.connect(lambda _=False, c=cle: self._choisi(c))
        self._placer(4)

    def _placer(self, colonnes: int) -> None:
        """Les aperçus sur autant de colonnes que la largeur le permet."""
        if colonnes == self._colonnes:
            return
        self._colonnes = colonnes
        for apercu in self.apercus.values():
            self._grille.removeWidget(apercu)
        for rang, apercu in enumerate(self.apercus.values()):
            self._grille.addWidget(apercu, rang // colonnes, rang % colonnes)
        for colonne in range(len(self.apercus) + 1):
            self._grille.setColumnStretch(colonne, 1 if colonne == colonnes else 0)

    def resizeEvent(self, evenement) -> None:
        super().resizeEvent(evenement)
        largeur = ApercuTheme.LARGEUR + 12
        self._placer(max(1, min(4, (self.width() + 12) // largeur)))

    def minimumSizeHint(self) -> QSize:
        apercu = next(iter(self.apercus.values()))
        return QSize(apercu.width(), super().minimumSizeHint().height())

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
        self.onglets = onglets
        self._groupe_onglet: dict[str, int] = {}
        onglets.tabBar().setUsesScrollButtons(True)
        onglets.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
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
                rang = onglets.addTab(
                    defilement, TITRES_ONGLETS.get(meta["groupe"], meta["groupe"])
                )
                onglets.setTabToolTip(rang, meta["groupe"])
                self._groupe_onglet[meta["groupe"]] = rang
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
            if champ.name == "intervalle_verification":
                self.estimation = etiquette("", "tertiaire", retour_ligne=True)
                disposition.addWidget(self.estimation)
                widget.valueChanged.connect(self._estimer)
            self._suivre(widget)
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
        annuler = composants.bouton(
            "Annuler les modifications",
            "erreur",
            aide="Revient aux réglages enregistrés",
        )
        annuler.clicked.connect(self.recharger)
        defaut = composants.bouton(
            "Valeurs par défaut",
            "redemarrer",
            aide="Remet les valeurs par défaut dans le formulaire (à enregistrer ensuite)",
        )
        defaut.clicked.connect(self.valeurs_par_defaut)
        self.bouton_enregistrer = enregistrer
        self.bouton_annuler = annuler
        self.bouton_defaut = defaut
        importer = composants.bouton("Importer…", "importer")
        importer.clicked.connect(self.importer)
        exporter = composants.bouton("Exporter…", "exporter")
        exporter.setToolTip("Les exports ne contiennent jamais le code npsso")
        exporter.clicked.connect(self.exporter)
        boutons = composants.RangeeAdaptative(
            enregistrer, annuler, defaut, importer, exporter
        )

        boutons_compte = []
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
                boutons_compte.append(bouton)
        compte = composants.RangeeAdaptative(*boutons_compte)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(12)
        disposition.addWidget(compte)
        disposition.addWidget(onglets, 1)
        disposition.addWidget(self.message)
        disposition.addWidget(boutons)
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
        for nom in self.champs:
            self._remplir_champ(nom, getattr(valeurs, nom))

    def _remplir_champ(self, nom: str, valeur: Any) -> None:
        widget = self.champs[nom]
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
        """Revient aux réglages enregistrés (toutes les modifications sont annulées)."""
        self._enregistres = self._actuels()
        self._chargement = True
        self.remplir(self._enregistres)
        self._chargement = False
        self.message.setText("")
        self.message.setObjectName("discret")
        self._mettre_a_jour()

    def synchroniser(self, nouveaux: Reglages) -> None:
        """Réglages changés ailleurs (page Demandes, moteur, thème) : seuls les champs
        que l'utilisateur n'est pas en train de modifier suivent ; ses modifications
        en cours ne sont jamais perdues."""
        anciens = getattr(self, "_enregistres", nouveaux)
        self._chargement = True
        for nom in self.champs:
            if nom in self._verrous:
                continue
            if self._egal(nom, self._valeur(nom), getattr(anciens, nom)):
                self._remplir_champ(nom, getattr(nouveaux, nom))
        self._chargement = False
        self._enregistres = nouveaux
        self._mettre_a_jour()

    def ouvrir_onglet(self, groupe: str) -> None:
        """Affiche un onglet par son groupe (« Demandes »…)."""
        if groupe in self._groupe_onglet:
            self.onglets.setCurrentIndex(self._groupe_onglet[groupe])

    # ─── Suivi des modifications ───

    @staticmethod
    def _egal(nom: str, a: Any, b: Any) -> bool:
        try:
            return reglages.normaliser(nom, a) == reglages.normaliser(nom, b)
        except TypeError, ValueError:
            return a == b

    def modifies(self) -> set[str]:
        """Les réglages changés dans le formulaire et pas encore enregistrés."""
        enregistres = getattr(self, "_enregistres", self._actuels())
        return {
            nom
            for nom in self.champs
            if nom not in APPARENCE
            and nom not in self._verrous
            and not self._egal(nom, self._valeur(nom), getattr(enregistres, nom))
        }

    def a_des_modifications(self) -> bool:
        return bool(self.modifies())

    def _suivre(self, widget: QWidget) -> None:
        for signal in ("toggled", "currentIndexChanged", "valueChanged", "textChanged"):
            if hasattr(widget, signal):
                getattr(widget, signal).connect(self._mettre_a_jour)
                return

    def _mettre_a_jour(self, *_: object) -> None:
        """Boutons et repères selon l'état réel des modifications."""
        if getattr(self, "_chargement", False) or not hasattr(
            self, "bouton_enregistrer"
        ):
            return
        modifies = self.modifies()
        self.bouton_enregistrer.setVisible(bool(modifies))
        self.bouton_annuler.setVisible(bool(modifies))
        defauts = Reglages()
        differe = any(
            not self._egal(nom, self._valeur(nom), getattr(defauts, nom))
            for nom in self.champs
            if nom not in APPARENCE and nom not in self._verrous
        )
        self.bouton_defaut.setVisible(differe)
        # Onglets marqués d'un point s'ils contiennent des modifications.
        groupes = {reglages.info(nom)["groupe"] for nom in modifies}
        for groupe, rang in self._groupe_onglet.items():
            titre = TITRES_ONGLETS.get(groupe, groupe)
            self.onglets.setTabText(rang, f"{titre} •" if groupe in groupes else titre)
        if modifies:
            self._afficher(
                "attention",
                f"{len(modifies)} réglage(s) modifié(s), pas encore enregistré(s) : "
                "Enregistrer pour les garder, ou Annuler les modifications.",
            )
        elif self.message.objectName() == "bandeau_attention":
            self.message.setText("")
        if hasattr(self, "estimation"):
            self._estimer()

    def _estimer(self, *_: object) -> None:
        secondes = max(1, int(self._valeur("intervalle_verification")))
        par_minute = 2 * 60 / secondes
        self.estimation.setText(
            f"Avec {secondes} s : environ {par_minute:.1f} requête(s) par minute quand il "
            "ne se passe rien (estimation, hors acceptations ; PSNAWP en autorise 20)."
        )

    def valeurs_par_defaut(self) -> None:
        """Valeurs par défaut dans le formulaire ; le thème et les animations
        (appliqués immédiatement) ne sont pas touchés."""
        enregistres = getattr(self, "_enregistres", self._actuels())
        defauts = replace(
            Reglages(), **{nom: getattr(enregistres, nom) for nom in APPARENCE}
        )
        for nom in self.champs:
            if nom not in APPARENCE and nom not in self._verrous:
                self._remplir_champ(nom, getattr(defauts, nom))
        self._mettre_a_jour()

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
        self._enregistres = nouveaux
        self._mettre_a_jour()
        if not resultat.effets:
            self._afficher("succes", "✔ Enregistré et appliqué immédiatement.")
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
        for nom in self.champs:
            if nom not in APPARENCE and nom not in self._verrous:
                self._remplir_champ(nom, getattr(lus, nom))
        # Thème et animations s'appliquent tout de suite, comme dans l'onglet Apparence.
        enregistres = getattr(self, "_enregistres", self._actuels())
        for nom in APPARENCE:
            if getattr(lus, nom) != getattr(enregistres, nom):
                self._apparence(nom, getattr(lus, nom))
        self._mettre_a_jour()
        if not self.a_des_modifications():
            texte = "Ces réglages sont déjà ceux en place : rien à enregistrer."
        else:
            texte = (
                "Réglages importés dans le formulaire : vérifiez-les puis enregistrez."
            )
        if problemes:
            texte += " Problèmes : " + " ".join(problemes)
        self._afficher("attention" if problemes else "info", texte)

    def exporter(self) -> None:
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Exporter les réglages", "reglages-psn-amis.toml", "Réglages (*.toml)"
        )
        if chemin:
            try:
                reglages.exporter(self._actuels(), Path(chemin))
            except OSError as erreur:
                self._afficher(
                    "erreur", f"Export impossible : {erreur.strerror or erreur}"
                )
            else:
                self._afficher(
                    "succes", f"✔ Réglages exportés dans {Path(chemin).name}."
                )
