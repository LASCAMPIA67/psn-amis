"""Thèmes de PSN Amis : jetons de couleur centralisés, palette Qt et feuille de style.

Toute l'apparence part d'ici : chaque thème est un jeu complet de jetons (fonds,
surfaces, bordures, textes, accent, états), traduit en une palette Qt (pour les
menus, dialogues et contrôles standard) et en une feuille de style (pour les
composants de PSN Amis). Le style Qt « Fusion » est utilisé partout : il respecte
fidèlement la palette et la feuille de style, ce que le style natif ne garantit pas.

Chaque information portée par une couleur l'est aussi par un symbole, une icône ou un
texte (statut, niveau d'un événement, protection) : rien ne dépend de la seule couleur.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette


@dataclass(frozen=True)
class Palette:
    nom: str
    description: str
    sombre: bool
    fond: str
    fond_lateral: str
    surface: str
    surface_haute: str
    surface_active: str
    bordure: str
    bordure_forte: str
    texte: str
    discret: str
    tertiaire: str
    accent: str
    accent_survol: str
    accent_presse: str
    sur_accent: str
    succes: str
    attention: str
    erreur: str
    info: str

    @property
    def selection(self) -> str:
        return teinte(self.accent, 0.28 if self.sombre else 0.16)

    @property
    def accent_doux(self) -> str:
        return teinte(self.accent, 0.16 if self.sombre else 0.10)

    def doux(self, couleur: str) -> str:
        """Fond discret d'une couleur d'état (pastilles, bandeaux)."""
        return teinte(couleur, 0.14 if self.sombre else 0.10)

    # Noms gardés pour les modules qui les utilisaient déjà.
    @property
    def texte_discret(self) -> str:
        return self.discret


def teinte(couleur: str, opacite: float) -> str:
    """La couleur avec une opacité, au format rgba() des feuilles de style Qt."""
    c = QColor(couleur)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {round(opacite * 255)})"


PALETTES: dict[str, Palette] = {
    "graphite": Palette(
        nom="Graphite Premium",
        description="Sombre et sobre, gris profonds et touches champagne.",
        sombre=True,
        fond="#111214",
        fond_lateral="#0b0c0e",
        surface="#18191c",
        surface_haute="#202227",
        surface_active="#2a2d33",
        bordure="#26282d",
        bordure_forte="#3a3d44",
        texte="#ececee",
        discret="#a3a6ad",
        tertiaire="#7d818a",
        accent="#d9b26f",
        accent_survol="#e6c487",
        accent_presse="#c39a55",
        sur_accent="#1a1408",
        succes="#4cc38a",
        attention="#e7b24a",
        erreur="#f0716b",
        info="#6fb3f2",
    ),
    "minuit": Palette(
        nom="Bleu Minuit",
        description="Bleu nuit profond et accents bleu vif.",
        sombre=True,
        fond="#0a1020",
        fond_lateral="#070c18",
        surface="#111a2e",
        surface_haute="#18233c",
        surface_active="#20304f",
        bordure="#1e2a44",
        bordure_forte="#2c3d60",
        texte="#e7eefb",
        discret="#9fb0cf",
        tertiaire="#7a8cae",
        accent="#5b97ff",
        accent_survol="#78a9ff",
        accent_presse="#3d7ff0",
        sur_accent="#06102a",
        succes="#3dd68c",
        attention="#f5b94d",
        erreur="#ff6b7a",
        info="#5cc8ff",
    ),
    "emeraude": Palette(
        nom="Émeraude",
        description="Vert sombre apaisant et accents émeraude.",
        sombre=True,
        fond="#0b1412",
        fond_lateral="#08100e",
        surface="#111d1a",
        surface_haute="#172723",
        surface_active="#1f332d",
        bordure="#1c2c27",
        bordure_forte="#2a4039",
        texte="#e6f2ee",
        discret="#9db9af",
        tertiaire="#76968b",
        accent="#2fcb8f",
        accent_survol="#4fdca4",
        accent_presse="#22ad78",
        sur_accent="#04140d",
        succes="#7ad67e",
        attention="#f2c14e",
        erreur="#ff7b72",
        info="#58b4f0",
    ),
    "amethyste": Palette(
        nom="Améthyste",
        description="Violet nuit raffiné et accents lavande.",
        sombre=True,
        fond="#110e19",
        fond_lateral="#0c0a12",
        surface="#191523",
        surface_haute="#221c2f",
        surface_active="#2d253e",
        bordure="#261f35",
        bordure_forte="#3a3050",
        texte="#eee9f7",
        discret="#b0a6c6",
        tertiaire="#8a80a2",
        accent="#a78bfa",
        accent_survol="#bba3ff",
        accent_presse="#8f70f0",
        sur_accent="#140c24",
        succes="#4ade9a",
        attention="#f5c15a",
        erreur="#ff7a90",
        info="#7cc4ff",
    ),
    "clair": Palette(
        nom="Clair Élégant",
        description="Lumineux et professionnel, accents bleu franc.",
        sombre=False,
        fond="#f4f5f8",
        fond_lateral="#eaedf2",
        surface="#ffffff",
        surface_haute="#f1f3f6",
        surface_active="#e4e8ef",
        bordure="#e1e4ea",
        bordure_forte="#c6ccd6",
        texte="#161a22",
        discret="#4f5765",
        tertiaire="#6b7380",
        accent="#2459d6",
        accent_survol="#3369e6",
        accent_presse="#1c47ad",
        sur_accent="#ffffff",
        succes="#13703a",
        attention="#8a5300",
        erreur="#b42318",
        info="#0b5f96",
    ),
    "daltonien": Palette(
        nom="Contraste daltonien",
        description="Sombre, bleu, jaune et orange : faciles à distinguer sans rouge ni vert.",
        sombre=True,
        fond="#0b1220",
        fond_lateral="#080d18",
        surface="#121b2e",
        surface_haute="#1a2540",
        surface_active="#23305a",
        bordure="#26324d",
        bordure_forte="#3a4a6e",
        texte="#f2f5fb",
        discret="#aab5cc",
        tertiaire="#8794ae",
        accent="#ffd84d",
        accent_survol="#ffe27a",
        accent_presse="#f0c630",
        sur_accent="#1a1400",
        succes="#4da3ff",
        attention="#ffd84d",
        erreur="#ff9a3d",
        info="#b8c4ff",
    ),
}

# Ordre d'affichage dans les paramètres ; « systeme » suit Windows.
ORDRE = ("graphite", "minuit", "emeraude", "amethyste", "clair", "daltonien", "systeme")
NOMS = {cle: p.nom for cle, p in PALETTES.items()} | {"systeme": "Système"}
DESCRIPTIONS = {cle: p.description for cle, p in PALETTES.items()} | {
    "systeme": "Suit le mode clair ou sombre de Windows (Graphite ou Clair Élégant)."
}


def windows_en_sombre() -> bool:
    """Le mode d'affichage de Windows, tel que Qt le connaît (sombre par défaut)."""
    from PySide6.QtCore import Qt

    application = QGuiApplication.instance()
    if application is None:
        return True
    schema = application.styleHints().colorScheme()
    return schema != Qt.ColorScheme.Light


def resoudre(nom: str) -> str:
    """Le thème réellement utilisé (« systeme » devient graphite ou clair)."""
    if nom == "systeme":
        return "graphite" if windows_en_sombre() else "clair"
    return nom if nom in PALETTES else "graphite"


def palette(nom: str) -> Palette:
    return PALETTES[resoudre(nom)]


def palette_qt(p: Palette) -> QPalette:
    """Palette Qt du thème : menus, dialogues et contrôles standard suivent le thème."""
    qp = QPalette()
    roles = {
        QPalette.ColorRole.Window: p.fond,
        QPalette.ColorRole.WindowText: p.texte,
        QPalette.ColorRole.Base: p.surface,
        QPalette.ColorRole.AlternateBase: p.surface_haute,
        QPalette.ColorRole.ToolTipBase: p.surface_haute,
        QPalette.ColorRole.ToolTipText: p.texte,
        QPalette.ColorRole.PlaceholderText: p.tertiaire,
        QPalette.ColorRole.Text: p.texte,
        QPalette.ColorRole.Button: p.surface_haute,
        QPalette.ColorRole.ButtonText: p.texte,
        QPalette.ColorRole.BrightText: p.erreur,
        QPalette.ColorRole.Highlight: p.accent,
        QPalette.ColorRole.HighlightedText: p.sur_accent,
        QPalette.ColorRole.Link: p.accent,
        QPalette.ColorRole.LinkVisited: p.accent_presse,
        QPalette.ColorRole.Light: p.bordure_forte,
        QPalette.ColorRole.Midlight: p.bordure,
        QPalette.ColorRole.Mid: p.bordure,
        QPalette.ColorRole.Dark: p.fond_lateral,
        QPalette.ColorRole.Shadow: "#000000",
    }
    for role, couleur in roles.items():
        qp.setColor(role, QColor(couleur))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        qp.setColor(QPalette.ColorGroup.Disabled, role, QColor(p.tertiaire))
    return qp


def police() -> QFont:
    """Segoe UI Variable (Windows 11), sinon Segoe UI : polices du système, rien à
    embarquer ni à redistribuer."""
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Arial", "sans-serif"])
    font.setPointSizeF(10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def appliquer(application, nom: str) -> Palette:
    """Applique un thème à toute l'application (immédiat, sans redémarrage)."""
    p = palette(nom)
    application.setStyle("Fusion")
    application.setFont(police())
    application.setPalette(palette_qt(p))
    application.setStyleSheet(feuille_de_style(nom))
    return p


def jetons(p: Palette) -> dict[str, str]:
    return {champ.name: getattr(p, champ.name) for champ in fields(p)} | {
        "selection": p.selection,
        "accent_doux": p.accent_doux,
    }


def feuille_de_style(nom: str) -> str:
    p = palette(nom)
    s = jetons(p)
    return """
* { outline: none; }
QWidget { background: transparent; color: %(texte)s; font-size: 10pt; }
QMainWindow, QDialog, QWizard, QMessageBox { background: %(fond)s; }
QWidget#page, QWidget#centre, QStackedWidget, QScrollArea > QWidget > QWidget {
    background: %(fond)s; }
QToolTip { background: %(surface_active)s; color: %(texte)s;
    border: 1px solid %(bordure_forte)s; border-radius: 6px; padding: 6px 8px; }

/* ─── Navigation latérale ─── */
QFrame#laterale { background: %(fond_lateral)s; border: none;
    border-right: 1px solid %(bordure)s; }
QLabel#marque { font-size: 13pt; font-weight: 700; }
QLabel#marque_sous { color: %(tertiaire)s; font-size: 8.5pt; }
QPushButton#nav { text-align: left; padding: 9px 12px; border-radius: 10px;
    border: 1px solid transparent; background: transparent; color: %(discret)s;
    font-weight: 600; }
QPushButton#nav:hover { background: %(surface_haute)s; color: %(texte)s; }
QPushButton#nav:checked { background: %(accent_doux)s; color: %(texte)s;
    border: 1px solid %(selection)s; }
QPushButton#nav:focus { border: 1px solid %(accent)s; }
QLabel#section_nav { color: %(tertiaire)s; font-size: 8pt; font-weight: 700;
    letter-spacing: 1px; padding: 10px 14px 4px 14px; }
QFrame#pied_nav { background: %(surface)s; border: 1px solid %(bordure)s;
    border-radius: 12px; }

/* ─── En-tête de page ─── */
QFrame#entete { background: %(fond)s; border: none;
    border-bottom: 1px solid %(bordure)s; }
QLabel#titre_page { font-size: 17pt; font-weight: 700; }
QLabel#sous_titre_page { color: %(discret)s; }
QLabel#titre { font-size: 15pt; font-weight: 700; }
QLabel#grand { font-size: 22pt; font-weight: 700; }
QLabel#tres_grand { font-size: 26pt; font-weight: 800; }
QLabel#discret, QLabel#description { color: %(discret)s; }
QLabel#tertiaire { color: %(tertiaire)s; font-size: 9pt; }
QLabel#etiquette_carte { color: %(discret)s; font-size: 9pt; font-weight: 600; }

/* ─── Cartes et panneaux ─── */
QFrame#carte, QGroupBox { background: %(surface)s; border: 1px solid %(bordure)s;
    border-radius: 14px; }
QFrame#carte:hover { border-color: %(bordure_forte)s; }
QFrame#carte_accent { background: %(surface)s; border: 1px solid %(selection)s;
    border-radius: 14px; }
QGroupBox { margin-top: 18px; padding: 14px 12px 12px 12px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px;
    color: %(texte)s; }
QFrame#etat_vide { background: %(surface)s; border: 1px dashed %(bordure_forte)s;
    border-radius: 14px; }
QLabel#titre_vide { font-size: 12pt; font-weight: 700; }

/* ─── Bandeaux ─── */
QFrame#bandeau_info, QFrame#bandeau_attention, QFrame#bandeau_erreur,
QFrame#bandeau_succes { border-radius: 12px; }
QFrame#bandeau_info { background: %(info_doux)s; border: 1px solid %(info)s; }
QFrame#bandeau_attention { background: %(attention_doux)s; border: 1px solid %(attention)s; }
QFrame#bandeau_erreur { background: %(erreur_doux)s; border: 1px solid %(erreur)s; }
QFrame#bandeau_succes { background: %(succes_doux)s; border: 1px solid %(succes)s; }
QLabel#bandeau_info, QLabel#bandeau_attention, QLabel#bandeau_erreur,
QLabel#bandeau_succes { border-radius: 10px; padding: 9px 12px; }
QLabel#bandeau_info { background: %(info_doux)s; color: %(texte)s;
    border: 1px solid %(info)s; }
QLabel#bandeau_attention { background: %(attention_doux)s; color: %(texte)s;
    border: 1px solid %(attention)s; }
QLabel#bandeau_erreur { background: %(erreur_doux)s; color: %(texte)s;
    border: 1px solid %(erreur)s; }
QLabel#bandeau_succes { background: %(succes_doux)s; color: %(texte)s;
    border: 1px solid %(succes)s; }

/* ─── Boutons ─── */
QPushButton, QToolButton { background: %(surface_haute)s; color: %(texte)s;
    border: 1px solid %(bordure_forte)s; border-radius: 9px; padding: 7px 14px;
    font-weight: 600; min-height: 18px; }
QPushButton:hover, QToolButton:hover { background: %(surface_active)s;
    border-color: %(tertiaire)s; }
QPushButton:pressed, QToolButton:pressed { background: %(bordure)s; }
QPushButton:checked, QToolButton:checked { background: %(accent_doux)s;
    border-color: %(accent)s; }
QPushButton:focus, QToolButton:focus { border: 2px solid %(accent)s; }
QPushButton:disabled, QToolButton:disabled { background: %(surface)s;
    color: %(tertiaire)s; border-color: %(bordure)s; }
QPushButton#principal { background: %(accent)s; color: %(sur_accent)s;
    border: 1px solid %(accent)s; }
QPushButton#principal:hover { background: %(accent_survol)s; border-color: %(accent_survol)s; }
QPushButton#principal:pressed { background: %(accent_presse)s; }
QPushButton#principal:focus { border: 2px solid %(texte)s; }
QPushButton#principal:disabled { background: %(surface_haute)s; color: %(tertiaire)s;
    border-color: %(bordure)s; }
QPushButton#danger { background: %(erreur)s; color: %(fond)s; border: 1px solid %(erreur)s; }
QPushButton#danger:hover { background: %(erreur)s; border: 2px solid %(texte)s; }
QPushButton#danger:disabled { background: %(surface_haute)s; color: %(tertiaire)s;
    border-color: %(bordure)s; }
QPushButton#secondaire_danger { color: %(erreur)s; border-color: %(erreur)s; }
QPushButton#plat, QToolButton#plat { background: transparent; border: 1px solid transparent; }
QPushButton#plat:hover, QToolButton#plat:hover { background: %(surface_haute)s; }
QToolButton::menu-indicator { image: none; width: 0; }

/* ─── Champs de saisie ─── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit,
QTextBrowser { background: %(surface)s; border: 1px solid %(bordure_forte)s;
    border-radius: 9px; padding: 6px 9px; selection-background-color: %(accent)s;
    selection-color: %(sur_accent)s; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QPlainTextEdit:hover { border-color: %(tertiaire)s; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus { border: 2px solid %(accent)s; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    color: %(tertiaire)s; background: %(fond)s; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: %(surface_haute)s;
    border: 1px solid %(bordure_forte)s; border-radius: 8px; padding: 4px;
    selection-background-color: %(selection)s; selection-color: %(texte)s; }
QAbstractSpinBox { padding-right: 24px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 22px;
    border: none; background: transparent; subcontrol-origin: border; }
QAbstractSpinBox::up-button { subcontrol-position: top right; }
QAbstractSpinBox::down-button { subcontrol-position: bottom right; }
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {
    background: %(surface_haute)s; }
QAbstractSpinBox::up-arrow { width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-bottom: 5px solid %(discret)s; }
QAbstractSpinBox::down-arrow { width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid %(discret)s; }

/* ─── Cases, listes, tableaux ─── */
QCheckBox { spacing: 8px; }
QCheckBox::indicator, QTableView::indicator, QListWidget::indicator {
    width: 16px; height: 16px; border: 2px solid %(tertiaire)s; border-radius: 5px;
    background: %(surface)s; }
QCheckBox::indicator:hover, QTableView::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked, QTableView::indicator:checked,
QListWidget::indicator:checked { background: %(accent)s; border-color: %(accent)s; }
QCheckBox::indicator:disabled { border-color: %(bordure)s; background: %(fond)s; }
QTableView, QListWidget, QTreeWidget { background: %(surface)s;
    alternate-background-color: %(surface_haute)s; border: 1px solid %(bordure)s;
    border-radius: 12px; gridline-color: %(bordure)s;
    selection-background-color: %(selection)s; selection-color: %(texte)s; }
QTableView::item, QListWidget::item { padding: 5px 6px; border: none; }
QListWidget::item:hover { background: %(surface_haute)s; }
QHeaderView { background: transparent; }
QHeaderView::section { background: %(surface)s; color: %(discret)s; border: none;
    border-bottom: 1px solid %(bordure_forte)s; padding: 8px 6px; font-weight: 700; }
QTableCornerButton::section { background: %(surface)s; border: none; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle { background: %(bordure_forte)s; border-radius: 4px;
    min-height: 32px; min-width: 32px; }
QScrollBar::handle:hover { background: %(tertiaire)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ─── Barres, onglets, menus ─── */
QProgressBar { background: %(surface_haute)s; border: none; border-radius: 5px;
    text-align: center; min-height: 10px; max-height: 10px; color: transparent; }
QProgressBar::chunk { background: %(accent)s; border-radius: 5px; }
QProgressBar#avec_texte { max-height: 18px; min-height: 18px; color: %(texte)s; }
QTabWidget::pane { border: none; }
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab { background: transparent; color: %(discret)s; padding: 8px 14px;
    margin-right: 4px; border: none; border-bottom: 2px solid transparent;
    font-weight: 600; }
QTabBar::tab:hover { color: %(texte)s; }
QTabBar::tab:selected { color: %(texte)s; border-bottom: 2px solid %(accent)s; }
QTabBar::tab:focus { color: %(accent)s; }
QMenu { background: %(surface_haute)s; border: 1px solid %(bordure_forte)s;
    border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 26px 7px 12px; border-radius: 6px; }
QMenu::item:selected { background: %(selection)s; }
QMenu::item:disabled { color: %(tertiaire)s; }
QMenu::separator { height: 1px; background: %(bordure)s; margin: 5px 8px; }
QStatusBar { background: %(fond_lateral)s; color: %(tertiaire)s;
    border-top: 1px solid %(bordure)s; }
QStatusBar::item { border: none; }
QScrollArea { border: none; }
QSplitter::handle { background: transparent; }

/* ─── Notifications temporaires ─── */
QFrame#toast { background: %(surface_active)s; border: 1px solid %(bordure_forte)s;
    border-radius: 12px; }
QLabel#toast_titre { font-weight: 700; }
""" % (
        s
        | {
            "info_doux": p.doux(p.info),
            "attention_doux": p.doux(p.attention),
            "erreur_doux": p.doux(p.erreur),
            "succes_doux": p.doux(p.succes),
        }
    )


# ─── Contrastes (accessibilité, WCAG 2.1) ─────────────────────────────────────


def luminance(couleur: str) -> float:
    c = QColor(couleur)

    def canal(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * canal(c.red()) + 0.7152 * canal(c.green()) + 0.0722 * canal(c.blue())
    )


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)
