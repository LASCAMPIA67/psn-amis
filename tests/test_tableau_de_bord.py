"""Le tableau de bord : dessin à toutes les tailles, messages entiers, touches."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from rich.console import Console

from psn_amis import moteur
from psn_amis import tableau_de_bord as tb
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
    suivi.retrait("Pseudo_b")
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
        # Dans « Derniers ajouts », l'ami retiré est marqué, les autres non.
        "Pseudo_b ▼",
        "retiré",
    ):
        assert mot in apercu
    assert "Pseudo_c ▼" not in apercu
    # Pas de symbole émoji : Windows les dessine en couleur et deux fois trop larges.
    assert "✔" not in apercu
    assert "✖" not in apercu


@pytest.mark.parametrize(
    ("largeur", "attendus"),
    [
        (120, ("Vérifier maintenant", "Code npsso", "Aide", "Son", "Quitter")),
        (90, ("Vérifier", "Code", "Aide", "Son")),
        (76, ("vérif.", "aide", "quitter")),
        (40, (" P ", " H ", " Q ")),
    ],
)
def test_touches_lisibles_en_entier(suivi_rempli, sortie_nulle, largeur, attendus):
    bas = rendre(suivi_rempli.instantane(), largeur, 24, sortie_nulle).splitlines()[-1]
    assert all(mot in bas for mot in attendus)
    assert "…" not in bas


def test_message_du_pied_jamais_coupe(suivi_rempli, sortie_nulle):
    interface = tb.EtatInterface()
    interface.informer("Vérification demandée…")
    bas = rendre(suivi_rempli.instantane(), 100, 24, sortie_nulle, interface)
    assert "Vérification demandée…" in bas.splitlines()[-1]


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


def test_date_devant_les_messages_des_jours_precedents(sortie_nulle):
    suivi = moteur.Suivi()
    hier = datetime.now() - timedelta(days=1)
    suivi.evenement(hier, logging.INFO, "info", "Message d'hier")
    suivi.evenement(datetime.now(), logging.INFO, "info", "Message du jour")
    console = console_test(80, 10, sortie_nulle)
    lignes = console.render_lines(
        tb.FilActivite(suivi.instantane().evenements),
        console.options.update(width=80, height=5),
    )
    texte = "\n".join("".join(segment.text for segment in ligne) for ligne in lignes)
    assert hier.strftime("%d/%m %H:%M") + " • Message d'hier" in texte
    assert "• Message du jour" in texte
    assert "/" not in texte.splitlines()[0]


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
        with clavier.mode_initial():
            pass


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


# ─── Nouveautés de la version 2.5 ─────────────────────────────────────────────


def test_retraits_du_jour_et_dernier_ajout(suivi_rempli, sortie_nulle):
    texte = rendre(suivi_rempli.instantane(), 120, 32, sortie_nulle)
    assert "1 retrait" in texte
    assert "Dernier ajout à l'instant" in texte


def test_rythme_par_heure(sortie_nulle):
    assert tb.rythme_par_heure(3, 3600) == "3,0"
    assert tb.rythme_par_heure(5, 1800) == "10,0"
    assert tb.rythme_par_heure(3, 300) is None
    assert tb.rythme_par_heure(0, 7200) is None
    suivi = moteur.Suivi()
    suivi._debut = datetime.now() - timedelta(hours=2)
    for pseudo in ("a", "b", "c"):
        suivi.ajout(pseudo)
    assert "1,5 par heure" in rendre(suivi.instantane(), 160, 40, sortie_nulle)


def test_histogramme_des_24_heures(sortie_nulle):
    maintenant = datetime.now()
    ajouts = [
        moteur.Ajout(maintenant - timedelta(hours=heures, minutes=1), f"J{heures}")
        for heures in (0, 0, 0, 5, 22, 30)
    ]
    instant = moteur.Suivi(ajouts).instantane()
    dessin, total = tb.histogramme(instant, maintenant)
    # 30 heures : trop ancien, pas compté.
    assert total == 5
    assert len(dessin.plain) == 24
    assert dessin.plain[-1] == "█"
    assert dessin.plain[-6] != "▁"
    texte = rendre(instant, 160, 40, sortie_nulle)
    assert "24 h " in texte
    assert "5 ajouts" in texte


def test_demandes_en_attente_pendant_la_pause(sortie_nulle):
    suivi = moteur.Suivi()
    suivi.statut(moteur.Statut.PAUSE, "Les demandes attendent · P : reprendre")
    il_y_a_5_min = datetime.now() - timedelta(minutes=5, seconds=10)
    suivi.en_attente(
        [
            moteur.Attente("Joueur_en_attente", il_y_a_5_min, "en pause"),
            moteur.Attente("Sans_date", None, "en pause"),
        ]
    )
    texte = rendre(suivi.instantane(), 120, 32, sortie_nulle)
    assert "Demandes en attente · 2" in texte
    assert "Joueur_en_attente" in texte
    assert "il y a 5 min" in texte
    assert "Derniers ajouts" not in texte
    # Hors pause, « Derniers ajouts » revient.
    suivi.statut(moteur.Statut.EN_MARCHE, "En attente de demandes d'amis", 15)
    assert "Derniers ajouts" in rendre(suivi.instantane(), 120, 32, sortie_nulle)


def test_trop_de_demandes_en_attente(sortie_nulle):
    suivi = moteur.Suivi()
    suivi.statut(moteur.Statut.PAUSE, "pause")
    suivi.en_attente([moteur.Attente(f"J{n}", None) for n in range(40)])
    texte = rendre(suivi.instantane(), 120, 32, sortie_nulle)
    assert "autre(s)" in texte
    assert len(texte.splitlines()) <= 32


def test_defilement_de_l_activite(sortie_nulle):
    suivi = moteur.Suivi()
    for numero in range(30):
        suivi.evenement(datetime.now(), logging.INFO, "info", f"message n°{numero}")
    interface, commandes = tb.EtatInterface(), moteur.Commandes()
    instant = suivi.instantane()
    assert interface.decalage(instant.evenements) == 0
    tb.traiter_touche("bas", interface, commandes)
    tb.traiter_touche("page_bas", interface, commandes)
    assert interface.decalage() == 6
    texte = rendre(instant, 120, 32, sortie_nulle, interface)
    assert "6 plus récent(s) au-dessus" in texte
    assert "message n°29" not in texte
    # Un nouveau message ne fait pas bouger ce qu'on est en train de lire.
    suivi.evenement(datetime.now(), logging.INFO, "info", "message tout neuf")
    assert interface.decalage(suivi.instantane().evenements) == 7
    tb.traiter_touche("haut", interface, commandes)
    assert interface.decalage() == 6
    tb.traiter_touche("debut", interface, commandes)
    assert interface.decalage() == 0
    # Jamais au-delà du plus ancien message.
    for _ in range(20):
        tb.traiter_touche("page_bas", interface, commandes)
    assert interface.decalage() == 30


def test_aide_avec_les_7_derniers_jours(dossier, sortie_nulle, suivi_rempli):
    aujourd_hui = datetime.now()
    (dossier / "journal.txt").write_text(
        f"{aujourd_hui:%Y-%m-%d} 00:00:01  Demande acceptée : Un\n"
        f"{aujourd_hui:%Y-%m-%d} 00:00:02  Ami retiré : Un\n",
        encoding="utf-8",
    )
    interface, commandes = tb.EtatInterface(), moteur.Commandes()
    tb.traiter_touche("h", interface, commandes)
    assert interface.aide
    assert len(interface.statistiques) == 7
    assert interface.statistiques[0][1:] == (1, 1)
    for largeur, hauteur in ((160, 50), (80, 40), (40, 20)):
        texte = rendre(
            suivi_rempli.instantane(), largeur, hauteur, sortie_nulle, interface
        )
        lignes = texte.splitlines()
        assert "Aide" in texte
        assert len(lignes) <= hauteur
        assert all(len(ligne) <= largeur for ligne in lignes)
    texte = rendre(suivi_rempli.instantane(), 160, 50, sortie_nulle, interface)
    for mot in ("Touches", "Symboles", "7 derniers jours", "aujourd'hui", "reglages"):
        assert mot in texte
    tb.traiter_touche("echap", interface, commandes)
    assert not interface.aide
    tb.traiter_touche("H", interface, commandes)
    tb.traiter_touche("h", interface, commandes)
    assert not interface.aide


def test_pause_minutee(sortie_nulle):
    interface, commandes = tb.EtatInterface(), moteur.Commandes()
    tb.traiter_touche("2", interface, commandes)
    assert commandes.pause.is_set()
    assert interface.reprise_a is not None
    assert 590 < interface.reprise_a - time.monotonic() <= 600
    suivi = moteur.Suivi()
    suivi.statut(moteur.Statut.PAUSE, "pause")
    texte = rendre(suivi.instantane(), 120, 32, sortie_nulle, interface)
    assert "Reprise dans 9 min" in texte or "Reprise dans 10 min" in texte
    # Pas encore l'heure : rien ne change.
    tb.reprendre_si_l_heure_est_venue(interface, commandes)
    assert commandes.pause.is_set()
    interface.reprise_a = time.monotonic() - 1
    tb.reprendre_si_l_heure_est_venue(interface, commandes)
    assert not commandes.pause.is_set()
    assert interface.reprise_a is None
    # La touche P annule la reprise prévue.
    tb.traiter_touche("1", interface, commandes)
    tb.traiter_touche("p", interface, commandes)
    assert interface.reprise_a is None
    assert not commandes.pause.is_set()


def test_touche_s_et_bip(isolement, sortie_nulle, suivi_rempli):
    interface = tb.EtatInterface()
    tb.traiter_touche("s", interface, moteur.Commandes())
    assert interface.son
    assert isolement.bips == 1
    assert "activé" in (interface.message_actuel() or "")
    texte = rendre(suivi_rempli.instantane(), 120, 32, sortie_nulle, interface)
    assert "♪" in texte
    tb.traiter_touche("S", interface, moteur.Commandes())
    assert not interface.son
    assert isolement.bips == 1


@pytest.mark.parametrize("nom", list(tb.THEMES))
def test_themes_complets(nom, suivi_rempli, sortie_nulle):
    # Chaque thème définit exactement les mêmes couleurs que le thème sombre.
    assert set(tb.THEMES[nom].styles) == set(tb.THEME.styles)
    console = Console(
        width=120,
        height=32,
        force_terminal=True,
        theme=tb.THEMES[nom],
        file=sortie_nulle,
    )
    ecran = tb.construire_ecran(suivi_rempli.instantane(), tb.EtatInterface(), 120, 32)
    console.print(ecran)
