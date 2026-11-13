"""Composants visuels communs de PSN Amis (un seul endroit pour l'apparence).

Les couleurs viennent toutes du thème courant (theme.py) ; les animations passent par
`Animations`, qui les coupe si l'utilisateur ou Windows le demande. Aucune animation
ne tourne en permanence : elles ne durent que le temps d'une transition.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from psn_amis import systeme
from psn_amis.ui import icones
from psn_amis.ui.theme import Palette, palette

# ─── Animations ───────────────────────────────────────────────────────────────


class Animations:
    """Réglage global : animations actives ou non (réglage + préférence Windows)."""

    _actives = True
    # Durées en millisecondes : courtes, pour rester réactif.
    RAPIDE = 120
    NORMALE = 180

    @classmethod
    def definir(cls, mode: str) -> None:
        if mode == "coupees":
            cls._actives = False
        elif mode == "activees":
            cls._actives = True
        else:
            cls._actives = systeme.animations_windows()

    @classmethod
    def actives(cls) -> bool:
        return cls._actives


def fondu_entrant(widget: QWidget, duree: int = Animations.NORMALE) -> None:
    """Fait apparaître un widget en fondu (instantané si les animations sont coupées).

    L'effet est retiré à la fin : rien ne reste actif, et les widgets enfants
    retrouvent un rendu normal.
    """
    if not Animations.actives():
        widget.setGraphicsEffect(None)
        return
    effet = QGraphicsOpacityEffect(widget)
    effet.setOpacity(0.0)
    widget.setGraphicsEffect(effet)
    animation = QPropertyAnimation(effet, b"opacity", widget)
    animation.setDuration(duree)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


class Pages(QStackedWidget):
    """Pile de pages avec une transition douce (fondu et léger glissement)."""

    def afficher(self, rang: int) -> None:
        if rang == self.currentIndex():
            return
        self.setCurrentIndex(rang)
        page = self.currentWidget()
        if page is None or not Animations.actives():
            return
        fondu_entrant(page, Animations.NORMALE)
        depart = page.pos()
        glissement = QPropertyAnimation(page, b"pos", page)
        glissement.setDuration(Animations.NORMALE)
        glissement.setStartValue(depart + QPoint(0, 10))
        glissement.setEndValue(depart)
        glissement.setEasingCurve(QEasingCurve.Type.OutCubic)
        glissement.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


# ─── Textes ───────────────────────────────────────────────────────────────────


def etiquette(texte: str = "", nom: str = "", retour_ligne: bool = False) -> QLabel:
    label = QLabel(texte)
    if nom:
        label.setObjectName(nom)
    label.setWordWrap(retour_ligne)
    return label


def changer_texte(label: QLabel, texte: str) -> None:
    """Ne redessine que si le texte change (pas de rafraîchissement inutile)."""
    if label.text() != texte:
        label.setText(texte)


# ─── Boutons ──────────────────────────────────────────────────────────────────


def bouton(
    texte: str,
    icone_nom: str = "",
    genre: str = "",
    aide: str = "",
    action: Callable[[], object] | None = None,
) -> QPushButton:
    """Bouton harmonisé : genre « principal », « danger », « secondaire_danger »,
    « plat » ou normal ; icône facultative, recolorée selon le thème."""
    b = QPushButton(texte)
    if genre:
        b.setObjectName(genre)
    if icone_nom:
        b.setProperty("icone", icone_nom)
        b.setIconSize(QSize(16, 16))
    if aide:
        b.setToolTip(aide)
    if action is not None:
        b.clicked.connect(action)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    colorer_icone(b, palette_courante())
    return b


def colorer_icone(b: QAbstractButton, p: Palette) -> None:
    nom = b.property("icone")
    if not nom:
        return
    genre = b.objectName()
    couleur = {
        "principal": p.sur_accent,
        "danger": p.fond,
        "secondaire_danger": p.erreur,
        "nav": p.discret,
    }.get(genre, p.texte)
    b.setIcon(icones.icone(str(nom), couleur, 18, desactivee=p.tertiaire))


_THEME_COURANT = ["graphite"]


def palette_courante() -> Palette:
    return palette(_THEME_COURANT[0])


def changer_theme_courant(nom: str) -> None:
    _THEME_COURANT[0] = nom


def recolorer(racine: QWidget) -> None:
    """Après un changement de thème : icônes et éléments peints à la main."""
    p = palette_courante()
    for b in racine.findChildren(QAbstractButton):
        colorer_icone(b, p)
    for element in racine.findChildren(QWidget):
        rafraichir = getattr(element, "changer_palette", None)
        if callable(rafraichir) and element is not racine:
            rafraichir(p)


# ─── Interrupteur ─────────────────────────────────────────────────────────────


class Interrupteur(QCheckBox):
    """Interrupteur moderne (même interface qu'une case à cocher : isChecked, toggled).

    Clavier : Espace pour basculer ; focus visible ; texte à droite.
    """

    LARGEUR = 40
    HAUTEUR = 22

    def __init__(self, texte: str = "", parent: QWidget | None = None) -> None:
        super().__init__(texte, parent)
        self._position = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(Animations.RAPIDE)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animer)

    def _lire_position(self) -> float:
        return self._position

    def _ecrire_position(self, valeur: float) -> None:
        self._position = valeur
        self.update()

    position = Property(float, _lire_position, _ecrire_position)

    def setChecked(self, coche: bool) -> None:
        super().setChecked(coche)
        # Positionné tout de suite quand le changement vient du programme.
        self._animation.stop()
        self._ecrire_position(1.0 if coche else 0.0)

    def _animer(self, coche: bool) -> None:
        fin = 1.0 if coche else 0.0
        if not Animations.actives() or not self.isVisible():
            self._ecrire_position(fin)
            return
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(fin)
        self._animation.start()

    def sizeHint(self) -> QSize:
        largeur_texte = self.fontMetrics().horizontalAdvance(self.text())
        espace = 10 if self.text() else 0
        hauteur = max(self.HAUTEUR + 6, self.fontMetrics().height() + 6)
        return QSize(self.LARGEUR + espace + largeur_texte + 6, hauteur)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, point) -> bool:
        return self.rect().contains(point)

    def paintEvent(self, evenement) -> None:
        p = palette_courante()
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - self.HAUTEUR) / 2
        piste = QRectF(1, y, self.LARGEUR, self.HAUTEUR)
        actif = self.isEnabled()
        fond_off = QColor(p.surface_active)
        fond_on = QColor(p.accent if actif else p.bordure_forte)
        t = self._position
        couleur = QColor(
            round(fond_off.red() + (fond_on.red() - fond_off.red()) * t),
            round(fond_off.green() + (fond_on.green() - fond_off.green()) * t),
            round(fond_off.blue() + (fond_on.blue() - fond_off.blue()) * t),
        )
        peintre.setPen(QPen(QColor(p.bordure_forte if t < 0.5 else p.accent), 1))
        peintre.setBrush(couleur)
        peintre.drawRoundedRect(piste, self.HAUTEUR / 2, self.HAUTEUR / 2)
        diametre = self.HAUTEUR - 6
        x = piste.left() + 3 + (self.LARGEUR - diametre - 6) * t
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(QColor(p.sur_accent if t > 0.5 else p.discret))
        if not actif:
            peintre.setBrush(QColor(p.tertiaire))
        peintre.drawEllipse(QRectF(x, y + 3, diametre, diametre))
        if self.hasFocus():
            peintre.setPen(QPen(QColor(p.accent), 2))
            peintre.setBrush(Qt.BrushStyle.NoBrush)
            peintre.drawRoundedRect(piste.adjusted(-2, -2, 2, 2), 13, 13)
        if self.text():
            peintre.setPen(QColor(p.texte if actif else p.tertiaire))
            zone = QRect(
                self.LARGEUR + 12, 0, self.width() - self.LARGEUR - 12, self.height()
            )
            peintre.drawText(
                zone,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self.text(),
            )
        peintre.end()


# ─── Cartes, pastilles, bandeaux ──────────────────────────────────────────────


class Carte(QFrame):
    """Panneau arrondi avec un titre discret (et une icône) en haut."""

    def __init__(
        self,
        titre: str = "",
        icone_nom: str = "",
        parent: QWidget | None = None,
        accent: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("carte_accent" if accent else "carte")
        self.contenu = QVBoxLayout(self)
        self.contenu.setContentsMargins(18, 14, 18, 16)
        self.contenu.setSpacing(6)
        self._icone_nom = icone_nom
        self._icone = QLabel()
        self._titre = etiquette(titre, "etiquette_carte")
        if titre:
            ligne = QHBoxLayout()
            ligne.setSpacing(8)
            if icone_nom:
                ligne.addWidget(self._icone)
            ligne.addWidget(self._titre, 1)
            self.entete = ligne
            self.contenu.addLayout(ligne)
        self.changer_palette(palette_courante())

    def changer_palette(self, p: Palette) -> None:
        if self._icone_nom:
            self._icone.setPixmap(icones.pixmap(self._icone_nom, p.discret, 16))

    def ajouter(self, *widgets: QWidget) -> Carte:
        for widget in widgets:
            self.contenu.addWidget(widget)
        return self


class Statistique(Carte):
    """Carte « chiffre clé » : titre, grand nombre, détail."""

    def __init__(
        self, titre: str, icone_nom: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(titre, icone_nom, parent)
        self.valeur = etiquette("—", "grand")
        self.detail = etiquette("", "tertiaire", retour_ligne=True)
        self.contenu.addWidget(self.valeur)
        self.contenu.addWidget(self.detail)
        self.contenu.addStretch(1)

    def afficher(self, valeur: str, detail: str = "") -> None:
        changer_texte(self.valeur, valeur)
        changer_texte(self.detail, detail)


class Pastille(QLabel):
    """Indicateur d'état : point de couleur + texte (jamais la couleur seule)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cle = "discret"
        self._texte = ""
        self.setTextFormat(Qt.TextFormat.RichText)

    def afficher(self, texte: str, cle: str) -> None:
        if (texte, cle) == (self._texte, self._cle):
            return
        self._texte, self._cle = texte, cle
        self._dessiner(palette_courante())

    def changer_palette(self, p: Palette) -> None:
        self._dessiner(p)

    def _dessiner(self, p: Palette) -> None:
        couleur = getattr(p, self._cle, p.discret)
        self.setStyleSheet(
            f"background: {p.doux(couleur)}; border: 1px solid {couleur};"
            "border-radius: 11px; padding: 3px 10px; font-weight: 600;"
        )
        self.setText(
            f'<span style="color:{couleur}">●</span>&nbsp;'
            f'<span style="color:{p.texte}">{self._texte}</span>'
        )


class Bandeau(QFrame):
    """Message d'information, d'avertissement, d'erreur ou de réussite, avec icône."""

    ICONES: ClassVar[dict[str, str]] = {
        "info": "info",
        "attention": "alerte",
        "erreur": "erreur",
        "succes": "succes",
    }

    def __init__(self, niveau: str, texte: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.niveau = niveau
        self.setObjectName(f"bandeau_{niveau}")
        # Toujours à la hauteur de son texte, jamais étiré.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(12, 9, 12, 9)
        disposition.setSpacing(10)
        self._icone = QLabel()
        self._icone.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.texte = etiquette(texte, retour_ligne=True)
        self.texte.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        disposition.addWidget(self._icone)
        disposition.addWidget(self.texte, 1)
        self.actions = QHBoxLayout()
        disposition.addLayout(self.actions)
        self.changer_palette(palette_courante())

    def changer_palette(self, p: Palette) -> None:
        couleur = getattr(p, self.niveau, p.info)
        self._icone.setPixmap(
            icones.pixmap(self.ICONES.get(self.niveau, "info"), couleur, 18)
        )

    def ajouter_action(self, b: QPushButton) -> Bandeau:
        self.actions.addWidget(b)
        return self


class EtatVide(QFrame):
    """Écran « rien à afficher » qui explique quoi faire, avec une action éventuelle."""

    def __init__(
        self,
        icone_nom: str,
        titre: str,
        texte: str,
        action: QPushButton | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("etat_vide")
        self._icone_nom = icone_nom
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(24, 28, 24, 28)
        disposition.setSpacing(8)
        disposition.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icone = QLabel()
        self._icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.titre = etiquette(titre, "titre_vide")
        self.titre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.texte = etiquette(texte, "discret", retour_ligne=True)
        self.texte.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.texte.setMaximumWidth(460)
        disposition.addWidget(self._icone)
        disposition.addWidget(self.titre)
        disposition.addWidget(self.texte, 0, Qt.AlignmentFlag.AlignHCenter)
        if action is not None:
            disposition.addSpacing(6)
            disposition.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)
        self.changer_palette(palette_courante())

    def changer_palette(self, p: Palette) -> None:
        self._icone.setPixmap(icones.pixmap(self._icone_nom, p.tertiaire, 40))


class Chargement(QWidget):
    """Indicateur d'activité discret ; ne tourne que tant qu'il est visible."""

    def __init__(self, cote: int = 18, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(cote, cote)
        self._angle = 0
        self._minuterie = QTimer(self)
        self._minuterie.setInterval(40)
        self._minuterie.timeout.connect(self._tourner)
        self.setToolTip("En cours…")

    def _tourner(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def showEvent(self, evenement) -> None:
        if Animations.actives():
            self._minuterie.start()
        super().showEvent(evenement)

    def hideEvent(self, evenement) -> None:
        self._minuterie.stop()
        super().hideEvent(evenement)

    def paintEvent(self, evenement) -> None:
        p = palette_courante()
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        zone = QRectF(2, 2, self.width() - 4, self.height() - 4)
        peintre.setPen(QPen(QColor(p.bordure_forte), 2.2))
        peintre.drawEllipse(zone)
        stylo = QPen(QColor(p.accent), 2.2)
        stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
        peintre.setPen(stylo)
        peintre.drawArc(zone, -self._angle * 16, 100 * 16)
        peintre.end()


# ─── Notifications temporaires ────────────────────────────────────────────────


class Toast(QFrame):
    """Notification temporaire en bas à droite de la fenêtre, qui disparaît seule."""

    ferme = Signal()

    def __init__(self, parent: QWidget, niveau: str, titre: str, texte: str) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.niveau = niveau
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(14, 12, 10, 12)
        disposition.setSpacing(10)
        p = palette_courante()
        icone = QLabel()
        couleur = getattr(p, niveau, p.info)
        icone.setPixmap(icones.pixmap(Bandeau.ICONES.get(niveau, "info"), couleur, 20))
        icone.setAlignment(Qt.AlignmentFlag.AlignTop)
        textes = QVBoxLayout()
        textes.setSpacing(2)
        self.titre = etiquette(titre, "toast_titre")
        self.texte = etiquette(texte, "discret", retour_ligne=True)
        textes.addWidget(self.titre)
        if texte:
            textes.addWidget(self.texte)
        fermer = QPushButton("✕")
        fermer.setObjectName("plat")
        fermer.setFixedSize(26, 26)
        fermer.setToolTip("Fermer")
        fermer.setAccessibleName("Fermer la notification")
        fermer.clicked.connect(self.fermer)
        disposition.addWidget(icone)
        disposition.addLayout(textes, 1)
        disposition.addWidget(fermer, 0, Qt.AlignmentFlag.AlignTop)
        self.setFixedWidth(360)
        ombre = QGraphicsDropShadowEffect(self)
        ombre.setBlurRadius(28)
        ombre.setOffset(0, 6)
        ombre.setColor(QColor(0, 0, 0, 90 if p.sombre else 40))
        self.setGraphicsEffect(ombre)
        self._delai = QTimer(self)
        self._delai.setSingleShot(True)
        self._delai.timeout.connect(self.fermer)

    def montrer(self, duree_ms: int) -> None:
        self.adjustSize()
        self.show()
        self.raise_()
        self._delai.start(duree_ms)

    def fermer(self) -> None:
        self._delai.stop()
        self.hide()
        self.ferme.emit()
        self.deleteLater()


class Notifications(QWidget):
    """Empile les notifications temporaires dans un coin de la fenêtre."""

    MARGE = 18
    MAXIMUM = 3

    def __init__(self, hote: QWidget) -> None:
        super().__init__(hote)
        self._hote = hote
        self._toasts: list[Toast] = []
        self.hide()

    def afficher(
        self, niveau: str, titre: str, texte: str = "", duree_ms: int = 4500
    ) -> Toast:
        toast = Toast(self._hote, niveau, titre, texte)
        toast.ferme.connect(lambda t=toast: self._retirer(t))
        self._toasts.append(toast)
        while len(self._toasts) > self.MAXIMUM:
            self._toasts[0].fermer()
        toast.montrer(duree_ms)
        self.replacer()
        if Animations.actives():
            # Glissement depuis la droite (l'ombre de la notification est gardée).
            arrivee = toast.pos()
            glissement = QPropertyAnimation(toast, b"pos", toast)
            glissement.setDuration(Animations.NORMALE)
            glissement.setStartValue(arrivee + QPoint(24, 0))
            glissement.setEndValue(arrivee)
            glissement.setEasingCurve(QEasingCurve.Type.OutCubic)
            glissement.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        return toast

    def _retirer(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self.replacer()

    def replacer(self) -> None:
        y = self._hote.height() - self.MARGE
        for toast in reversed(self._toasts):
            toast.adjustSize()
            y -= toast.height()
            toast.move(self._hote.width() - toast.width() - self.MARGE, y)
            y -= 10

    def actives(self) -> list[Toast]:
        return list(self._toasts)


# ─── Divers ───────────────────────────────────────────────────────────────────


def ligne(*widgets: QWidget, espace: int = 8, etirer: bool = True) -> QHBoxLayout:
    disposition = QHBoxLayout()
    disposition.setSpacing(espace)
    for widget in widgets:
        disposition.addWidget(widget)
    if etirer:
        disposition.addStretch(1)
    return disposition


def separateur() -> QFrame:
    trait = QFrame()
    trait.setFrameShape(QFrame.Shape.HLine)
    trait.setStyleSheet(
        "color: transparent; border: none; min-height: 1px; max-height: 1px;"
    )
    trait.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return trait


def police_titre(taille: float, graisse: QFont.Weight = QFont.Weight.Bold) -> QFont:
    font = QFont()
    font.setPointSizeF(taille)
    font.setWeight(graisse)
    return font


def dessin_arrondi(rect: QRectF, rayon: float) -> QPainterPath:
    chemin = QPainterPath()
    chemin.addRoundedRect(rect, rayon, rayon)
    return chemin


class RangeeAdaptative(QWidget):
    """Rangée de boutons qui passe à la ligne quand la fenêtre est étroite : aucun
    bouton n'est jamais tronqué ni caché."""

    def __init__(self, *boutons: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QGridLayout

        self._boutons = list(boutons)
        self._grille = QGridLayout(self)
        self._grille.setContentsMargins(0, 0, 0, 0)
        self._grille.setHorizontalSpacing(8)
        self._grille.setVerticalSpacing(8)
        self._colonnes = 0
        self._placer(len(self._boutons))

    def _placer(self, colonnes: int) -> None:
        if colonnes == self._colonnes:
            return
        self._colonnes = colonnes
        for bouton in self._boutons:
            self._grille.removeWidget(bouton)
        for rang, bouton in enumerate(self._boutons):
            self._grille.addWidget(bouton, rang // colonnes, rang % colonnes)
        for colonne in range(len(self._boutons) + 1):
            self._grille.setColumnStretch(colonne, 0)
        self._grille.setColumnStretch(colonnes, 1)

    def resizeEvent(self, evenement) -> None:
        super().resizeEvent(evenement)
        largeur = self.width()
        largeurs = [
            max(b.minimumSizeHint().width(), b.sizeHint().width())
            for b in self._boutons
        ]
        colonnes = len(self._boutons)
        while colonnes > 1:
            # Chaque colonne prend la largeur de son bouton le plus large.
            besoin = sum(
                max(largeurs[colonne::colonnes]) for colonne in range(colonnes)
            ) + 8 * (colonnes - 1)
            if besoin <= largeur:
                break
            colonnes -= 1
        self._placer(colonnes)

    def minimumSizeHint(self) -> QSize:
        plus_large = max(
            (
                max(b.minimumSizeHint().width(), b.sizeHint().width())
                for b in self._boutons
            ),
            default=0,
        )
        return QSize(plus_large, super().minimumSizeHint().height())


# ─── Dialogues au thème de l'application ──────────────────────────────────────


class Dialogue(QDialog):
    """Fenêtre de message ou de confirmation, au thème de PSN Amis (titre, icône,
    texte, boutons). Échap annule ; pour une action destructrice, le bouton par
    défaut est « Annuler »."""

    def __init__(
        self,
        parent: QWidget | None,
        titre: str,
        texte: str,
        niveau: str = "info",
        bouton: str = "OK",
        annuler: str | None = None,
        danger: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PSN Amis")
        self.setMinimumWidth(420)
        self.setMaximumWidth(620)
        p = palette_courante()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(24, 22, 24, 18)
        disposition.setSpacing(12)
        entete = QHBoxLayout()
        entete.setSpacing(12)
        icone = QLabel()
        couleur = getattr(p, niveau, p.info)
        icone.setPixmap(icones.pixmap(Bandeau.ICONES.get(niveau, "info"), couleur, 28))
        icone.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.titre = etiquette(titre, "titre_vide", retour_ligne=True)
        entete.addWidget(icone)
        entete.addWidget(self.titre, 1)
        disposition.addLayout(entete)
        self.texte = etiquette(texte, "discret", retour_ligne=True)
        self.texte.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        disposition.addWidget(self.texte)
        disposition.addSpacing(4)
        boutons = QHBoxLayout()
        boutons.addStretch(1)
        self.bouton_annuler: QPushButton | None = None
        if annuler is not None:
            self.bouton_annuler = QPushButton(annuler)
            self.bouton_annuler.clicked.connect(self.reject)
            boutons.addWidget(self.bouton_annuler)
        self.bouton_ok = QPushButton(bouton)
        self.bouton_ok.setObjectName("danger" if danger else "principal")
        self.bouton_ok.clicked.connect(self.accept)
        boutons.addWidget(self.bouton_ok)
        disposition.addLayout(boutons)
        # Action destructrice : Entrée ne la déclenche pas par accident.
        defaut = (
            self.bouton_annuler if danger and self.bouton_annuler else self.bouton_ok
        )
        defaut.setDefault(True)
        defaut.setFocus()


def informer(
    parent: QWidget | None, titre: str, texte: str, niveau: str = "info"
) -> None:
    Dialogue(parent, titre, texte, niveau).exec()


def confirmer(
    parent: QWidget | None,
    titre: str,
    texte: str,
    bouton: str = "Continuer",
    danger: bool = False,
) -> bool:
    """Demande une confirmation ; True seulement si l'utilisateur valide."""
    dialogue = Dialogue(
        parent,
        titre,
        texte,
        "attention" if danger else "info",
        bouton,
        "Annuler",
        danger,
    )
    return dialogue.exec() == QDialog.DialogCode.Accepted
