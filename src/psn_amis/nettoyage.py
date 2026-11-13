"""Nettoyage de la liste d'amis : quand et combien, selon les réglages.

Désactivé par défaut (mode « manuel »). En mode « assisté », PSN Amis prépare une
sélection et attend la confirmation de l'utilisateur ; en mode « automatique », il
supprime lui-même, dans des limites prudentes :

- seuil de déclenchement et capacité cible (cible < seuil) ;
- nombre maximum de suppressions par nettoyage et par jour ;
- délai minimum entre deux nettoyages ;
- plage horaire autorisée ;
- arrêt si les nettoyages s'enchaînent trop souvent (cycle suppression/acceptation) :
  le mode repasse en « manuel » et l'utilisateur est prévenu.

Ce module décide seulement ; la suppression elle-même passe par amis.executer().
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from psn_amis.reglages import Reglages, ecrire_atomique, plage_horaire

# Au-delà de ce nombre de nettoyages en 24 h, on soupçonne un cycle sans fin.
NETTOYAGES_MAX_24H = 6


@dataclass
class Memoire:
    """Ce qu'il faut retenir d'un lancement à l'autre (nettoyage.json)."""

    jour: str = ""
    supprimes_jour: int = 0
    dernier: datetime | None = None
    declenchements: list[datetime] = field(default_factory=list)

    @classmethod
    def lire(cls, chemin: Path) -> Memoire:
        try:
            brut = json.loads(chemin.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return cls()
        if not isinstance(brut, dict):
            return cls()

        def date(texte: object) -> datetime | None:
            try:
                return datetime.fromisoformat(str(texte))
            except ValueError:
                return None

        return cls(
            jour=str(brut.get("jour", "")),
            supprimes_jour=int(brut.get("supprimes_jour", 0) or 0),
            dernier=date(brut.get("dernier")) if brut.get("dernier") else None,
            declenchements=[
                d for d in map(date, brut.get("declenchements", [])) if d is not None
            ],
        )

    def ecrire(self, chemin: Path) -> None:
        ecrire_atomique(
            chemin,
            json.dumps(
                {
                    "jour": self.jour,
                    "supprimes_jour": self.supprimes_jour,
                    "dernier": self.dernier.isoformat() if self.dernier else None,
                    "declenchements": [d.isoformat() for d in self.declenchements],
                }
            ),
        )

    def nouveau_jour_si_besoin(self, maintenant: datetime) -> None:
        jour = maintenant.date().isoformat()
        if self.jour != jour:
            self.jour = jour
            self.supprimes_jour = 0

    def noter(self, maintenant: datetime, supprimes: int) -> None:
        self.nouveau_jour_si_besoin(maintenant)
        self.supprimes_jour += supprimes
        self.dernier = maintenant
        self.declenchements = [
            d for d in self.declenchements if maintenant - d < timedelta(hours=24)
        ] + [maintenant]


@dataclass(frozen=True)
class Decision:
    """Nettoyer maintenant `nombre` amis ; ou None avec la raison (pour l'affichage)."""

    nombre: int
    raison: str
    # Le nettoyage doit être coupé (cycle détecté) : repasser en mode manuel.
    couper: bool = False


def dans_la_plage(texte: str, maintenant: datetime) -> bool:
    if not texte.strip():
        return True
    plage = plage_horaire(texte)
    if plage is None:
        return False
    debut, fin = plage
    heure = maintenant.hour
    # Plage qui passe minuit (22-06) ou non (02-07).
    return debut <= heure < fin if debut < fin else heure >= debut or heure < fin


def decider(
    reglages: Reglages, nombre_amis: int, memoire: Memoire, maintenant: datetime
) -> Decision:
    """Faut-il nettoyer, et combien ? Ne modifie rien."""
    if reglages.nettoyage_mode == "manuel":
        return Decision(0, "nettoyage manuel")
    if nombre_amis < reglages.nettoyage_seuil:
        return Decision(0, "seuil non atteint")
    if not dans_la_plage(reglages.nettoyage_heures, maintenant):
        return Decision(0, "en dehors des heures autorisées")
    if memoire.dernier and maintenant - memoire.dernier < timedelta(
        minutes=reglages.nettoyage_intervalle
    ):
        return Decision(0, "délai entre deux nettoyages pas encore écoulé")
    recents = [
        d for d in memoire.declenchements if maintenant - d < timedelta(hours=24)
    ]
    if len(recents) >= NETTOYAGES_MAX_24H:
        return Decision(
            0,
            f"{len(recents)} nettoyages en 24 h : les suppressions et les acceptations "
            "semblent tourner en boucle. Nettoyage repassé en mode manuel ; augmentez "
            "l'écart entre le seuil et la cible, ou mettez les acceptations en pause.",
            couper=True,
        )
    jour = maintenant.date().isoformat()
    deja = memoire.supprimes_jour if memoire.jour == jour else 0
    reste_jour = reglages.nettoyage_max_par_jour - deja
    if reste_jour <= 0:
        return Decision(0, "limite de suppressions du jour atteinte")
    nombre = min(
        nombre_amis - reglages.nettoyage_cible,
        reglages.nettoyage_max_par_cycle,
        reste_jour,
    )
    if nombre <= 0:
        return Decision(0, "rien à supprimer")
    return Decision(
        nombre,
        f"{nombre_amis} amis (seuil {reglages.nettoyage_seuil}, cible "
        f"{reglages.nettoyage_cible})",
    )
