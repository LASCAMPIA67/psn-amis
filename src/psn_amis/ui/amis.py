"""Page « Amis » : consulter, protéger, sélectionner et supprimer des amis.

Toutes les règles de sécurité sont aussi appliquées par le service (amis.py) : une
erreur de l'interface ne peut pas faire supprimer un ami protégé.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from psn_amis.amis import EXPLICATIONS_CRITERES, Critere, Resultat, Selection, Verdict
from psn_amis.gestion import Gestion, LigneAmi, Vue
from psn_amis.ui.commun import date_courte, etiquette

COLONNES = (
    "Pseudo",
    "Identifiant PSN",
    "Protection",
    "Accepté par PSN Amis le",
    "Vu pour la première fois",
    "Vu pour la dernière fois",
)
NOMS_CRITERES = {
    Critere.PLUS_ANCIENS_ACCEPTES: "Les plus anciennement acceptés",
    Critere.PREMIERE_OBSERVATION: "Les premiers vus par PSN Amis",
    Critere.ALPHABETIQUE: "Ordre alphabétique des pseudos",
}
FILTRES = (
    "Tous les amis",
    "Non protégés",
    "Protégés",
    "Pseudo inconnu",
    "Acceptés par PSN Amis",
)
SYMBOLES_PROTECTION = {
    Verdict.PROTEGE: "🛡 protégé",
    Verdict.DOUTE: "? incertain",
    Verdict.LIBRE: "—",
}


class ModeleAmis(QAbstractTableModel):
    """Les amis, avec une case à cocher par ligne."""

    def __init__(self) -> None:
        super().__init__()
        self.lignes: list[LigneAmi] = []
        self.coches: set[str] = set()

    def remplacer(self, lignes: tuple[LigneAmi, ...]) -> None:
        self.beginResetModel()
        self.lignes = list(lignes)
        presents = {ligne.compte for ligne in lignes}
        self.coches &= presents
        self.endResetModel()

    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        return 0 if parent.isValid() else len(self.lignes)

    def columnCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        return 0 if parent.isValid() else len(COLONNES)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return COLONNES[section]
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            base |= Qt.ItemFlag.ItemIsUserCheckable
        return base

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        ligne = self.lignes[index.row()]
        colonne = index.column()
        if role == Qt.ItemDataRole.CheckStateRole and colonne == 0:
            return (
                Qt.CheckState.Checked
                if ligne.compte in self.coches
                else Qt.CheckState.Unchecked
            )
        if role == Qt.ItemDataRole.UserRole:
            # Valeur de tri.
            return (
                (ligne.pseudo or "~").casefold(),
                ligne.compte,
                ligne.protection.value,
                ligne.accepte_le.isoformat() if ligne.accepte_le else "~",
                ligne.premiere_observation.isoformat()
                if ligne.premiere_observation
                else "~",
                ligne.derniere_observation.isoformat()
                if ligne.derniere_observation
                else "~",
            )[colonne]
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                ligne.pseudo or "(pseudo inconnu)",
                ligne.compte,
                SYMBOLES_PROTECTION[ligne.protection],
                date_courte(ligne.accepte_le, "Inconnue"),
                date_courte(ligne.premiere_observation, "Inconnue"),
                date_courte(ligne.derniere_observation, "Inconnue"),
            )[colonne]
        if (
            role == Qt.ItemDataRole.ToolTipRole
            and colonne == 3
            and not ligne.accepte_le
        ):
            return "Date connue seulement pour les demandes acceptées par PSN Amis."
        return None

    def setData(
        self, index: QModelIndex | QPersistentModelIndex, valeur: Any, role: int = 0
    ) -> bool:
        if role != Qt.ItemDataRole.CheckStateRole or index.column() != 0:
            return False
        compte = self.lignes[index.row()].compte
        if Qt.CheckState(valeur) == Qt.CheckState.Checked:
            self.coches.add(compte)
        else:
            self.coches.discard(compte)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        return True

    def cocher(self, comptes: set[str], coche: bool) -> None:
        if coche:
            self.coches |= comptes
        else:
            self.coches -= comptes
        if self.lignes:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.lignes) - 1, 0),
                [Qt.ItemDataRole.CheckStateRole],
            )


class FiltreAmis(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.texte = ""
        self.genre = FILTRES[0]
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def filterAcceptsRow(
        self, ligne_source: int, parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        modele = self.sourceModel()
        if not isinstance(modele, ModeleAmis):
            return True
        ami = modele.lignes[ligne_source]
        if self.texte and (
            self.texte not in (ami.pseudo or "").casefold()
            and self.texte not in ami.compte
        ):
            return False
        return {
            "Non protégés": ami.protection is Verdict.LIBRE,
            "Protégés": ami.protection is Verdict.PROTEGE,
            "Pseudo inconnu": ami.pseudo is None,
            "Acceptés par PSN Amis": ami.accepte_le is not None,
        }.get(self.genre, True)

    def changer(self, texte: str | None = None, genre: str | None = None) -> None:
        if texte is not None:
            self.texte = texte.strip().casefold()
        if genre is not None:
            self.genre = genre
        self.invalidateRowsFilter()


class Apercu(QDialog):
    """« Prévisualiser les suppressions » : rien n'est supprimé ici."""

    def __init__(self, selection: Selection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prévisualiser les suppressions")
        self.resize(560, 560)
        n = selection.supprimables
        resume = (
            f"Amis dans la liste : {selection.total_amis}\n"
            f"Demandés : {selection.demandes}\n"
            f"Protégés (exclus) : {selection.proteges}\n"
            f"Protection incertaine (exclus) : {selection.incertains}\n"
            f"Effectivement supprimables : {n}\n"
            f"Critère : {selection.critere}\n"
            f"Requêtes à Sony estimées : {selection.requetes} "
            "(vérification puis suppression, une toutes les 3 secondes au plus)"
        )
        disposition = QVBoxLayout(self)
        disposition.addWidget(etiquette(resume, retour_ligne=True))
        for avertissement in selection.avertissements:
            disposition.addWidget(
                etiquette(f"▲ {avertissement}", "bandeau_attention", True)
            )
        liste = QListWidget()
        liste.setAccessibleName("Amis qui seraient supprimés")
        for rang, cible in enumerate(selection.cibles, start=1):
            liste.addItem(f"{rang:>3}. {cible.nom}  (compte n°{cible.compte})")
        disposition.addWidget(liste, 1)
        self.comprendre = QCheckBox(
            "Je comprends que ces suppressions sont définitives sur mon compte PSN."
        )
        disposition.addWidget(self.comprendre)
        boutons = QDialogButtonBox()
        self.supprimer = QPushButton(f"Supprimer {n} ami{'s' if n > 1 else ''}")
        self.supprimer.setObjectName("danger")
        self.supprimer.setEnabled(False)
        boutons.addButton(self.supprimer, QDialogButtonBox.ButtonRole.AcceptRole)
        fermer = boutons.addButton(
            "Fermer sans rien supprimer", QDialogButtonBox.ButtonRole.RejectRole
        )
        fermer.setDefault(True)
        self.comprendre.toggled.connect(
            lambda c: self.supprimer.setEnabled(c and n > 0)
        )
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        disposition.addWidget(boutons)


class PageAmis(QWidget):
    def __init__(
        self,
        gestion: Gestion,
        verifier: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.gestion = gestion
        self._verifier = verifier
        self._version = -1

        self.entete = etiquette("Connexion à Sony en attente…", retour_ligne=True)
        self.bandeaux = QVBoxLayout()
        actualiser = QPushButton("Actualiser")
        actualiser.setToolTip("Redemande la liste d'amis à Sony (F5)")
        actualiser.clicked.connect(self._actualiser)
        self.pseudos = QPushButton("Récupérer les pseudos")
        self.pseudos.setToolTip(
            "Demande à Sony les pseudos inconnus (200 au plus, une requête chacun, "
            "environ 3 secondes par pseudo)."
        )
        self.pseudos.clicked.connect(self._recuperer_pseudos)

        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher un pseudo ou un identifiant")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.setAccessibleName("Rechercher un ami")
        self.filtre = QComboBox()
        self.filtre.addItems(FILTRES)
        self.filtre.setToolTip("Filtrer la liste")

        self.modele = ModeleAmis()
        self.proxy = FiltreAmis()
        self.proxy.setSourceModel(self.modele)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName("Liste des amis")
        self.recherche.textChanged.connect(lambda t: self.proxy.changer(texte=t))
        self.filtre.currentTextChanged.connect(lambda g: self.proxy.changer(genre=g))
        self.modele.dataChanged.connect(self._compter_coches)
        self.modele.modelReset.connect(self._compter_coches)

        tout = QPushButton("Tout cocher (affichés)")
        tout.setToolTip("Coche tous les amis visibles avec la recherche et le filtre")
        tout.clicked.connect(lambda: self._cocher_affiches(True))
        rien = QPushButton("Tout décocher")
        rien.clicked.connect(lambda: self.modele.cocher(set(self.modele.coches), False))
        proteger = QPushButton("Protéger")
        proteger.setToolTip("Protège les amis cochés contre toute suppression")
        proteger.clicked.connect(self._proteger_coches)
        deproteger = QPushButton("Retirer la protection")
        deproteger.clicked.connect(self._deproteger_coches)
        self.supprimer_coches = QPushButton("Supprimer les cochés…")
        self.supprimer_coches.setObjectName("danger")
        self.supprimer_coches.clicked.connect(self._supprimer_coches)
        self.coches = etiquette("0 coché", "discret")

        barre_haut = QHBoxLayout()
        barre_haut.addWidget(self.recherche, 3)
        barre_haut.addWidget(self.filtre, 1)
        barre_haut.addWidget(actualiser)
        barre_haut.addWidget(self.pseudos)
        barre_coches = QHBoxLayout()
        for bouton in (tout, rien, proteger, deproteger):
            barre_coches.addWidget(bouton)
        barre_coches.addWidget(self.coches)
        barre_coches.addStretch(1)
        barre_coches.addWidget(self.supprimer_coches)

        # Sélection par nombre.
        self.nombre = QSpinBox()
        self.nombre.setRange(1, 500)
        self.nombre.setValue(50)
        self.nombre.setAccessibleName("Nombre d'amis à sélectionner")
        self.critere = QComboBox()
        for critere, nom in NOMS_CRITERES.items():
            self.critere.addItem(nom, critere)
            self.critere.setItemData(
                self.critere.count() - 1,
                EXPLICATIONS_CRITERES[critere],
                Qt.ItemDataRole.ToolTipRole,
            )
        apercu = QPushButton("Prévisualiser les suppressions…")
        apercu.setObjectName("principal")
        apercu.clicked.connect(self._apercu_par_nombre)
        groupe_nombre = QGroupBox("Supprimer un nombre d'amis non protégés")
        ligne_nombre = QHBoxLayout(groupe_nombre)
        ligne_nombre.addWidget(etiquette("Nombre :"))
        ligne_nombre.addWidget(self.nombre)
        ligne_nombre.addWidget(etiquette("Critère :"))
        ligne_nombre.addWidget(self.critere, 1)
        ligne_nombre.addWidget(apercu)

        # Opération en cours.
        self.progression = QProgressBar()
        self.progression_texte = etiquette("Aucune suppression en cours.", "discret")
        self.annuler = QPushButton("Arrêter les suppressions")
        self.annuler.setToolTip(
            "Vide la file et s'arrête après l'ami en cours de traitement"
        )
        self.annuler.clicked.connect(self.gestion.annuler)
        self.resultats = QListWidget()
        self.resultats.setAccessibleName("Résultat de chaque suppression")
        groupe_operation = QGroupBox("Suppressions")
        disposition_operation = QVBoxLayout(groupe_operation)
        ligne_progression = QHBoxLayout()
        ligne_progression.addWidget(self.progression, 1)
        ligne_progression.addWidget(self.annuler)
        disposition_operation.addLayout(ligne_progression)
        disposition_operation.addWidget(self.progression_texte)
        disposition_operation.addWidget(self.resultats, 1)

        # Amis protégés.
        self.liste_proteges = QListWidget()
        self.liste_proteges.setAccessibleName("Amis protégés")
        self.nouveau_protege = QLineEdit()
        self.nouveau_protege.setPlaceholderText("Pseudo à protéger")
        self.nouveau_protege.returnPressed.connect(self._ajouter_protege)
        ajouter = QPushButton("Protéger")
        ajouter.clicked.connect(self._ajouter_protege)
        retirer = QPushButton("Retirer")
        retirer.clicked.connect(self._retirer_protege)
        importer = QPushButton("Importer…")
        importer.setToolTip("Fichier exporté, ou un pseudo par ligne")
        importer.clicked.connect(self._importer)
        exporter = QPushButton("Exporter…")
        exporter.clicked.connect(self._exporter)
        groupe_proteges = QGroupBox("Amis protégés (jamais supprimés)")
        disposition_proteges = QVBoxLayout(groupe_proteges)
        disposition_proteges.addWidget(
            etiquette(
                "Différent de la liste blanche des demandes. La protection suit "
                "l'identifiant du compte, même si le joueur change de pseudo.",
                "description",
                retour_ligne=True,
            )
        )
        ligne_ajout = QHBoxLayout()
        ligne_ajout.addWidget(self.nouveau_protege, 1)
        ligne_ajout.addWidget(ajouter)
        disposition_proteges.addLayout(ligne_ajout)
        disposition_proteges.addWidget(self.liste_proteges, 1)
        ligne_fichiers = QHBoxLayout()
        for bouton in (retirer, importer, exporter):
            ligne_fichiers.addWidget(bouton)
        disposition_proteges.addLayout(ligne_fichiers)

        gauche = QWidget()
        disposition_gauche = QVBoxLayout(gauche)
        disposition_gauche.setContentsMargins(0, 0, 0, 0)
        disposition_gauche.addLayout(barre_haut)
        disposition_gauche.addWidget(self.table, 1)
        disposition_gauche.addLayout(barre_coches)
        disposition_gauche.addWidget(groupe_nombre)
        droite = QWidget()
        disposition_droite = QVBoxLayout(droite)
        disposition_droite.setContentsMargins(0, 0, 0, 0)
        disposition_droite.addWidget(groupe_proteges, 1)
        disposition_droite.addWidget(groupe_operation, 1)
        separateur = QSplitter()
        separateur.addWidget(gauche)
        separateur.addWidget(droite)
        separateur.setStretchFactor(0, 3)
        separateur.setStretchFactor(1, 2)

        disposition = QVBoxLayout(self)
        disposition.addWidget(etiquette("Amis", "titre"))
        disposition.addWidget(self.entete)
        disposition.addLayout(self.bandeaux)
        disposition.addWidget(separateur, 1)
        self._bandeaux_actuels: tuple = ()

    # ─── Mise à jour ───

    def actualiser(self) -> None:
        if self.gestion.version() == self._version:
            return
        vue = self.gestion.vue()
        self._version = vue.version
        if vue.compte is None:
            self.entete.setText(
                "Connectez votre compte PSN : la liste d'amis apparaîtra ici."
            )
        else:
            proteges = sum(a.protection is Verdict.PROTEGE for a in vue.amis)
            etat = (
                f"reçue le {date_courte(vue.synchronise_le)}"
                if vue.liste_complete
                else "pas encore entièrement reçue de Sony"
            )
            self.entete.setText(
                f"Compte : {vue.pseudo_compte} · {len(vue.amis)} amis · "
                f"{proteges} protégés · {vue.pseudos_manquants} pseudo(s) inconnu(s) · "
                f"liste {etat}"
            )
        if list(vue.amis) != self.modele.lignes:
            # Seulement si la liste a changé : le défilement et le tri restent.
            premiere_fois = not self.modele.lignes
            self.modele.remplacer(vue.amis)
            if premiere_fois:
                self.table.resizeColumnsToContents()
                self.table.setColumnWidth(0, max(self.table.columnWidth(0), 220))
        self.pseudos.setEnabled(vue.pseudos_manquants > 0)
        self._afficher_proteges(vue)
        self._afficher_operation(vue)
        self._afficher_bandeaux(vue)

    def _afficher_proteges(self, vue: Vue) -> None:
        self.liste_proteges.clear()
        for protection in vue.proteges:
            texte = protection.pseudo + (
                f"  (compte n°{protection.compte})"
                if protection.compte
                else "  (pseudo seulement : identifiant non trouvé)"
            )
            self.liste_proteges.addItem(texte)
            element = self.liste_proteges.item(self.liste_proteges.count() - 1)
            element.setData(Qt.ItemDataRole.UserRole, protection.cle)
        if not vue.proteges:
            self.liste_proteges.addItem("Aucun ami protégé.")

    def _afficher_operation(self, vue: Vue) -> None:
        operation = vue.operation or vue.derniere_operation
        self.annuler.setEnabled(vue.operation is not None or vue.en_file > 0)
        if operation is None:
            self.progression.setRange(0, 1)
            self.progression.setValue(0)
            texte = "Aucune suppression en cours."
            if vue.tache:
                texte = f"{vue.tache}…"
            self.progression_texte.setText(texte)
            return
        total = len(operation.cibles)
        self.progression.setRange(0, max(total, 1))
        faits = sum(
            1 for x in operation.lignes if x.resultat is not Resultat.NON_TRAITE
        )
        self.progression.setValue(faits)
        if vue.operation is not None:
            texte = f"Progression : {faits} / {total} ({operation.critere})"
        else:
            bilan = ", ".join(f"{n} {r.value}" for r, n in operation.bilan().items())
            texte = f"Dernière opération ({operation.etat}) : {bilan or 'rien'}"
            if operation.raison_arret:
                texte += f" — arrêt : {operation.raison_arret}"
        if vue.en_file:
            texte += f" · {vue.en_file} en attente"
        self.progression_texte.setText(texte)
        self.resultats.clear()
        for ligne in operation.lignes:
            detail = f" ({ligne.detail})" if ligne.detail else ""
            self.resultats.addItem(
                f"[{ligne.rang:02d}/{total:02d}] {ligne.cible.nom} — "
                f"{ligne.resultat.value}{detail}"
            )
        self.resultats.scrollToBottom()

    def _afficher_bandeaux(self, vue: Vue) -> None:
        bandeaux: list[tuple[str, str, Callable[[], None] | None]] = []
        if vue.interrompue:
            bandeaux.append(
                (
                    "attention",
                    "La dernière suppression a été interrompue (fermeture ou coupure). "
                    "Elle n'est pas reprise automatiquement ; préparez-en une nouvelle "
                    "si besoin.",
                    None,
                )
            )
        if vue.proposition is not None:
            bandeaux.append(
                (
                    "info",
                    f"Nettoyage proposé : {len(vue.proposition.cibles)} ami(s) "
                    f"({vue.proposition.critere}).",
                    self._voir_proposition,
                )
            )
        cle = tuple((n, t) for n, t, _ in bandeaux)
        if cle == self._bandeaux_actuels:
            return
        self._bandeaux_actuels = cle
        while self.bandeaux.count():
            element = self.bandeaux.takeAt(0)
            if element.layout():
                while element.layout().count():
                    sous = element.layout().takeAt(0)
                    if sous.widget():
                        sous.widget().deleteLater()
            elif element.widget():
                element.widget().deleteLater()
        for niveau, texte, action in bandeaux:
            ligne = QHBoxLayout()
            ligne.addWidget(etiquette(texte, f"bandeau_{niveau}", True), 1)
            if action is not None:
                bouton = QPushButton("Voir et confirmer…")
                bouton.clicked.connect(action)
                ligne.addWidget(bouton)
                ecarter = QPushButton("Ignorer")
                ecarter.clicked.connect(self.gestion.ecarter_proposition)
                ligne.addWidget(ecarter)
            self.bandeaux.addLayout(ligne)

    def _compter_coches(self, *_: object) -> None:
        n = len(self.modele.coches)
        self.coches.setText(f"{n} coché{'s' if n > 1 else ''}")
        self.supprimer_coches.setEnabled(n > 0)

    # ─── Actions ───

    def _erreur(self, erreur: Exception | str) -> None:
        QMessageBox.warning(self, "PSN Amis", f"Impossible : {erreur}")

    def _actualiser(self) -> None:
        self._verifier()

    def _recuperer_pseudos(self) -> None:
        try:
            self.gestion.demander_pseudos(200)
        except ValueError as erreur:
            self._erreur(erreur)
            return
        self._verifier()

    def _cocher_affiches(self, coche: bool) -> None:
        comptes = {
            self.modele.lignes[
                self.proxy.mapToSource(self.proxy.index(r, 0)).row()
            ].compte
            for r in range(self.proxy.rowCount())
        }
        self.modele.cocher(comptes, coche)

    def _lignes_cochees(self) -> list[LigneAmi]:
        return [x for x in self.modele.lignes if x.compte in self.modele.coches]

    def _proteger_coches(self) -> None:
        try:
            for ligne in self._lignes_cochees():
                self.gestion.proteger(ligne.pseudo or ligne.compte, ligne.compte)
        except ValueError as erreur:
            self._erreur(erreur)

    def _deproteger_coches(self) -> None:
        try:
            for ligne in self._lignes_cochees():
                self.gestion.deproteger(ligne.compte)
        except ValueError as erreur:
            self._erreur(erreur)

    def _ajouter_protege(self) -> None:
        pseudo = self.nouveau_protege.text().strip()
        if not pseudo:
            return
        try:
            self.gestion.proteger(pseudo)
        except ValueError as erreur:
            self._erreur(erreur)
            return
        self.nouveau_protege.clear()
        self._verifier()

    def _retirer_protege(self) -> None:
        element = self.liste_proteges.currentItem()
        cle = element.data(Qt.ItemDataRole.UserRole) if element else None
        if cle:
            self.gestion.deproteger(cle)

    def _importer(self) -> None:
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Importer des amis protégés", "", "Listes (*.json *.txt)"
        )
        if not chemin:
            return
        try:
            ajoutees = self.gestion.importer_protections(Path(chemin))
        except (OSError, ValueError) as erreur:
            self._erreur(erreur)
            return
        QMessageBox.information(
            self, "PSN Amis", f"{ajoutees} protection(s) ajoutée(s)."
        )
        self._verifier()

    def _exporter(self) -> None:
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Exporter les amis protégés", "amis-proteges.json", "JSON (*.json)"
        )
        if chemin:
            try:
                self.gestion.exporter_protections(Path(chemin))
            except (OSError, ValueError) as erreur:
                self._erreur(erreur)

    def _apercu_par_nombre(self) -> None:
        try:
            selection = self.gestion.selection(
                self.critere.currentData(), self.nombre.value()
            )
        except ValueError as erreur:
            self._erreur(erreur)
            return
        self.confirmer(selection, "manuelle")

    def _supprimer_coches(self) -> None:
        try:
            selection = self.gestion.selection_manuelle(sorted(self.modele.coches))
        except ValueError as erreur:
            self._erreur(erreur)
            return
        self.confirmer(selection, "manuelle")

    def _voir_proposition(self) -> None:
        proposition = self.gestion.vue().proposition
        if proposition is not None:
            # Recalculée : les protections ont pu changer depuis.
            try:
                selection = self.gestion.selection_manuelle(
                    [c.compte for c in proposition.cibles]
                )
            except ValueError as erreur:
                self._erreur(erreur)
                return
            selection.critere = proposition.critere
            self.confirmer(selection, "assistee")

    def confirmer(self, selection: Selection, origine: str) -> bool:
        """Aperçu, puis suppression seulement après confirmation explicite."""
        dialogue = Apercu(selection, self)
        if dialogue.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            self.gestion.demander_suppression(selection, origine)
        except ValueError as erreur:
            self._erreur(erreur)
            return False
        self.modele.cocher(set(self.modele.coches), False)
        self._verifier()
        return True
