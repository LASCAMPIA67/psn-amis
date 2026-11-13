"""Les outils du dossier outils/ : icône, export du journal, raccourcis Windows."""

from __future__ import annotations

import csv
import struct
import sys
import zlib
from datetime import datetime
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "outils"))

import exporter_journal  # noqa: E402
import icone  # noqa: E402
import raccourcis  # noqa: E402


def test_icone_valide():
    donnees = icone.ico({16: icone.png(16), 32: icone.png(32)})
    reserve, nature, nombre = struct.unpack("<HHH", donnees[:6])
    assert (reserve, nature, nombre) == (0, 1, 2)
    largeur, _, _, _, _, _, taille, position = struct.unpack("<BBBBHHII", donnees[6:22])
    assert largeur == 16
    assert donnees[position : position + 8] == b"\x89PNG\r\n\x1a\n"
    assert position + taille <= len(donnees)


def images_de_l_icone(donnees: bytes) -> dict[int, bytes]:
    """Taille -> pixels décompressés de chaque image PNG d'un fichier .ico."""
    images: dict[int, bytes] = {}
    for rang in range(struct.unpack("<H", donnees[4:6])[0]):
        debut = 6 + 16 * rang
        cote, *_, taille, position = struct.unpack(
            "<BBBBHHII", donnees[debut : debut + 16]
        )
        image = donnees[position : position + taille]
        longueur = struct.unpack(">I", image[33:37])[0]
        assert image[37:41] == b"IDAT"
        images[cote or 256] = zlib.decompress(image[41 : 41 + longueur])
    return images


def test_icone_du_depot_a_jour():
    # docs/images/icone.ico est bien celle que dessine outils/icone.py (comparée
    # pixel par pixel : la compression peut varier d'une version de zlib à l'autre).
    images = images_de_l_icone(icone.FICHIER.read_bytes())
    assert sorted(images) == list(icone.TAILLES)
    for taille in (16, 32):
        assert images[taille] == icone.pixels(taille)


def test_coins_transparents_et_coche_blanche():
    taille = 32
    pixels = icone.pixels(taille)

    def pixel(x: int, y: int) -> bytes:
        debut = y * (taille * 4 + 1) + 1 + x * 4
        return pixels[debut : debut + 4]

    assert pixel(0, 0)[3] == 0
    assert pixel(16, 2)[3] == 255
    # Sur le trait de la coche : presque blanc.
    assert min(pixel(14, 21)[:3]) > 200


def test_export_du_journal(dossier, tmp_path):
    (dossier / "journal.txt.1").write_text(
        "2026-11-01 10:00:00  Demande acceptée : Ancien\n", encoding="utf-8"
    )
    (dossier / "journal.txt").write_text(
        "2026-11-10 09:00:00  Demande acceptée : Élodie_Gamer\n"
        "2026-11-10 09:00:05  Connecté au compte PSN x (3 amis).\n"
        "2026-11-10 09:30:00  Ami retiré : Élodie_Gamer\n"
        "2026-11-10 09:40:00  Ami retiré pendant l'arrêt : Autre\n",
        encoding="utf-8",
    )
    sortie = tmp_path / "export.csv"
    assert exporter_journal.exporter(sortie, datetime(2026, 11, 5)) == 3
    brut = sortie.read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf")
    with sortie.open(encoding="utf-8-sig", newline="") as fichier:
        lignes = list(csv.reader(fichier, delimiter=";"))
    assert lignes == [
        ["date", "heure", "événement", "pseudo"],
        ["10/11/2026", "09:00:00", "ajout", "Élodie_Gamer"],
        ["10/11/2026", "09:30:00", "retrait", "Élodie_Gamer"],
        ["10/11/2026", "09:40:00", "retrait", "Autre"],
    ]


def test_raccourci_cree_avec_les_bons_chemins(monkeypatch):
    appels: list[dict[str, str]] = []

    def faux_powershell(script: str, **variables: str) -> str:
        appels.append(variables)
        return r"C:\Bureau\PSN Amis.lnk"

    monkeypatch.setattr(raccourcis, "powershell", faux_powershell)
    chemin = raccourcis.creer("Startup", raccourcis.FENETRE_REDUITE)
    assert chemin == Path(r"C:\Bureau\PSN Amis.lnk")
    variables = appels[0]
    assert variables["DOSSIER"] == "Startup"
    assert variables["LANCEUR"].endswith("Lancer PSN Amis.cmd")
    assert variables["ICONE"].endswith("icone.ico,0")
    assert variables["FENETRE"] == "7"


@pytest.mark.parametrize("nom", ["Lancer PSN Amis.cmd", "Raccourcis PSN Amis.cmd"])
def test_lanceurs_en_fins_de_ligne_windows(nom):
    contenu = (RACINE / nom).read_bytes()
    assert b"\r\n" in contenu
    assert b"\n" not in contenu.replace(b"\r\n", b"")
    assert contenu.decode("utf-8")
