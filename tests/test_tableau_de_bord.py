"""Le tableau de bord : dessin à toutes les tailles, messages entiers, touches."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path

import pytest
from rich.console import Console

import moteur
import tableau_de_bord as tb
from tests.conftest import FAUX_CODE

MESSAGE_LONG = (
    "Demande de GaBi_Snoop__El refusée par Sony (Friend relation mismatch "
    "[code 2282512]). Nouvel essai dans 30 min. Message volontairement très long "
    "pour vérifier qu'il est bien affiché en entier sur plusieurs lignes."
)


@pytest.fixture(scope="module")
def sortie_nulle():
    with Path(os.devnull).open("w", encoding="utf-8") as nul:
        yield nul


def console_test(largeur: int, hauteur: int, sortie) -> Console:
    return Console(
        record=True,
        width=largeur,
        height=hauteur,
        force_terminal=True,
        legacy_windows=False,
        color_system="truecolor",
        theme=tb.THEME,
        file=sortie,
    )


def rendre(instant, largeur, hauteur, sortie, interface=None) -> str:
    console = console_test(largeur, hauteur, sortie)
    console.print(
        tb.construire_ecran(instant, interface or tb.EtatInterface(), largeur, hauteur)
    )
    return console.export_text()


@pytest.fixture
def suivi_rempli() -> moteur.Suivi:
    suivi = moteur.Suivi()
    suivi.connecte("compte_test", 10)
    maintenant = datetime.now()
    for rang, pseudo in enumerate(["Pseudo_a", "Pseudo_b", "Pseudo_c"]):
        suivi.ajout(pseudo)
        suivi.evenement(
            maintenant, logging.INFO, moteur.GENRE_AJOUT, f"Demande acceptée : {pseudo}"
        )
        if rang == 1:
            suivi.evenement(maintenant, logging.WARNING, "info", MESSAGE_LONG)
    suivi.evenement(
        maintenant, logging.INFO, moteur.GENRE_RETRAIT, "Ami retiré : Pseudo_b"
    )
    suivi.verification_terminee()
    suivi.statut(moteur.Statut.EN_MARCHE, "En attente de demandes d'amis", 15)
    return suivi


TAILLES = [
    (240, 60),
    (160, 40),
    (120, 32),
    (100, 24),
    (100, 20),
    (80, 40),
    (80, 24),
    (70, 20),
    (59, 20),
    (40, 15),
    (30, 10),
]


@pytest.mark.parametrize(("largeur", "hauteur"), TAILLES)
def test_rien_ne_depasse_a_chaque_taille(suivi_rempli, sortie_nulle, largeur, hauteur):
    texte = rendre(suivi_rempli.instantane(), largeur, hauteur, sortie_nulle)
    lignes = texte.splitlines()
    assert len(lignes) <= hauteur
    assert all(len(ligne) <= largeur for ligne in lignes)
    assert "Activité" in texte
    if tb.Disposition.pour(largeur, hauteur).avec_ajouts:
        assert "Derniers ajouts" in texte


def test_dispositions():
    assert tb.Disposition.pour(120, 32).colonnes == 4
    assert tb.Disposition.pour(120, 32).gros_chiffres
    assert tb.Disposition.pour(80, 24).colonnes == 2
    assert not tb.Disposition.pour(80, 24).gros_chiffres
    assert not tb.Disposition.pour(80, 24).avec_ajouts
    assert tb.Disposition.pour(50, 20).colonnes == 1


def test_contenu_des_cartes(suivi_rempli, sortie_nulle):
    apercu = rendre(suivi_rempli.instantane(), 120, 32, sortie_nulle)
    for mot in (
        "PSN AMIS",
        moteur.VERSION,
        "Aujourd'hui",
        "Pseudo_c",
        "Quitter",
        "vérifié à",
        "en attente",
        "dernier à",
        "lancé à",
        "% de 2000",
        "compté",
        "▼ Ami retiré : Pseudo_b",
    ):
        assert mot in apercu
    # Pas de symbole émoji : Windows les dessine en couleur et deux fois trop larges.
    assert "✔" not in apercu
    assert "✖" not in apercu


@pytest.mark.parametrize(
    ("largeur", "attendus"),
    [
        (120, ("Vérifier maintenant", "Code npsso", "Quitter")),
        (70, ("Vérifier", "Code")),
        (56, ("vérif.", "quitter")),
    ],
)
def test_touches_lisibles_en_entier(suivi_rempli, sortie_nulle, largeur, attendus):
    bas = rendre(suivi_rempli.instantane(), largeur, 24, sortie_nulle).splitlines()[-1]
    assert all(mot in bas for mot in attendus)
    assert "…" not in bas


@pytest.mark.parametrize("largeur", [120, 60, 34])
def test_message_long_affiche_en_entier(sortie_nulle, largeur):
    suivi = moteur.Suivi()
    suivi.evenement(datetime.now(), logging.WARNING, "info", MESSAGE_LONG)
    console = console_test(largeur, 30, sortie_nulle)
    lignes = console.render_lines(
        tb.FilActivite(suivi.instantane().evenements),
        console.options.update(width=largeur, height=20),
    )
    affiche = " ".join("".join(segment.text for segment in ligne) for ligne in lignes)
    assert " ".join(MESSAGE_LONG.split()) in " ".join(affiche.split())
    assert "…" not in affiche


def test_jamais_de_message_coupe_en_deux(sortie_nulle):
    suivi = moteur.Suivi()
    for numero in range(6):
        suivi.evenement(
            datetime.now(), logging.INFO, "info", f"message {numero} " + MESSAGE_LONG
        )
    console = console_test(60, 30, sortie_nulle)
    lignes = console.render_lines(
        tb.FilActivite(suivi.instantane().evenements),
        console.options.update(width=60, height=9),
    )
    texte = " ".join("".join(segment.text for segment in ligne) for ligne in lignes)
    assert texte.count("message ") == texte.count("plusieurs lignes.")


def test_panneau_code_npsso(sortie_nulle):
    suivi = moteur.Suivi()
    suivi.code_a_changer(
        "PROBLÈME : Sony refuse le code npsso (il est expiré ou incorrect)."
    )
    texte = rendre(suivi.instantane(), 120, 40, sortie_nulle)
    assert "Action nécessaire" in texte
    assert "ssocookie" in texte
    assert "CODE NPSSO" in texte
    assert " C " in texte


def test_pause_et_confirmation(suivi_rempli, sortie_nulle):
    suivi = moteur.Suivi()
    suivi.statut(moteur.Statut.PAUSE, "Les nouvelles demandes attendent.")
    texte = rendre(suivi.instantane(), 120, 32, sortie_nulle)
    assert "EN PAUSE" in texte
    assert "Reprendre" in texte
    interface = tb.EtatInterface(quitter_avant=time.monotonic() + 3)
    texte = rendre(suivi_rempli.instantane(), 120, 32, sortie_nulle, interface)
    assert "Appuyez encore sur Q" in texte


def test_dessin_rapide(suivi_rempli, sortie_nulle):
    depart = time.perf_counter()
    for _ in range(10):
        rendre(suivi_rempli.instantane(), 160, 45, sortie_nulle)
    assert (time.perf_counter() - depart) / 10 < 0.1


# ─── Touches ──────────────────────────────────────────────────────────────────


def test_touches():
    interface, commandes = tb.EtatInterface(), moteur.Commandes()
    assert tb.traiter_touche("q", interface, commandes) is None
    assert interface.confirmation_quitter()
    assert tb.traiter_touche("Q", interface, commandes) == "touche Q"
    tb.traiter_touche("q", interface, commandes)
    tb.traiter_touche("x", interface, commandes)
    assert not interface.confirmation_quitter()
    tb.traiter_touche("p", interface, commandes)
    assert commandes.pause.is_set()
    tb.traiter_touche("P", interface, commandes)
    assert not commandes.pause.is_set()
    assert tb.traiter_touche("\x03", interface, commandes) == "Ctrl+C"
    assert tb.traiter_touche("c", interface, commandes) == "configurer"


def test_touche_j_sans_journal(dossier):
    interface = tb.EtatInterface()
    tb.traiter_touche("j", interface, moteur.Commandes())
    assert interface.message_actuel() == "Le journal est encore vide."


def test_clavier_sans_console():
    with tb.Clavier() as clavier:
        assert clavier.touches(100) == []


# ─── Journal → Activité ───────────────────────────────────────────────────────


def test_vers_tableau_masque_et_filtre(secret):
    suivi = moteur.Suivi()
    gestionnaire = tb.VersTableau(suivi)
    for texte, genre in (
        (f"secret {FAUX_CODE}\ndeuxième ligne", ""),
        ("aide", moteur.GENRE_AIDE),
    ):
        enregistrement = logging.LogRecord("t", logging.INFO, "", 0, texte, None, None)
        if genre:
            enregistrement.genre = genre
        gestionnaire.emit(enregistrement)
    evenements = suivi.instantane().evenements
    assert len(evenements) == 1
    assert evenements[0].texte == "secret [code masqué]"
