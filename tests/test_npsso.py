"""Le code npsso : lecture tolérante, format vérifié, jamais affiché, enregistrement."""

from __future__ import annotations

import json

import pytest

import moteur
from tests.conftest import FAUX_CODE

CAS_ACCEPTES = {
    "code seul": FAUX_CODE.encode(),
    "espaces autour": b"  " + FAUX_CODE.encode() + b"\r\n",
    "guillemets": ('"' + FAUX_CODE + '"').encode(),
    "ligne JSON entière": json.dumps({"npsso": FAUX_CODE}).encode(),
    "UTF-8 avec BOM": b"\xef\xbb\xbf" + FAUX_CODE.encode(),
    "UTF-16 (Bloc-notes)": FAUX_CODE.encode("utf-16"),
}
CAS_REFUSES = {
    "trop court": b"abc",
    "vide": b"",
    "63 caractères": FAUX_CODE[:63].encode(),
    "espace au milieu": (FAUX_CODE[:30] + " " + FAUX_CODE[30:63]).encode(),
}


@pytest.mark.parametrize("contenu", CAS_ACCEPTES.values(), ids=CAS_ACCEPTES.keys())
def test_lecture_tolerante(dossier, secret, contenu):
    moteur.FICHIER_NPSSO.write_bytes(contenu)
    assert moteur.lire_npsso() == FAUX_CODE


@pytest.mark.parametrize("contenu", CAS_REFUSES.values(), ids=CAS_REFUSES.keys())
def test_format_refuse_sans_devoiler_le_contenu(dossier, secret, contenu):
    moteur.FICHIER_NPSSO.write_bytes(contenu)
    with pytest.raises(moteur.ProblemeNpsso) as erreur:
        moteur.lire_npsso()
    assert "bon format" in str(erreur.value) or "vide" in str(erreur.value)
    assert FAUX_CODE not in str(erreur.value)


def test_fichier_absent(dossier, secret):
    with pytest.raises(moteur.ProblemeNpsso, match="introuvable"):
        moteur.lire_npsso()


def test_masquage_prefere_le_code_le_plus_long(monkeypatch):
    # Un ancien code mal copié (plus court) ne doit pas laisser dépasser une lettre.
    monkeypatch.setattr(moteur, "_secrets", {FAUX_CODE, FAUX_CODE[:63]})
    assert moteur.masquer(f"a {FAUX_CODE} b") == "a [code masqué] b"


def test_masquage_dans_le_statut_affiche(secret):
    suivi = moteur.Suivi()
    suivi.statut(moteur.Statut.ERREUR, f"erreur avec {FAUX_CODE}")
    assert FAUX_CODE not in suivi.instantane().detail
    assert "[code masqué]" in suivi.instantane().detail


def test_enregistrer_un_code_colle(dossier, secret, monkeypatch):
    monkeypatch.setattr(moteur, "proteger_fichier", lambda chemin: True)
    moteur.enregistrer_npsso(f'  "{FAUX_CODE}"  ')
    assert moteur.FICHIER_NPSSO.read_text(encoding="utf-8").strip() == FAUX_CODE
    assert moteur.lire_npsso() == FAUX_CODE


def test_assistant_enregistre_apres_un_essai_rate(dossier, secret, monkeypatch):
    import getpass

    saisies = iter(["pas un code", FAUX_CODE])
    monkeypatch.setattr(getpass, "getpass", lambda invite: next(saisies))
    monkeypatch.setattr(moteur, "proteger_fichier", lambda chemin: True)
    messages: list[str] = []
    assert moteur.assistant_npsso(dire=messages.append) is True
    assert moteur.lire_npsso() == FAUX_CODE
    assert any("pas un code valide" in m for m in messages)
    assert not any(FAUX_CODE in m for m in messages)


def test_assistant_abandonne_sur_entree_vide(dossier, secret, monkeypatch):
    import getpass

    monkeypatch.setattr(getpass, "getpass", lambda invite: "")
    assert moteur.assistant_npsso(dire=lambda texte: None) is False
    assert not moteur.FICHIER_NPSSO.exists()


def test_assistant_abandonne_sur_ctrl_c(dossier, secret, monkeypatch):
    import getpass

    def interrompre(invite):
        raise KeyboardInterrupt

    monkeypatch.setattr(getpass, "getpass", interrompre)
    assert moteur.assistant_npsso(dire=lambda texte: None) is False
