"""Reprise des données d'une ancienne version (2.x), rangées à côté du code.

La migration copie, elle ne déplace rien : les anciens fichiers restent en place et
servent de sauvegarde. Un fichier déjà présent dans le nouveau dossier n'est jamais
remplacé. Le résultat est noté dans migration.json, ce qui évite de recommencer.

Le code npsso n'est jamais lu ici : un ancien npsso.txt est seulement copié, puis le
moteur le range dans le coffre de Windows au premier démarrage (et supprime la copie).
L'ancien fichier, lui, reste en place : l'application invite à le supprimer.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# Fichiers repris, dans cet ordre. diagnostic.txt n'a d'intérêt que pour un signalement
# en cours, mais il est repris aussi pour ne rien perdre.
FICHIERS = (
    "reglages.toml",
    "amis.json",
    "journal.txt",
    "journal.txt.1",
    "journal.txt.2",
    "journal.txt.3",
    "diagnostic.txt",
    "npsso.txt",
)
FICHIER_RAPPORT = "migration.json"


@dataclass
class Rapport:
    source: str
    copies: list[str] = field(default_factory=list)
    # Déjà présents dans le nouveau dossier : laissés tels quels.
    gardes: list[str] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)
    # Un ancien npsso.txt existe encore à l'ancien emplacement.
    ancien_npsso: bool = False
    date: str = ""

    @property
    def utile(self) -> bool:
        return bool(self.copies or self.gardes or self.erreurs)


def anciennes_donnees(source: Path) -> list[str]:
    """Les fichiers d'une ancienne version présents dans un dossier."""
    return [nom for nom in FICHIERS if (source / nom).is_file()]


def deja_faite(destination: Path) -> bool:
    return (destination / FICHIER_RAPPORT).is_file()


def migrer(source: Path, destination: Path) -> Rapport:
    """Copie les anciennes données de `source` vers `destination` (sans rien écraser)."""
    rapport = Rapport(source=str(source))
    if source.resolve() == destination.resolve():
        return rapport
    destination.mkdir(parents=True, exist_ok=True)
    for nom in anciennes_donnees(source):
        cible = destination / nom
        if cible.exists():
            rapport.gardes.append(nom)
            continue
        try:
            # Copie dans un fichier temporaire, puis renommage : jamais de fichier à
            # moitié copié sous le vrai nom.
            temporaire = cible.with_name(cible.name + ".copie")
            shutil.copy2(source / nom, temporaire)
            temporaire.replace(cible)
        except OSError as erreur:
            rapport.erreurs.append(f"{nom} : {erreur.strerror or erreur}")
            continue
        rapport.copies.append(nom)
    rapport.ancien_npsso = (source / "npsso.txt").is_file()
    rapport.date = datetime.now().isoformat(timespec="seconds")
    if not rapport.erreurs:
        (destination / FICHIER_RAPPORT).write_text(
            json.dumps(asdict(rapport), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return rapport


def migrer_si_besoin(source: Path | None, destination: Path) -> Rapport | None:
    """Migration automatique (lancement depuis le code source) : une seule fois."""
    if source is None or deja_faite(destination) or not anciennes_donnees(source):
        return None
    return migrer(source, destination)
