"""Emplacements des fichiers de PSN Amis.

Les fichiers du programme (dossier d'installation) et les données de l'utilisateur sont
séparés :

- programme : le dossier choisi à l'installation (par défaut
  %LOCALAPPDATA%\\Programs\\PSN Amis), jamais modifié par l'application ;
- données : %LOCALAPPDATA%\\PSN Amis (réglages, journal, amis connus, protections,
  historique des opérations, téléchargements de mises à jour).

Les données restent sur ce PC (pas de dossier « itinérant » %APPDATA%) : le code npsso
est lui aussi rangé pour ce PC seulement, dans le Gestionnaire d'identification, et une
liste d'amis n'a rien à faire sur un serveur de profils itinérants.

La variable d'environnement PSN_AMIS_DONNEES remplace le dossier des données : elle sert
aux tests et au mode démonstration, pour ne jamais toucher aux vraies données.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

NOM_APPLICATION = "PSN Amis"
VARIABLE_DONNEES = "PSN_AMIS_DONNEES"
# Fichier témoin : prouve qu'un dossier a bien été créé par PSN Amis (le programme de
# désinstallation ne supprime rien dans un dossier qui ne le contient pas).
MARQUEUR = "psn-amis.donnees"
TEXTE_MARQUEUR = (
    "Dossier des données de PSN Amis. Ne supprimez pas ce fichier : il permet au "
    "programme de désinstallation de reconnaître ce dossier.\n"
)


def est_compile() -> bool:
    """Vrai pour l'application installée (exécutable produit par PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def dossier_paquet() -> Path:
    """Le dossier du code (ressources comprises), compilé ou non."""
    if est_compile():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "psn_amis"
    return Path(__file__).resolve().parent


def dossier_projet() -> Path | None:
    """La racine du dépôt quand PSN Amis est lancé depuis son code source, sinon None.

    C'est là que les versions 2.x rangeaient leurs fichiers (réglages, journal...).
    """
    if est_compile():
        return None
    racine = Path(__file__).resolve().parents[2]
    return racine if (racine / "pyproject.toml").is_file() else None


def dossier_donnees() -> Path:
    """Le dossier des données de l'utilisateur (non créé ici)."""
    force = os.environ.get(VARIABLE_DONNEES, "").strip()
    if force:
        return Path(force).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA", "").strip()
    if base:
        return Path(base) / NOM_APPLICATION
    # Hors de Windows (développement, intégration continue) : dossier personnel.
    return Path.home() / ".local" / "share" / "psn-amis"


def preparer(dossier: Path) -> Path:
    """Crée le dossier des données et son fichier témoin s'il le faut."""
    dossier.mkdir(parents=True, exist_ok=True)
    marqueur = dossier / MARQUEUR
    if not marqueur.exists():
        marqueur.write_text(TEXTE_MARQUEUR, encoding="utf-8")
    return dossier


def nom_de_compte_sur(identifiant: str) -> str:
    """Un identifiant de compte PSN utilisable comme nom de dossier (chiffres seuls).

    Les identifiants de compte Sony sont des nombres : tout autre caractère est retiré,
    ce qui empêche un nom de dossier piégé (« .. », barres obliques...).
    """
    propre = "".join(c for c in identifiant if c.isdigit())
    if not propre:
        raise ValueError("identifiant de compte PSN invalide")
    return propre
