"""Gestion des amis : registre local, amis protégés, sélection et suppressions.

Ce module ne contacte jamais Sony lui-même : les suppressions passent par un ClientPSN
(psn.py) fourni par le moteur, seul fil autorisé à envoyer des requêtes.

Règles de sécurité appliquées par le service (et pas seulement par l'interface) :
- un ami protégé n'est jamais supprimé, la protection est revérifiée juste avant
  chaque suppression (une protection ajoutée pendant l'opération compte) ;
- le compte connecté n'est jamais une cible ; une opération préparée pour un autre
  compte n'est jamais exécutée ;
- l'identité est vérifiée par l'identifiant de compte (stable), et la relation
  « ami » est vérifiée auprès de Sony juste avant la suppression ;
- en cas de doute (pseudo inconnu face à une protection textuelle, réponse ambiguë),
  rien n'est supprimé, ou le résultat est marqué « à vérifier » sans nouvel essai.

Les dates affichées ne sont jamais inventées : « acceptée le » n'est connue que pour
les demandes acceptées par PSN Amis, « vu pour la première fois » est la date à
laquelle PSN Amis a vu l'ami dans la liste (pas la date d'amitié réelle).
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import requests
from psnawp_api.core import (
    PSNAWPAuthenticationError,
    PSNAWPClientError,
    PSNAWPError,
    PSNAWPNotFoundError,
    PSNAWPServerError,
    PSNAWPTooManyRequestsError,
    PSNAWPUnauthorizedError,
)

from psn_amis.psn import ClientPSN, ReponseInattendue
from psn_amis.reglages import ecrire_atomique

FORMAT_DATE = "%Y-%m-%dT%H:%M:%S"


def _date(texte: object) -> datetime | None:
    if not isinstance(texte, str):
        return None
    try:
        return datetime.strptime(texte, FORMAT_DATE)
    except ValueError:
        return None


def _texte(moment: datetime | None) -> str | None:
    return moment.strftime(FORMAT_DATE) if moment else None


def _lire_json(chemin: Path) -> Any:
    """Contenu d'un fichier JSON ; None s'il est absent. Un fichier abîmé est mis de
    côté (renommé en .abime) plutôt qu'écrasé : rien n'est perdu."""
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except OSError, ValueError:
        abime = chemin.with_name(chemin.name + ".abime")
        with contextlib.suppress(OSError):
            chemin.replace(abime)
        return None


# ─── Registre : ce que PSN Amis sait de chaque ami ────────────────────────────


@dataclass
class Fiche:
    compte: str
    pseudo: str | None = None
    # Demande acceptée par PSN Amis à ce moment (sinon inconnu).
    accepte_le: datetime | None = None
    premiere_observation: datetime | None = None
    derniere_observation: datetime | None = None


class Registre:
    """Fiches des amis d'un compte, gardées dans amis_connus.json."""

    def __init__(self, chemin: Path) -> None:
        self.chemin = chemin
        self._verrou = threading.RLock()
        self._fiches: dict[str, Fiche] = {}
        self._modifie = False
        contenu = _lire_json(chemin)
        if isinstance(contenu, dict):
            for compte, brut in contenu.get("amis", {}).items():
                if isinstance(compte, str) and isinstance(brut, dict):
                    pseudo = brut.get("pseudo")
                    self._fiches[compte] = Fiche(
                        compte,
                        pseudo if isinstance(pseudo, str) else None,
                        _date(brut.get("accepte_le")),
                        _date(brut.get("premiere")),
                        _date(brut.get("derniere")),
                    )

    def fiche(self, compte: str) -> Fiche:
        with self._verrou:
            if compte not in self._fiches:
                self._fiches[compte] = Fiche(compte)
            return self._fiches[compte]

    def pseudo(self, compte: str) -> str | None:
        with self._verrou:
            fiche = self._fiches.get(compte)
            return fiche.pseudo if fiche else None

    def nommer(self, compte: str, pseudo: str) -> None:
        with self._verrou:
            fiche = self.fiche(compte)
            if pseudo and fiche.pseudo != pseudo:
                fiche.pseudo = pseudo
                self._modifie = True

    def accepte(self, compte: str, pseudo: str, moment: datetime) -> None:
        with self._verrou:
            fiche = self.fiche(compte)
            fiche.pseudo = pseudo or fiche.pseudo
            fiche.accepte_le = moment
            fiche.premiere_observation = fiche.premiere_observation or moment
            fiche.derniere_observation = moment
            self._modifie = True

    def observer(self, comptes: Iterable[str], moment: datetime) -> None:
        """Les amis présents dans une liste complète renvoyée par Sony."""
        with self._verrou:
            for compte in comptes:
                fiche = self.fiche(compte)
                fiche.premiere_observation = fiche.premiere_observation or moment
                fiche.derniere_observation = moment
            self._modifie = True

    def importer_dates(self, acceptations: dict[str, datetime]) -> None:
        """Dates d'acceptation retrouvées dans l'ancien journal (par pseudo)."""
        with self._verrou:
            par_pseudo = {
                f.pseudo.casefold(): f for f in self._fiches.values() if f.pseudo
            }
            for pseudo, moment in acceptations.items():
                fiche = par_pseudo.get(pseudo.casefold())
                if fiche and fiche.accepte_le is None:
                    fiche.accepte_le = moment
                    self._modifie = True

    def toutes(self) -> dict[str, Fiche]:
        with self._verrou:
            return {c: Fiche(**asdict(f)) for c, f in self._fiches.items()}

    def enregistrer(self) -> None:
        with self._verrou:
            if not self._modifie:
                return
            contenu = {
                "amis": {
                    compte: {
                        "pseudo": f.pseudo,
                        "accepte_le": _texte(f.accepte_le),
                        "premiere": _texte(f.premiere_observation),
                        "derniere": _texte(f.derniere_observation),
                    }
                    for compte, f in sorted(self._fiches.items())
                }
            }
            ecrire_atomique(self.chemin, json.dumps(contenu, ensure_ascii=False))
            self._modifie = False


# ─── Amis protégés ────────────────────────────────────────────────────────────


class Verdict(StrEnum):
    LIBRE = "non protégé"
    PROTEGE = "protégé"
    # Protection textuelle sans pseudo connu pour comparer : on ne supprime pas.
    DOUTE = "protection incertaine"


@dataclass
class Protection:
    pseudo: str
    # Identifiant de compte PSN (stable) ; None si le pseudo n'a pas pu être résolu.
    compte: str | None = None
    ajoutee_le: datetime | None = None
    note: str = ""

    @property
    def cle(self) -> str:
        return self.compte or f"pseudo:{self.pseudo.casefold()}"


class Protections:
    """Liste des amis protégés d'un compte, gardée dans amis_proteges.json.

    Différente de la « liste blanche » des réglages, qui sert seulement à choisir les
    demandes acceptées.
    """

    def __init__(self, chemin: Path) -> None:
        self.chemin = chemin
        self._verrou = threading.RLock()
        self._liste: dict[str, Protection] = {}
        contenu = _lire_json(chemin)
        if isinstance(contenu, dict):
            for brut in contenu.get("proteges", []):
                if isinstance(brut, dict) and isinstance(brut.get("pseudo"), str):
                    compte = brut.get("compte")
                    protection = Protection(
                        brut["pseudo"],
                        compte if isinstance(compte, str) and compte else None,
                        _date(brut.get("ajoutee_le")),
                        str(brut.get("note", "")),
                    )
                    self._liste[protection.cle] = protection

    def toutes(self) -> list[Protection]:
        with self._verrou:
            return sorted(self._liste.values(), key=lambda p: p.pseudo.casefold())

    def textuelles(self) -> bool:
        """Au moins une protection n'a qu'un pseudo (identifiant inconnu)."""
        with self._verrou:
            return any(p.compte is None for p in self._liste.values())

    def ajouter(
        self, pseudo: str, compte: str | None = None, note: str = ""
    ) -> Protection:
        pseudo = pseudo.strip()
        if not pseudo and not compte:
            raise ValueError("pseudo vide")
        with self._verrou:
            # Une protection textuelle devient précise quand l'identifiant est connu.
            self._liste.pop(f"pseudo:{pseudo.casefold()}", None)
            protection = Protection(
                pseudo or compte or "", compte, datetime.now(), note
            )
            ancienne = self._liste.get(protection.cle)
            if ancienne is not None:
                protection.ajoutee_le = ancienne.ajoutee_le or protection.ajoutee_le
                protection.note = note or ancienne.note
            self._liste[protection.cle] = protection
            self._enregistrer()
            return protection

    def retirer(self, cle: str) -> bool:
        with self._verrou:
            retiree = self._liste.pop(cle, None) is not None
            if retiree:
                self._enregistrer()
            return retiree

    def verdict(self, compte: str, pseudo: str | None) -> Verdict:
        """Le compte est-il protégé ? Vérifié par identifiant, puis par pseudo exact."""
        with self._verrou:
            if compte in self._liste:
                return Verdict.PROTEGE
            textuelles = [p for p in self._liste.values() if p.compte is None]
            if not textuelles:
                return Verdict.LIBRE
            if pseudo is None:
                return Verdict.DOUTE
            cible = pseudo.casefold()
            if any(p.pseudo.casefold() == cible for p in textuelles):
                return Verdict.PROTEGE
            return Verdict.LIBRE

    def exporter(self, chemin: Path) -> None:
        ecrire_atomique(chemin, self._en_json())

    def importer(self, chemin: Path) -> int:
        """Ajoute les protections d'un fichier : JSON exporté, ou un pseudo par ligne.
        Renvoie le nombre de protections ajoutées."""
        texte = chemin.read_text(encoding="utf-8-sig")
        entrees: list[tuple[str, str | None]] = []
        try:
            contenu = json.loads(texte)
        except ValueError:
            contenu = None
        if isinstance(contenu, dict):
            for brut in contenu.get("proteges", []):
                if isinstance(brut, dict) and isinstance(brut.get("pseudo"), str):
                    compte = brut.get("compte")
                    entrees.append(
                        (brut["pseudo"], compte if isinstance(compte, str) else None)
                    )
        else:
            for ligne in texte.splitlines():
                ligne = ligne.split("#", 1)[0].strip()
                if ligne:
                    entrees.append((ligne, None))
        avant = len(self._liste)
        for pseudo, compte in entrees:
            self.ajouter(pseudo, compte)
        return len(self._liste) - avant

    def _en_json(self) -> str:
        return json.dumps(
            {
                "proteges": [
                    {
                        "pseudo": p.pseudo,
                        "compte": p.compte,
                        "ajoutee_le": _texte(p.ajoutee_le),
                        "note": p.note,
                    }
                    for p in self.toutes()
                ]
            },
            ensure_ascii=False,
            indent=2,
        )

    def _enregistrer(self) -> None:
        ecrire_atomique(self.chemin, self._en_json())


# ─── Sélection et aperçu ──────────────────────────────────────────────────────


class Critere(StrEnum):
    PLUS_ANCIENS_ACCEPTES = "plus_anciens_acceptes"
    PREMIERE_OBSERVATION = "premiere_observation"
    ALPHABETIQUE = "alphabetique"


EXPLICATIONS_CRITERES = {
    Critere.PLUS_ANCIENS_ACCEPTES: (
        "les amis dont PSN Amis a accepté la demande il y a le plus longtemps "
        "(seuls les amis dont la date d'acceptation est connue sont concernés)"
    ),
    Critere.PREMIERE_OBSERVATION: (
        "les amis que PSN Amis a vus en premier dans votre liste (date de première "
        "observation, qui n'est pas la date d'amitié réelle)"
    ),
    Critere.ALPHABETIQUE: (
        "l'ordre alphabétique des pseudos (seuls les amis dont le pseudo est connu "
        "sont concernés)"
    ),
}


@dataclass(frozen=True)
class Cible:
    compte: str
    pseudo: str | None

    @property
    def nom(self) -> str:
        return self.pseudo or f"compte n°{self.compte}"


@dataclass
class Selection:
    critere: str
    cibles: list[Cible]
    total_amis: int
    proteges: int
    incertains: int
    # Amis écartés parce que le critère n'a pas de donnée fiable pour eux.
    sans_donnee: int
    demandes: int
    avertissements: list[str] = field(default_factory=list)

    @property
    def supprimables(self) -> int:
        return len(self.cibles)

    @property
    def requetes(self) -> int:
        """Estimation : vérification de la relation puis suppression, par ami."""
        return 2 * len(self.cibles)


def selectionner(
    amis: Iterable[str],
    registre: Registre,
    protections: Protections,
    compte_connecte: str,
    critere: Critere,
    nombre: int,
) -> Selection:
    """Choisit au plus `nombre` amis non protégés selon un critère explicite."""
    fiches = registre.toutes()
    amis = sorted(set(amis))
    libres: list[Fiche] = []
    proteges = incertains = 0
    for compte in amis:
        if compte == compte_connecte:
            continue
        fiche = fiches.get(compte, Fiche(compte))
        verdict = protections.verdict(compte, fiche.pseudo)
        if verdict is Verdict.PROTEGE:
            proteges += 1
        elif verdict is Verdict.DOUTE:
            incertains += 1
        else:
            libres.append(fiche)

    if critere is Critere.PLUS_ANCIENS_ACCEPTES:
        avec = [f for f in libres if f.accepte_le]
        avec.sort(key=lambda f: (f.accepte_le, f.compte))
    elif critere is Critere.PREMIERE_OBSERVATION:
        avec = [f for f in libres if f.premiere_observation]
        avec.sort(key=lambda f: (f.premiere_observation, f.compte))
    else:
        avec = [f for f in libres if f.pseudo]
        avec.sort(key=lambda f: ((f.pseudo or "").casefold(), f.compte))
    choisis = avec[: max(0, nombre)]
    selection = Selection(
        critere=EXPLICATIONS_CRITERES[critere],
        cibles=[Cible(f.compte, f.pseudo) for f in choisis],
        total_amis=len(amis),
        proteges=proteges,
        incertains=incertains,
        sans_donnee=len(libres) - len(avec),
        demandes=nombre,
    )
    if len(choisis) < nombre:
        selection.avertissements.append(
            f"Seulement {len(choisis)} ami(s) correspondent au critère "
            f"(sur {nombre} demandés)."
        )
    if incertains:
        selection.avertissements.append(
            f"{incertains} ami(s) écarté(s) : pseudo inconnu alors qu'une protection "
            "n'est connue que par son pseudo. Récupérez les pseudos pour les départager."
        )
    return selection


def selection_manuelle(
    comptes: Iterable[str],
    amis: Iterable[str],
    registre: Registre,
    protections: Protections,
    compte_connecte: str,
) -> Selection:
    """Les amis cochés à la main, protégés et compte connecté retirés."""
    fiches = registre.toutes()
    amis = set(amis)
    cibles: list[Cible] = []
    proteges = incertains = 0
    demandes = 0
    for compte in dict.fromkeys(comptes):
        demandes += 1
        if compte == compte_connecte or compte not in amis:
            continue
        pseudo = fiches.get(compte, Fiche(compte)).pseudo
        verdict = protections.verdict(compte, pseudo)
        if verdict is Verdict.PROTEGE:
            proteges += 1
        elif verdict is Verdict.DOUTE:
            incertains += 1
        else:
            cibles.append(Cible(compte, pseudo))
    selection = Selection(
        critere="les amis choisis à la main",
        cibles=cibles,
        total_amis=len(amis),
        proteges=proteges,
        incertains=incertains,
        sans_donnee=0,
        demandes=demandes,
    )
    if proteges or incertains:
        selection.avertissements.append(
            f"{proteges + incertains} ami(s) protégé(s) ou incertain(s) retiré(s) de "
            "la sélection."
        )
    return selection


# ─── Exécution des suppressions ───────────────────────────────────────────────


class Resultat(StrEnum):
    SUPPRIME = "supprimé"
    A_VERIFIER = "à vérifier"
    DEJA_RETIRE = "n'était plus ami"
    PROTEGE = "protégé, ignoré"
    INCERTAIN = "protection incertaine, ignoré"
    REFUSE = "refusé (compte non valable)"
    ERREUR = "erreur"
    NON_TRAITE = "non traité"
    # Après coup, d'après la liste renvoyée par Sony.
    CONFIRME = "supprimé (confirmé par la liste)"
    TOUJOURS_AMI = "toujours ami (échec)"


@dataclass
class Ligne:
    rang: int
    cible: Cible
    resultat: Resultat
    detail: str = ""


@dataclass
class Operation:
    """Une suppression d'amis demandée par l'utilisateur (ou le nettoyage)."""

    compte_proprietaire: str
    cibles: list[Cible]
    critere: str
    origine: str = "manuelle"
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    creee_le: datetime = field(default_factory=datetime.now)
    lignes: list[Ligne] = field(default_factory=list)
    etat: str = "en attente"
    raison_arret: str = ""

    @property
    def traites(self) -> int:
        return len(self.lignes)

    def bilan(self) -> dict[Resultat, int]:
        compte: dict[Resultat, int] = {}
        for ligne in self.lignes:
            compte[ligne.resultat] = compte.get(ligne.resultat, 0) + 1
        return compte


class Historique:
    """Journal des opérations d'un compte (operations.jsonl, une ligne par événement).

    Il sert à consulter la dernière opération et à repérer une opération interrompue
    (fermeture, coupure) : elle n'est jamais reprise sans nouvelle confirmation.
    """

    def __init__(self, chemin: Path) -> None:
        self.chemin = chemin
        self._verrou = threading.Lock()

    def noter(self, evenement: dict[str, Any]) -> None:
        evenement = {"moment": _texte(datetime.now()), **evenement}
        with self._verrou:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            with self.chemin.open("a", encoding="utf-8") as fichier:
                fichier.write(json.dumps(evenement, ensure_ascii=False) + "\n")

    def evenements(self) -> list[dict[str, Any]]:
        try:
            lignes = self.chemin.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        sortie = []
        for ligne in lignes:
            try:
                brut = json.loads(ligne)
            except ValueError:
                continue
            if isinstance(brut, dict):
                sortie.append(brut)
        return sortie

    def a_verifier(self) -> dict[str, str]:
        """Suppressions au résultat ambigu pas encore réconciliées : compte → id op."""
        ouvertes: dict[str, str] = {}
        for evenement in self.evenements():
            compte = evenement.get("compte")
            if not isinstance(compte, str):
                continue
            if evenement.get("resultat") == Resultat.A_VERIFIER:
                ouvertes[compte] = str(evenement.get("operation", ""))
            elif evenement.get("type") == "reconciliation":
                ouvertes.pop(compte, None)
        return ouvertes

    def interrompue(self) -> dict[str, Any] | None:
        """La dernière opération commencée sans ligne de fin, s'il y en a une."""
        debuts: dict[str, dict[str, Any]] = {}
        for evenement in self.evenements():
            identifiant = evenement.get("operation")
            if evenement.get("type") == "debut" and isinstance(identifiant, str):
                debuts[identifiant] = evenement
            elif evenement.get("type") == "fin":
                debuts.pop(str(identifiant), None)
        return list(debuts.values())[-1] if debuts else None

    def supprimes_le(self, jour: str, origine: str | None = None) -> int:
        """Nombre de suppressions réussies un jour donné (AAAA-MM-JJ)."""
        total = 0
        for evenement in self.evenements():
            if (
                evenement.get("type") == "ligne"
                and evenement.get("resultat") == Resultat.SUPPRIME
                and str(evenement.get("moment", "")).startswith(jour)
                and (origine is None or evenement.get("origine") == origine)
            ):
                total += 1
        return total


class ArretOperation(Exception):
    """L'opération ne peut pas continuer (session, limite de Sony, compte changé)."""


ERREURS_RESEAU = (requests.RequestException,)
# Après ce nombre d'erreurs réseau de suite, l'opération s'arrête (pas d'acharnement).
ERREURS_AVANT_ARRET = 3


@dataclass
class Contexte:
    """Ce dont l'exécution a besoin, fourni par le moteur."""

    client: ClientPSN
    compte_connecte: str
    registre: Registre
    protections: Protections
    historique: Historique
    # Attend un nombre de secondes ; renvoie True si l'opération doit s'arrêter.
    attendre: Callable[[float], bool]
    annulee: Callable[[], bool]
    pause: float
    # Appelé après chaque ami traité (progression visible).
    rapporter: Callable[[Operation, Ligne], None] = lambda operation, ligne: None
    # Compte → appelé après une suppression réussie (mise à jour du moteur).
    supprime: Callable[[str], None] = lambda compte: None


def _verifier_cible(
    contexte: Contexte, operation: Operation, cible: Cible
) -> tuple[Resultat, str] | None:
    """Contrôles faits avant toute requête ; un résultat si la cible est écartée."""
    if contexte.compte_connecte != operation.compte_proprietaire:
        raise ArretOperation(
            "le compte connecté a changé : opération préparée pour un autre compte"
        )
    if not cible.compte or cible.compte == contexte.compte_connecte:
        return Resultat.REFUSE, "le compte connecté ne peut pas être supprimé"
    pseudo = contexte.registre.pseudo(cible.compte) or cible.pseudo
    verdict = contexte.protections.verdict(cible.compte, pseudo)
    if verdict is Verdict.PROTEGE:
        return Resultat.PROTEGE, ""
    if verdict is Verdict.DOUTE:
        return Resultat.INCERTAIN, "pseudo inconnu"
    return None


def _supprimer_un(
    contexte: Contexte, operation: Operation, cible: Cible
) -> tuple[Resultat, str]:
    ecart = _verifier_cible(contexte, operation, cible)
    if ecart:
        return ecart
    client = contexte.client
    try:
        # Protection textuelle : le pseudo actuel est relu (il a pu changer).
        if contexte.protections.textuelles():
            pseudo = client.pseudo(cible.compte)
            contexte.registre.nommer(cible.compte, pseudo)
            verdict = contexte.protections.verdict(cible.compte, pseudo)
            if verdict is not Verdict.LIBRE:
                return Resultat.PROTEGE, f"protégé sous le pseudo {pseudo}"
        relation = client.relation(cible.compte)
    except PSNAWPNotFoundError:
        return Resultat.DEJA_RETIRE, "compte introuvable"
    except ReponseInattendue as erreur:
        return Resultat.ERREUR, f"réponse inattendue de Sony ({erreur})"
    if not relation.est_ami:
        return Resultat.DEJA_RETIRE, ""
    # Dernière vérification juste avant l'opération destructive.
    ecart = _verifier_cible(contexte, operation, cible)
    if ecart:
        return ecart
    try:
        client.supprimer(cible.compte)
    except PSNAWPNotFoundError:
        return Resultat.DEJA_RETIRE, ""
    except ERREURS_RESEAU as erreur:
        # La demande a peut-être été traitée : jamais renvoyée à l'aveugle.
        return Resultat.A_VERIFIER, f"réponse non reçue ({type(erreur).__name__})"
    contexte.supprime(cible.compte)
    return Resultat.SUPPRIME, ""


def executer(operation: Operation, contexte: Contexte) -> Operation:
    """Supprime les amis de l'opération un par un, avec une pause entre chacun."""
    historique = contexte.historique
    operation.etat = "en cours"
    historique.noter(
        {
            "type": "debut",
            "operation": operation.identifiant,
            "origine": operation.origine,
            "critere": operation.critere,
            "nombre": len(operation.cibles),
            "proprietaire": operation.compte_proprietaire,
        }
    )
    erreurs_de_suite = 0
    try:
        for rang, cible in enumerate(operation.cibles, start=1):
            if contexte.annulee():
                operation.raison_arret = "annulée"
                break
            try:
                resultat, detail = _supprimer_un(contexte, operation, cible)
            except (PSNAWPAuthenticationError, PSNAWPUnauthorizedError) as erreur:
                raise ArretOperation("session Sony expirée") from erreur
            except PSNAWPTooManyRequestsError as erreur:
                raise ArretOperation("Sony demande de ralentir") from erreur
            except ERREURS_RESEAU as erreur:
                resultat, detail = Resultat.ERREUR, f"réseau ({type(erreur).__name__})"
            except (PSNAWPServerError, PSNAWPClientError, PSNAWPError) as erreur:
                texte = getattr(erreur, "message", None) or type(erreur).__name__
                resultat, detail = Resultat.ERREUR, f"Sony : {texte}"
            ligne = Ligne(rang, cible, resultat, detail)
            operation.lignes.append(ligne)
            historique.noter(
                {
                    "type": "ligne",
                    "operation": operation.identifiant,
                    "origine": operation.origine,
                    "compte": cible.compte,
                    "pseudo": cible.pseudo,
                    "resultat": resultat.value,
                    "detail": detail,
                }
            )
            contexte.rapporter(operation, ligne)
            if resultat is Resultat.ERREUR and detail.startswith("réseau"):
                erreurs_de_suite += 1
                if erreurs_de_suite >= ERREURS_AVANT_ARRET:
                    operation.raison_arret = "erreurs réseau répétées"
                    break
            else:
                erreurs_de_suite = 0
            requete_faite = resultat not in (
                Resultat.PROTEGE,
                Resultat.INCERTAIN,
                Resultat.REFUSE,
            )
            if (
                rang < len(operation.cibles)
                and requete_faite
                and contexte.attendre(contexte.pause)
            ):
                operation.raison_arret = "annulée"
                break
    except ArretOperation as arret:
        operation.raison_arret = str(arret)
    finally:
        restants = operation.cibles[operation.traites :]
        for rang, cible in enumerate(restants, start=operation.traites + 1):
            operation.lignes.append(Ligne(rang, cible, Resultat.NON_TRAITE))
        operation.etat = "terminée" if not operation.raison_arret else "arrêtée"
        historique.noter(
            {
                "type": "fin",
                "operation": operation.identifiant,
                "etat": operation.etat,
                "raison": operation.raison_arret,
                "bilan": {r.value: n for r, n in operation.bilan().items()},
            }
        )
        contexte.registre.enregistrer()
    return operation


def reconcilier(
    historique: Historique, amis: set[str], liste_complete: bool
) -> dict[str, Resultat]:
    """Compare les suppressions « à vérifier » à une liste d'amis renvoyée par Sony.

    Une liste partielle ne prouve rien : elle est ignorée.
    """
    if not liste_complete:
        return {}
    conclusions: dict[str, Resultat] = {}
    for compte, operation in historique.a_verifier().items():
        resultat = Resultat.TOUJOURS_AMI if compte in amis else Resultat.CONFIRME
        conclusions[compte] = resultat
        historique.noter(
            {
                "type": "reconciliation",
                "operation": operation,
                "compte": compte,
                "resultat": resultat.value,
            }
        )
    return conclusions


def attente_interruptible(
    est_arrete: Callable[[], bool], secondes: float, pas: float = 0.2
) -> bool:
    """Attend `secondes` en vérifiant régulièrement l'arrêt ; True si arrêté."""
    fin = time.monotonic() + secondes
    while time.monotonic() < fin:
        if est_arrete():
            return True
        time.sleep(min(pas, max(0.0, fin - time.monotonic())))
    return est_arrete()
