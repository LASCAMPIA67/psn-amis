"""Dessine l'icône de PSN Amis (docs/images/icone.ico), sans aucune bibliothèque.

Un carré aux coins arrondis, dégradé bleu, avec une coche blanche : « demande
acceptée ». L'icône contient quatre tailles (16, 32, 48 et 256 pixels), chacune
dessinée directement à sa taille, avec un lissage des bords.

Depuis le dossier du projet :

    uv run outils/icone.py
"""

from __future__ import annotations

import math
import struct
import sys
import zlib
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
FICHIER = RACINE / "docs" / "images" / "icone.ico"
TAILLES = (16, 32, 48, 256)
# Sous-pixels par côté pour lisser les bords.
LISSAGE = 4

HAUT = (0x4D, 0xA6, 0xFF)
BAS = (0x1F, 0x6F, 0xD1)
BLANC = (0xFF, 0xFF, 0xFF)
# La coche, en coordonnées de 0 à 1 : trois points reliés par un trait épais.
COCHE = ((0.27, 0.53), (0.43, 0.69), (0.74, 0.34))
EPAISSEUR = 0.105


def dans_le_carre(x: float, y: float) -> bool:
    """Le point (de 0 à 1) est dans le carré aux coins arrondis."""
    marge, rayon = 0.04, 0.22
    gauche, droite = marge + rayon, 1 - marge - rayon
    cx = min(max(x, gauche), droite)
    cy = min(max(y, gauche), droite)
    return (x - cx) ** 2 + (y - cy) ** 2 <= rayon**2 and marge <= x <= 1 - marge


def distance_segment(x: float, y: float, a: tuple, b: tuple) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy))


def sur_la_coche(x: float, y: float) -> bool:
    return any(
        distance_segment(x, y, COCHE[rang], COCHE[rang + 1]) <= EPAISSEUR / 2
        for rang in range(len(COCHE) - 1)
    )


def pixels(taille: int) -> bytes:
    """Les pixels RVBA d'une taille donnée, ligne par ligne (haut en premier)."""
    lignes = bytearray()
    for py in range(taille):
        lignes.append(0)  # Filtre PNG « aucun » au début de chaque ligne.
        for px in range(taille):
            fond = coche = 0
            for sy in range(LISSAGE):
                for sx in range(LISSAGE):
                    x = (px + (sx + 0.5) / LISSAGE) / taille
                    y = (py + (sy + 0.5) / LISSAGE) / taille
                    if dans_le_carre(x, y):
                        fond += 1
                        coche += sur_la_coche(x, y)
            total = LISSAGE * LISSAGE
            if not fond:
                lignes += bytes(4)
                continue
            part = py / max(taille - 1, 1)
            bleu = [round(h + (b - h) * part) for h, b in zip(HAUT, BAS, strict=True)]
            melange = coche / fond
            couleur = [
                round(c + (blanc - c) * melange)
                for c, blanc in zip(bleu, BLANC, strict=True)
            ]
            lignes += bytes([*couleur, round(255 * fond / total)])
    return bytes(lignes)


def png(taille: int) -> bytes:
    def morceau(nature: bytes, donnees: bytes) -> bytes:
        return (
            struct.pack(">I", len(donnees))
            + nature
            + donnees
            + struct.pack(">I", zlib.crc32(nature + donnees) & 0xFFFFFFFF)
        )

    entete = struct.pack(">IIBBBBB", taille, taille, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + morceau(b"IHDR", entete)
        + morceau(b"IDAT", zlib.compress(pixels(taille), 9))
        + morceau(b"IEND", b"")
    )


def ico(images: dict[int, bytes]) -> bytes:
    """Un fichier .ico qui contient des images PNG (Windows Vista et suivants)."""
    entete = struct.pack("<HHH", 0, 1, len(images))
    position = 6 + 16 * len(images)
    repertoire = b""
    for taille, donnees in images.items():
        cote = 0 if taille >= 256 else taille
        repertoire += struct.pack(
            "<BBBBHHII", cote, cote, 0, 0, 1, 32, len(donnees), position
        )
        position += len(donnees)
    return entete + repertoire + b"".join(images.values())


def main() -> int:
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_bytes(ico({taille: png(taille) for taille in TAILLES}))
    print(f"Icône écrite : {FICHIER.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
