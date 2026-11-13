"""Moteur de PSN Amis : connexion à Sony et acceptation des demandes d'amis.

Ce fichier ne dessine rien : il publie son état dans un objet Suivi, que le tableau de
bord (tableau_de_bord.py) lit pour afficher la console en couleur.

Sécurité :
- le code npsso est gardé dans le coffre de Windows (ou dans npsso.txt) ; il n'est jamais
  affiché ni écrit dans journal.txt ;
- seuls les serveurs de Sony (sony.com, playstation.com, playstation.net) sont contactés,
  sauf la vérification de version sur GitHub, coupée au départ ;
- le moteur ne retire jamais d'amis de lui-même : les suppressions sont demandées
  par l'utilisateur ou par un nettoyage qu'il a activé (voir gestion.py).
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import logging
import logging.handlers
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import IO, Any
from urllib.parse import urlparse

import requests
from psnawp_api import PSNAWP
from psnawp_api.core import (
    PSNAWPAuthenticationError,
    PSNAWPClientError,
    PSNAWPError,
    PSNAWPNotFoundError,
    PSNAWPServerError,
    PSNAWPTooManyRequestsError,
    PSNAWPUnauthorizedError,
)
from psnawp_api.models import User
from psnawp_api.utils import API_PATH, BASE_PATH
from requests.adapters import HTTPAdapter

from psn_amis import __version__, chemins, coffre, mises_a_jour, notifications, psn
from psn_amis import demandes as types_demandes
from psn_amis import reglages as reglages_module

# Version du programme (définie dans psn_amis/__init__.py).
VERSION = __version__

# ─── Réglages ─────────────────────────────────────────────────────────────────
# Les réglages ci-dessous sont les valeurs par défaut ; reglages.toml peut en changer
# certains (voir reglages.py). Les autres sont fixés ici.

# Secondes entre deux vérifications. À chaque fois : demandes reçues acceptées, puis
# liste d'amis recomptée (pour repérer les amis retirés).
INTERVALLE_VERIFICATION = 15
# Secondes de pause entre deux acceptations.
PAUSE_ENTRE_ACCEPTATIONS = 2
# Nombre maximum d'amis sur un compte PSN (limite officielle de Sony).
LIMITE_AMIS_PSN = 2000
# Secondes d'attente maximum pour une réponse de Sony.
DELAI_RESEAU = 20
# Attente maximum entre deux essais, après des erreurs répétées (5 min).
ATTENTE_MAX_APRES_ERREUR = 300
# Pause si Sony demande de ralentir (15 min).
ATTENTE_SI_TROP_DE_REQUETES = 900
# Nouvel essai d'un code refusé, même s'il n'a pas changé (30 min).
REESSAI_CODE_REFUSE = 1800
# Un joueur refusé par Sony est réessayé 30 min plus tard.
DUREE_MISE_DE_COTE = 1800
# Rappel « toujours actif » toutes les 10 min (affichage texte simple seulement).
RAPPEL_ACTIVITE = 600
# Reconnexion 1 h avant l'expiration de la session Sony (qui dure environ 2 mois).
MARGE_RENOUVELLEMENT = 3600
# L'autorisation d'accès Sony dure environ 1 h : on la renouvelle 2 min avant la fin.
MARGE_ACCES = 120
# Nombre de pseudos affichés au maximum en mode test.
NOMBRE_MAX_PSEUDOS_TEST = 20
# Amis retirés d'un coup : au-delà de ce nombre, on résume au lieu de tout détailler
# (chaque pseudo coûte une requête à Sony).
NOMBRE_MAX_RETRAITS_DETAILLES = 10
# Heures de journal relues au démarrage (histogramme des ajouts).
HEURES_RELUES = 24
# Coupure Internet : une bulle Windows après ce nombre d'essais ratés de suite.
ESSAIS_AVANT_ALERTE = 3

# Les réglages de reglages.toml, appliqués par appliquer_reglages().
REGLAGES = reglages_module.Reglages()

# ─── Fichiers et adresses ─────────────────────────────────────────────────────
# Dossier des données de l'utilisateur (voir chemins.py), séparé du programme.
DOSSIER = chemins.dossier_donnees()
FICHIER_NPSSO = DOSSIER / "npsso.txt"
FICHIER_JOURNAL = DOSSIER / "journal.txt"
FICHIER_VERROU = DOSSIER / "psn-amis.lock"
FICHIER_REGLAGES = DOSSIER / "reglages.toml"
# Les amis connus au dernier comptage : les retraits survenus pendant l'arrêt sont
# ainsi repérés au démarrage suivant.
FICHIER_AMIS = DOSSIER / "amis.json"
FICHIER_DIAGNOSTIC = DOSSIER / "diagnostic.txt"

DOMAINES_SONY = ("sony.com", "playstation.com", "playstation.net")
ADRESSE_CODE_NPSSO = "https://ca.account.sony.com/api/v1/ssocookie"

ETAPES_CODE_NPSSO = f"""\
  1. Dans votre navigateur, connectez-vous sur https://www.playstation.com avec votre compte PSN.
  2. Dans le même navigateur, ouvrez : {ADRESSE_CODE_NPSSO}
  3. Double-cliquez sur le code de 64 caractères et copiez-le (Ctrl+C)."""
AIDE_NPSSO = f"""Pour mettre un nouveau code npsso :
{ETAPES_CODE_NPSSO}
  4. Dans PSN Amis, cliquez sur « Changer le code » (console : touche C), collez le
     code (Ctrl+V) et validez.
  Attention : si votre écran est partagé ou enregistré, le code y serait visible."""

# ─── Journal (journal.txt + écran), avec masquage du code npsso ───────────────
journal = logging.getLogger("psn_amis")

GENRE_AJOUT = "ajout"
# Un ami ne fait plus partie de la liste (il vous a retiré, ou vous l'avez retiré).
GENRE_RETRAIT = "retrait"
# Explications longues : le tableau de bord les affiche dans son propre panneau.
GENRE_AIDE = "aide"
# « Toujours actif » : inutile quand le tableau de bord est affiché.
GENRE_RAPPEL = "rappel"
# Ami supprimé par PSN Amis (gestion des amis).
GENRE_SUPPRESSION = "suppression"

ECRAN_SEULEMENT = {"ecran_seulement": True}
AIDE = {"ecran_seulement": True, "genre": GENRE_AIDE}
_secrets: set[str] = set()


def masquer(texte: str) -> str:
    """Remplace le code npsso par un texte neutre, s'il apparaissait dans un message."""
    # Le plus long d'abord : un ancien code mal copié (plus court) ne doit pas
    # laisser dépasser un morceau du bon code.
    for secret in sorted(_secrets, key=len, reverse=True):
        texte = texte.replace(secret, "[code masqué]")
    return texte


class FormatMasque(logging.Formatter):
    """Mise en forme qui masque toujours le code npsso (détails d'erreur compris)."""

    def format(self, record: logging.LogRecord) -> str:
        return masquer(super().format(record))


class SansMessagesEcran(logging.Filter):
    """Garde hors de journal.txt les messages prévus pour l'écran seulement."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, "ecran_seulement", False)


def preparer_dossier() -> Path:
    """Crée le dossier des données s'il n'existe pas (premier lancement).

    Appelée avant chaque première écriture (verrou, journal, réglages, amis.json...) :
    aucune opération ne suppose que le dossier existe déjà.
    """
    return chemins.preparer(DOSSIER)


def configurer_journal(*, ecran: bool, fichier: bool, diagnostic: bool = False) -> None:
    # En mode détaillé, PSNAWP et requests écrivent les requêtes envoyées, code npsso
    # compris : on les rend complètement muets, ainsi que les avertissements Python.
    logging.captureWarnings(True)
    for nom in ("psnawp", "urllib3", "requests", "pyrate_limiter", "py.warnings"):
        bibliotheque = logging.getLogger(nom)
        bibliotheque.setLevel(logging.CRITICAL + 1)
        bibliotheque.propagate = False
        bibliotheque.addHandler(logging.NullHandler())
    # Sans cela, un message d'une autre bibliothèque s'afficherait tel quel à l'écran.
    logging.getLogger().addHandler(logging.NullHandler())
    # En cas de souci d'écriture, logging afficherait le message brut : on l'en empêche.
    logging.raiseExceptions = False
    # Une erreur imprévue dans un fil d'exécution est notée (masquée) au lieu d'être
    # affichée en vrac dans la console.
    threading.excepthook = lambda args: journal.error(
        "Erreur interne (%s : %s).", args.exc_type.__name__, args.exc_value
    )

    journal.setLevel(logging.DEBUG if diagnostic else logging.INFO)
    journal.propagate = False

    # sys.stdout est absent quand le script tourne sans fenêtre.
    if ecran and sys.stdout is not None:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        gestionnaire = logging.StreamHandler(sys.stdout)
        gestionnaire.setLevel(logging.INFO)
        gestionnaire.setFormatter(
            FormatMasque("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
        )
        journal.addHandler(gestionnaire)

    if fichier or diagnostic:
        preparer_dossier()
    if fichier:
        gestionnaire = logging.handlers.RotatingFileHandler(
            FICHIER_JOURNAL,
            maxBytes=1_000_000,
            backupCount=REGLAGES.journaux_archives,
            encoding="utf-8",
        )
        gestionnaire.setLevel(logging.INFO)
        gestionnaire.setFormatter(
            FormatMasque("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        gestionnaire.addFilter(SansMessagesEcran())
        journal.addHandler(gestionnaire)

    if diagnostic:
        # Tout, détails techniques compris (code npsso toujours masqué), pour joindre
        # quelque chose d'utile à un ticket.
        gestionnaire = logging.handlers.RotatingFileHandler(
            FICHIER_DIAGNOSTIC, maxBytes=2_000_000, backupCount=1, encoding="utf-8"
        )
        gestionnaire.setLevel(logging.DEBUG)
        gestionnaire.setFormatter(
            FormatMasque(
                "%(asctime)s %(levelname)-8s %(threadName)s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        journal.addHandler(gestionnaire)
        journal.debug("Diagnostic : PSN Amis %s, Python %s", VERSION, sys.version)


def appliquer_reglages(nouveaux: reglages_module.Reglages) -> None:
    """Fait suivre les réglages de reglages.toml aux constantes du moteur."""
    global REGLAGES, INTERVALLE_VERIFICATION, PAUSE_ENTRE_ACCEPTATIONS, LIMITE_AMIS_PSN
    REGLAGES = nouveaux
    INTERVALLE_VERIFICATION = nouveaux.intervalle_verification
    PAUSE_ENTRE_ACCEPTATIONS = nouveaux.pause_entre_acceptations
    LIMITE_AMIS_PSN = nouveaux.limite_amis


def charger_reglages() -> tuple[reglages_module.Reglages, list[str]]:
    """Crée reglages.toml au besoin, le lit et l'applique ; renvoie (réglages, problèmes)."""
    preparer_dossier()
    reglages_module.creer_si_absent(FICHIER_REGLAGES)
    reglages_module.mettre_a_jour_le_format(FICHIER_REGLAGES)
    charges, problemes = reglages_module.charger(FICHIER_REGLAGES)
    appliquer_reglages(charges)
    return charges, problemes


def alerter(titre: str, texte: str) -> None:
    """Bulle de notification Windows, si le réglage le permet."""
    if REGLAGES.notifications:
        notifications.notifier(titre, texte)


def en_amis(nombre: int) -> str:
    """« 0 ami », « 1 ami », « 2 amis »..."""
    return f"{nombre} ami" if nombre <= 1 else f"{nombre} amis"


def duree(secondes: float) -> str:
    secondes = int(secondes)
    return f"{secondes} s" if secondes < 60 else f"{secondes // 60} min"


def raison(erreur: PSNAWPError) -> str:
    """Résumé court de l'erreur renvoyée par Sony."""
    texte = erreur.message or str(erreur) or type(erreur).__name__
    texte = " ".join(texte.split())[:200]
    return f"{texte} [code {erreur.code}]" if erreur.code else texte


# ─── Windows : une seule fenêtre à la fois, priorité basse ────────────────────
def verrouiller_instance() -> IO[str] | None:
    """Empêche de lancer le script deux fois en même temps (requêtes doublées)."""
    # Premier lancement : le dossier des données n'existe peut-être pas encore.
    FICHIER_VERROU.parent.mkdir(parents=True, exist_ok=True)
    # Le fichier reste ouvert exprès : c'est lui qui sert de verrou.
    fichier = FICHIER_VERROU.open("a+", encoding="utf-8")
    if os.name == "nt":
        import msvcrt

        try:
            fichier.seek(0)
            msvcrt.locking(fichier.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            fichier.close()
            return None
    return fichier


def baisser_priorite() -> None:
    """Laisse la priorité aux autres programmes (jeu, capture vidéo, navigateur...)."""
    if os.name != "nt":
        return
    below_normal_priority_class = 0x00004000
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel32.SetPriorityClass(
            kernel32.GetCurrentProcess(), below_normal_priority_class
        )
    except AttributeError, OSError:
        pass


def nettoyer_fichiers_temporaires() -> None:
    """PSNAWP crée un petit fichier de suivi des requêtes dans le dossier temporaire."""
    shutil.rmtree(
        Path(tempfile.gettempdir()) / f"psnawp-{os.getpid()}", ignore_errors=True
    )


# ─── Réseau : uniquement Sony, jamais d'attente infinie ──────────────────────
class AdresseNonSony(Exception):
    """Une requête vers un serveur qui n'appartient pas à Sony a été bloquée."""


class AdaptateurSony(HTTPAdapter):
    """N'autorise que les serveurs de Sony et impose un délai maximal à chaque réponse."""

    def send(
        self, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        hote = (urlparse(request.url or "").hostname or "").lower()
        if not any(
            hote == domaine or hote.endswith("." + domaine) for domaine in DOMAINES_SONY
        ):
            raise AdresseNonSony(
                f"requête bloquée vers {hote or 'une adresse inconnue'} "
                "(pas un serveur Sony)"
            )
        # PSNAWP ne fixe pas de délai : sans cela, une coupure bloquerait tout.
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = DELAI_RESEAU
        return super().send(request, **kwargs)


def installer_protections(psnawp: PSNAWP) -> None:
    session_http = psnawp.authenticator.request_builder.session
    adaptateur = AdaptateurSony()
    session_http.mount("https://", adaptateur)
    session_http.mount("http://", adaptateur)


# ─── État partagé avec l'affichage ────────────────────────────────────────────
class Statut(StrEnum):
    DEMARRAGE = "démarrage"
    CONNEXION = "connexion"
    EN_MARCHE = "en marche"
    VERIFICATION = "vérification"
    PAUSE = "pause"
    HORS_LIGNE = "hors ligne"
    ATTENTE = "attente"
    CODE_NPSSO = "code npsso"
    # Aucun code configuré : il faut connecter un compte (premier lancement).
    CONNEXION_REQUISE = "connexion requise"
    LISTE_PLEINE = "liste pleine"
    ERREUR = "erreur"
    SUPPRESSION = "gestion des amis"


@dataclass(frozen=True)
class Ajout:
    moment: datetime
    pseudo: str


@dataclass(frozen=True)
class Attente:
    """Une demande d'ami pas encore acceptée (en pause, refusée, ignorée)."""

    pseudo: str
    depuis: datetime | None
    motif: str = ""


@dataclass(frozen=True)
class Evenement:
    moment: datetime
    niveau: int
    genre: str
    texte: str


@dataclass(frozen=True)
class Instantane:
    """Photo de l'état du moteur à un instant donné, pour l'affichage."""

    statut: Statut
    detail: str
    pseudo_compte: str | None
    nombre_amis: int | None
    demandes_en_attente: int | None
    # Les demandes en attente, avec leur pseudo et leur ancienneté.
    attentes: tuple[Attente, ...]
    ajouts_session: int
    ajouts_jour: int
    retraits_session: int
    retraits_jour: int
    # Du plus récent au plus ancien (les dernières 24 heures au moins).
    derniers_ajouts: tuple[Ajout, ...]
    # Amis retirés (pseudo et moment), du plus récent au plus ancien.
    retraits: tuple[Ajout, ...]
    evenements: tuple[Evenement, ...]
    debut: datetime
    # Moment de la prochaine vérification, sur l'horloge time.monotonic().
    prochaine_verification: float | None
    intervalle: float
    derniere_verification: datetime | None
    probleme_npsso: str | None
    # Heure du dernier comptage des amis auprès de Sony.
    amis_comptes_a: datetime | None
    # Amis supprimés par PSN Amis (gestion des amis).
    supprimes_session: int = 0
    supprimes_jour: int = 0


class Suivi:
    """État du moteur, lu par l'affichage. Un verrou le protège : deux fils l'utilisent."""

    def __init__(
        self,
        ajouts_recents: list[Ajout] | None = None,
        retraits_recents: list[Ajout] | None = None,
        suppressions_recentes: list[Ajout] | None = None,
    ) -> None:
        ajouts = sorted(ajouts_recents or [], key=lambda ajout: ajout.moment)
        retraits = sorted(retraits_recents or [], key=lambda retrait: retrait.moment)
        self._verrou = threading.Lock()
        self._statut = Statut.DEMARRAGE
        self._detail = "Démarrage…"
        self._pseudo_compte: str | None = None
        self._nombre_amis: int | None = None
        self._en_attente: int | None = None
        self._attentes: tuple[Attente, ...] = ()
        self._jour = date.today()
        self._ajouts_session = 0
        self._ajouts_jour = sum(ajout.moment.date() == self._jour for ajout in ajouts)
        self._retraits_session = 0
        self._retraits_jour = sum(r.moment.date() == self._jour for r in retraits)
        self._derniers: deque[Ajout] = deque(reversed(ajouts[-500:]), maxlen=500)
        self._retraits: deque[Ajout] = deque(reversed(retraits[-500:]), maxlen=500)
        self._evenements: deque[Evenement] = deque(maxlen=300)
        self._debut = datetime.now()
        self._prochaine: float | None = None
        self._intervalle = float(INTERVALLE_VERIFICATION)
        self._derniere_verification: datetime | None = None
        self._probleme_npsso: str | None = None
        self._amis_comptes_a: datetime | None = None
        self._supprimes_session = 0
        self._supprimes_jour = sum(
            s.moment.date() == self._jour for s in suppressions_recentes or []
        )

    def statut(
        self, statut: Statut, detail: str = "", prochaine_dans: float | None = None
    ) -> None:
        with self._verrou:
            self._statut = statut
            self._detail = masquer(detail)
            if prochaine_dans is None:
                self._prochaine = None
            else:
                self._prochaine = time.monotonic() + prochaine_dans
                self._intervalle = max(float(prochaine_dans), 1.0)

    def connecte(self, pseudo: str, nombre_amis: int) -> None:
        with self._verrou:
            self._pseudo_compte = pseudo
            self._nombre_amis = nombre_amis
            self._amis_comptes_a = datetime.now()
            self._probleme_npsso = None

    def amis(self, nombre: int) -> int | None:
        """Enregistre le nombre d'amis compté par Sony ; renvoie l'ancien chiffre."""
        with self._verrou:
            avant = self._nombre_amis
            self._nombre_amis = nombre
            self._amis_comptes_a = datetime.now()
            return avant

    def connexion_requise(self, texte: str) -> None:
        """Aucun code enregistré : ce n'est pas une erreur, il faut connecter un compte."""
        with self._verrou:
            self._statut = Statut.CONNEXION_REQUISE
            self._detail = "Connectez votre compte PSN pour commencer"
            self._prochaine = None
            self._probleme_npsso = masquer(texte)

    def code_a_changer(self, texte: str) -> None:
        with self._verrou:
            self._statut = Statut.CODE_NPSSO
            self._detail = "Nouveau code : touche C"
            self._prochaine = None
            self._probleme_npsso = masquer(texte)

    def code_valide(self) -> None:
        with self._verrou:
            self._probleme_npsso = None

    def demandes_trouvees(self, nombre: int) -> None:
        with self._verrou:
            self._en_attente = nombre

    def en_attente(self, attentes: list[Attente]) -> None:
        """La liste des demandes pas encore acceptées (affichée pendant une pause)."""
        with self._verrou:
            self._attentes = tuple(attentes)
            self._en_attente = len(attentes)

    def verification_terminee(self) -> None:
        with self._verrou:
            self._derniere_verification = datetime.now()

    def ajout(self, pseudo: str) -> None:
        with self._verrou:
            maintenant = datetime.now()
            self._changer_de_jour_si_besoin(maintenant.date())
            self._ajouts_session += 1
            self._ajouts_jour += 1
            self._derniers.appendleft(Ajout(maintenant, pseudo))
            if self._nombre_amis is not None:
                self._nombre_amis += 1
            if self._en_attente:
                self._en_attente -= 1
            self._attentes = tuple(a for a in self._attentes if a.pseudo != pseudo)

    def retrait(self, pseudo: str, moment: datetime | None = None) -> None:
        """Un ami a quitté la liste : « Derniers ajouts » le signalera."""
        with self._verrou:
            moment = moment or datetime.now()
            self._changer_de_jour_si_besoin(date.today())
            self._retraits_session += 1
            if moment.date() == self._jour:
                self._retraits_jour += 1
            self._retraits.appendleft(Ajout(moment, pseudo))

    def suppression(self, pseudo: str) -> None:
        """Un ami supprimé par PSN Amis (il n'est pas compté comme « retrait »)."""
        with self._verrou:
            self._changer_de_jour_si_besoin(date.today())
            self._supprimes_session += 1
            self._supprimes_jour += 1
            if self._nombre_amis is not None and self._nombre_amis > 0:
                self._nombre_amis -= 1

    def evenement(self, moment: datetime, niveau: int, genre: str, texte: str) -> None:
        with self._verrou:
            self._evenements.appendleft(Evenement(moment, niveau, genre, texte))

    def instantane(self) -> Instantane:
        with self._verrou:
            self._changer_de_jour_si_besoin(date.today())
            return Instantane(
                statut=self._statut,
                detail=self._detail,
                pseudo_compte=self._pseudo_compte,
                nombre_amis=self._nombre_amis,
                demandes_en_attente=self._en_attente,
                attentes=self._attentes,
                ajouts_session=self._ajouts_session,
                ajouts_jour=self._ajouts_jour,
                retraits_session=self._retraits_session,
                retraits_jour=self._retraits_jour,
                derniers_ajouts=tuple(self._derniers),
                retraits=tuple(self._retraits),
                evenements=tuple(self._evenements),
                debut=self._debut,
                prochaine_verification=self._prochaine,
                intervalle=self._intervalle,
                derniere_verification=self._derniere_verification,
                probleme_npsso=self._probleme_npsso,
                amis_comptes_a=self._amis_comptes_a,
                supprimes_session=self._supprimes_session,
                supprimes_jour=self._supprimes_jour,
            )

    def _changer_de_jour_si_besoin(self, jour: date) -> None:
        if jour != self._jour:
            self._jour = jour
            self._ajouts_jour = 0
            self._retraits_jour = 0
            self._supprimes_jour = 0


class Commandes:
    """Ordres envoyés au moteur (clavier ou fenêtre) : pause, vérification, arrêt."""

    def __init__(self) -> None:
        self.arret = threading.Event()
        self.pause = threading.Event()
        self.reconnecter = threading.Event()
        self._reveil = threading.Event()

    def arreter(self) -> None:
        self.arret.set()
        self._reveil.set()

    def basculer_pause(self) -> bool:
        """Met en pause ou relance ; renvoie True si le moteur est maintenant en pause."""
        if self.pause.is_set():
            self.pause.clear()
        else:
            self.pause.set()
        self._reveil.set()
        return self.pause.is_set()

    def verifier_maintenant(self) -> None:
        """Touche V : vérifie les demandes et recompte les amis tout de suite."""
        self._reveil.set()

    def demander_reconnexion(self) -> None:
        """Nouveau code npsso enregistré : se reconnecter tout de suite avec ce compte."""
        self.reconnecter.set()
        self._reveil.set()

    def attendre(self, secondes: float) -> bool:
        """Attend ; renvoie True si on a été réveillé avant la fin (touche ou arrêt)."""
        reveille = self._reveil.wait(timeout=max(0.0, secondes))
        if reveille and not self.arret.is_set():
            self._reveil.clear()
        return reveille


# ─── Relecture du journal ─────────────────────────────────────────────────────
MOTIF_AJOUT = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})  Demande acceptée : (.+)$"
)
MOTIF_SUPPRESSION = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})  Ami supprimé par PSN Amis : (.+)$"
)
MOTIF_RETRAIT = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})  Ami retiré(?: pendant l'arrêt)? : (.+)$"
)


def fichiers_journal() -> list[Path]:
    """journal.txt et ses archives, de la plus ancienne à la plus récente."""
    return [
        FICHIER_JOURNAL.with_name(f"{FICHIER_JOURNAL.name}.{numero}")
        for numero in range(REGLAGES.journaux_archives, 0, -1)
    ] + [FICHIER_JOURNAL]


def _dans_journal(motif: re.Pattern[str], depuis: datetime) -> list[Ajout]:
    """Les lignes du journal qui suivent un motif, à partir d'un moment donné."""
    trouves: list[Ajout] = []
    for fichier in fichiers_journal():
        try:
            lignes = fichier.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for ligne in lignes:
            correspondance = motif.match(ligne)
            if not correspondance:
                continue
            moment = datetime.strptime(correspondance[1], "%Y-%m-%d %H:%M:%S")
            if moment >= depuis:
                trouves.append(Ajout(moment, correspondance[2].strip()))
    return trouves


def ajouts_recents_dans_journal(heures: int = HEURES_RELUES) -> list[Ajout]:
    """Les ajouts des dernières heures, relus dans journal.txt au démarrage."""
    return _dans_journal(MOTIF_AJOUT, datetime.now() - timedelta(hours=heures))


def suppressions_recentes_dans_journal(heures: int = HEURES_RELUES) -> list[Ajout]:
    """Les amis supprimés par PSN Amis ces dernières heures (relus au démarrage)."""
    return _dans_journal(MOTIF_SUPPRESSION, datetime.now() - timedelta(hours=heures))


def retraits_recents_dans_journal(heures: int = HEURES_RELUES) -> list[Ajout]:
    """Les amis retirés ces dernières heures, relus dans journal.txt au démarrage."""
    return _dans_journal(MOTIF_RETRAIT, datetime.now() - timedelta(hours=heures))


def ajouts_du_jour_dans_journal() -> list[Ajout]:
    aujourd_hui = date.today()
    return [
        a for a in ajouts_recents_dans_journal(48) if a.moment.date() == aujourd_hui
    ]


def retraits_du_jour_dans_journal() -> list[Ajout]:
    aujourd_hui = date.today()
    return [
        r for r in retraits_recents_dans_journal(48) if r.moment.date() == aujourd_hui
    ]


def statistiques_par_jour(jours: int = 7) -> list[tuple[date, int, int]]:
    """Pour chacun des derniers jours : (date, ajouts, retraits), du plus récent au plus
    ancien. Les journées sans rien comptent 0."""
    depuis = datetime.combine(
        date.today() - timedelta(days=jours - 1), datetime.min.time()
    )
    ajouts = Counter(a.moment.date() for a in _dans_journal(MOTIF_AJOUT, depuis))
    retraits = Counter(r.moment.date() for r in _dans_journal(MOTIF_RETRAIT, depuis))
    return [
        (jour, ajouts.get(jour, 0), retraits.get(jour, 0))
        for jour in (date.today() - timedelta(days=n) for n in range(jours))
    ]


# ─── Code npsso ───────────────────────────────────────────────────────────────
class ProblemeNpsso(Exception):
    """Le code npsso est absent, illisible ou mal formé."""


class AucunCode(ProblemeNpsso):
    """Aucun code npsso n'a encore été configuré (compte pas encore connecté)."""


def extraire_npsso(texte: str, origine: str) -> str:
    """Retrouve le code dans un texte collé ou lu, et vérifie son format.

    Tolère les espaces, les guillemets et la ligne {"npsso":"..."} entière.
    `origine` sert aux messages d'erreur (« le contenu de npsso.txt », « le code collé »).
    """
    texte = texte.strip()
    # Toute la ligne {"npsso":"..."} a été collée : on en extrait le code.
    if texte.startswith("{"):
        with contextlib.suppress(ValueError, AttributeError):
            texte = str(json.loads(texte).get("npsso", ""))
    texte = texte.strip().strip("\"'").strip()

    if not texte:
        raise ProblemeNpsso(f"{origine} est vide.")
    if len(texte) >= 16:
        # Masqué dans tous les messages, même s'il est mal formé.
        _secrets.add(texte)
    if not re.fullmatch(r"[A-Za-z0-9]{64}", texte):
        raise ProblemeNpsso(
            f"{origine} n'a pas le bon format ({len(texte)} caractères trouvés, "
            "il faut exactement 64 lettres et chiffres, sans espace ni guillemet)."
        )
    return texte


def coffre_actif() -> bool:
    """Le coffre de Windows est utilisé pour le code npsso."""
    return REGLAGES.coffre_windows and coffre.disponible()


def code_present() -> bool:
    """Un code npsso est enregistré quelque part (coffre ou fichier)."""
    if coffre_actif() and coffre.lire():
        return True
    return FICHIER_NPSSO.exists()


def _lire_fichier_npsso() -> str:
    """Lit npsso.txt et vérifie le format du code."""
    try:
        brut = FICHIER_NPSSO.read_bytes()
    except FileNotFoundError:
        raise AucunCode(
            f"aucun code enregistré (npsso.txt introuvable dans {DOSSIER})."
        ) from None
    except OSError:
        raise ProblemeNpsso("Windows refuse d'ouvrir npsso.txt.") from None

    # Enregistré en « UTF-16 » par le Bloc-notes : on le décode quand même.
    if brut.startswith((b"\xff\xfe", b"\xfe\xff")):
        texte = brut.decode("utf-16", errors="ignore")
    else:
        texte = brut.decode("utf-8-sig", errors="ignore")
    return extraire_npsso(texte, "le contenu de npsso.txt")


def ranger_dans_le_coffre(code: str) -> bool:
    """Garde le code dans le coffre de Windows et vérifie qu'il s'y relit bien."""
    return coffre_actif() and coffre.ecrire(code) and coffre.lire() == code


def lire_npsso() -> str:
    """Lit le code et vérifie son format.

    Un npsso.txt présent passe en premier : c'est le code le plus récent (mis à la
    main avec le Bloc-notes). Avec le coffre de Windows, il y est alors rangé, et
    npsso.txt est supprimé une fois le code relu sans erreur dans le coffre.
    """
    if FICHIER_NPSSO.exists() or not coffre_actif():
        code = _lire_fichier_npsso()
        if ranger_dans_le_coffre(code):
            FICHIER_NPSSO.unlink(missing_ok=True)
            journal.info(
                "Code npsso rangé dans le coffre de Windows : npsso.txt n'est plus "
                "nécessaire et a été supprimé."
            )
        return code
    depuis_le_coffre = coffre.lire()
    if not depuis_le_coffre:
        raise AucunCode(
            "aucun code enregistré (ni dans le coffre de Windows, ni dans npsso.txt)."
        )
    return extraire_npsso(depuis_le_coffre, "le code du coffre de Windows")


def proteger_fichier(chemin: Path) -> bool:
    """Réserve un fichier au compte Windows courant (et à Windows lui-même)."""
    icacls = shutil.which("icacls")
    utilisateur = os.environ.get("USERNAME")
    if os.name != "nt" or icacls is None or not utilisateur:
        return False
    # Programme de Windows, trouvé par son chemin complet, arguments fixes.
    resultat = subprocess.run(  # noqa: S603
        [
            icacls,
            str(chemin),
            "/inheritance:r",
            "/grant:r",
            f"{utilisateur}:(F)",
            "*S-1-5-18:(F)",
        ],
        capture_output=True,
        check=False,
    )
    return resultat.returncode == 0


def enregistrer_npsso(saisie: str) -> str:
    """Vérifie un code collé et l'enregistre : coffre de Windows, sinon npsso.txt.

    Renvoie où il a été rangé (« le coffre de Windows » ou « npsso.txt »).
    """
    code = extraire_npsso(saisie, "le code collé")
    if ranger_dans_le_coffre(code):
        # L'ancien fichier, s'il existe, passerait avant le coffre : il est retiré.
        FICHIER_NPSSO.unlink(missing_ok=True)
        return "le coffre de Windows"
    FICHIER_NPSSO.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_NPSSO.write_text(code + "\n", encoding="utf-8")
    proteger_fichier(FICHIER_NPSSO)
    return "npsso.txt"


def assistant_npsso(dire: Callable[[str], None] = print) -> bool:
    """Demande le code npsso au clavier (saisie masquée), le vérifie et l'enregistre.

    C'est ce qui relie PSN Amis à un compte PlayStation : le compte connecté est
    celui dont vient le code. Renvoie True si un code valide a été enregistré.
    """
    import getpass

    dire("")
    dire(
        "Connexion de votre compte PlayStation : PSN Amis a besoin de votre code npsso."
    )
    dire(ETAPES_CODE_NPSSO)
    dire(
        "Le code ne s'affiche pas pendant la saisie. Entrée sans rien coller : abandon."
    )
    for _ in range(3):
        try:
            saisie = getpass.getpass(
                "Collez votre code npsso, puis appuyez sur Entrée : "
            )
        except EOFError, KeyboardInterrupt:
            saisie = ""
        if not saisie.strip():
            dire("Aucun code enregistré.")
            return False
        try:
            rangement = enregistrer_npsso(saisie)
        except ProblemeNpsso as probleme:
            dire(f"Ce n'est pas un code valide : {probleme} Réessayez.")
            continue
        dire(
            f"Code enregistré dans {rangement}, lisible seulement par votre compte "
            "Windows. Ne le partagez jamais."
        )
        return True
    dire("Trois essais sans code valide : abandon.")
    return False


def date_modification_npsso() -> int | None:
    try:
        return FICHIER_NPSSO.stat().st_mtime_ns
    except OSError:
        return None


def attendre_nouveau_code(commandes: Commandes, duree_max: float) -> None:
    """Attend que npsso.txt soit modifié (vérifié toutes les 5 s), ou au plus duree_max.
    La touche V fait réessayer tout de suite."""
    depart = date_modification_npsso()
    fin = time.monotonic() + duree_max
    while not commandes.arret.is_set() and time.monotonic() < fin:
        if commandes.attendre(5):
            return
        if date_modification_npsso() != depart:
            # Laisse le temps au Bloc-notes de finir l'enregistrement.
            commandes.attendre(1)
            return


# ─── Connexion à Sony ─────────────────────────────────────────────────────────
@dataclass
class Connexion:
    psnawp: PSNAWP
    pseudo: str
    # Identifiant de compte PSN (stable, contrairement au pseudo).
    compte_id: str = ""

    def expire_bientot(self) -> bool:
        auth = self.psnawp.authenticator
        return (
            auth.token_response is not None
            and auth.refresh_token_expiration_time < time.time() + MARGE_RENOUVELLEMENT
        )

    def renouveler_acces_si_besoin(self) -> None:
        """Renouvelle l'autorisation d'accès 2 min avant son expiration.

        PSNAWP ne la renouvelle qu'une fois expirée, et vérifie l'heure *avant*
        d'attendre son tour d'envoi (jusqu'à 3 s) : la requête pouvait partir avec une
        autorisation tout juste expirée, et Sony la refusait (« connexion expirée »).
        """
        auth = self.psnawp.authenticator
        if auth.token_response is None:
            return
        if auth.access_token_expiration_time > time.time() + MARGE_ACCES:
            return
        # Marquée comme expirée : PSNAWP la renouvelle alors avec son jeton de session.
        auth.token_response["access_token_expires_at"] = 0
        try:
            auth.fetch_access_token_from_refresh()
        except PSNAWPClientError as erreur:
            raise PSNAWPAuthenticationError(raison(erreur)) from None

    def fermer(self) -> None:
        self.psnawp.authenticator.request_builder.session.close()


def ouvrir_connexion(npsso: str) -> Connexion:
    psnawp = PSNAWP(npsso)
    installer_protections(psnawp)
    # Première requête : c'est là que Sony vérifie le code. L'identifiant du compte
    # est demandé au passage par PSNAWP (aucune requête de plus).
    moi = psnawp.me()
    pseudo = moi.online_id
    return Connexion(psnawp, pseudo, moi.account_id)


def client_psn(connexion: Connexion) -> psn.ClientPSN:
    """Les opérations de gestion des amis pour cette connexion."""
    return psn.ClientPSNAWP(connexion.psnawp)


def connecter(suivi: Suivi, commandes: Commandes, attendre: bool) -> Connexion | None:
    """Se connecte à Sony. Si le code est absent, mal rempli ou refusé, explique quoi
    faire, puis attend un nouveau code (attendre=True) ou abandonne (attendre=False).
    Renvoie None si l'arrêt est demandé. Les coupures réseau remontent à l'appelant."""
    deja_alerte = False
    while not commandes.arret.is_set():
        suivi.statut(Statut.CONNEXION, "Connexion aux serveurs de Sony…")
        journal.info("Connexion aux serveurs de Sony...", extra=ECRAN_SEULEMENT)
        aucun_code = False
        try:
            connexion = ouvrir_connexion(lire_npsso())
        except AucunCode as probleme:
            aucun_code = True
            texte = f"Connexion PSN nécessaire : {probleme}"
        except ProblemeNpsso as probleme:
            texte = f"PROBLÈME avec le code npsso : {probleme}"
        except PSNAWPAuthenticationError:
            texte = "PROBLÈME : Sony refuse le code npsso (il est expiré ou incorrect)."
        else:
            suivi.code_valide()
            return connexion
        if aucun_code:
            # Premier lancement : rien d'anormal, pas de bulle d'alerte Windows.
            journal.warning("%s", texte)
            suivi.connexion_requise(texte)
        else:
            journal.error("%s", texte)
            suivi.code_a_changer(texte)
        journal.info(AIDE_NPSSO, extra=AIDE)
        if not deja_alerte and not aucun_code:
            deja_alerte = True
            alerter("PSN Amis : code npsso à changer", texte)
        if not attendre:
            journal.info("Une fois le code remplacé, relancez le test.", extra=AIDE)
            return None
        journal.info(
            "Le script repère le nouveau code tout seul : inutile de le relancer. "
            "En attente (nouvel essai automatique dans %s au plus tard)...",
            duree(REESSAI_CODE_REFUSE),
            extra=AIDE,
        )
        attendre_nouveau_code(commandes, REESSAI_CODE_REFUSE)
    return None


# ─── Demandes d'amis ──────────────────────────────────────────────────────────
ERREURS_A_REMONTER = (
    PSNAWPAuthenticationError,
    PSNAWPUnauthorizedError,
    PSNAWPTooManyRequestsError,
)


@dataclass(frozen=True)
class Demandes:
    """Demandes reçues, triées en deux sortes."""

    # Vraies demandes d'ami : elles sont acceptées.
    amis: list[str]
    # Joueurs déjà amis qui demandent à partager vos vrais noms : jamais acceptées.
    partages: list[str]
    # Compte -> moment où la demande a été envoyée (quand Sony le donne).
    depuis: dict[str, datetime] = field(default_factory=dict)
    # Demandes d'ami accompagnées d'une demande de partage du vrai nom : jamais
    # acceptées automatiquement.
    avec_vrai_nom: list[str] = field(default_factory=list)
    # Demandes d'un type que PSN Amis ne connaît pas.
    inconnues: list[str] = field(default_factory=list)


def _moment_sony(texte: object) -> datetime | None:
    """« 2026-11-10T20:48:01.552Z » → heure locale, ou None si illisible."""
    if not isinstance(texte, str):
        return None
    try:
        universel = datetime.fromisoformat(texte)
    except ValueError:
        return None
    return universel.astimezone().replace(tzinfo=None)


def demandes_recues(connexion: Connexion) -> Demandes:
    """Identifiants des comptes qui ont envoyé une demande.

    Même appel à Sony que client.friend_requests() de PSNAWP, mais on ne garde que les
    identifiants : un compte à problème (supprimé, banni...) ne bloque pas les suivants.

    Sony range dans la même liste les demandes de partage du vrai nom, envoyées par des
    joueurs déjà amis (« relation » vaut alors « friend »). Les accepter comme demandes
    d'ami échoue (« Friend relation mismatch ») : on les met à part.
    """
    adresse = API_PATH["friends_request"].format(account_id="me")
    reponse = connexion.psnawp.authenticator.get(
        url=f"{BASE_PATH['profile_uri']}{adresse}",
    ).json()
    triees: dict[types_demandes.TypeDemande, list[str]] = {
        sorte: [] for sorte in types_demandes.TypeDemande
    }
    depuis: dict[str, datetime] = {}
    for demande in reponse.get("receivedRequests", []):
        if not isinstance(demande, dict):
            continue
        compte = demande.get("accountId")
        if not compte or not isinstance(compte, str):
            continue
        triees[types_demandes.classer(demande)].append(compte)
        moment = _moment_sony(demande.get("requestedDate"))
        if moment is not None:
            depuis[compte] = moment
    return Demandes(
        triees[types_demandes.TypeDemande.ORDINAIRE],
        triees[types_demandes.TypeDemande.AMI_PROCHE],
        depuis,
        triees[types_demandes.TypeDemande.AVEC_VRAI_NOM],
        triees[types_demandes.TypeDemande.NON_RECONNUE],
    )


def trouver_joueur(connexion: Connexion, compte: str) -> User:
    """Retrouve le pseudo d'un compte ; sans pseudo, on peut quand même accepter."""
    try:
        return connexion.psnawp.user(account_id=compte)
    except ERREURS_A_REMONTER:
        raise
    except PSNAWPClientError:
        return User(
            connexion.psnawp.authenticator,
            f"(pseudo inconnu, compte n°{compte})",
            compte,
        )


def liste_amis(connexion: Connexion) -> tuple[set[str], int]:
    """Identifiants des amis du compte connecté, et leur nombre total selon Sony."""
    adresse = API_PATH["friends_list"].format(account_id="me")
    amis: set[str] = set()
    total: int | None = None
    # Pages de 1000 amis : 5 au maximum, c'est plus que la limite de Sony.
    for _ in range(5):
        reponse = connexion.psnawp.authenticator.get(
            url=f"{BASE_PATH['profile_uri']}{adresse}",
            params={"limit": 1000, "offset": len(amis)},
        ).json()
        if isinstance(reponse.get("totalItemCount"), int):
            total = int(reponse["totalItemCount"])
        page = {
            compte for compte in reponse.get("friends", []) if isinstance(compte, str)
        }
        nouveaux = page - amis
        amis |= nouveaux
        if not nouveaux or total is None or len(amis) >= total:
            break
    return amis, len(amis) if total is None else total


def nombre_amis(connexion: Connexion) -> int:
    """Nombre d'amis actuel du compte connecté, selon Sony."""
    return liste_amis(connexion)[1]


@dataclass
class Etat:
    acceptees: int = 0
    # Compte -> moment du prochain essai.
    mis_de_cote: dict[str, float] = field(default_factory=dict)
    liste_pleine: bool = False
    dernier_rappel_liste_pleine: float = 0.0
    # Amis connus au dernier comptage, pour repérer ceux qui disparaissent.
    # None tant que Sony n'a pas renvoyé une liste complète.
    amis_connus: set[str] | None = None
    # Demandes de partage du vrai nom déjà signalées (une seule fois chacune).
    partages_signales: set[str] = field(default_factory=set)
    # Compte -> joueur, pour ne pas redemander un pseudo déjà connu à Sony.
    # Vidé à chaque nouvelle connexion (un joueur garde sa connexion d'origine).
    joueurs: dict[str, User] = field(default_factory=dict)
    # Demandes ignorées (liste noire ou blanche) déjà signalées.
    ignores_signales: set[str] = field(default_factory=set)
    # Ajouts depuis la dernière reprise, pour la pause automatique.
    ajouts_depuis_reprise: int = 0
    # Gestion des amis (gestion.Gestion), si l'application l'utilise.
    gestion: Any = None
    # Demandes laissées en attente à cause de leur type, déjà signalées.
    types_signales: set[str] = field(default_factory=set)
    # Refus impossible des demandes d'ami proche : signalé une seule fois.
    refus_proche_signale: bool = False


def joueur(connexion: Connexion, etat: Etat, compte: str) -> User:
    """Le joueur d'un compte, gardé en mémoire d'une vérification à l'autre."""
    trouve = etat.joueurs.get(compte)
    if trouve is None:
        trouve = trouver_joueur(connexion, compte)
        etat.joueurs[compte] = trouve
        if etat.gestion is not None:
            etat.gestion.nommer(compte, trouve.online_id)
    return trouve


def _dans_la_liste(pseudo: str, compte: str, liste: list[str]) -> bool:
    cibles = {valeur.casefold() for valeur in liste}
    return pseudo.casefold() in cibles or compte.casefold() in cibles


def motif_ignore(pseudo: str, compte: str) -> str | None:
    """Pourquoi une demande n'est pas acceptée d'après reglages.toml, ou None."""
    if _dans_la_liste(pseudo, compte, REGLAGES.liste_noire):
        return "liste noire"
    if REGLAGES.liste_blanche and not _dans_la_liste(
        pseudo, compte, REGLAGES.liste_blanche
    ):
        return "pas dans la liste blanche"
    return None


def signaler_partages(connexion: Connexion, etat: Etat, partages: list[str]) -> None:
    """Signale une seule fois chaque demande de partage du vrai nom.

    Le script ne les accepte jamais : cela dévoilerait votre identité réelle.
    """
    for compte in partages:
        if compte in etat.partages_signales:
            continue
        etat.partages_signales.add(compte)
        journal.info(
            "%s (déjà votre ami) envoie une demande d'ami proche (partage des vrais "
            "noms) : PSN Amis n'y touche pas. Répondez-y vous-même sur la console "
            "ou l'appli PlayStation si vous le souhaitez.",
            joueur(connexion, etat, compte).online_id,
        )


def signaler_types(connexion: Connexion, etat: Etat, demandes: Demandes) -> None:
    """Signale une fois chaque demande laissée en attente à cause de son type."""
    if (
        demandes.partages
        and REGLAGES.refuser_demandes_ami_proche
        and not etat.refus_proche_signale
    ):
        etat.refus_proche_signale = True
        journal.warning("%s", types_demandes.EXPLICATION_REFUS_AMI_PROCHE)
    for compte in demandes.avec_vrai_nom:
        if compte in etat.types_signales:
            continue
        etat.types_signales.add(compte)
        journal.info(
            "Demande de %s laissée en attente : elle demande aussi à partager vos vrais "
            "noms (ami proche). Répondez-y vous-même.",
            joueur(connexion, etat, compte).online_id,
        )
    if REGLAGES.demandes_non_reconnues == "accepter":
        return
    for compte in demandes.inconnues:
        if compte in etat.types_signales:
            continue
        etat.types_signales.add(compte)
        journal.warning(
            "Demande de %s laissée en attente : type de demande non reconnu par PSN "
            "Amis (réglage « Demandes d'un type non reconnu »).",
            joueur(connexion, etat, compte).online_id,
        )


def refuser_liste_noire(connexion: Connexion, etat: Etat, compte: str) -> bool:
    """Refuse la demande d'un joueur de la liste noire ; True si c'est fait.

    Vérifie d'abord auprès de Sony qu'il n'est pas déjà ami : l'opération de refus
    supprimerait sinon l'amitié.
    """
    client = client_psn(connexion)
    try:
        if client.relation(compte).est_ami:
            return False
        client.refuser(compte)
    except ERREURS_A_REMONTER:
        raise
    except (PSNAWPError, psn.ReponseInattendue, requests.RequestException) as erreur:
        journal.debug("Refus impossible pour %s : %s", compte, erreur)
        return False
    return True


def signaler_liste_pleine(etat: Etat, nombre: int) -> None:
    maintenant = time.monotonic()
    if not etat.liste_pleine:
        etat.liste_pleine = True
        etat.dernier_rappel_liste_pleine = maintenant
        journal.error(
            "LISTE D'AMIS PLEINE (%d amis) : impossible d'accepter de nouvelles "
            "demandes. Retirez vous-même des amis (console ou appli PlayStation) ; "
            "le script reprendra tout seul dès qu'il y aura de la place.",
            nombre,
        )
        alerter(
            "PSN Amis : liste d'amis pleine",
            f"{nombre} amis : retirez-en pour que les acceptations reprennent.",
        )
    elif maintenant - etat.dernier_rappel_liste_pleine >= RAPPEL_ACTIVITE:
        etat.dernier_rappel_liste_pleine = maintenant
        journal.warning(
            "Rappel : la liste d'amis est toujours pleine (%d amis).",
            nombre,
            extra=ECRAN_SEULEMENT,
        )


def fin_liste_pleine(etat: Etat) -> None:
    if etat.liste_pleine:
        etat.liste_pleine = False
        # Ces joueurs n'avaient été refusés qu'à cause de la liste pleine.
        etat.mis_de_cote.clear()
        journal.info(
            "De la place s'est libérée dans la liste d'amis : "
            "les acceptations reprennent."
        )


def attentes(
    connexion: Connexion, etat: Etat, demandes: Demandes, comptes: list[str], motif: str
) -> list[Attente]:
    """Les demandes pas encore acceptées, avec pseudo et ancienneté, pour l'affichage."""
    return [
        Attente(
            joueur(connexion, etat, compte).online_id,
            demandes.depuis.get(compte),
            motif,
        )
        for compte in comptes
    ]


def verifier_demandes(
    connexion: Connexion, etat: Etat, suivi: Suivi, commandes: Commandes
) -> None:
    """Récupère les demandes reçues et les accepte une par une."""
    maintenant = time.monotonic()
    etat.mis_de_cote = {
        compte: moment
        for compte, moment in etat.mis_de_cote.items()
        if moment > maintenant
    }
    demandes = demandes_recues(connexion)
    signaler_partages(connexion, etat, demandes.partages)
    signaler_types(connexion, etat, demandes)
    candidats = list(demandes.amis)
    if REGLAGES.demandes_non_reconnues == "accepter":
        candidats += demandes.inconnues

    # Listes noire et blanche des réglages.
    retenus: list[str] = []
    for compte in candidats:
        pseudo = joueur(connexion, etat, compte).online_id
        motif = motif_ignore(pseudo, compte)
        if motif is None:
            retenus.append(compte)
        elif compte not in etat.ignores_signales:
            etat.ignores_signales.add(compte)
            if (
                motif == "liste noire"
                and REGLAGES.liste_noire_refuser
                and refuser_liste_noire(connexion, etat, compte)
            ):
                journal.info("Demande de %s refusée (liste noire).", pseudo)
            else:
                journal.info("Demande de %s ignorée (%s).", pseudo, motif)
    suivi.demandes_trouvees(len(retenus))
    comptes = [compte for compte in retenus if compte not in etat.mis_de_cote]
    if not REGLAGES.acceptation_auto:
        suivi.en_attente(
            attentes(
                connexion, etat, demandes, retenus, "acceptation automatique coupée"
            )
        )
        return
    suivi.en_attente(attentes(connexion, etat, demandes, retenus, ""))

    if not comptes:
        if etat.liste_pleine:
            nombre = nombre_amis(connexion)
            suivi.amis(nombre)
            if nombre < LIMITE_AMIS_PSN:
                fin_liste_pleine(etat)
        return

    for rang, compte in enumerate(comptes):
        # Pause (touche P) ou arrêt demandés : on s'arrête là, sans rien perdre.
        if commandes.pause.is_set() or commandes.arret.is_set():
            return
        if rang > 0 and commandes.arret.wait(PAUSE_ENTRE_ACCEPTATIONS):
            return
        demandeur = joueur(connexion, etat, compte)
        try:
            demandeur.accept_friend_request()
        except ERREURS_A_REMONTER:
            raise
        except PSNAWPNotFoundError:
            journal.info("%s a annulé sa demande entre-temps.", demandeur.online_id)
            continue
        except PSNAWPClientError as refus:
            journal.debug("Refus de Sony pour %s :", compte, exc_info=refus)
            etat.mis_de_cote[compte] = time.monotonic() + DUREE_MISE_DE_COTE
            nombre = nombre_amis(connexion)
            suivi.amis(nombre)
            if nombre >= LIMITE_AMIS_PSN:
                signaler_liste_pleine(etat, nombre)
                # Inutile d'essayer les suivants : on réessaie au prochain tour.
                return
            journal.warning(
                "Demande de %s refusée par Sony (%s). Nouvel essai dans %s.",
                demandeur.online_id,
                raison(refus),
                duree(DUREE_MISE_DE_COTE),
            )
            continue
        fin_liste_pleine(etat)
        etat.acceptees += 1
        etat.ajouts_depuis_reprise += 1
        # Connu tout de suite : s'il nous retire avant le prochain comptage, on le verra.
        if etat.amis_connus is not None:
            etat.amis_connus.add(compte)
        suivi.ajout(demandeur.online_id)
        if etat.gestion is not None:
            etat.gestion.accepte(compte, demandeur.online_id)
        journal.info(
            "Demande acceptée : %s", demandeur.online_id, extra={"genre": GENRE_AJOUT}
        )
        limite = REGLAGES.pause_apres_ajouts
        if limite and etat.ajouts_depuis_reprise >= limite:
            commandes.pause.set()
            journal.info(
                "Pause automatique après %d ajout(s) : touche P pour reprendre.", limite
            )
            return


def recompter_amis(connexion: Connexion, etat: Etat, suivi: Suivi) -> None:
    """Recompte les amis auprès de Sony et note chaque ami qui n'est plus dans la liste."""
    amis, total = liste_amis(connexion)
    avant = suivi.amis(total)
    # Si Sony n'a pas renvoyé toute la liste, on ne compare pas (faux retraits).
    complete = len(amis) >= total
    retires = []
    if etat.amis_connus is not None and complete:
        retires = sorted(etat.amis_connus - amis)
    if etat.gestion is not None:
        # Les amis supprimés par PSN Amis ne sont pas des « retraits » inconnus.
        retires = etat.gestion.filtrer_retraits(retires)
        etat.gestion.observer(amis, complete)

    for compte in retires[:NOMBRE_MAX_RETRAITS_DETAILLES]:
        pseudo = joueur(connexion, etat, compte).online_id
        suivi.retrait(pseudo)
        journal.info("Ami retiré : %s", pseudo, extra={"genre": GENRE_RETRAIT})
    if len(retires) > NOMBRE_MAX_RETRAITS_DETAILLES:
        journal.info(
            "... et %d autre(s) ami(s) retiré(s).",
            len(retires) - NOMBRE_MAX_RETRAITS_DETAILLES,
            extra={"genre": GENRE_RETRAIT},
        )
    if complete and amis != etat.amis_connus:
        memoriser_amis(connexion.pseudo, amis)
    etat.amis_connus = amis if complete else None

    # Écart que les retraits n'expliquent pas (ami ajouté depuis la console, par ex.).
    if avant is not None and total != avant - len(retires):
        journal.info(
            "Amis recomptés auprès de Sony : %s (au lieu de %d affichés).",
            en_amis(total),
            avant,
        )


# ─── Mémoire des amis entre deux lancements ───────────────────────────────────
def memoriser_amis(compte: str, amis: set[str]) -> None:
    """Garde la liste des amis connus dans amis.json (identifiants seulement)."""
    contenu = {
        "compte": compte,
        "date": datetime.now().isoformat(timespec="seconds"),
        "amis": sorted(amis),
    }
    try:
        FICHIER_AMIS.parent.mkdir(parents=True, exist_ok=True)
        FICHIER_AMIS.write_text(json.dumps(contenu), encoding="utf-8")
    except OSError as erreur:
        journal.debug("amis.json impossible à écrire : %s", erreur)


def amis_memorises(compte: str) -> set[str] | None:
    """Les amis connus au dernier arrêt, pour ce compte ; None s'il n'y en a pas."""
    try:
        contenu = json.loads(FICHIER_AMIS.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    if not isinstance(contenu, dict) or contenu.get("compte") != compte:
        return None
    amis = contenu.get("amis")
    if not isinstance(amis, list):
        return None
    return {compte for compte in amis if isinstance(compte, str)}


def retraits_pendant_l_arret(
    connexion: Connexion, etat: Etat, suivi: Suivi, amis: set[str]
) -> None:
    """Au démarrage : compare la liste d'amis à celle du dernier arrêt."""
    anciens = amis_memorises(connexion.pseudo)
    if anciens is None:
        return
    retires = sorted(anciens - amis)
    for compte in retires[:NOMBRE_MAX_RETRAITS_DETAILLES]:
        pseudo = joueur(connexion, etat, compte).online_id
        suivi.retrait(pseudo)
        journal.info(
            "Ami retiré pendant l'arrêt : %s", pseudo, extra={"genre": GENRE_RETRAIT}
        )
    if len(retires) > NOMBRE_MAX_RETRAITS_DETAILLES:
        journal.info(
            "... et %d autre(s) ami(s) retiré(s) pendant l'arrêt.",
            len(retires) - NOMBRE_MAX_RETRAITS_DETAILLES,
            extra={"genre": GENRE_RETRAIT},
        )


# ─── Nouvelle version ─────────────────────────────────────────────────────────
def signaler_nouvelle_version() -> None:
    """Dans un fil à part : dit s'il existe une version plus récente sur GitHub."""
    if not REGLAGES.verifier_mises_a_jour:
        return

    def verifier() -> None:
        derniere = mises_a_jour.derniere_version()
        if derniere and mises_a_jour.plus_recente(VERSION, derniere):
            journal.info(
                "Nouvelle version disponible : %s (vous avez la %s). %s",
                derniere,
                VERSION,
                mises_a_jour.PAGE,
            )

    threading.Thread(target=verifier, name="mises-a-jour", daemon=True).start()


# ─── Boucle principale ────────────────────────────────────────────────────────
def attente_progressive(erreurs_de_suite: int) -> int:
    """30 s, puis 1 min, 2 min, 4 min, et 5 min au maximum."""
    return min(30 * 2 ** (erreurs_de_suite - 1), ATTENTE_MAX_APRES_ERREUR)


def attentes_en_pause(connexion: Connexion, etat: Etat, suivi: Suivi) -> None:
    """Pendant une pause : met à jour la liste des demandes qui attendent."""
    try:
        connexion.renouveler_acces_si_besoin()
        demandes = demandes_recues(connexion)
        suivi.en_attente(attentes(connexion, etat, demandes, demandes.amis, "en pause"))
    except (requests.RequestException, PSNAWPError, AdresseNonSony) as erreur:
        journal.debug("Lecture des demandes en pause impossible : %s", erreur)


def outils_de_gestion(
    connexion: Connexion, etat: Etat, suivi: Suivi, commandes: Commandes
) -> Any:
    """Ce que le moteur prête à la gestion des amis pendant qu'elle travaille."""
    from psn_amis.gestion import Outils

    def supprime(compte: str, nom: str) -> None:
        if etat.amis_connus is not None:
            etat.amis_connus.discard(compte)
        suivi.suppression(nom)
        journal.info(
            "Ami supprimé par PSN Amis : %s", nom, extra={"genre": GENRE_SUPPRESSION}
        )

    return Outils(
        client=client_psn(connexion),
        rafraichir=connexion.renouveler_acces_si_besoin,
        arret=commandes.arret.is_set,
        supprime=supprime,
        alerter=alerter,
    )


def faire_travailler_la_gestion(
    connexion: Connexion, etat: Etat, suivi: Suivi, commandes: Commandes
) -> None:
    """Opérations demandées depuis l'onglet Amis, puis nettoyage automatique."""
    if etat.gestion is None or commandes.arret.is_set():
        return
    vue_avant = etat.gestion.vue()
    if vue_avant.en_file:
        suivi.statut(Statut.SUPPRESSION, vue_avant.tache or "Gestion des amis…")
    etat.gestion.travailler(outils_de_gestion(connexion, etat, suivi, commandes))


def tourner_en_continu(
    etat: Etat, suivi: Suivi, commandes: Commandes, gestion: Any = None
) -> None:
    """Vérifie et accepte les demandes jusqu'à l'arrêt. Ne s'arrête jamais tout seul.

    `gestion` (gestion.Gestion) ajoute la gestion des amis : ses opérations passent
    par ce même fil, entre deux vérifications.
    """
    if gestion is not None:
        etat.gestion = gestion
    connexion: Connexion | None = None
    erreurs_de_suite = 0
    dernier_rappel = time.monotonic()
    en_pause = False
    try:
        while not commandes.arret.is_set():
            if commandes.pause.is_set():
                en_pause = True
                suivi.statut(Statut.PAUSE, "Les demandes attendent · P : reprendre")
                if connexion is not None:
                    attentes_en_pause(connexion, etat, suivi)
                    # La gestion des amis reste possible pendant la pause.
                    try:
                        faire_travailler_la_gestion(connexion, etat, suivi, commandes)
                    except (requests.RequestException, PSNAWPError) as erreur:
                        journal.warning("Gestion des amis interrompue : %s", erreur)
                    if commandes.pause.is_set():
                        suivi.statut(
                            Statut.PAUSE, "Les demandes attendent · P : reprendre"
                        )
                commandes.attendre(INTERVALLE_VERIFICATION)
                continue
            if en_pause:
                en_pause = False
                etat.ajouts_depuis_reprise = 0

            attente: float = INTERVALLE_VERIFICATION
            statut_suivant, detail = Statut.EN_MARCHE, "En attente de demandes d'amis"
            try:
                if connexion is not None and commandes.reconnecter.is_set():
                    # Nouveau code npsso (touche C) : on repart avec ce compte.
                    connexion.fermer()
                    connexion = None
                if connexion is not None and connexion.expire_bientot():
                    journal.info("Renouvellement de la connexion à Sony...")
                    connexion.fermer()
                    connexion = None
                if connexion is None:
                    commandes.reconnecter.clear()
                    connexion = connecter(suivi, commandes, attendre=True)
                    if connexion is None:
                        break
                    etat.joueurs.clear()
                    if etat.gestion is not None:
                        etat.gestion.connecte(connexion.compte_id, connexion.pseudo)
                    amis, total_amis = liste_amis(connexion)
                    complete = len(amis) >= total_amis
                    if etat.gestion is not None:
                        etat.gestion.observer(amis, complete)
                    suivi.connecte(connexion.pseudo, total_amis)
                    journal.info(
                        "Connecté au compte PSN %s (%s). "
                        "Vérification toutes les %d secondes.",
                        connexion.pseudo,
                        en_amis(total_amis),
                        INTERVALLE_VERIFICATION,
                    )
                    journal.info("Pour arrêter : Ctrl+C.", extra=AIDE)
                    if complete:
                        retraits_pendant_l_arret(connexion, etat, suivi, amis)
                        memoriser_amis(connexion.pseudo, amis)
                    etat.amis_connus = amis if complete else None
                connexion.renouveler_acces_si_besoin()
                suivi.statut(Statut.VERIFICATION, "Vérification des demandes…")
                verifier_demandes(connexion, etat, suivi, commandes)
                recompter_amis(connexion, etat, suivi)
                suivi.verification_terminee()
                faire_travailler_la_gestion(connexion, etat, suivi, commandes)
                erreurs_de_suite = 0
                if etat.liste_pleine:
                    statut_suivant = Statut.LISTE_PLEINE
                    detail = (
                        "Retirez des amis : reprise automatique "
                        "dès qu'il y a de la place"
                    )
            except PSNAWPAuthenticationError, PSNAWPUnauthorizedError:
                journal.info(
                    "Session Sony expirée : reconnexion automatique dans 10 secondes."
                )
                if connexion is not None:
                    connexion.fermer()
                connexion = None
                attente = 10
                statut_suivant, detail = Statut.CONNEXION, "Reconnexion à Sony"
            except PSNAWPTooManyRequestsError:
                attente = ATTENTE_SI_TROP_DE_REQUETES
                journal.warning(
                    "Sony demande de ralentir : pause de %s.", duree(attente)
                )
                statut_suivant, detail = Statut.ATTENTE, "Sony demande de ralentir"
            except requests.RequestException as erreur:
                erreurs_de_suite += 1
                attente = attente_progressive(erreurs_de_suite)
                journal.debug("Détail de la coupure :", exc_info=erreur)
                journal.warning(
                    "Pas d'accès à Internet, ou serveurs Sony injoignables. "
                    "Nouvel essai dans %s.",
                    duree(attente),
                )
                if erreurs_de_suite == ESSAIS_AVANT_ALERTE:
                    alerter(
                        "PSN Amis : hors ligne",
                        "Sony est injoignable depuis plusieurs minutes. "
                        "Nouvel essai automatique.",
                    )
                statut_suivant = Statut.HORS_LIGNE
                detail = "Pas d'accès à Internet ou serveurs Sony injoignables"
            except PSNAWPServerError as erreur:
                erreurs_de_suite += 1
                attente = attente_progressive(erreurs_de_suite)
                journal.debug("Détail de l'erreur Sony :", exc_info=erreur)
                journal.warning(
                    "Les serveurs PlayStation ont un problème passager. "
                    "Nouvel essai dans %s.",
                    duree(attente),
                )
                statut_suivant = Statut.ATTENTE
                detail = "Serveurs PlayStation en difficulté"
            # Filet de sécurité voulu : le script ne doit jamais s'arrêter tout seul.
            except Exception as erreur:  # noqa: BLE001
                erreurs_de_suite += 1
                attente = attente_progressive(erreurs_de_suite)
                journal.debug("Détail de l'erreur inattendue :", exc_info=erreur)
                journal.error(
                    "Erreur inattendue (%s : %s). Nouvel essai dans %s.",
                    type(erreur).__name__,
                    erreur,
                    duree(attente),
                )
                statut_suivant = Statut.ERREUR
                detail = f"{type(erreur).__name__} : {erreur}"
                # Après 3 erreurs de suite, on repart d'une connexion neuve.
                if erreurs_de_suite >= 3 and connexion is not None:
                    connexion.fermer()
                    connexion = None

            if commandes.arret.is_set():
                break
            if commandes.pause.is_set():
                # Pause automatique : le statut « pause » est posé au tour suivant.
                continue
            suivi.statut(statut_suivant, detail, prochaine_dans=attente)
            if time.monotonic() - dernier_rappel >= RAPPEL_ACTIVITE:
                dernier_rappel = time.monotonic()
                journal.info(
                    "Toujours actif : %d demande(s) acceptée(s) depuis le lancement.",
                    etat.acceptees,
                    extra={**ECRAN_SEULEMENT, "genre": GENRE_RAPPEL},
                )
            commandes.attendre(attente)
    finally:
        if connexion is not None:
            connexion.fermer()


def tester(suivi: Suivi, commandes: Commandes) -> int:
    """Affiche le compte connecté et les demandes en attente, sans rien accepter."""
    try:
        connexion = connecter(suivi, commandes, attendre=False)
        if connexion is None:
            return 1
        try:
            journal.info(
                "Connecté au compte PSN %s (%s).",
                connexion.pseudo,
                en_amis(nombre_amis(connexion)),
            )
            demandes = demandes_recues(connexion)
            comptes = demandes.amis
            if demandes.partages:
                journal.info(
                    "%d demande(s) de partage du vrai nom (le script n'y touche pas).",
                    len(demandes.partages),
                )
            if not comptes:
                journal.info("Aucune demande d'ami en attente.")
            else:
                journal.info("%d demande(s) d'ami en attente :", len(comptes))
                for compte in comptes[:NOMBRE_MAX_PSEUDOS_TEST]:
                    journal.info("  - %s", trouver_joueur(connexion, compte).online_id)
                if len(comptes) > NOMBRE_MAX_PSEUDOS_TEST:
                    journal.info(
                        "  ... et %d autre(s).", len(comptes) - NOMBRE_MAX_PSEUDOS_TEST
                    )
            journal.info("Mode test terminé : aucune demande n'a été acceptée.")
            return 0
        finally:
            connexion.fermer()
    except requests.RequestException:
        journal.info(
            "Impossible de joindre les serveurs de Sony : "
            "vérifiez votre connexion Internet."
        )
    except PSNAWPError as erreur:
        journal.info("Sony a renvoyé une erreur : %s", raison(erreur))
    return 1
