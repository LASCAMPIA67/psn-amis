"""Préparation commune aux tests : dossier temporaire, faux Sony, moteur en marche.

Aucun test ne touche à Internet, ni au vrai dossier du projet : les fichiers du moteur
(npsso.txt, journal.txt, verrou) sont redirigés vers un dossier temporaire, et Sony est
remplacé par un faux serveur en mémoire.
"""

from __future__ import annotations

import os
import tempfile

# Avant tout import de psn_amis : jamais le vrai dossier des données
# (%LOCALAPPDATA%\PSN Amis), même par erreur.
os.environ["PSN_AMIS_DONNEES"] = tempfile.mkdtemp(prefix="psn-amis-tests-")

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
import requests

from psn_amis import coffre, moteur, notifications, reglages, tableau_de_bord

# Un code au bon format, inventé pour les tests.
FAUX_CODE = ("Ab3" * 22)[:64]


def attendre_que(condition: Callable[[], bool], delai: float = 10.0) -> bool:
    """Attend qu'une condition devienne vraie (au plus `delai` secondes)."""
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture(scope="session", autouse=True)
def journal_configure() -> None:
    """Journal réglé une fois pour tous les tests : ni écran, ni fichier."""
    moteur.configurer_journal(ecran=False, fichier=False)


@dataclass
class Alertes:
    """Bulles et bips demandés pendant un test (aucun n'est vraiment affiché)."""

    bulles: list[tuple[str, str]] = field(default_factory=list)
    bips: int = 0


@pytest.fixture(autouse=True)
def isolement(monkeypatch) -> Alertes:
    """Pour tous les tests : réglages par défaut, coffre de Windows remplacé par un
    coffre en mémoire, bulles et bips seulement notés."""
    monkeypatch.setattr(moteur, "REGLAGES", reglages.Reglages())
    faux_coffre: dict[str, str] = {}
    monkeypatch.setattr(coffre, "disponible", lambda: True)
    monkeypatch.setattr(
        coffre, "lire", lambda cible=coffre.CIBLE: faux_coffre.get(cible)
    )

    def ecrire(code: str, cible: str = coffre.CIBLE) -> bool:
        faux_coffre[cible] = code
        return True

    def effacer(cible: str = coffre.CIBLE) -> bool:
        faux_coffre.pop(cible, None)
        return True

    monkeypatch.setattr(coffre, "ecrire", ecrire)
    monkeypatch.setattr(coffre, "effacer", effacer)
    alertes = Alertes()

    def notifier(titre: str, texte: str) -> bool:
        alertes.bulles.append((titre, texte))
        return True

    def bip() -> bool:
        alertes.bips += 1
        return True

    monkeypatch.setattr(notifications, "notifier", notifier)
    monkeypatch.setattr(notifications, "bip", bip)
    return alertes


@pytest.fixture
def sans_coffre(monkeypatch) -> None:
    """Le code npsso est gardé dans npsso.txt, comme sans le coffre de Windows."""
    monkeypatch.setattr(moteur, "REGLAGES", reglages.Reglages(coffre_windows=False))


@pytest.fixture
def dossier(tmp_path, monkeypatch):
    """Fichiers du moteur redirigés vers un dossier temporaire."""
    monkeypatch.setattr(moteur, "DOSSIER", tmp_path)
    monkeypatch.setattr(moteur, "FICHIER_NPSSO", tmp_path / "npsso.txt")
    monkeypatch.setattr(moteur, "FICHIER_JOURNAL", tmp_path / "journal.txt")
    monkeypatch.setattr(moteur, "FICHIER_VERROU", tmp_path / "psn-amis.lock")
    monkeypatch.setattr(moteur, "FICHIER_AMIS", tmp_path / "amis.json")
    monkeypatch.setattr(moteur, "FICHIER_REGLAGES", tmp_path / "reglages.toml")
    monkeypatch.setattr(moteur, "FICHIER_DIAGNOSTIC", tmp_path / "diagnostic.txt")
    return tmp_path


@pytest.fixture
def secret(monkeypatch) -> str:
    """Le faux code est le seul secret connu du masquage pendant le test."""
    monkeypatch.setattr(moteur, "_secrets", {FAUX_CODE})
    return FAUX_CODE


@dataclass
class FauxSony:
    """Sony en mémoire : demandes reçues, liste d'amis, pannes à la demande."""

    demandes: list[str] = field(default_factory=lambda: ["a", "b"])
    partages: list[str] = field(default_factory=list)
    acceptes: list[str] = field(default_factory=list)
    ids: set[str] = field(default_factory=lambda: {f"ami{n}" for n in range(10)})
    total_force: int | None = None
    depuis: dict = field(default_factory=dict)
    refuser: bool = False
    coupure: bool = False

    def demandes_recues(self, connexion) -> moteur.Demandes:
        if self.coupure:
            raise requests.ConnectionError("coupure simulée")
        amis = [d for d in self.demandes if d not in self.acceptes]
        return moteur.Demandes(amis, list(self.partages), dict(self.depuis))

    def liste_amis(self, connexion) -> tuple[set[str], int]:
        ids = set(self.ids)
        return ids, self.total_force or len(ids)


class FauxJoueur:
    def __init__(self, sony: FauxSony, compte: str) -> None:
        self._sony = sony
        self.compte = compte
        self.online_id = f"Pseudo_{compte}"

    def accept_friend_request(self) -> None:
        if self._sony.refuser:
            raise moteur.PSNAWPClientError(
                '{"error": {"message": "limite", "code": 1}}'
            )
        self._sony.acceptes.append(self.compte)
        self._sony.ids.add(self.compte)


class FausseConnexion:
    pseudo = "compte_test"

    def expire_bientot(self) -> bool:
        return False

    def renouveler_acces_si_besoin(self) -> None:
        pass

    def fermer(self) -> None:
        pass


@pytest.fixture
def faux_sony(monkeypatch, dossier, secret) -> FauxSony:
    """Branche le moteur sur le faux Sony, avec des attentes très courtes."""
    sony = FauxSony()
    monkeypatch.setattr(moteur, "lire_npsso", lambda: secret)
    monkeypatch.setattr(moteur, "ouvrir_connexion", lambda npsso: FausseConnexion())
    monkeypatch.setattr(moteur, "demandes_recues", sony.demandes_recues)
    monkeypatch.setattr(
        moteur, "trouver_joueur", lambda connexion, compte: FauxJoueur(sony, compte)
    )
    monkeypatch.setattr(moteur, "liste_amis", sony.liste_amis)
    monkeypatch.setattr(moteur, "INTERVALLE_VERIFICATION", 1)
    monkeypatch.setattr(moteur, "PAUSE_ENTRE_ACCEPTATIONS", 0.05)
    return sony


@pytest.fixture
def moteur_en_marche(faux_sony):
    """Le moteur tourne dans un fil, relié à un Suivi et au panneau d'activité."""
    suivi = moteur.Suivi()
    commandes = moteur.Commandes()
    gestionnaire = tableau_de_bord.VersTableau(suivi)
    moteur.journal.addHandler(gestionnaire)
    fil = threading.Thread(
        target=moteur.tourner_en_continu,
        args=(moteur.Etat(), suivi, commandes),
        daemon=True,
    )
    fil.start()
    yield suivi, commandes, fil
    commandes.arreter()
    fil.join(5)
    moteur.journal.removeHandler(gestionnaire)


@pytest.fixture(autouse=True)
def dialogues(monkeypatch) -> list[tuple[str, str]]:
    """Aucun dialogue de PSN Amis ne bloque un test : il est noté, puis refusé
    (« Annuler »), comme si l'utilisateur ne confirmait pas."""
    from psn_amis.ui import composants

    vus: list[tuple[str, str]] = []

    def exec_(dialogue) -> int:
        vus.append((dialogue.titre.text(), dialogue.texte.text()))
        return 0

    monkeypatch.setattr(composants.Dialogue, "exec", exec_)
    return vus
