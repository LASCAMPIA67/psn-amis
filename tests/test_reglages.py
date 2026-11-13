"""reglages.toml, coffre de Windows, notifications et vérification de version."""

from __future__ import annotations

import base64
import os
from dataclasses import asdict

import pytest
import requests

from psn_amis import coffre, mises_a_jour, notifications, reglages

# Les vraies fonctions, gardées avant que les tests ne les remplacent.
VRAI_LIRE, VRAI_ECRIRE, VRAI_EFFACER = coffre.lire, coffre.ecrire, coffre.effacer
VRAI_NOTIFIER = notifications.notifier


# ─── reglages.toml ────────────────────────────────────────────────────────────


def test_fichier_absent_valeurs_par_defaut(tmp_path):
    lus, problemes = reglages.charger(tmp_path / "reglages.toml")
    assert lus == reglages.Reglages()
    assert problemes == []


def test_le_fichier_cree_donne_les_valeurs_par_defaut(tmp_path):
    # Le fichier créé documente chaque réglage avec sa vraie valeur par défaut.
    cible = tmp_path / "reglages.toml"
    assert reglages.creer_si_absent(cible)
    assert not reglages.creer_si_absent(cible)
    lus, problemes = reglages.charger(cible)
    assert problemes == []
    assert lus == reglages.Reglages()
    texte = cible.read_text(encoding="utf-8")
    for nom in asdict(reglages.Reglages()):
        assert f"\n{nom} = " in texte


def test_valeurs_lues(tmp_path):
    fichier = tmp_path / "reglages.toml"
    fichier.write_text(
        'intervalle_verification = 30\ntheme = " Doux "\nson = true\n'
        'liste_noire = ["Spam", "  "]\npause_entre_acceptations = 0.5\n',
        encoding="utf-8",
    )
    lus, problemes = reglages.charger(fichier)
    assert problemes == []
    assert lus.intervalle_verification == 30
    # Ancien nom de thème (2.x) : repris sous son nouveau nom.
    assert lus.theme == "minuit"
    assert lus.son is True
    assert lus.liste_noire == ["Spam"]
    assert lus.pause_entre_acceptations == 0.5


@pytest.mark.parametrize(
    ("ligne", "attendu"),
    [
        ("intervalle_verification = 1", "entre 5 et 3600"),
        ("intervalle_verification = true", "nombre"),
        ('intervalle_verification = "15"', "nombre"),
        ('notifications = "oui"', "true ou false"),
        ('theme = "rose"', "daltonien ou systeme"),
        ("theme = 3", "texte"),
        ("intervalle_verification = 7.5", "entier"),
        ('nettoyage_mode = "toujours"', "manuel, assiste ou automatique"),
        ('nettoyage_heures = "25-3"', "02-07"),
        ('liste_noire = "Spam"', "liste"),
        ("reglage_invente = 1", "inconnu"),
    ],
)
def test_valeur_fautive_signalee(tmp_path, ligne, attendu):
    fichier = tmp_path / "reglages.toml"
    fichier.write_text(ligne + "\n", encoding="utf-8")
    lus, problemes = reglages.charger(fichier)
    assert len(problemes) == 1
    assert attendu in problemes[0]
    # La valeur par défaut est gardée : PSN Amis démarre quand même.
    assert lus == reglages.Reglages()


def test_fichier_mal_ecrit(tmp_path):
    fichier = tmp_path / "reglages.toml"
    fichier.write_text("intervalle_verification = = 3\n", encoding="utf-8")
    lus, problemes = reglages.charger(fichier)
    assert lus == reglages.Reglages()
    assert "mal écrit" in problemes[0]


# ─── Vérification de version ──────────────────────────────────────────────────


def test_comparaison_des_versions():
    assert mises_a_jour.numero("v2.10.1") == (2, 10, 1)
    assert mises_a_jour.plus_recente("2.5.0", "2.10.0")
    assert not mises_a_jour.plus_recente("2.5.0", "v2.5.0")
    assert not mises_a_jour.plus_recente("2.5.0", "2.4.9")


class FausseReponse:
    def __init__(self, donnees, statut: int = 200) -> None:
        self._donnees = donnees
        self._statut = statut

    def raise_for_status(self) -> None:
        if self._statut >= 400:
            raise requests.HTTPError(str(self._statut))

    def json(self):
        return self._donnees


def test_derniere_version(monkeypatch):
    adresses: list[str] = []

    def get(adresse, **options):
        adresses.append(adresse)
        assert options["timeout"]
        return FausseReponse({"tag_name": "v9.9.9"})

    monkeypatch.setattr(requests, "get", get)
    assert mises_a_jour.derniere_version() == "9.9.9"
    # Seule adresse contactée : l'API publique de GitHub, pour ce dépôt.
    assert adresses == [
        "https://api.github.com/repos/LASCAMPIA67/psn-amis/releases/latest"
    ]


@pytest.mark.parametrize(
    "reponse",
    [
        FausseReponse({}, 404),
        FausseReponse({"tag_name": 3}),
        FausseReponse(["pas", "un", "objet"]),
    ],
)
def test_derniere_version_inconnue(monkeypatch, reponse):
    monkeypatch.setattr(requests, "get", lambda adresse, **options: reponse)
    assert mises_a_jour.derniere_version() is None


def test_derniere_version_hors_ligne(monkeypatch):
    def coupure(adresse, **options):
        raise requests.ConnectionError("hors ligne")

    monkeypatch.setattr(requests, "get", coupure)
    assert mises_a_jour.derniere_version() is None


# ─── Notifications ────────────────────────────────────────────────────────────


def test_notification_texte_protege(monkeypatch):
    lancements: list[list[str]] = []
    monkeypatch.setattr(notifications, "_powershell", lambda: "powershell.exe")
    monkeypatch.setattr(
        notifications.subprocess,
        "run",
        lambda commande, **options: lancements.append(commande),
    )

    class FilImmediat:
        def __init__(self, target, **options) -> None:
            self._cible = target

        def start(self) -> None:
            self._cible()

    monkeypatch.setattr(notifications.threading, "Thread", FilImmediat)
    assert VRAI_NOTIFIER("PSN Amis", "Liste pleine <2000> & 'rappel'")
    commande = lancements[0]
    assert commande[0] == "powershell.exe"
    script = base64.b64decode(commande[-1]).decode("utf-16-le")
    # Caractères spéciaux neutralisés : ils ne peuvent pas casser le script.
    assert "Liste pleine &lt;2000&gt; &amp; &apos;rappel&apos;" in script
    assert "{titre}" not in script


def test_notification_impossible_hors_windows(monkeypatch):
    monkeypatch.setattr(notifications, "_powershell", lambda: None)
    assert VRAI_NOTIFIER("titre", "texte") is False


# ─── Vrai coffre de Windows ───────────────────────────────────────────────────


@pytest.mark.skipif(os.name != "nt", reason="coffre de Windows seulement")
def test_vrai_coffre_de_windows():
    # Une entrée à part, jamais celle de PSN Amis : le vrai code n'est pas touché.
    cible = "PSN Amis/test-automatique"
    assert cible != coffre.CIBLE
    if os.environ.get("GITHUB_ACTIONS") and not VRAI_ECRIRE("essai", cible):
        pytest.skip("coffre de Windows indisponible sur cette machine de GitHub")
    try:
        assert VRAI_ECRIRE("code-de-test-sans-valeur", cible)
        assert VRAI_LIRE(cible) == "code-de-test-sans-valeur"
        assert VRAI_ECRIRE("deuxième-code", cible)
        assert VRAI_LIRE(cible) == "deuxième-code"
    finally:
        assert VRAI_EFFACER(cible)
    assert VRAI_LIRE(cible) is None
    # Effacer une entrée absente n'est pas une erreur.
    assert VRAI_EFFACER(cible)
