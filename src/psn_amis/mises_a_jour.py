"""Mises à jour de PSN Amis depuis les publications GitHub du projet.

C'est la seule partie qui ne contacte pas Sony. Elle ne fait rien sans l'accord de
l'utilisateur : la vérification au lancement est un réglage (coupé par défaut), et
l'installation n'a lieu qu'après un clic sur « Installer la mise à jour ».

Sécurité du téléchargement :
- HTTPS avec vérification des certificats (comportement par défaut de requests) ;
- seulement l'installateur officiel du dépôt LASCAMPIA67/psn-amis, nommé
  PSN-Amis-Setup-X.Y.Z.exe, depuis github.com et ses serveurs de fichiers ;
- taille et empreinte SHA-256 comparées à celles annoncées par GitHub (champ
  « digest » de l'API) et au fichier SHA256SUMS.txt de la publication.
  Ces deux empreintes viennent de GitHub, comme le fichier : elles prouvent que le
  téléchargement est intact, pas qu'il est authentique. L'authenticité repose sur le
  compte GitHub du projet et, si l'installateur est signé, sur sa signature
  Authenticode (vérifiée avant le lancement).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

DEPOT = "LASCAMPIA67/psn-amis"
ADRESSE = f"https://api.github.com/repos/{DEPOT}/releases/latest"
PAGE = f"https://github.com/{DEPOT}/releases/latest"
HOTES_AUTORISES = (
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
)
CHEMIN_TELECHARGEMENT = f"/{DEPOT}/releases/download/"
MOTIF_INSTALLATEUR = re.compile(r"^PSN-Amis-Setup-(\d+\.\d+\.\d+)\.exe$")
FICHIER_EMPREINTES = "SHA256SUMS.txt"
EN_TETES = {"Accept": "application/vnd.github+json", "User-Agent": "psn-amis"}
TAILLE_MAX = 400 * 1024 * 1024
DELAI = 15


class ErreurMiseAJour(Exception):
    """Mise à jour impossible : le message est destiné à l'utilisateur."""


# ─── Versions ─────────────────────────────────────────────────────────────────


def version_stable(texte: str) -> tuple[int, int, int] | None:
    """« v2.10.1 » → (2, 10, 1). None pour une préversion (« 3.0.0-rc.1 ») ou un texte
    qui n'est pas une version X.Y.Z : seules les versions stables sont proposées."""
    correspondance = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", texte.strip())
    if correspondance is None:
        return None
    majeur, mineur, correctif = (int(n) for n in correspondance.groups())
    return majeur, mineur, correctif


def numero(version: str) -> tuple[int, ...]:
    """« v2.5.0 » → (2, 5, 0) ; (0,) si illisible. Gardé pour la compatibilité."""
    return version_stable(version) or (0,)


def plus_recente(actuelle: str, derniere: str) -> bool:
    nouvelle = version_stable(derniere)
    installee = version_stable(actuelle)
    return nouvelle is not None and installee is not None and nouvelle > installee


# ─── Publication ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Fichier:
    nom: str
    adresse: str
    taille: int
    # Empreinte SHA-256 annoncée par GitHub (en hexadécimal), si disponible.
    empreinte: str | None


@dataclass(frozen=True)
class Publication:
    version: str
    notes: str
    page: str
    installateur: Fichier | None
    empreintes: Fichier | None


def _fichier(brut: object) -> Fichier | None:
    if not isinstance(brut, dict):
        return None
    nom, adresse, taille = (
        brut.get("name"),
        brut.get("browser_download_url"),
        brut.get("size"),
    )
    if not (
        isinstance(nom, str) and isinstance(adresse, str) and isinstance(taille, int)
    ):
        return None
    digest = brut.get("digest")
    empreinte = None
    if isinstance(digest, str) and digest.startswith("sha256:"):
        empreinte = digest.removeprefix("sha256:").lower()
    return Fichier(nom, adresse, taille, empreinte)


def lire_publication(donnees: object) -> Publication | None:
    """La publication décrite par l'API GitHub, si c'est une version stable."""
    if not isinstance(donnees, dict):
        return None
    if donnees.get("draft") or donnees.get("prerelease"):
        return None
    etiquette = donnees.get("tag_name")
    if not isinstance(etiquette, str) or version_stable(etiquette) is None:
        return None
    version = etiquette.removeprefix("v")
    installateur = empreintes = None
    for brut in donnees.get("assets", []) or []:
        fichier = _fichier(brut)
        if fichier is None:
            continue
        correspondance = MOTIF_INSTALLATEUR.fullmatch(fichier.nom)
        if correspondance and correspondance.group(1) == version:
            installateur = fichier
        elif fichier.nom == FICHIER_EMPREINTES:
            empreintes = fichier
    notes = donnees.get("body")
    page = donnees.get("html_url")
    return Publication(
        version=version,
        notes=notes if isinstance(notes, str) else "",
        page=page if isinstance(page, str) and page.startswith("https://") else PAGE,
        installateur=installateur,
        empreintes=empreintes,
    )


def derniere_publication() -> Publication | None:
    """La dernière version stable publiée ; None si GitHub est injoignable."""
    try:
        reponse = requests.get(ADRESSE, headers=EN_TETES, timeout=DELAI)
        reponse.raise_for_status()
        return lire_publication(reponse.json())
    except requests.RequestException, ValueError:
        return None


def derniere_version() -> str | None:
    """Le numéro de la dernière version publiée (sans « v »), ou None si inconnu."""
    try:
        reponse = requests.get(ADRESSE, headers=EN_TETES, timeout=10)
        reponse.raise_for_status()
        etiquette = reponse.json().get("tag_name", "")
    except requests.RequestException, ValueError, AttributeError:
        return None
    return etiquette.removeprefix("v") if isinstance(etiquette, str) else None


# ─── Téléchargement vérifié ───────────────────────────────────────────────────


def adresse_autorisee(adresse: str, initiale: bool = True) -> bool:
    """HTTPS vers GitHub seulement ; l'adresse de départ doit être celle du dépôt."""
    morceaux = urlparse(adresse)
    if morceaux.scheme != "https" or (morceaux.hostname or "") not in HOTES_AUTORISES:
        return False
    if initiale:
        return morceaux.hostname == "github.com" and morceaux.path.startswith(
            CHEMIN_TELECHARGEMENT
        )
    return True


def empreinte_dans(texte: str, nom: str) -> str | None:
    """L'empreinte d'un fichier dans un SHA256SUMS.txt (format de sha256sum)."""
    for ligne in texte.splitlines():
        morceaux = ligne.strip().split()
        if len(morceaux) == 2 and morceaux[1].lstrip("*") == nom:
            empreinte = morceaux[0].lower()
            if re.fullmatch(r"[0-9a-f]{64}", empreinte):
                return empreinte
    return None


def _obtenir(adresse: str, flux: bool) -> requests.Response:
    if not adresse_autorisee(adresse):
        raise ErreurMiseAJour(f"adresse de téléchargement refusée : {adresse}")
    reponse = requests.get(
        adresse, headers={"User-Agent": "psn-amis"}, timeout=DELAI, stream=flux
    )
    # Après les redirections, le fichier doit toujours venir de GitHub.
    if not adresse_autorisee(reponse.url, initiale=False):
        reponse.close()
        raise ErreurMiseAJour("le téléchargement a été redirigé hors de GitHub")
    reponse.raise_for_status()
    return reponse


def telecharger(
    publication: Publication,
    dossier: Path,
    progression: Callable[[int, int], None] = lambda faits, total: None,
    annule: Callable[[], bool] = lambda: False,
) -> Path:
    """Télécharge l'installateur et vérifie son intégrité ; renvoie son chemin.

    Lève ErreurMiseAJour (message pour l'utilisateur) en cas de problème ; un fichier
    incomplet ou abîmé n'est jamais gardé.
    """
    fichier = publication.installateur
    if fichier is None:
        raise ErreurMiseAJour(
            "cette version n'a pas d'installateur : téléchargez-la depuis GitHub."
        )
    if not 0 < fichier.taille <= TAILLE_MAX:
        raise ErreurMiseAJour("taille de l'installateur inattendue")
    attendues: set[str] = set()
    if fichier.empreinte:
        attendues.add(fichier.empreinte)
    try:
        if publication.empreintes is not None:
            texte = _obtenir(publication.empreintes.adresse, flux=False).text
            depuis_la_liste = empreinte_dans(texte, fichier.nom)
            if depuis_la_liste:
                attendues.add(depuis_la_liste)
        if not attendues:
            raise ErreurMiseAJour(
                "aucune empreinte SHA-256 publiée : impossible de vérifier le fichier."
            )
        if len(attendues) > 1:
            raise ErreurMiseAJour("les empreintes publiées ne concordent pas")
        dossier.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(dossier).free < fichier.taille * 2:
            raise ErreurMiseAJour("espace disque insuffisant")
        partiel = dossier / (fichier.nom + ".partiel")
        cible = dossier / fichier.nom
        calcul = hashlib.sha256()
        faits = 0
        try:
            with (
                _obtenir(fichier.adresse, flux=True) as reponse,
                partiel.open("wb") as sortie,
            ):
                for morceau in reponse.iter_content(chunk_size=256 * 1024):
                    if annule():
                        raise ErreurMiseAJour("téléchargement annulé")
                    faits += len(morceau)
                    if faits > fichier.taille:
                        raise ErreurMiseAJour("fichier plus gros qu'annoncé")
                    calcul.update(morceau)
                    sortie.write(morceau)
                    progression(faits, fichier.taille)
            if faits != fichier.taille:
                raise ErreurMiseAJour("téléchargement incomplet")
            if calcul.hexdigest() not in attendues:
                raise ErreurMiseAJour(
                    "empreinte SHA-256 différente : fichier abîmé ou modifié"
                )
            partiel.replace(cible)
        except BaseException:
            partiel.unlink(missing_ok=True)
            raise
    except requests.RequestException as erreur:
        raise ErreurMiseAJour(
            f"téléchargement impossible ({type(erreur).__name__})"
        ) from erreur
    except OSError as erreur:
        raise ErreurMiseAJour(f"écriture impossible ({erreur.strerror})") from erreur
    return cible


def signature(chemin: Path) -> str:
    """État de la signature Authenticode du fichier (Valid, NotSigned...), selon
    Windows. « Inconnu » hors de Windows ou si la vérification échoue."""
    powershell = shutil.which("powershell") if os.name == "nt" else None
    if powershell is None:
        return "Inconnu"
    # Chemin passé en variable d'environnement : jamais intégré au texte du script.
    script = "(Get-AuthenticodeSignature -LiteralPath $env:PSN_AMIS_FICHIER).Status"
    try:
        resultat = subprocess.run(  # noqa: S603
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={**os.environ, "PSN_AMIS_FICHIER": str(chemin)},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError, subprocess.SubprocessError:
        return "Inconnu"
    return resultat.stdout.strip() or "Inconnu"


SIGNATURES_REFUSEES = ("HashMismatch", "NotTrusted", "Incompatible")


def lancer_installateur(chemin: Path) -> None:
    """Lance l'installateur vérifié, qui fermera PSN Amis, le mettra à jour en gardant
    les données, puis le relancera. PSN Amis doit se fermer juste après."""
    if not MOTIF_INSTALLATEUR.fullmatch(chemin.name) or not chemin.is_file():
        raise ErreurMiseAJour("installateur introuvable")
    etat = signature(chemin)
    if etat in SIGNATURES_REFUSEES:
        raise ErreurMiseAJour(f"signature de l'installateur invalide ({etat})")
    subprocess.Popen(  # noqa: S603 (fichier vérifié, arguments fixes)
        [str(chemin), "/SILENT", "/SP-", "/NOCANCEL", "/RELANCER=1"],
        close_fds=True,
    )
