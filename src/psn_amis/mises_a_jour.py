"""Vérification d'une nouvelle version de PSN Amis sur GitHub.

C'est la seule requête qui ne va pas chez Sony. Elle n'est faite que si le réglage
« verifier_mises_a_jour » est activé, une fois au démarrage, et n'envoie rien d'autre
que la demande elle-même.
"""

from __future__ import annotations

import re

import requests

DEPOT = "LASCAMPIA67/psn-amis"
ADRESSE = f"https://api.github.com/repos/{DEPOT}/releases/latest"
PAGE = f"https://github.com/{DEPOT}/releases/latest"


def numero(version: str) -> tuple[int, ...]:
    """« v2.5.0 » → (2, 5, 0), pour comparer deux versions."""
    morceaux = re.findall(r"\d+", version)
    return tuple(int(m) for m in morceaux[:3]) or (0,)


def derniere_version() -> str | None:
    """Le numéro de la dernière version publiée (sans « v »), ou None si inconnu."""
    try:
        reponse = requests.get(
            ADRESSE,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "psn-amis"},
            timeout=10,
        )
        reponse.raise_for_status()
        etiquette = reponse.json().get("tag_name", "")
    except requests.RequestException, ValueError, AttributeError:
        return None
    return etiquette.removeprefix("v") if isinstance(etiquette, str) else None


def plus_recente(actuelle: str, derniere: str) -> bool:
    return numero(derniere) > numero(actuelle)
