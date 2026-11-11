"""Moteur de PSN Amis : connexion à Sony et acceptation des demandes d'amis.

Ce fichier ne dessine rien : il publie son état dans un objet Suivi, que le tableau de
bord (tableau_de_bord.py) lit pour afficher la console en couleur.

Sécurité :
- le code npsso est lu dans npsso.txt ; il n'est jamais affiché ni écrit dans journal.txt ;
- seuls les serveurs de Sony (sony.com, playstation.com, playstation.net) sont contactés ;
- le script ne retire jamais d'amis.
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
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
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

# Version du programme (la même que dans pyproject.toml et CHANGELOG.md).
VERSION = "2.2.0"

# ─── Réglages ─────────────────────────────────────────────────────────────────
# Secondes entre deux vérifications. À chaque fois : demandes reçues acceptées, puis
# liste d'amis recomptée (pour repérer les amis retirés).
INTERVALLE_VERIFICATION = 15
# Secondes de pause entre deux acceptations.
PAUSE_ENTRE_ACCEPTATIONS = 2
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
# Nombre maximum d'amis sur un compte PSN (limite officielle de Sony).
LIMITE_AMIS_PSN = 2000
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

# ─── Fichiers et adresses ─────────────────────────────────────────────────────
DOSSIER = Path(__file__).resolve().parent
FICHIER_NPSSO = DOSSIER / "npsso.txt"
FICHIER_JOURNAL = DOSSIER / "journal.txt"
FICHIER_VERROU = DOSSIER / "accepter_amis.lock"

DOMAINES_SONY = ("sony.com", "playstation.com", "playstation.net")
ADRESSE_CODE_NPSSO = "https://ca.account.sony.com/api/v1/ssocookie"

ETAPES_CODE_NPSSO = f"""\
  1. Dans votre navigateur, connectez-vous sur https://www.playstation.com avec votre compte PSN.
  2. Dans le même navigateur, ouvrez : {ADRESSE_CODE_NPSSO}
  3. Double-cliquez sur le code de 64 caractères et copiez-le (Ctrl+C)."""
AIDE_NPSSO = f"""Pour mettre un nouveau code npsso :
{ETAPES_CODE_NPSSO}
  4. Dans PSN Amis, appuyez sur C, puis collez le code (Ctrl+V) et validez avec Entrée.
     Sans le tableau de bord : « accepter_amis.py --configurer », ou mettez le code
     dans npsso.txt avec le Bloc-notes (dossier {DOSSIER}).
  Attention : ne le faites pas pendant un live, le code serait visible à l'écran."""

# ─── Journal (journal.txt + écran), avec masquage du code npsso ───────────────
journal = logging.getLogger("psn_amis")

GENRE_AJOUT = "ajout"
# Un ami ne fait plus partie de la liste (il vous a retiré, ou vous l'avez retiré).
GENRE_RETRAIT = "retrait"
# Explications longues : le tableau de bord les affiche dans son propre panneau.
GENRE_AIDE = "aide"
# « Toujours actif » : inutile quand le tableau de bord est affiché.
GENRE_RAPPEL = "rappel"

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


def configurer_journal(*, ecran: bool, fichier: bool) -> None:
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

    journal.setLevel(logging.INFO)
    journal.propagate = False

    # sys.stdout est absent quand le script tourne sans fenêtre.
    if ecran and sys.stdout is not None:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        gestionnaire = logging.StreamHandler(sys.stdout)
        gestionnaire.setFormatter(
            FormatMasque("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
        )
        journal.addHandler(gestionnaire)

    if fichier:
        gestionnaire = logging.handlers.RotatingFileHandler(
            FICHIER_JOURNAL, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        gestionnaire.setFormatter(
            FormatMasque("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        gestionnaire.addFilter(SansMessagesEcran())
        journal.addHandler(gestionnaire)


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
    """Laisse la priorité à Black Ops 2, OBS et TikTok LIVE Studio."""
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
    LISTE_PLEINE = "liste pleine"
    ERREUR = "erreur"


@dataclass(frozen=True)
class Ajout:
    moment: datetime
    pseudo: str


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
    ajouts_session: int
    ajouts_jour: int
    # Du plus récent au plus ancien.
    derniers_ajouts: tuple[Ajout, ...]
    evenements: tuple[Evenement, ...]
    debut: datetime
    # Moment de la prochaine vérification, sur l'horloge time.monotonic().
    prochaine_verification: float | None
    intervalle: float
    derniere_verification: datetime | None
    probleme_npsso: str | None
    # Heure du dernier comptage des amis auprès de Sony.
    amis_comptes_a: datetime | None


class Suivi:
    """État du moteur, lu par l'affichage. Un verrou le protège : deux fils l'utilisent."""

    def __init__(self, ajouts_du_jour: list[Ajout] | None = None) -> None:
        precedents = sorted(ajouts_du_jour or [], key=lambda ajout: ajout.moment)
        self._verrou = threading.Lock()
        self._statut = Statut.DEMARRAGE
        self._detail = "Démarrage…"
        self._pseudo_compte: str | None = None
        self._nombre_amis: int | None = None
        self._en_attente: int | None = None
        self._ajouts_session = 0
        self._jour = date.today()
        self._ajouts_jour = len(precedents)
        self._derniers: deque[Ajout] = deque(reversed(precedents[-200:]), maxlen=200)
        self._evenements: deque[Evenement] = deque(maxlen=100)
        self._debut = datetime.now()
        self._prochaine: float | None = None
        self._intervalle = float(INTERVALLE_VERIFICATION)
        self._derniere_verification: datetime | None = None
        self._probleme_npsso: str | None = None
        self._amis_comptes_a: datetime | None = None

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
                ajouts_session=self._ajouts_session,
                ajouts_jour=self._ajouts_jour,
                derniers_ajouts=tuple(self._derniers),
                evenements=tuple(self._evenements),
                debut=self._debut,
                prochaine_verification=self._prochaine,
                intervalle=self._intervalle,
                derniere_verification=self._derniere_verification,
                probleme_npsso=self._probleme_npsso,
                amis_comptes_a=self._amis_comptes_a,
            )

    def _changer_de_jour_si_besoin(self, jour: date) -> None:
        if jour != self._jour:
            self._jour = jour
            self._ajouts_jour = 0


class Commandes:
    """Ordres envoyés au moteur depuis le clavier : pause, vérification, arrêt."""

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


MOTIF_AJOUT = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})  Demande acceptée : (.+)$"
)


def ajouts_du_jour_dans_journal() -> list[Ajout]:
    """Relit les ajouts d'aujourd'hui dans journal.txt (et ses archives) au démarrage."""
    aujourd_hui = date.today()
    fichiers = [
        FICHIER_JOURNAL.with_name(f"{FICHIER_JOURNAL.name}.{numero}")
        for numero in (3, 2, 1)
    ] + [FICHIER_JOURNAL]
    ajouts: list[Ajout] = []
    for fichier in fichiers:
        try:
            lignes = fichier.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for ligne in lignes:
            correspondance = MOTIF_AJOUT.match(ligne)
            if not correspondance:
                continue
            moment = datetime.strptime(correspondance[1], "%Y-%m-%d %H:%M:%S")
            if moment.date() == aujourd_hui:
                ajouts.append(Ajout(moment, correspondance[2].strip()))
    return ajouts


# ─── Code npsso ───────────────────────────────────────────────────────────────
class ProblemeNpsso(Exception):
    """Le fichier npsso.txt est absent, illisible ou mal rempli."""


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


def lire_npsso() -> str:
    """Lit le code dans npsso.txt et vérifie son format, sans jamais l'afficher."""
    try:
        brut = FICHIER_NPSSO.read_bytes()
    except FileNotFoundError:
        raise ProblemeNpsso(
            f"le fichier npsso.txt est introuvable dans {DOSSIER}."
        ) from None
    except OSError:
        raise ProblemeNpsso("Windows refuse d'ouvrir npsso.txt.") from None

    # Enregistré en « UTF-16 » par le Bloc-notes : on le décode quand même.
    if brut.startswith((b"\xff\xfe", b"\xfe\xff")):
        texte = brut.decode("utf-16", errors="ignore")
    else:
        texte = brut.decode("utf-8-sig", errors="ignore")
    return extraire_npsso(texte, "le contenu de npsso.txt")


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


def enregistrer_npsso(saisie: str) -> None:
    """Vérifie un code collé et l'écrit dans npsso.txt, réservé au compte Windows."""
    code = extraire_npsso(saisie, "le code collé")
    FICHIER_NPSSO.write_text(code + "\n", encoding="utf-8")
    proteger_fichier(FICHIER_NPSSO)


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
            enregistrer_npsso(saisie)
        except ProblemeNpsso as probleme:
            dire(f"Ce n'est pas un code valide : {probleme} Réessayez.")
            continue
        dire(
            "Code enregistré dans npsso.txt, lisible seulement par votre compte "
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
    # Première requête : c'est là que Sony vérifie le code.
    pseudo = psnawp.me().online_id
    return Connexion(psnawp, pseudo)


def connecter(suivi: Suivi, commandes: Commandes, attendre: bool) -> Connexion | None:
    """Se connecte à Sony. Si le code est absent, mal rempli ou refusé, explique quoi
    faire, puis attend un nouveau code (attendre=True) ou abandonne (attendre=False).
    Renvoie None si l'arrêt est demandé. Les coupures réseau remontent à l'appelant."""
    while not commandes.arret.is_set():
        suivi.statut(Statut.CONNEXION, "Connexion aux serveurs de Sony…")
        journal.info("Connexion aux serveurs de Sony...", extra=ECRAN_SEULEMENT)
        try:
            connexion = ouvrir_connexion(lire_npsso())
        except ProblemeNpsso as probleme:
            texte = f"PROBLÈME avec le code npsso : {probleme}"
        except PSNAWPAuthenticationError:
            texte = "PROBLÈME : Sony refuse le code npsso (il est expiré ou incorrect)."
        else:
            suivi.code_valide()
            return connexion
        journal.error("%s", texte)
        suivi.code_a_changer(texte)
        journal.info(AIDE_NPSSO, extra=AIDE)
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
    amis: list[str] = []
    partages: list[str] = []
    for demande in reponse.get("receivedRequests", []):
        compte = demande.get("accountId")
        if not compte:
            continue
        if demande.get("relation") == "friend":
            partages.append(compte)
        else:
            amis.append(compte)
    return Demandes(amis, partages)


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


def signaler_partages(connexion: Connexion, etat: Etat, partages: list[str]) -> None:
    """Signale une seule fois chaque demande de partage du vrai nom.

    Le script ne les accepte jamais : cela dévoilerait votre identité réelle.
    """
    for compte in partages:
        if compte in etat.partages_signales:
            continue
        etat.partages_signales.add(compte)
        journal.info(
            "%s (déjà votre ami) demande à partager vos vrais noms : le script n'y "
            "touche pas. Répondez vous-même sur la console si vous le souhaitez.",
            trouver_joueur(connexion, compte).online_id,
        )


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
    suivi.demandes_trouvees(len(demandes.amis))
    comptes = [compte for compte in demandes.amis if compte not in etat.mis_de_cote]

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
        joueur = trouver_joueur(connexion, compte)
        try:
            joueur.accept_friend_request()
        except ERREURS_A_REMONTER:
            raise
        except PSNAWPNotFoundError:
            journal.info("%s a annulé sa demande entre-temps.", joueur.online_id)
            continue
        except PSNAWPClientError as refus:
            etat.mis_de_cote[compte] = time.monotonic() + DUREE_MISE_DE_COTE
            nombre = nombre_amis(connexion)
            suivi.amis(nombre)
            if nombre >= LIMITE_AMIS_PSN:
                signaler_liste_pleine(etat, nombre)
                # Inutile d'essayer les suivants : on réessaie au prochain tour.
                return
            journal.warning(
                "Demande de %s refusée par Sony (%s). Nouvel essai dans %s.",
                joueur.online_id,
                raison(refus),
                duree(DUREE_MISE_DE_COTE),
            )
            continue
        fin_liste_pleine(etat)
        etat.acceptees += 1
        # Connu tout de suite : s'il nous retire avant le prochain comptage, on le verra.
        if etat.amis_connus is not None:
            etat.amis_connus.add(compte)
        suivi.ajout(joueur.online_id)
        journal.info(
            "Demande acceptée : %s", joueur.online_id, extra={"genre": GENRE_AJOUT}
        )


def recompter_amis(connexion: Connexion, etat: Etat, suivi: Suivi) -> None:
    """Recompte les amis auprès de Sony et note chaque ami qui n'est plus dans la liste."""
    amis, total = liste_amis(connexion)
    avant = suivi.amis(total)
    # Si Sony n'a pas renvoyé toute la liste, on ne compare pas (faux retraits).
    complete = len(amis) >= total
    retires = []
    if etat.amis_connus is not None and complete:
        retires = sorted(etat.amis_connus - amis)

    for compte in retires[:NOMBRE_MAX_RETRAITS_DETAILLES]:
        journal.info(
            "Ami retiré : %s",
            trouver_joueur(connexion, compte).online_id,
            extra={"genre": GENRE_RETRAIT},
        )
    if len(retires) > NOMBRE_MAX_RETRAITS_DETAILLES:
        journal.info(
            "... et %d autre(s) ami(s) retiré(s).",
            len(retires) - NOMBRE_MAX_RETRAITS_DETAILLES,
            extra={"genre": GENRE_RETRAIT},
        )
    etat.amis_connus = amis if complete else None

    # Écart que les retraits n'expliquent pas (ami ajouté depuis la console, par ex.).
    if avant is not None and total != avant - len(retires):
        journal.info(
            "Amis recomptés auprès de Sony : %s (au lieu de %d affichés).",
            en_amis(total),
            avant,
        )


# ─── Boucle principale ────────────────────────────────────────────────────────
def attente_progressive(erreurs_de_suite: int) -> int:
    """30 s, puis 1 min, 2 min, 4 min, et 5 min au maximum."""
    return min(30 * 2 ** (erreurs_de_suite - 1), ATTENTE_MAX_APRES_ERREUR)


def tourner_en_continu(etat: Etat, suivi: Suivi, commandes: Commandes) -> None:
    """Vérifie et accepte les demandes jusqu'à l'arrêt. Ne s'arrête jamais tout seul."""
    connexion: Connexion | None = None
    erreurs_de_suite = 0
    dernier_rappel = time.monotonic()
    try:
        while not commandes.arret.is_set():
            if commandes.pause.is_set():
                suivi.statut(
                    Statut.PAUSE,
                    "Les nouvelles demandes attendent. Touche P pour reprendre.",
                )
                commandes.attendre(3600)
                continue

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
                    amis, total_amis = liste_amis(connexion)
                    etat.amis_connus = amis if len(amis) >= total_amis else None
                    suivi.connecte(connexion.pseudo, total_amis)
                    journal.info(
                        "Connecté au compte PSN %s (%s). "
                        "Vérification toutes les %d secondes.",
                        connexion.pseudo,
                        en_amis(total_amis),
                        INTERVALLE_VERIFICATION,
                    )
                    journal.info("Pour arrêter : Ctrl+C.", extra=AIDE)
                connexion.renouveler_acces_si_besoin()
                suivi.statut(Statut.VERIFICATION, "Vérification des demandes…")
                verifier_demandes(connexion, etat, suivi, commandes)
                recompter_amis(connexion, etat, suivi)
                suivi.verification_terminee()
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
            except requests.RequestException:
                erreurs_de_suite += 1
                attente = attente_progressive(erreurs_de_suite)
                journal.warning(
                    "Pas d'accès à Internet, ou serveurs Sony injoignables. "
                    "Nouvel essai dans %s.",
                    duree(attente),
                )
                statut_suivant = Statut.HORS_LIGNE
                detail = "Pas d'accès à Internet ou serveurs Sony injoignables"
            except PSNAWPServerError:
                erreurs_de_suite += 1
                attente = attente_progressive(erreurs_de_suite)
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
