"""Le programme lancé pour de vrai, dans un autre processus, sur une copie du projet
(jamais sur le vrai dossier : il pourrait contenir un vrai code npsso)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from psn_amis import console as accepter_amis
from psn_amis import moteur

RACINE = Path(__file__).resolve().parents[1]


@pytest.fixture
def copie(tmp_path) -> Path:
    """Un dossier de données neuf (jamais le vrai : il pourrait contenir un vrai code)."""
    # Jamais le vrai coffre de Windows (il peut contenir un vrai code npsso), ni de
    # bulles de notification pendant les tests.
    (tmp_path / "reglages.toml").write_text(
        "coffre_windows = false\nnotifications = false\n", encoding="utf-8"
    )
    return tmp_path


def commande(*options: str) -> list[str]:
    return [sys.executable, "-m", "psn_amis", *options]


def environnement(copie: Path) -> dict[str, str]:
    return dict(
        os.environ,
        PYTHONUNBUFFERED="1",
        PYTHONPATH=str(RACINE / "src"),
        PSN_AMIS_DONNEES=str(copie),
    )


def lancer(copie: Path, *options: str, **kwargs):
    return subprocess.Popen(
        commande("--simple", *options),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        env=environnement(copie),
        **kwargs,
    )


def executer(copie: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        commande(*options),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
        env=environnement(copie),
    )


def test_fin_de_session_une_seule_fois(dossier):
    captures: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captures.append(record.getMessage())

    capture = Capture()
    moteur.journal.addHandler(capture)
    try:
        verrou = moteur.verrouiller_instance()
        fin = accepter_amis.Fin(moteur.Suivi(), moteur.Commandes(), verrou, noter=True)
        fin("test")
        fin("deuxième appel")
    finally:
        moteur.journal.removeHandler(capture)
    assert sum("Arrêt (test)" in t for t in captures) == 1
    assert not any("deuxième" in t for t in captures)
    assert not moteur.FICHIER_VERROU.exists()


def test_texte_simple_sans_code_puis_code_invalide(copie):
    # Sortie redirigée : pas de tableau de bord, affichage texte simple.
    premier = lancer(copie)
    try:
        time.sleep(4)
        second = executer(copie, "--test")
        assert second.returncode == 1
        assert "tourne déjà" in second.stdout
        # Le programme repère tout seul un nouveau fichier npsso.txt.
        (copie / "npsso.txt").write_bytes(b"abc")
        time.sleep(8)
    finally:
        premier.terminate()
        sortie = premier.communicate(timeout=30)[0]
    assert "introuvable" in sortie
    assert "pas le bon format" in sortie
    assert "Traceback" not in sortie
    journal = (copie / "journal.txt").read_text(encoding="utf-8")
    assert "Démarrage de PSN Amis" in journal
    assert "PROBLÈME" in journal
    assert "Ctrl+A" not in journal


def test_mode_test_sans_fichier(copie):
    resultat = executer(copie, "--test")
    assert resultat.returncode == 1
    assert "introuvable" in resultat.stdout


def test_aide_en_ligne_de_commande(copie):
    resultat = executer(copie, "--help")
    assert resultat.returncode == 0
    assert "--configurer" in resultat.stdout
