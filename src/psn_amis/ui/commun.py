"""Outils communs de l'interface : pont journal → Qt, tâches de fond, petits widgets.

Le moteur tourne dans son propre fil et ne touche jamais aux widgets : ses messages
passent par un signal Qt, que Qt remet au fil de l'interface (connexion « en file »).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from psn_amis import moteur
from psn_amis.moteur import Statut


@dataclass(frozen=True)
class Message:
    """Un événement du journal, prêt pour la console intégrée."""

    moment: datetime
    niveau: int
    genre: str
    texte: str
    # Détail technique (trace d'erreur), masqué, affiché à la demande.
    detail: str = ""


class PontJournal(QObject):
    """Reçoit les messages du journal depuis n'importe quel fil et les émet en signal."""

    message = Signal(object)


class VersInterface(logging.Handler):
    """Gestionnaire de journal : chaque message (masqué) part vers l'interface."""

    def __init__(self, pont: PontJournal) -> None:
        super().__init__(logging.INFO)
        self._pont = pont
        self._format = logging.Formatter()

    def emit(self, record: logging.LogRecord) -> None:
        # Aides et rappels propres à la console texte (touches, « toujours actif ») :
        # la fenêtre a ses propres boutons et bandeaux.
        if getattr(record, "genre", "") in (moteur.GENRE_AIDE, moteur.GENRE_RAPPEL):
            return
        try:
            texte = moteur.masquer(record.getMessage())
            detail = ""
            if record.exc_info:
                detail = moteur.masquer(self._format.formatException(record.exc_info))
            self._pont.message.emit(
                Message(
                    datetime.fromtimestamp(record.created),
                    record.levelno,
                    getattr(record, "genre", ""),
                    texte,
                    detail,
                )
            )
        except RuntimeError:
            # Fenêtre déjà détruite pendant la fermeture : rien à afficher.
            pass


class Tache(QObject):
    """Exécute une fonction dans un fil à part ; le résultat revient par signal."""

    reussie = Signal(object)
    echouee = Signal(object)
    progression = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fil: threading.Thread | None = None

    def en_cours(self) -> bool:
        return self._fil is not None and self._fil.is_alive()

    def lancer(self, fonction: Callable[..., Any], *arguments: Any) -> bool:
        if self.en_cours():
            return False

        def travailler() -> None:
            try:
                resultat = fonction(*arguments)
            except Exception as erreur:  # noqa: BLE001 (renvoyée à l'interface)
                self.echouee.emit(erreur)
            else:
                self.reussie.emit(resultat)

        self._fil = threading.Thread(target=travailler, name="tache", daemon=True)
        self._fil.start()
        return True


# ─── Présentation ─────────────────────────────────────────────────────────────

# Statut → (symbole, clé de couleur de la palette, libellé).
STATUTS: dict[Statut, tuple[str, str, str]] = {
    Statut.DEMARRAGE: ("◌", "discret", "Démarrage"),
    Statut.CONNEXION: ("◌", "info", "Connexion à Sony"),
    Statut.EN_MARCHE: ("●", "succes", "En marche"),
    Statut.VERIFICATION: ("↻", "info", "Vérification"),
    Statut.PAUSE: ("⏸", "attention", "En pause"),
    Statut.HORS_LIGNE: ("⚠", "erreur", "Hors ligne"),
    Statut.ATTENTE: ("⏳", "attention", "En attente"),
    Statut.CODE_NPSSO: ("⚠", "erreur", "Code npsso à changer"),
    Statut.LISTE_PLEINE: ("⚠", "attention", "Liste d'amis pleine"),
    Statut.ERREUR: ("✖", "erreur", "Erreur"),
    Statut.SUPPRESSION: ("✂", "info", "Gestion des amis"),
}

# Niveau du journal → (symbole, clé de couleur, nom).
NIVEAUX: dict[int, tuple[str, str, str]] = {
    logging.DEBUG: ("·", "discret", "détail"),
    logging.INFO: ("•", "texte", "info"),
    logging.WARNING: ("▲", "attention", "attention"),
    logging.ERROR: ("✖", "erreur", "erreur"),
    logging.CRITICAL: ("✖", "erreur", "erreur"),
}

GENRES: dict[str, tuple[str, str]] = {
    moteur.GENRE_AJOUT: ("+", "succes"),
    moteur.GENRE_RETRAIT: ("−", "attention"),
    moteur.GENRE_SUPPRESSION: ("✂", "info"),
    "operation": ("✂", "info"),
}


def apparence(message: Message) -> tuple[str, str]:
    """(symbole, clé de couleur) d'un message, d'après son genre puis son niveau."""
    if message.genre in GENRES:
        return GENRES[message.genre]
    symbole, couleur, _ = NIVEAUX.get(message.niveau, NIVEAUX[logging.INFO])
    return symbole, couleur


def carte(titre: str, *widgets: QWidget) -> QFrame:
    cadre = QFrame()
    cadre.setObjectName("carte")
    disposition = QVBoxLayout(cadre)
    disposition.setContentsMargins(14, 10, 14, 12)
    etiquette = QLabel(titre)
    etiquette.setObjectName("discret")
    disposition.addWidget(etiquette)
    for widget in widgets:
        disposition.addWidget(widget)
    return cadre


def etiquette(texte: str = "", nom: str = "", retour_ligne: bool = False) -> QLabel:
    label = QLabel(texte)
    if nom:
        label.setObjectName(nom)
    label.setWordWrap(retour_ligne)
    return label


def date_courte(moment: datetime | None, inconnu: str = "Inconnue") -> str:
    if moment is None:
        return inconnu
    return moment.strftime("%d/%m/%Y %H:%M")
