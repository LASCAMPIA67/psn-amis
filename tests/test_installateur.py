"""Le script de l'installateur (installer/psn-amis.iss) : règles qui ne doivent pas changer.

La fenêtre de désinstallation ne peut pas être cliquée par un test automatique : ces
tests lisent le code Pascal du script pour garder ses règles, et
outils/tester_installation.py vérifie les trois niveaux en vrai (mode silencieux).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "installer" / "psn-amis.iss"


@pytest.fixture(scope="module")
def code() -> str:
    return SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")


def procedure(code: str, nom: str) -> str:
    """Le corps d'une procédure ou fonction Pascal du script."""
    trouve = re.search(
        rf"^(?:procedure|function) {nom}\b.*?^end;$", code, re.MULTILINE | re.DOTALL
    )
    assert trouve, f"{nom} introuvable dans {SCRIPT.name}"
    return trouve.group(0)


def test_les_trois_niveaux_mettent_a_jour_la_case_du_code(code):
    # Anomalie constatée dans Windows Sandbox : au niveau 3, la case restait décochée.
    choisir = procedure(code, "ChoisirNiveau")
    for bouton in ("Standard", "AvecDonnees", "Complete"):
        assert f"{bouton}.OnClick := @SynchroniserCaseCode;" in choisir
    assert "Code.OnClick := @CaseCodeCliquee;" in choisir
    # État de départ cohérent (niveau 1 choisi au départ).
    assert choisir.index("Standard.Checked := True;") < choisir.index(
        "SynchroniserCaseCode(nil);"
    )


def test_niveau_3_coche_et_grise_la_case(code):
    synchro = procedure(code, "SynchroniserCaseCode")
    complet, autres = synchro.split("else", 1)
    assert "if ChoixComplet.Checked then" in complet
    assert "CaseCode.Enabled := False;" in complet
    assert "CaseCode.Checked := True;" in complet
    # Niveaux 1 et 2 : la case redevient libre, avec le choix de l'utilisateur.
    assert "CaseCode.Enabled := True;" in autres
    assert "CaseCode.Checked := CodeChoisi;" in autres


def test_seul_un_clic_de_l_utilisateur_est_retenu(code):
    clic = procedure(code, "CaseCodeCliquee")
    assert "if CaseCode.Enabled then" in clic
    assert "CodeChoisi := CaseCode.Checked;" in clic


def test_regle_de_suppression_du_code_inchangee(code):
    # Fenêtre : niveau 3, ou case cochée. Mode silencieux : /NIVEAU=3 ou /IDENTIFIANT=1.
    assert "EffacerCode := (Niveau = 3) or Code.Checked;" in procedure(
        code, "ChoisirNiveau"
    )
    initialisation = procedure(code, "InitializeUninstall")
    assert (
        "EffacerCode := (Niveau = 3) or "
        "(ExpandConstant('{param:IDENTIFIANT|0}') = '1');" in initialisation
    )


def test_garde_fous_de_la_desinstallation(code):
    donnees = procedure(code, "EffacerDonnees")
    # Rien n'est effacé sans le fichier témoin ; aucun joker de suppression.
    assert "if not FileExists(Dossier + '\\' + MARQUEUR) then" in donnees
    assert "*" not in donnees.replace("(*", "")
    cible = procedure(code, "CibleCode")
    # Mode test : jamais le vrai code, même si /CIBLE= manque.
    assert "Result := '';" in cible
    assert "Pos('PSN Amis/test', Test) = 1" in cible
