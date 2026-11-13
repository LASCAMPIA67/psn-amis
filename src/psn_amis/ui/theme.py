"""Thèmes de la fenêtre : sombre, doux, daltonien (ceux de la console) et clair.

Chaque information portée par une couleur l'est aussi par un symbole ou un texte
(statut, niveau d'un événement, protection) : rien ne dépend de la seule couleur.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    fond: str
    surface: str
    surface_haute: str
    bordure: str
    texte: str
    discret: str
    accent: str
    succes: str
    attention: str
    erreur: str
    info: str
    selection: str


PALETTES = {
    "sombre": Palette(
        fond="#0b1220",
        surface="#121b2e",
        surface_haute="#1a2540",
        bordure="#26324d",
        texte="#e6ecf8",
        discret="#8f9bb5",
        accent="#3d9bff",
        succes="#3ccf7a",
        attention="#ffb347",
        erreur="#ff6b6b",
        info="#62d2ff",
        selection="#24406e",
    ),
    "doux": Palette(
        fond="#10151f",
        surface="#171e2b",
        surface_haute="#1f2838",
        bordure="#2c3647",
        texte="#d9e0ea",
        discret="#8792a6",
        accent="#7aa2c8",
        succes="#8fbf9a",
        attention="#d8b07a",
        erreur="#d68a8a",
        info="#93b8d6",
        selection="#2d3d57",
    ),
    "daltonien": Palette(
        fond="#0b1220",
        surface="#121b2e",
        surface_haute="#1a2540",
        bordure="#26324d",
        texte="#e6ecf8",
        discret="#9aa6bf",
        accent="#b8c4ff",
        succes="#4da3ff",
        attention="#ffd84d",
        erreur="#ff9a3d",
        info="#b8c4ff",
        selection="#2b3f73",
    ),
    "clair": Palette(
        fond="#f4f6fa",
        surface="#ffffff",
        surface_haute="#eef1f7",
        bordure="#d3d9e4",
        texte="#1b2333",
        discret="#5b6579",
        accent="#1f6fd1",
        succes="#1d8a4b",
        attention="#a35f00",
        erreur="#c0392b",
        info="#0f6f9c",
        selection="#cfe0fa",
    ),
}


def palette(nom: str) -> Palette:
    return PALETTES.get(nom, PALETTES["sombre"])


def feuille_de_style(nom: str) -> str:
    p = palette(nom)
    return f"""
QWidget {{ background: {p.fond}; color: {p.texte}; font-size: 10pt; }}
QToolTip {{ background: {p.surface_haute}; color: {p.texte};
    border: 1px solid {p.bordure}; padding: 4px; }}
QFrame#carte, QGroupBox {{ background: {p.surface}; border: 1px solid {p.bordure};
    border-radius: 8px; }}
QGroupBox {{ margin-top: 14px; padding: 10px 8px 8px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
    color: {p.accent}; }}
QLabel {{ background: transparent; }}
QLabel#titre {{ font-size: 15pt; font-weight: 600; }}
QLabel#grand {{ font-size: 20pt; font-weight: 700; }}
QLabel#discret, QLabel#description {{ color: {p.discret}; }}
QLabel#bandeau_attention {{ background: {p.surface_haute}; color: {p.attention};
    border: 1px solid {p.attention}; border-radius: 6px; padding: 8px; }}
QLabel#bandeau_erreur {{ background: {p.surface_haute}; color: {p.erreur};
    border: 1px solid {p.erreur}; border-radius: 6px; padding: 8px; }}
QLabel#bandeau_info {{ background: {p.surface_haute}; color: {p.info};
    border: 1px solid {p.info}; border-radius: 6px; padding: 8px; }}
QListWidget#navigation {{ background: {p.surface}; border: none;
    border-right: 1px solid {p.bordure}; padding-top: 8px; outline: none; }}
QListWidget#navigation::item {{ padding: 10px 14px; border-radius: 6px;
    margin: 2px 6px; }}
QListWidget#navigation::item:selected {{ background: {p.selection}; color: {p.texte}; }}
QListWidget#navigation::item:hover {{ background: {p.surface_haute}; }}
QPushButton, QToolButton {{ background: {p.surface_haute}; color: {p.texte};
    border: 1px solid {p.bordure}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {p.accent}; }}
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus, QTableView:focus,
QCheckBox:focus {{ border: 1px solid {p.accent}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {p.discret}; }}
QPushButton#principal {{ background: {p.accent}; color: {p.fond}; font-weight: 600; }}
QPushButton#danger {{ background: {p.erreur}; color: {p.fond}; font-weight: 600; }}
QPushButton#principal:disabled {{ background: {p.surface_haute}; color: {p.discret}; }}
QPushButton#danger:disabled {{ background: {p.surface_haute}; color: {p.discret}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {p.surface}; border: 1px solid {p.bordure}; border-radius: 6px;
    padding: 4px 6px; selection-background-color: {p.selection}; }}
QTableView, QListWidget, QTreeWidget {{ background: {p.surface};
    alternate-background-color: {p.surface_haute}; border: 1px solid {p.bordure};
    border-radius: 6px; selection-background-color: {p.selection};
    selection-color: {p.texte}; gridline-color: {p.bordure}; }}
QHeaderView::section {{ background: {p.surface_haute}; color: {p.discret};
    border: none; border-bottom: 1px solid {p.bordure}; padding: 6px; }}
QProgressBar {{ background: {p.surface_haute}; border: 1px solid {p.bordure};
    border-radius: 5px; text-align: center; min-height: 14px; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}
QTabWidget::pane {{ border: 1px solid {p.bordure}; border-radius: 6px; }}
QTabBar::tab {{ background: {p.surface}; padding: 7px 14px; border: 1px solid
    {p.bordure}; border-bottom: none; border-top-left-radius: 6px;
    border-top-right-radius: 6px; }}
QTabBar::tab:selected {{ background: {p.surface_haute}; color: {p.accent}; }}
QStatusBar {{ background: {p.surface}; color: {p.discret}; }}
QToolBar {{ background: {p.surface}; border: none; border-bottom: 1px solid
    {p.bordure}; spacing: 4px; padding: 4px; }}
QScrollArea {{ border: none; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.bordure}; }}
QCheckBox::indicator, QTableView::indicator, QListWidget::indicator {{
    width: 15px; height: 15px; border: 2px solid {p.discret};
    border-radius: 4px; background: {p.surface}; }}
QCheckBox::indicator:checked, QTableView::indicator:checked,
QListWidget::indicator:checked {{ background: {p.accent};
    border-color: {p.accent}; }}
QCheckBox::indicator:disabled {{ border-color: {p.bordure}; }}
QAbstractSpinBox {{ padding-right: 22px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; background: {p.surface_haute};
    border-left: 1px solid {p.bordure}; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right;
    border-top-right-radius: 6px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right;
    border-bottom-right-radius: 6px; }}
QAbstractSpinBox::up-arrow {{ width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid {p.texte}; }}
QAbstractSpinBox::down-arrow {{ width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {p.texte}; }}
QMenu::item:selected {{ background: {p.selection}; }}
"""
