"""Coordination de la gestion des amis entre l'interface et le moteur.

L'interface (fil principal) prépare des sélections, protège des amis et demande des
opérations ; le moteur (seul fil qui parle à Sony) les exécute une par une, entre deux
vérifications des demandes. Ainsi acceptations, synchronisations, suppressions et
nettoyage ne se chevauchent jamais, et le limiteur de débit de PSNAWP est respecté.

Les données sont rangées par compte PSN (identifiant de compte stable) :
comptes/<identifiant>/amis_connus.json, amis_proteges.json, operations.jsonl,
nettoyage.json. Changer de compte ne mélange donc rien, et une opération préparée pour
un compte n'est jamais exécutée sur un autre.
"""

from __future__ import annotations

import copy
import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from psnawp_api.core import (
    PSNAWPAuthenticationError,
    PSNAWPError,
    PSNAWPNotFoundError,
    PSNAWPTooManyRequestsError,
    PSNAWPUnauthorizedError,
)

from psn_amis import amis as amis_module
from psn_amis import chemins, nettoyage
from psn_amis.amis import (
    Contexte,
    Critere,
    Historique,
    Operation,
    Protection,
    Protections,
    Registre,
    Resultat,
    Selection,
    Verdict,
)
from psn_amis.psn import ClientPSN
from psn_amis.reglages import Reglages

journal = logging.getLogger("psn_amis")

GENRE_SUPPRESSION = "suppression"
GENRE_OPERATION = "operation"


@dataclass(frozen=True)
class LigneAmi:
    compte: str
    pseudo: str | None
    accepte_le: datetime | None
    premiere_observation: datetime | None
    derniere_observation: datetime | None
    protection: Verdict


@dataclass(frozen=True)
class Vue:
    """Photo de la gestion des amis, lue par l'interface."""

    version: int
    compte: str | None
    pseudo_compte: str | None
    amis: tuple[LigneAmi, ...]
    liste_complete: bool
    synchronise_le: datetime | None
    proteges: tuple[Protection, ...]
    operation: Operation | None
    derniere_operation: Operation | None
    interrompue: dict[str, Any] | None
    en_file: int
    tache: str
    proposition: Selection | None
    pseudos_manquants: int


@dataclass
class _Tache:
    genre: str
    description: str
    operation: Operation | None = None
    maximum: int = 0
    pseudo: str = ""


@dataclass
class Outils:
    """Ce que le moteur prête à la gestion pendant qu'elle travaille."""

    client: ClientPSN
    arret: Callable[[], bool]
    # Renouvelle l'accès à Sony si besoin (appelé entre deux suppressions).
    rafraichir: Callable[[], None] = lambda: None
    # Un ami vient d'être supprimé : (compte, pseudo affiché).
    supprime: Callable[[str, str], None] = lambda compte, nom: None
    alerter: Callable[[str, str], None] = lambda titre, texte: None


@dataclass
class _Compte:
    identifiant: str
    pseudo: str
    dossier: Path
    registre: Registre
    protections: Protections
    historique: Historique
    memoire: nettoyage.Memoire = field(default_factory=nettoyage.Memoire)


class Gestion:
    def __init__(
        self,
        dossier_donnees: Path,
        reglages: Callable[[], Reglages],
        couper_nettoyage: Callable[[str], None] = lambda raison: None,
    ) -> None:
        self._dossier = dossier_donnees
        self._reglages = reglages
        self._couper_nettoyage = couper_nettoyage
        self._verrou = threading.RLock()
        self._compte: _Compte | None = None
        self._amis: set[str] = set()
        self._complete = False
        self._synchronise_le: datetime | None = None
        self._file: deque[_Tache] = deque()
        self._annuler = threading.Event()
        self._operation: Operation | None = None
        self._derniere: Operation | None = None
        self._interrompue: dict[str, Any] | None = None
        self._tache = ""
        self._proposition: Selection | None = None
        self._proposition_le: datetime | None = None
        # Comptes supprimés par PSN Amis : leur disparition n'est pas un « retrait ».
        self._supprimes: set[str] = set()
        self._version = 0
        self._vue: Vue | None = None

    # ─── Appelé par le moteur ───

    def connecte(self, identifiant: str, pseudo: str) -> None:
        """Nouvelle connexion : change de compte si besoin (données séparées)."""
        try:
            nom = chemins.nom_de_compte_sur(identifiant)
        except ValueError:
            journal.warning(
                "Identifiant du compte PSN inconnu : la gestion des amis est "
                "indisponible pour cette connexion."
            )
            with self._verrou:
                self._compte = None
                self._changer()
            return
        with self._verrou:
            if self._compte and self._compte.identifiant == nom:
                self._compte.pseudo = pseudo
                self._changer()
                return
            if self._compte is not None:
                journal.warning(
                    "Changement de compte PSN (%s → %s) : opérations en attente "
                    "annulées, données de chaque compte gardées à part.",
                    self._compte.pseudo,
                    pseudo,
                )
            self._file.clear()
            self._proposition = None
            self._amis = set()
            self._complete = False
            self._synchronise_le = None
            self._supprimes = set()
            dossier = self._dossier / "comptes" / nom
            dossier.mkdir(parents=True, exist_ok=True)
            compte = _Compte(
                identifiant=nom,
                pseudo=pseudo,
                dossier=dossier,
                registre=Registre(dossier / "amis_connus.json"),
                protections=Protections(dossier / "amis_proteges.json"),
                historique=Historique(dossier / "operations.jsonl"),
                memoire=nettoyage.Memoire.lire(dossier / "nettoyage.json"),
            )
            self._compte = compte
            self._derniere = None
            self._interrompue = compte.historique.interrompue()
            if self._interrompue is not None:
                compte.historique.noter(
                    {
                        "type": "fin",
                        "operation": self._interrompue.get("operation"),
                        "etat": "interrompue",
                        "raison": "PSN Amis a été fermé ou coupé pendant l'opération",
                    }
                )
                journal.warning(
                    "La dernière suppression d'amis a été interrompue (fermeture ou "
                    "coupure). Elle ne reprendra pas toute seule : consultez l'onglet "
                    "Amis."
                )
            self._changer()

    def observer(self, amis: set[str], complete: bool) -> None:
        """Liste d'amis renvoyée par Sony (complète ou non)."""
        with self._verrou:
            compte = self._compte
            if compte is None:
                return
            if complete:
                self._amis = set(amis)
                self._complete = True
                self._synchronise_le = datetime.now()
                compte.registre.observer(amis, self._synchronise_le)
            else:
                self._complete = False
            self._changer()
        if complete:
            for numero, resultat in amis_module.reconcilier(
                compte.historique, amis, True
            ).items():
                nom = compte.registre.pseudo(numero) or f"compte n°{numero}"
                journal.info(
                    "Suppression à vérifier de %s : %s.",
                    nom,
                    resultat.value,
                    extra={"genre": GENRE_OPERATION},
                )
            compte.registre.enregistrer()

    def accepte(self, compte: str, pseudo: str) -> None:
        with self._verrou:
            if self._compte is None:
                return
            self._compte.registre.accepte(compte, pseudo, datetime.now())
            self._amis.add(compte)
            self._changer()

    def nommer(self, compte: str, pseudo: str) -> None:
        if pseudo.startswith("(pseudo inconnu"):
            return
        with self._verrou:
            if (
                self._compte is not None
                and self._compte.registre.pseudo(compte) != pseudo
            ):
                self._compte.registre.nommer(compte, pseudo)
                self._changer()

    def filtrer_retraits(self, comptes: list[str]) -> list[str]:
        """Retire des « amis disparus » ceux que PSN Amis a lui-même supprimés."""
        with self._verrou:
            restants = [c for c in comptes if c not in self._supprimes]
            self._supprimes -= set(comptes)
            return restants

    def travailler(self, outils: Outils) -> None:
        """Exécute les tâches en attente, puis vérifie le nettoyage automatique."""
        while not outils.arret():
            with self._verrou:
                if not self._file or self._compte is None:
                    break
                tache = self._file.popleft()
                self._tache = tache.description
                self._changer()
            try:
                self._executer(tache, outils)
            finally:
                with self._verrou:
                    self._tache = ""
                    self._changer()
        if not outils.arret():
            self._nettoyage(outils)

    # ─── Appelé par l'interface ───

    def vue(self) -> Vue:
        with self._verrou:
            # Rien n'a changé depuis la dernière photo : elle est réutilisée.
            if self._vue is not None and self._vue.version == self._version:
                return self._vue
            compte = self._compte
            lignes: tuple[LigneAmi, ...] = ()
            proteges: tuple[Protection, ...] = ()
            manquants = 0
            if compte is not None:
                fiches = compte.registre.toutes()
                construites = []
                for numero in sorted(self._amis):
                    fiche = fiches.get(numero, amis_module.Fiche(numero))
                    manquants += fiche.pseudo is None
                    construites.append(
                        LigneAmi(
                            numero,
                            fiche.pseudo,
                            fiche.accepte_le,
                            fiche.premiere_observation,
                            fiche.derniere_observation,
                            compte.protections.verdict(numero, fiche.pseudo),
                        )
                    )
                lignes = tuple(construites)
                proteges = tuple(compte.protections.toutes())
            self._vue = Vue(
                version=self._version,
                compte=compte.identifiant if compte else None,
                pseudo_compte=compte.pseudo if compte else None,
                amis=lignes,
                liste_complete=self._complete,
                synchronise_le=self._synchronise_le,
                proteges=proteges,
                operation=copy.deepcopy(self._operation),
                derniere_operation=copy.deepcopy(self._derniere),
                interrompue=self._interrompue,
                en_file=len(self._file),
                tache=self._tache,
                proposition=self._proposition,
                pseudos_manquants=manquants,
            )
            return self._vue

    def version(self) -> int:
        with self._verrou:
            return self._version

    def selection(self, critere: Critere, nombre: int) -> Selection:
        """Aperçu d'une sélection par nombre (aucune requête, aucune suppression)."""
        with self._verrou:
            compte = self._exiger_compte()
            return amis_module.selectionner(
                self._amis,
                compte.registre,
                compte.protections,
                compte.identifiant,
                critere,
                nombre,
            )

    def selection_manuelle(self, comptes: list[str]) -> Selection:
        with self._verrou:
            compte = self._exiger_compte()
            return amis_module.selection_manuelle(
                comptes,
                self._amis,
                compte.registre,
                compte.protections,
                compte.identifiant,
            )

    def demander_suppression(
        self, selection: Selection, origine: str = "manuelle"
    ) -> Operation:
        """Met une suppression confirmée dans la file du moteur."""
        reglages = self._reglages()
        with self._verrou:
            compte = self._exiger_compte()
            if not self._complete:
                raise ValueError(
                    "la liste d'amis n'a pas encore été entièrement reçue de Sony"
                )
            if not selection.cibles:
                raise ValueError("aucun ami supprimable dans la sélection")
            if len(selection.cibles) > reglages.suppression_max:
                raise ValueError(
                    f"au plus {reglages.suppression_max} amis par opération "
                    "(réglage « Suppressions par opération »)"
                )
            operation = Operation(
                compte_proprietaire=compte.identifiant,
                cibles=list(selection.cibles),
                critere=selection.critere,
                origine=origine,
            )
            self._annuler.clear()
            self._file.append(
                _Tache(
                    "suppression",
                    f"Suppression de {len(operation.cibles)} ami(s)",
                    operation=operation,
                )
            )
            if origine == "assistee":
                self._proposition = None
            self._changer()
        journal.info(
            "Suppression de %d ami(s) demandée (%s).",
            len(operation.cibles),
            selection.critere,
            extra={"genre": GENRE_OPERATION},
        )
        return operation

    def annuler(self) -> None:
        """Vide la file et arrête l'opération en cours après l'ami en cours."""
        with self._verrou:
            annulees = sum(t.genre == "suppression" for t in self._file)
            self._file = deque(t for t in self._file if t.genre != "suppression")
            self._annuler.set()
            self._changer()
        journal.info(
            "Suppressions annulées%s.",
            f" ({annulees} opération(s) en attente retirée(s))" if annulees else "",
            extra={"genre": GENRE_OPERATION},
        )

    def ecarter_proposition(self) -> None:
        with self._verrou:
            self._proposition = None
            self._changer()

    def demander_pseudos(self, maximum: int) -> None:
        with self._verrou:
            self._exiger_compte()
            if any(t.genre == "pseudos" for t in self._file):
                return
            self._file.append(
                _Tache("pseudos", "Récupération des pseudos", maximum=maximum)
            )
            self._changer()

    def proteger(self, pseudo: str, compte: str | None = None) -> Protection:
        """Protège un ami. Le pseudo est d'abord cherché parmi les amis connus, puis,
        si besoin, auprès de Sony (par le moteur) ; en attendant, la protection
        textuelle s'applique déjà."""
        with self._verrou:
            donnees = self._exiger_compte()
            if compte is None:
                cible = pseudo.strip().casefold()
                trouves = [
                    f.compte
                    for f in donnees.registre.toutes().values()
                    if f.pseudo and f.pseudo.casefold() == cible
                ]
                if len(trouves) == 1:
                    compte = trouves[0]
            protection = donnees.protections.ajouter(pseudo, compte)
            if compte is None:
                self._file.append(
                    _Tache("resoudre", f"Recherche de {pseudo}", pseudo=pseudo)
                )
            self._changer()
            return protection

    def deproteger(self, cle: str) -> bool:
        with self._verrou:
            retiree = self._exiger_compte().protections.retirer(cle)
            self._changer()
            return retiree

    def importer_protections(self, chemin: Path) -> int:
        with self._verrou:
            ajoutees = self._exiger_compte().protections.importer(chemin)
            self._changer()
            return ajoutees

    def exporter_protections(self, chemin: Path) -> None:
        with self._verrou:
            self._exiger_compte().protections.exporter(chemin)

    def dossier_compte(self) -> Path | None:
        with self._verrou:
            return self._compte.dossier if self._compte else None

    # ─── Interne ───

    def _exiger_compte(self) -> _Compte:
        if self._compte is None:
            raise ValueError("aucun compte PSN connecté pour l'instant")
        return self._compte

    def _changer(self) -> None:
        self._version += 1

    def _executer(self, tache: _Tache, outils: Outils) -> None:
        with self._verrou:
            compte = self._compte
        if compte is None:
            return
        if tache.genre == "suppression" and tache.operation is not None:
            self._suppression(tache.operation, compte, outils)
        elif tache.genre == "pseudos":
            self._pseudos(tache.maximum, compte, outils)
        elif tache.genre == "resoudre":
            self._resoudre(tache.pseudo, compte, outils)

    def _suppression(
        self, operation: Operation, compte: _Compte, outils: Outils
    ) -> None:
        with self._verrou:
            self._operation = operation
            self._annuler.clear()
            self._changer()
        reglages = self._reglages()

        def rapporter(operation: Operation, ligne: amis_module.Ligne) -> None:
            journal.info(
                "[%02d/%02d] %s — %s%s",
                ligne.rang,
                len(operation.cibles),
                ligne.cible.nom,
                ligne.resultat.value,
                f" ({ligne.detail})" if ligne.detail else "",
                extra={"genre": GENRE_OPERATION},
            )
            with self._verrou:
                self._changer()

        def supprime(numero: str) -> None:
            nom = compte.registre.pseudo(numero) or f"compte n°{numero}"
            with self._verrou:
                self._supprimes.add(numero)
                self._amis.discard(numero)
            outils.supprime(numero, nom)

        def attendre(secondes: float) -> bool:
            if amis_module.attente_interruptible(
                lambda: self._annuler.is_set() or outils.arret(), secondes
            ):
                return True
            outils.rafraichir()
            return False

        contexte = Contexte(
            client=outils.client,
            compte_connecte=compte.identifiant,
            registre=compte.registre,
            protections=compte.protections,
            historique=compte.historique,
            attendre=attendre,
            annulee=lambda: self._annuler.is_set() or outils.arret(),
            pause=reglages.suppression_pause,
            rapporter=rapporter,
            supprime=supprime,
        )
        try:
            amis_module.executer(operation, contexte)
        finally:
            bilan = operation.bilan()
            with self._verrou:
                self._operation = None
                self._derniere = operation
                if operation.origine == "nettoyage":
                    compte.memoire.noter(
                        datetime.now(), bilan.get(Resultat.SUPPRIME, 0)
                    )
                    compte.memoire.ecrire(compte.dossier / "nettoyage.json")
                self._changer()
        resume = ", ".join(f"{n} {r.value}" for r, n in bilan.items()) or "rien"
        journal.info(
            "Bilan de la suppression : %s%s.",
            resume,
            f" — arrêt : {operation.raison_arret}" if operation.raison_arret else "",
            extra={"genre": GENRE_OPERATION},
        )

    def _pseudos(self, maximum: int, compte: _Compte, outils: Outils) -> None:
        with self._verrou:
            manquants = [c for c in sorted(self._amis) if not compte.registre.pseudo(c)]
        trouves = 0
        for numero in manquants[:maximum]:
            if outils.arret() or self._annuler.is_set():
                break
            try:
                compte.registre.nommer(numero, outils.client.pseudo(numero))
                trouves += 1
            except PSNAWPNotFoundError:
                continue
            except (
                PSNAWPAuthenticationError,
                PSNAWPUnauthorizedError,
                PSNAWPTooManyRequestsError,
            ):
                break
            except (requests.RequestException, PSNAWPError) as erreur:
                journal.debug("Pseudo de %s introuvable : %s", numero, erreur)
                break
            if trouves % 20 == 0:
                compte.registre.enregistrer()
                with self._verrou:
                    self._changer()
        compte.registre.enregistrer()
        with self._verrou:
            self._changer()
        journal.info(
            "%d pseudo(s) récupéré(s) auprès de Sony.",
            trouves,
            extra={"genre": GENRE_OPERATION},
        )

    def _resoudre(self, pseudo: str, compte: _Compte, outils: Outils) -> None:
        try:
            numero, exact = outils.client.chercher(pseudo)
        except PSNAWPNotFoundError:
            journal.warning(
                "Aucun compte PSN ne s'appelle « %s » : la protection reste attachée "
                "à ce pseudo exact (si le joueur en change, elle ne le suivra pas).",
                pseudo,
            )
            return
        except (requests.RequestException, PSNAWPError) as erreur:
            journal.warning(
                "Recherche de « %s » impossible pour l'instant (%s) : protection "
                "gardée par pseudo.",
                pseudo,
                type(erreur).__name__,
            )
            return
        with self._verrou:
            compte.protections.ajouter(exact, numero)
            compte.registre.nommer(numero, exact)
            self._changer()
        journal.info(
            "%s est protégé (compte n°%s identifié).",
            exact,
            numero,
            extra={"genre": GENRE_OPERATION},
        )

    def _nettoyage(self, outils: Outils) -> None:
        reglages = self._reglages()
        maintenant = datetime.now()
        with self._verrou:
            compte = self._compte
            if compte is None or not self._complete or self._operation is not None:
                return
            nombre_amis = len(self._amis)
            compte.memoire.nouveau_jour_si_besoin(maintenant)
            decision = nettoyage.decider(
                reglages, nombre_amis, compte.memoire, maintenant
            )
        if decision.couper:
            journal.warning("%s", decision.raison)
            outils.alerter("PSN Amis : nettoyage arrêté", decision.raison)
            self._couper_nettoyage(decision.raison)
            return
        if decision.nombre <= 0:
            return
        critere = Critere(reglages.nettoyage_critere)
        selection = self.selection(critere, decision.nombre)
        if not selection.cibles:
            return
        if reglages.nettoyage_mode == "assiste":
            with self._verrou:
                if self._proposition is not None:
                    return
                self._proposition = selection
                self._proposition_le = maintenant
                compte.memoire.noter(maintenant, 0)
                compte.memoire.ecrire(compte.dossier / "nettoyage.json")
                self._changer()
            journal.info(
                "Nettoyage proposé : %d ami(s) à supprimer (%s). Confirmez dans "
                "l'onglet Amis.",
                len(selection.cibles),
                decision.raison,
                extra={"genre": GENRE_OPERATION},
            )
            outils.alerter(
                "PSN Amis : nettoyage proposé",
                f"{len(selection.cibles)} ami(s) proposés à la suppression.",
            )
            return
        journal.info(
            "Nettoyage automatique : %d ami(s) (%s).",
            len(selection.cibles),
            decision.raison,
            extra={"genre": GENRE_OPERATION},
        )
        operation = Operation(
            compte_proprietaire=compte.identifiant,
            cibles=list(selection.cibles),
            critere=selection.critere,
            origine="nettoyage",
        )
        self._suppression(operation, compte, outils)
