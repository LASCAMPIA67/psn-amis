"""Les réglages de PSN Amis, lus dans reglages.toml.

Au premier lancement, reglages.toml est créé à partir de reglages.exemple.toml, qui
explique chaque réglage. Un réglage absent prend sa valeur par défaut ; un réglage mal
écrit est signalé clairement et remplacé par sa valeur par défaut, sans arrêter PSN Amis.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

THEMES = ("sombre", "doux", "daltonien")

# Bornes des réglages numériques : (minimum, maximum).
BORNES = {
    "intervalle_verification": (5, 3600),
    "pause_entre_acceptations": (0, 60),
    "limite_amis": (1, 10000),
    "pause_apres_ajouts": (0, 10000),
}


@dataclass
class Reglages:
    """Tous les réglages, avec leurs valeurs par défaut."""

    # Secondes entre deux vérifications (demandes reçues, puis liste d'amis).
    intervalle_verification: int = 15
    # Secondes de pause entre deux acceptations.
    pause_entre_acceptations: float = 2
    # Nombre maximum d'amis sur un compte PSN.
    limite_amis: int = 2000
    # Couleurs du tableau de bord : sombre, doux ou daltonien.
    theme: str = "sombre"
    # Bulles de notification Windows pour les événements importants.
    notifications: bool = True
    # Petit bip à chaque ajout (touche S pour changer en cours de route).
    son: bool = False
    # Pause automatique après ce nombre d'ajouts depuis la dernière reprise (0 : jamais).
    pause_apres_ajouts: int = 0
    # Pseudos (ou identifiants de compte) à ne jamais accepter.
    liste_noire: list[str] = field(default_factory=list)
    # Si elle n'est pas vide : seuls ces pseudos (ou identifiants) sont acceptés.
    liste_blanche: list[str] = field(default_factory=list)
    # Vérifier au démarrage, sur GitHub, si une nouvelle version existe.
    verifier_mises_a_jour: bool = False
    # Garder le code npsso dans le Gestionnaire d'identification de Windows
    # plutôt que dans npsso.txt.
    coffre_windows: bool = True


def creer_si_absent(chemin: Path, exemple: Path) -> bool:
    """Crée reglages.toml à partir de l'exemple s'il n'existe pas ; True si créé."""
    if chemin.exists() or not exemple.exists():
        return False
    shutil.copyfile(exemple, chemin)
    return True


def charger(chemin: Path) -> tuple[Reglages, list[str]]:
    """Lit le fichier et renvoie (réglages, liste des problèmes rencontrés).

    Un problème ne bloque rien : le réglage fautif garde sa valeur par défaut.
    """
    reglages = Reglages()
    problemes: list[str] = []
    try:
        brut = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return reglages, problemes
    except OSError as erreur:
        return reglages, [f"{chemin.name} : impossible de lire le fichier ({erreur})."]
    try:
        donnees = tomllib.loads(brut)
    except tomllib.TOMLDecodeError as erreur:
        return reglages, [f"{chemin.name} : le fichier est mal écrit ({erreur})."]

    connus = {champ.name: champ for champ in fields(Reglages)}
    for cle, valeur in donnees.items():
        if cle not in connus:
            problemes.append(f"{chemin.name} : réglage inconnu « {cle} », ignoré.")
            continue
        probleme = _verifier(cle, valeur, getattr(reglages, cle))
        if probleme:
            problemes.append(f"{chemin.name} : {probleme}")
            continue
        setattr(reglages, cle, _normaliser(cle, valeur))
    return reglages, problemes


def _verifier(cle: str, valeur: object, defaut: object) -> str | None:
    """Le message d'erreur pour une valeur inacceptable, ou None si elle convient."""
    if isinstance(defaut, bool):
        if not isinstance(valeur, bool):
            return f"« {cle} » doit valoir true ou false (valeur par défaut gardée)."
        return None
    if isinstance(defaut, int | float):
        if isinstance(valeur, bool) or not isinstance(valeur, int | float):
            return f"« {cle} » doit être un nombre (valeur par défaut gardée)."
        minimum, maximum = BORNES[cle]
        if not minimum <= valeur <= maximum:
            return (
                f"« {cle} » doit être entre {minimum} et {maximum}, pas {valeur} "
                "(valeur par défaut gardée)."
            )
        return None
    if isinstance(defaut, str):
        if not isinstance(valeur, str):
            return f"« {cle} » doit être un texte entre guillemets."
        if cle == "theme" and valeur.strip().lower() not in THEMES:
            return (
                f"« theme » doit être {', '.join(THEMES[:-1])} ou {THEMES[-1]}, "
                f"pas « {valeur} » (sombre gardé)."
            )
        return None
    if isinstance(defaut, list):
        if not isinstance(valeur, list) or not all(isinstance(v, str) for v in valeur):
            return f"« {cle} » doit être une liste de pseudos entre guillemets."
        return None
    return None


def _normaliser(cle: str, valeur: object) -> object:
    if cle == "theme" and isinstance(valeur, str):
        return valeur.strip().lower()
    if cle in ("intervalle_verification", "limite_amis", "pause_apres_ajouts"):
        return int(valeur)  # type: ignore[call-overload]
    if isinstance(valeur, list):
        return [v.strip() for v in valeur if v.strip()]
    return valeur
