"""Mises à jour : versions, publication GitHub, téléchargement vérifié, échecs.

Aucune requête réelle : requests.get est remplacé par un faux GitHub.
"""

from __future__ import annotations

import hashlib
from collections import namedtuple

import pytest
import requests

from psn_amis import mises_a_jour
from psn_amis.mises_a_jour import ErreurMiseAJour

CONTENU = b"MZ" + b"installateur de test " * 30000
EMPREINTE = hashlib.sha256(CONTENU).hexdigest()
BASE = "https://github.com/LASCAMPIA67/psn-amis/releases/download/v3.1.0/"


def publication_brute(**changements) -> dict:
    brut = {
        "tag_name": "v3.1.0",
        "draft": False,
        "prerelease": False,
        "body": "## Ajouté\n- Une nouveauté",
        "html_url": "https://github.com/LASCAMPIA67/psn-amis/releases/tag/v3.1.0",
        "assets": [
            {
                "name": "PSN-Amis-Setup-3.1.0.exe",
                "browser_download_url": BASE + "PSN-Amis-Setup-3.1.0.exe",
                "size": len(CONTENU),
                "digest": f"sha256:{EMPREINTE}",
            },
            {
                "name": "SHA256SUMS.txt",
                "browser_download_url": BASE + "SHA256SUMS.txt",
                "size": 100,
            },
        ],
    }
    brut.update(changements)
    return brut


# ─── Versions ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("v2.10.1", (2, 10, 1)),
        ("3.0.0", (3, 0, 0)),
        ("3.0.0-rc.1", None),
        ("3.0", None),
        ("latest", None),
    ],
)
def test_version_stable(texte, attendu):
    assert mises_a_jour.version_stable(texte) == attendu


def test_comparaison_semantique_et_non_textuelle():
    assert mises_a_jour.plus_recente("2.9.0", "2.10.0")
    assert not mises_a_jour.plus_recente("3.0.0", "3.0.0")
    assert not mises_a_jour.plus_recente("3.0.0", "2.99.99")
    # Préversion jamais proposée.
    assert not mises_a_jour.plus_recente("3.0.0", "3.1.0-beta")


# ─── Publication ──────────────────────────────────────────────────────────────


def test_lecture_de_la_publication():
    publication = mises_a_jour.lire_publication(publication_brute())
    assert publication.version == "3.1.0"
    assert publication.installateur.empreinte == EMPREINTE
    assert publication.empreintes.nom == "SHA256SUMS.txt"
    assert "nouveauté" in publication.notes


@pytest.mark.parametrize(
    "changements",
    [{"prerelease": True}, {"draft": True}, {"tag_name": "nightly"}],
)
def test_publication_non_stable_ignoree(changements):
    assert mises_a_jour.lire_publication(publication_brute(**changements)) is None


def test_installateur_d_une_autre_version_ignore():
    brut = publication_brute()
    brut["assets"][0]["name"] = "PSN-Amis-Setup-3.0.9.exe"
    assert mises_a_jour.lire_publication(brut).installateur is None


@pytest.mark.parametrize(
    ("adresse", "initiale", "attendu"),
    [
        (BASE + "PSN-Amis-Setup-3.1.0.exe", True, True),
        ("http://github.com/LASCAMPIA67/psn-amis/releases/download/x", True, False),
        ("https://github.com/autre/projet/releases/download/x.exe", True, False),
        ("https://exemple.com/LASCAMPIA67/psn-amis/releases/download/x", True, False),
        ("https://objects.githubusercontent.com/abc", False, True),
        ("https://objects.githubusercontent.com.evil.com/abc", False, False),
    ],
)
def test_adresses_autorisees(adresse, initiale, attendu):
    assert mises_a_jour.adresse_autorisee(adresse, initiale) is attendu


def test_empreinte_dans_le_fichier_des_sommes():
    texte = f"{EMPREINTE}  PSN-Amis-Setup-3.1.0.exe\n{'0' * 64} *autre.zip\n"
    assert mises_a_jour.empreinte_dans(texte, "PSN-Amis-Setup-3.1.0.exe") == EMPREINTE
    assert mises_a_jour.empreinte_dans(texte, "absent.exe") is None


# ─── Téléchargement ───────────────────────────────────────────────────────────

Reponse = namedtuple("Reponse", "url contenu statut")


class FauxGitHub:
    def __init__(self, contenu: bytes = CONTENU, sommes: str | None = None) -> None:
        self.contenu = contenu
        self.sommes = (
            sommes if sommes is not None else f"{EMPREINTE}  PSN-Amis-Setup-3.1.0.exe\n"
        )
        self.redirection = "https://release-assets.githubusercontent.com/fichier"
        self.coupure_apres: int | None = None

    def get(self, adresse, **options):
        assert options["timeout"]
        if adresse.endswith("SHA256SUMS.txt"):
            return _Reponse(self.redirection, self.sommes.encode())
        return _Reponse(self.redirection, self.contenu, self.coupure_apres)


class _Reponse:
    def __init__(self, url: str, contenu: bytes, coupure: int | None = None) -> None:
        self.url = url
        self._contenu = contenu
        self._coupure = coupure

    @property
    def text(self) -> str:
        return self._contenu.decode()

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, chunk_size: int):
        for debut in range(0, len(self._contenu), chunk_size):
            if self._coupure is not None and debut >= self._coupure:
                raise requests.ConnectionError("coupure")
            yield self._contenu[debut : debut + chunk_size]

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *details) -> None:
        pass


@pytest.fixture
def github(monkeypatch) -> FauxGitHub:
    faux = FauxGitHub()
    monkeypatch.setattr(mises_a_jour.requests, "get", faux.get)
    return faux


def publication():
    return mises_a_jour.lire_publication(publication_brute())


def test_telechargement_verifie(github, tmp_path):
    etapes: list[tuple[int, int]] = []
    chemin = mises_a_jour.telecharger(
        publication(), tmp_path, lambda f, t: etapes.append((f, t))
    )
    assert chemin.name == "PSN-Amis-Setup-3.1.0.exe"
    assert chemin.read_bytes() == CONTENU
    assert etapes[-1] == (len(CONTENU), len(CONTENU))
    assert not list(tmp_path.glob("*.partiel"))


def test_fichier_corrompu_refuse(github, tmp_path):
    github.contenu = CONTENU[:-1] + b"X"
    with pytest.raises(ErreurMiseAJour, match="empreinte"):
        mises_a_jour.telecharger(publication(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_empreintes_discordantes(github, tmp_path):
    github.sommes = f"{'a' * 64}  PSN-Amis-Setup-3.1.0.exe\n"
    with pytest.raises(ErreurMiseAJour, match="concordent pas"):
        mises_a_jour.telecharger(publication(), tmp_path)


def test_telechargement_interrompu(github, tmp_path):
    github.coupure_apres = 256 * 1024
    with pytest.raises(ErreurMiseAJour, match="impossible"):
        mises_a_jour.telecharger(publication(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_telechargement_incomplet(github, tmp_path):
    github.contenu = CONTENU[:1000]
    with pytest.raises(ErreurMiseAJour, match="incomplet"):
        mises_a_jour.telecharger(publication(), tmp_path)


def test_redirection_hors_de_github(github, tmp_path):
    github.redirection = "https://pirate.example/fichier.exe"
    with pytest.raises(ErreurMiseAJour, match="hors de GitHub"):
        mises_a_jour.telecharger(publication(), tmp_path)


def test_annulation(github, tmp_path):
    with pytest.raises(ErreurMiseAJour, match="annulé"):
        mises_a_jour.telecharger(publication(), tmp_path, annule=lambda: True)
    assert list(tmp_path.iterdir()) == []


def test_espace_disque_insuffisant(github, tmp_path, monkeypatch):
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(
        mises_a_jour.shutil, "disk_usage", lambda chemin: Usage(10, 10, 0)
    )
    with pytest.raises(ErreurMiseAJour, match="espace disque"):
        mises_a_jour.telecharger(publication(), tmp_path)


def test_sans_empreinte_publiee(github, tmp_path):
    brut = publication_brute()
    del brut["assets"][0]["digest"]
    brut["assets"].pop()
    with pytest.raises(ErreurMiseAJour, match="aucune empreinte"):
        mises_a_jour.telecharger(mises_a_jour.lire_publication(brut), tmp_path)


def test_sans_installateur(tmp_path):
    brut = publication_brute(assets=[])
    with pytest.raises(ErreurMiseAJour, match="pas d'installateur"):
        mises_a_jour.telecharger(mises_a_jour.lire_publication(brut), tmp_path)


def test_github_injoignable(monkeypatch):
    def coupure(*arguments, **options):
        raise requests.ConnectionError("hors ligne")

    monkeypatch.setattr(mises_a_jour.requests, "get", coupure)
    assert mises_a_jour.derniere_publication() is None


# ─── Lancement de l'installateur ──────────────────────────────────────────────


def test_lancement_refuse_un_autre_fichier(tmp_path):
    autre = tmp_path / "virus.exe"
    autre.write_bytes(b"MZ")
    with pytest.raises(ErreurMiseAJour, match="introuvable"):
        mises_a_jour.lancer_installateur(autre)


def test_lancement_refuse_une_signature_invalide(tmp_path, monkeypatch):
    fichier = tmp_path / "PSN-Amis-Setup-3.1.0.exe"
    fichier.write_bytes(b"MZ")
    monkeypatch.setattr(mises_a_jour, "signature", lambda chemin: "HashMismatch")
    lances: list = []
    monkeypatch.setattr(
        mises_a_jour.subprocess, "Popen", lambda *a, **k: lances.append(a)
    )
    with pytest.raises(ErreurMiseAJour, match="signature"):
        mises_a_jour.lancer_installateur(fichier)
    assert lances == []


def test_lancement_avec_relance(tmp_path, monkeypatch):
    fichier = tmp_path / "PSN-Amis-Setup-3.1.0.exe"
    fichier.write_bytes(b"MZ")
    monkeypatch.setattr(mises_a_jour, "signature", lambda chemin: "NotSigned")
    lances: list = []
    monkeypatch.setattr(
        mises_a_jour.subprocess, "Popen", lambda commande, **k: lances.append(commande)
    )
    mises_a_jour.lancer_installateur(fichier)
    assert lances[0][0] == str(fichier)
    assert "/RELANCER=1" in lances[0]
