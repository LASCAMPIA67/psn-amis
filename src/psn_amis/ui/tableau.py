"""Page « Tableau de bord » : l'essentiel en un coup d'œil.

Seules des informations réellement connues sont affichées : ce que Sony renvoie
(nombre d'amis, demandes) et ce que PSN Amis a fait lui-même (acceptations,
suppressions). Rien n'est estimé ni inventé.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGridLayout,
    QListWidget,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from psn_amis.controleur import EtatMoteur
from psn_amis.gestion import Vue
from psn_amis.moteur import Instantane, en_amis
from psn_amis.ui.commun import STATUTS, Message, apparence, date_courte
from psn_amis.ui.composants import (
    Bandeau,
    Carte,
    EtatVide,
    Pastille,
    Statistique,
    changer_texte,
    etiquette,
    fondu_entrant,
)
from psn_amis.ui.theme import Palette


def il_y_a(moment: datetime | None, maintenant: datetime) -> str:
    if moment is None:
        return "jamais"
    secondes = int((maintenant - moment).total_seconds())
    if secondes < 60:
        return "à l'instant"
    if secondes < 3600:
        return f"il y a {secondes // 60} min"
    return f"il y a {secondes // 3600} h {secondes % 3600 // 60:02d}"


class TableauDeBord(QWidget):
    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._cle_statut = ""

        # ─── Carte d'état principale ───
        self.statut = etiquette("◌ Démarrage", "tres_grand")
        self.statut.setAccessibleName("État du moteur")
        self.detail = etiquette("", "discret", retour_ligne=True)
        self.compte = etiquette("Compte PSN : pas encore connecté")
        self.automatisation = Pastille()
        etat = Carte("État", "activite", accent=True)
        etat.contenu.addWidget(self.statut)
        etat.contenu.addWidget(self.detail)
        etat.contenu.addSpacing(4)
        etat.contenu.addWidget(self.compte)
        etat.contenu.addWidget(self.automatisation, 0, Qt.AlignmentFlag.AlignLeft)
        etat.contenu.addStretch(1)

        self.amis = etiquette("—", "tres_grand")
        self.amis.setAccessibleName("Nombre d'amis sur la capacité de la liste")
        self.capacite = QProgressBar()
        self.capacite.setAccessibleName("Remplissage de la liste d'amis")
        self.capacite_texte = etiquette("", "discret", retour_ligne=True)
        capacite = Carte("Liste d'amis", "amis")
        capacite.ajouter(self.amis, self.capacite, self.capacite_texte)
        capacite.contenu.addStretch(1)

        # ─── Chiffres clés ───
        self.carte_attente = Statistique("Demandes en attente", "demandes")
        self.carte_acceptees = Statistique("Acceptées aujourd'hui", "succes")
        self.carte_supprimes = Statistique("Supprimés par PSN Amis", "poubelle")
        self.carte_synchro = Statistique("Synchronisation", "horloge")
        # Noms gardés (tests, autres pages) : la valeur principale de chaque carte.
        self.en_attente = self.carte_attente.valeur
        self.acceptees = self.carte_acceptees.valeur
        self.supprimes = self.carte_supprimes.valeur

        # ─── Listes ───
        self.recents = QListWidget()
        self.recents.setAccessibleName("Derniers amis acceptés")
        self.vide_recents = EtatVide(
            "personne",
            "Aucun ajout pour l'instant",
            "Les demandes acceptées par PSN Amis apparaîtront ici, avec leur heure.",
        )
        self.pile_recents = QStackedWidget()
        self.pile_recents.addWidget(self.vide_recents)
        self.pile_recents.addWidget(self.recents)
        recents = Carte("Derniers ajouts", "personne")
        recents.contenu.addWidget(self.pile_recents, 1)

        self.activite = QListWidget()
        self.activite.setAccessibleName("Activité récente")
        self.activite.setWordWrap(True)
        activite = Carte("Activité récente", "liste")
        activite.contenu.addWidget(self.activite, 1)

        self.avertissements = QVBoxLayout()
        self.avertissements.setSpacing(8)

        grille = QGridLayout()
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(14)
        grille.addWidget(etat, 0, 0, 1, 2)
        grille.addWidget(capacite, 0, 2, 1, 2)
        for colonne, carte in enumerate(
            (
                self.carte_attente,
                self.carte_acceptees,
                self.carte_supprimes,
                self.carte_synchro,
            )
        ):
            grille.addWidget(carte, 1, colonne)
        grille.addWidget(recents, 2, 0, 1, 2)
        grille.addWidget(activite, 2, 2, 1, 2)
        grille.setRowStretch(2, 1)
        for colonne in range(4):
            grille.setColumnStretch(colonne, 1)

        contenu = QWidget()
        contenu.setObjectName("page")
        disposition_contenu = QVBoxLayout(contenu)
        disposition_contenu.setContentsMargins(0, 0, 4, 0)
        disposition_contenu.setSpacing(14)
        disposition_contenu.addLayout(self.avertissements)
        disposition_contenu.addLayout(grille, 1)
        defilement = QScrollArea()
        defilement.setWidgetResizable(True)
        defilement.setWidget(contenu)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addWidget(defilement)
        self._derniers: tuple = ()
        self._evenements: deque[Message] = deque(maxlen=8)
        self._activite_a_jour = False
        self._avertissements_actuels: tuple[tuple[str, str], ...] = ()

    def changer_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._cle_statut = ""
        self._activite_a_jour = False

    def ajouter_evenement(self, message: Message) -> None:
        """Un événement du journal (le plus récent en premier, 8 au plus)."""
        self._evenements.appendleft(message)
        self._activite_a_jour = False

    def actualiser(
        self,
        instant: Instantane,
        vue: Vue,
        etat_moteur: EtatMoteur,
        en_pause: bool,
        limite: int,
        acceptation_auto: bool,
        avertissements: list[tuple[str, str]],
    ) -> None:
        maintenant = datetime.now()
        if etat_moteur is EtatMoteur.EN_MARCHE:
            symbole, cle, libelle = STATUTS[instant.statut]
        elif etat_moteur is EtatMoteur.ARRET_EN_COURS:
            symbole, cle, libelle = "◌", "attention", "Arrêt en cours"
        else:
            symbole, cle, libelle = "■", "discret", "Moteur arrêté"
        changer_texte(self.statut, f"{symbole} {libelle}")
        if cle != self._cle_statut:
            self._cle_statut = cle
            self.statut.setStyleSheet(f"color: {getattr(self._palette, cle)};")
        changer_texte(
            self.detail, instant.detail if etat_moteur is EtatMoteur.EN_MARCHE else ""
        )
        changer_texte(
            self.compte,
            f"Compte PSN : {instant.pseudo_compte}"
            if instant.pseudo_compte
            else "Compte PSN : pas encore connecté",
        )
        if en_pause:
            self.automatisation.afficher("Acceptations en pause", "attention")
        elif not acceptation_auto:
            self.automatisation.afficher("Acceptation automatique coupée", "discret")
        else:
            self.automatisation.afficher("Acceptation automatique active", "succes")

        self.capacite.setRange(0, max(1, limite))
        if instant.nombre_amis is None:
            changer_texte(self.amis, "—")
            self.capacite.setValue(0)
            changer_texte(self.capacite_texte, "Nombre d'amis pas encore connu")
        else:
            changer_texte(self.amis, f"{instant.nombre_amis} / {limite}")
            self.capacite.setValue(min(instant.nombre_amis, limite))
            reste = limite - instant.nombre_amis
            changer_texte(
                self.capacite_texte,
                f"{en_amis(max(reste, 0))} de place · "
                f"{round(100 * instant.nombre_amis / max(limite, 1))} % utilisés"
                if reste > 0
                else "Liste pleine : faites de la place dans la page Amis",
            )

        self.carte_attente.afficher(
            "—"
            if instant.demandes_en_attente is None
            else str(instant.demandes_en_attente),
            "en pause : elles attendent"
            if en_pause
            else "acceptées à la prochaine vérification",
        )
        self.carte_acceptees.afficher(
            str(instant.ajouts_jour), f"{instant.ajouts_session} depuis le lancement"
        )
        self.carte_supprimes.afficher(
            str(instant.supprimes_jour),
            f"aujourd'hui · {instant.retraits_jour} parti(s) d'eux-mêmes",
        )
        if instant.prochaine_verification is not None and not en_pause:
            reste = max(0, int(instant.prochaine_verification - time.monotonic()))
            prochaine = f"prochaine dans {reste} s"
        else:
            prochaine = "prochaine : —"
        liste = (
            f" · liste reçue {date_courte(vue.synchronise_le)}"
            if vue.synchronise_le
            else ""
        )
        self.carte_synchro.afficher(
            il_y_a(instant.derniere_verification, maintenant).capitalize(),
            prochaine + liste,
        )

        if instant.derniers_ajouts[:12] != self._derniers:
            self._derniers = instant.derniers_ajouts[:12]
            self.recents.clear()
            for ajout in self._derniers:
                self.recents.addItem(f"＋  {ajout.moment:%d/%m %H:%M}   {ajout.pseudo}")
            self.pile_recents.setCurrentIndex(1 if self._derniers else 0)
        self._afficher_activite(instant)
        self._afficher_avertissements(tuple(avertissements))

    def _afficher_activite(self, instant: Instantane) -> None:
        if self._activite_a_jour:
            return
        self._activite_a_jour = True
        self.activite.clear()
        if not self._evenements:
            self.activite.addItem(
                "Rien pour l'instant : l'activité du moteur apparaîtra ici."
            )
            return
        for message in self._evenements:
            symbole, cle = apparence(message)
            self.activite.addItem(f"{message.moment:%H:%M}  {symbole}  {message.texte}")
            element = self.activite.item(self.activite.count() - 1)
            element.setForeground(
                QColor(getattr(self._palette, cle, self._palette.texte))
            )

    def _afficher_avertissements(
        self, avertissements: tuple[tuple[str, str], ...]
    ) -> None:
        if avertissements == self._avertissements_actuels:
            return
        self._avertissements_actuels = avertissements
        while self.avertissements.count():
            element = self.avertissements.takeAt(0)
            if element.widget():
                element.widget().deleteLater()
        for niveau, texte in avertissements:
            bandeau = Bandeau(niveau, texte)
            self.avertissements.addWidget(bandeau)
            fondu_entrant(bandeau)
