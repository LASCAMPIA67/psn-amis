"""Premier lancement sur un Windows vierge : aucun dossier de données n'existe encore.

Reproduit le plantage constaté dans Windows Sandbox (FileNotFoundError sur
psn-amis.lock) et vérifie que chaque écriture crée elle-même son dossier.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from psn_amis import moteur
from tests.conftest import FAUX_CODE

RACINE = Path(__file__).resolve().parents[1]


@pytest.fixture
def dossier_absent(tmp_path, monkeypatch) -> Path:
    """Le dossier des données tel qu'au premier lancement : il n'existe pas."""
    absent = tmp_path / "Données neuves é" / "PSN Amis"
    monkeypatch.setattr(moteur, "DOSSIER", absent)
    monkeypatch.setattr(moteur, "FICHIER_NPSSO", absent / "npsso.txt")
    monkeypatch.setattr(moteur, "FICHIER_JOURNAL", absent / "journal.txt")
    monkeypatch.setattr(moteur, "FICHIER_VERROU", absent / "psn-amis.lock")
    monkeypatch.setattr(moteur, "FICHIER_AMIS", absent / "amis.json")
    monkeypatch.setattr(moteur, "FICHIER_REGLAGES", absent / "reglages.toml")
    monkeypatch.setattr(moteur, "FICHIER_DIAGNOSTIC", absent / "diagnostic.txt")
    assert not absent.exists()
    return absent


def test_verrou_sans_dossier(dossier_absent):
    verrou = moteur.verrouiller_instance()
    assert verrou is not None
    verrou.close()
    assert (dossier_absent / "psn-amis.lock").exists()


def test_journal_sans_dossier(dossier_absent):
    avant = list(moteur.journal.handlers)
    try:
        moteur.configurer_journal(ecran=False, fichier=True, diagnostic=True)
        moteur.journal.info("premier message")
    finally:
        for gestionnaire in moteur.journal.handlers[len(avant) :]:
            gestionnaire.close()
            moteur.journal.removeHandler(gestionnaire)
    assert "premier message" in (dossier_absent / "journal.txt").read_text(
        encoding="utf-8"
    )
    assert (dossier_absent / "psn-amis.donnees").exists()


def test_reglages_sans_dossier(dossier_absent):
    reglages, problemes = moteur.charger_reglages()
    assert problemes == []
    assert (dossier_absent / "reglages.toml").exists()
    assert reglages.intervalle_verification == 15


def test_amis_et_code_sans_dossier(dossier_absent, sans_coffre):
    moteur.memoriser_amis("compte", {"1", "2"})
    assert moteur.amis_memorises("compte") == {"1", "2"}
    assert moteur.enregistrer_npsso(FAUX_CODE) == "npsso.txt"
    assert (dossier_absent / "npsso.txt").exists()


def test_lectures_sans_dossier(dossier_absent):
    # Rien à relire au premier lancement : aucune erreur, aucune création.
    assert moteur.ajouts_recents_dans_journal() == []
    assert moteur.retraits_recents_dans_journal() == []
    assert moteur.amis_memorises("compte") is None
    assert not moteur.code_present()
    assert not dossier_absent.exists()


def environnement(donnees: Path) -> dict[str, str]:
    return dict(
        os.environ,
        PYTHONPATH=str(RACINE / "src"),
        PSN_AMIS_DONNEES=str(donnees),
        QT_QPA_PLATFORM="offscreen",
        PSN_AMIS_SANS_FENETRE="1",
        PYTHONIOENCODING="utf-8",
    )


def test_fenetre_au_tout_premier_lancement(tmp_path):
    """Le scénario du Windows vierge : la fenêtre démarre et crée ses données."""
    donnees = tmp_path / "Utilisateur é" / "AppData" / "Local" / "PSN Amis"
    resultat = subprocess.run(
        [sys.executable, "-m", "psn_amis", "--demo", "--verifier", "4"],
        env=environnement(donnees),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert "Traceback" not in resultat.stderr
    assert (donnees / "psn-amis.donnees").exists()
    assert (donnees / "reglages.toml").exists()
    journal = (donnees / "journal.txt").read_text(encoding="utf-8")
    assert "Connecté au compte PSN MonCompte-PSN" in journal
    # Fermeture propre : verrou libéré.
    assert not (donnees / "psn-amis.lock").exists()


def test_console_au_tout_premier_lancement(tmp_path):
    donnees = tmp_path / "neuf" / "PSN Amis"
    resultat = subprocess.run(
        [sys.executable, "-m", "psn_amis", "--test", "--demo"],
        env=environnement(donnees),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert "Mode test terminé" in resultat.stdout
    assert (donnees / "reglages.toml").exists()


def test_dossier_impossible_a_creer(monkeypatch):
    """Dossier refusé (droits, antivirus) : un message clair, pas de trace Python."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    from psn_amis import app
    from psn_amis.__main__ import analyser

    QApplication.instance() or QApplication([])

    def refus():
        raise PermissionError(13, "Accès refusé")

    messages: list[str] = []
    monkeypatch.setattr(moteur, "preparer_dossier", refus)
    monkeypatch.setattr(
        QMessageBox, "critical", lambda parent, titre, texte: messages.append(texte)
    )
    assert app.main(analyser(["--verifier", "1"])) == 1
    assert "ne peut pas créer son dossier" in messages[0]
    assert "Accès refusé" in messages[0]


def test_plantage_signale_sans_secret(tmp_path, monkeypatch, secret):
    from psn_amis import __main__ as principal

    monkeypatch.setenv("PSN_AMIS_SANS_FENETRE", "1")
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    rapport = principal.signaler_plantage(RuntimeError(f"erreur avec {secret}"), "Test")
    assert rapport == tmp_path / "psn-amis-erreur.txt"
    contenu = rapport.read_text(encoding="utf-8")
    assert "RuntimeError" in contenu
    assert secret not in contenu
    assert "[code masqué]" in contenu


def test_premier_lancement_reel_dans_le_processus(dossier_absent, secret, monkeypatch):
    """Comme sur un PC neuf, sans le mode démonstration (faux Sony dans le processus,
    coffre factice : aucun vrai compte n'est utilisé)."""
    from PySide6.QtWidgets import QApplication

    from psn_amis import app, chemins
    from psn_amis.__main__ import analyser
    from psn_amis.simulation import ConnexionSimulee, SonySimule

    QApplication.instance() or QApplication([])
    sony = SonySimule(nombre_amis=5)
    connexion = ConnexionSimulee(sony)
    monkeypatch.setattr(chemins, "dossier_projet", lambda: None)
    monkeypatch.setattr(moteur, "lire_npsso", lambda: secret)
    monkeypatch.setattr(moteur, "ouvrir_connexion", lambda npsso: connexion)
    monkeypatch.setattr(moteur, "demandes_recues", sony.demandes_recues)
    monkeypatch.setattr(moteur, "liste_amis", sony.liste_amis)
    monkeypatch.setattr(moteur, "trouver_joueur", sony.trouver_joueur)
    monkeypatch.setattr(moteur, "client_psn", lambda connexion: sony)
    avant = list(moteur.journal.handlers)
    try:
        code = app.main(analyser(["--verifier", "3"]))
    finally:
        for gestionnaire in moteur.journal.handlers[len(avant) :]:
            gestionnaire.close()
            moteur.journal.removeHandler(gestionnaire)
    assert code == 0
    journal = (dossier_absent / "journal.txt").read_text(encoding="utf-8")
    assert "Démarrage de PSN Amis" in journal
    assert "Connecté au compte PSN MonCompte-PSN" in journal
    assert (dossier_absent / "comptes").is_dir()
    assert not (dossier_absent / "psn-amis.lock").exists()
