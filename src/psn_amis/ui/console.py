"""Console intégrée : les événements du moteur en temps réel, comme dans la console Rich.

Chaque ligne a une heure, un symbole, une couleur et un niveau. On peut chercher,
filtrer, copier, exporter, et effacer l'affichage (le journal sur disque n'est jamais
touché). La mémoire est bornée : au-delà de MAXIMUM messages, les plus anciens sortent.
Quand on remonte lire d'anciens messages, l'affichage ne saute plus en bas.
"""

from __future__ import annotations

import html
import logging
from collections import deque
from pathlib import Path

from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from psn_amis.ui.commun import Message, apparence
from psn_amis.ui.theme import Palette

MAXIMUM = 5000

FILTRES = {
    "Tous les événements": lambda m: True,
    "Ajouts et suppressions": lambda m: (
        m.genre in ("ajout", "retrait", "suppression") or m.genre == "operation"
    ),
    "Avertissements et erreurs": lambda m: m.niveau >= logging.WARNING,
    "Erreurs seulement": lambda m: m.niveau >= logging.ERROR,
}


class Console(QWidget):
    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._messages: deque[Message] = deque(maxlen=MAXIMUM)
        # Index du premier message encore affiché (après « Effacer l'affichage »).
        self._efface_jusqu_a = 0
        self._total = 0

        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher dans l'activité (Ctrl+F)")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.setAccessibleName("Rechercher dans l'activité")
        self.recherche.textChanged.connect(self.reafficher)
        self.filtre = QComboBox()
        self.filtre.addItems(list(FILTRES))
        self.filtre.setToolTip("N'afficher qu'une partie des événements")
        self.filtre.currentIndexChanged.connect(self.reafficher)
        self.details = QCheckBox("Détails des erreurs")
        self.details.setToolTip(
            "Affiche les détails techniques des erreurs (le code npsso reste masqué)."
        )
        self.details.toggled.connect(self.reafficher)

        copier = QPushButton("Copier")
        copier.setToolTip("Copie la sélection, ou tout ce qui est affiché")
        copier.clicked.connect(self.copier)
        effacer = QPushButton("Effacer l'affichage")
        effacer.setToolTip("Vide cet écran ; le journal enregistré n'est pas touché")
        effacer.clicked.connect(self.effacer_affichage)
        exporter = QPushButton("Exporter…")
        exporter.setToolTip("Enregistre les événements affichés dans un fichier texte")
        exporter.clicked.connect(self.exporter)

        barre = QHBoxLayout()
        barre.addWidget(self.recherche, 3)
        barre.addWidget(self.filtre, 2)
        barre.addWidget(self.details)
        barre.addWidget(copier)
        barre.addWidget(effacer)
        barre.addWidget(exporter)

        self.texte = QPlainTextEdit()
        self.texte.setReadOnly(True)
        self.texte.setMaximumBlockCount(MAXIMUM)
        self.texte.setAccessibleName("Activité du moteur")
        self.texte.setUndoRedoEnabled(False)
        police = self.texte.font()
        police.setFamilies(["Cascadia Mono", "Consolas", "Courier New", "monospace"])
        self.texte.setFont(police)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addLayout(barre)
        disposition.addWidget(self.texte)
        QShortcut(QKeySequence.StandardKey.Find, self, self.recherche.setFocus)

    # ─── Données ───

    def ajouter(self, message: Message) -> None:
        self._messages.append(message)
        self._total += 1
        if not self._visible(message):
            return
        barre = self.texte.verticalScrollBar()
        en_bas = barre.value() >= barre.maximum() - 4
        position = barre.value()
        self.texte.appendHtml(self._ligne(message))
        if en_bas:
            barre.setValue(barre.maximum())
        else:
            # L'utilisateur lit d'anciens messages : on ne le déplace pas.
            barre.setValue(position)

    def messages_affiches(self) -> list[Message]:
        debut = max(0, self._efface_jusqu_a - (self._total - len(self._messages)))
        return [m for m in list(self._messages)[debut:] if self._visible(m)]

    def changer_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.reafficher()

    # ─── Affichage ───

    def _visible(self, message: Message) -> bool:
        if not FILTRES[self.filtre.currentText()](message):
            return False
        cherche = self.recherche.text().strip().casefold()
        return not cherche or cherche in message.texte.casefold()

    def _ligne(self, message: Message) -> str:
        symbole, cle = apparence(message)
        couleur = getattr(self._palette, cle, self._palette.texte)
        heure = message.moment.strftime("%H:%M:%S")
        texte = html.escape(message.texte).replace("\n", "<br>&nbsp;&nbsp;")
        ligne = (
            f'<span style="color:{self._palette.discret}">{heure}</span> '
            f'<span style="color:{couleur}"><b>{symbole}</b> {texte}</span>'
        )
        if message.detail and self.details.isChecked():
            detail = html.escape(message.detail).replace("\n", "<br>")
            ligne += f'<br><span style="color:{self._palette.discret}">{detail}</span>'
        return ligne

    def reafficher(self) -> None:
        self.texte.clear()
        lignes = [self._ligne(m) for m in self.messages_affiches()]
        if lignes:
            self.texte.appendHtml("<br>".join(lignes))
        self.texte.moveCursor(QTextCursor.MoveOperation.End)

    def effacer_affichage(self) -> None:
        self._efface_jusqu_a = self._total
        self.texte.clear()

    def en_texte(self) -> str:
        return "\n".join(
            f"{m.moment:%Y-%m-%d %H:%M:%S}  {m.texte}" for m in self.messages_affiches()
        )

    def copier(self) -> None:
        if self.texte.textCursor().hasSelection():
            self.texte.copy()
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.en_texte())

    def exporter(self) -> None:
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Exporter l'activité", "activite-psn-amis.txt", "Texte (*.txt)"
        )
        if chemin:
            Path(chemin).write_text(self.en_texte() + "\n", encoding="utf-8")
