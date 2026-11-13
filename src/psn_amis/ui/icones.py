"""Icônes vectorielles de PSN Amis, dessinées pour le projet (licence MIT du projet).

Toutes sur une grille de 24 × 24, en traits de 1,75 px aux extrémités arrondies : un
style unique et cohérent. Elles sont rendues en SVG par QtSvg (aucun fichier à
embarquer, rien à télécharger), dans la couleur du thème, et à la densité de l'écran
(nettes à 100 %, 150 % ou 200 %).
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

TRACES: dict[str, str] = {
    "tableau": '<rect x="3.5" y="3.5" width="7" height="8" rx="1.8"/>'
    '<rect x="13.5" y="3.5" width="7" height="5" rx="1.8"/>'
    '<rect x="13.5" y="11.5" width="7" height="9" rx="1.8"/>'
    '<rect x="3.5" y="14.5" width="7" height="6" rx="1.8"/>',
    "activite": '<path d="M3 12h4l2.5-6 5 12 2.5-6H21"/>',
    "amis": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.3-5.5 6.5-5.5'
    's5.9 1.9 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8"/>'
    '<path d="M18 14.8c1.9.7 3.1 2.5 3.5 5.2"/>',
    "demandes": '<circle cx="10" cy="8" r="3.5"/><path d="M3.5 20c.6-3.6 3.3-5.5 6.5-5.5'
    'c1.4 0 2.7.3 3.8 1"/><path d="M18.5 13v7M15 16.5h7"/>',
    "parametres": '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.4M12 18.8v2.4'
    "M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7"
    'M16.8 7.2l1.7-1.7"/><circle cx="12" cy="12" r="6.5"/>',
    "apropos": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/>'
    '<circle cx="12" cy="7.6" r=".6" fill="currentColor"/>',
    "jouer": '<path d="M7.5 5.2v13.6a.8.8 0 0 0 1.2.7l11-6.8a.8.8 0 0 0 0-1.4l-11-6.8'
    'a.8.8 0 0 0-1.2.7z"/>',
    "arreter": '<rect x="6" y="6" width="12" height="12" rx="2.2"/>',
    "pause": '<rect x="6.5" y="5" width="3.6" height="14" rx="1.2"/>'
    '<rect x="13.9" y="5" width="3.6" height="14" rx="1.2"/>',
    "actualiser": '<path d="M20 11a8 8 0 0 0-14.3-4.6L4 8"/><path d="M4 3.5V8h4.5"/>'
    '<path d="M4 13a8 8 0 0 0 14.3 4.6L20 16"/><path d="M20 20.5V16h-4.5"/>',
    "lien": '<path d="M10 14a4.2 4.2 0 0 0 6 0l3-3a4.2 4.2 0 0 0-6-6l-1.2 1.2"/>'
    '<path d="M14 10a4.2 4.2 0 0 0-6 0l-3 3a4.2 4.2 0 0 0 6 6l1.2-1.2"/>',
    "redemarrer": '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 3.5V8h4.5"/>',
    "quitter": '<path d="M12 3v8"/><path d="M6.8 6.2a8 8 0 1 0 10.4 0"/>',
    "plus": '<circle cx="12" cy="12" r="1.2" fill="currentColor"/>'
    '<circle cx="5.5" cy="12" r="1.2" fill="currentColor"/>'
    '<circle cx="18.5" cy="12" r="1.2" fill="currentColor"/>',
    "recherche": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3"/>',
    "bouclier": '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.3-7.5 9.5-4.3-1.2-7.5-4.9-7.5-9.5'
    'V6z"/><path d="M8.8 12.2l2.2 2.2 4.4-4.6"/>',
    "poubelle": '<path d="M4 7h16M9.5 7V4.8h5V7"/><path d="M6.2 7l.9 12.4a1.8 1.8 0 0 0'
    ' 1.8 1.6h6.2a1.8 1.8 0 0 0 1.8-1.6L17.8 7"/><path d="M10 11v6M14 11v6"/>',
    "copier": '<rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2.2"/>'
    '<path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5"/>',
    "effacer": '<path d="M8 20h12"/><path d="M5.6 15.2l8.6-8.6a2 2 0 0 1 2.8 0l1.4 1.4'
    'a2 2 0 0 1 0 2.8L11 18.2a6 6 0 0 1-2 1.8L5.6 15.2z"/><path d="M9 11.8l3.2 3.2"/>',
    "exporter": '<path d="M12 3.5v11"/><path d="M7.5 10l4.5 4.5 4.5-4.5"/>'
    '<path d="M4.5 16.5v2a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2"/>',
    "importer": '<path d="M12 14.5v-11"/><path d="M7.5 8L12 3.5 16.5 8"/>'
    '<path d="M4.5 16.5v2a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2"/>',
    "alerte": '<path d="M10.3 4.2L2.8 17.5A2 2 0 0 0 4.5 20.5h15a2 2 0 0 0 1.7-3L13.7'
    ' 4.2a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4.5"/>'
    '<circle cx="12" cy="17" r=".6" fill="currentColor"/>',
    "succes": '<circle cx="12" cy="12" r="9"/><path d="M8 12.3l2.7 2.7L16.2 9.5"/>',
    "erreur": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/>'
    '<circle cx="12" cy="7.6" r=".6" fill="currentColor"/>',
    "horloge": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    "manette": '<path d="M7.5 7h9a4.5 4.5 0 0 1 4.4 3.6l.9 4.6a2.6 2.6 0 0 1-4.6 2.1'
    'L15.5 15h-7l-1.7 2.3a2.6 2.6 0 0 1-4.6-2.1l.9-4.6A4.5 4.5 0 0 1 7.5 7z"/>'
    '<path d="M8 9.8v3M6.5 11.3h3"/><circle cx="15.5" cy="10.3" r=".7" '
    'fill="currentColor"/><circle cx="17.2" cy="12.2" r=".7" fill="currentColor"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 1.8-.9 1.6-1.9-.3-1.3.6-2.6 2-2.6'
    'H18a3 3 0 0 0 3-3A9 9 0 0 0 12 3z"/><circle cx="7.5" cy="12" r="1.1" '
    'fill="currentColor"/><circle cx="10" cy="7.6" r="1.1" fill="currentColor"/>'
    '<circle cx="15" cy="7.8" r="1.1" fill="currentColor"/>',
    "cle": '<circle cx="8" cy="15" r="4"/><path d="M11 12l8-8M16 7l2.5 2.5M14 9l2 2"/>',
    "dossier": '<path d="M3.5 7a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2'
    'h-13a2 2 0 0 1-2-2z"/>',
    "urgence": '<path d="M8.2 3.5h7.6l5.2 5.2v7.6l-5.2 5.2H8.2L3 16.3V8.7z"/>'
    '<path d="M12 8v4.8"/><circle cx="12" cy="16" r=".6" fill="currentColor"/>',
    "mise_a_jour": '<path d="M12 20.5v-11"/><path d="M7.5 13.5L12 9l4.5 4.5"/>'
    '<path d="M5 5.5h14"/>',
    "nettoyage": '<path d="M14 3.5l6.5 6.5"/><path d="M12.5 5l6.5 6.5-7.8 7.8a2 2 0 0 1'
    '-2.8 0l-3.7-3.7a2 2 0 0 1 0-2.8z"/><path d="M4 20.5h7"/>',
    "liste": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.8" cy="6" r=".9" '
    'fill="currentColor"/><circle cx="4.8" cy="12" r=".9" fill="currentColor"/>'
    '<circle cx="4.8" cy="18" r=".9" fill="currentColor"/>',
    "personne": '<circle cx="12" cy="8" r="3.8"/><path d="M4.5 20.5c.7-4 3.7-6 7.5-6s6.8'
    ' 2 7.5 6"/>',
}


def svg(nom: str, couleur: str) -> bytes:
    if nom not in TRACES:
        raise KeyError(f"icône inconnue : {nom}")
    contenu = TRACES[nom].replace("currentColor", couleur)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{couleur}" stroke-width="1.75" stroke-linecap="round" '
        f'stroke-linejoin="round">{contenu}</svg>'
    ).encode()


def _densite() -> float:
    ecran = QGuiApplication.primaryScreen() if QGuiApplication.instance() else None
    return max(1.0, ecran.devicePixelRatio() if ecran else 1.0)


@lru_cache(maxsize=512)
def pixmap(nom: str, couleur: str, taille: int = 18, densite: float = 0.0) -> QPixmap:
    """L'icône en image, à la densité de l'écran (nette en 4K et à 200 %)."""
    densite = densite or _densite()
    cote = max(1, round(taille * densite))
    image = QPixmap(cote, cote)
    image.fill(Qt.GlobalColor.transparent)
    rendu = QSvgRenderer(QByteArray(svg(nom, couleur)))
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    rendu.render(peintre, QRectF(0, 0, cote, cote))
    peintre.end()
    image.setDevicePixelRatio(densite)
    return image


def icone(nom: str, couleur: str, taille: int = 18, desactivee: str = "") -> QIcon:
    """Une QIcon de la bonne couleur ; `desactivee` : couleur à l'état désactivé."""
    resultat = QIcon()
    resultat.addPixmap(pixmap(nom, couleur, taille), QIcon.Mode.Normal)
    if desactivee:
        resultat.addPixmap(pixmap(nom, desactivee, taille), QIcon.Mode.Disabled)
    return resultat


def taille(cote: int) -> QSize:
    return QSize(cote, cote)


def valide(couleur: str) -> bool:
    return QColor(couleur).isValid()
