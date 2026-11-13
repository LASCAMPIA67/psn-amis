"""Moteur, nouveautés de la version 2.5 : listes noire et blanche, pause automatique,
demandes en attente pendant la pause, mémoire des amis entre deux lancements,
notifications, relecture du journal sur 24 heures, statistiques des 7 derniers jours."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta

import pytest

from psn_amis import moteur, reglages, tableau_de_bord
from tests.conftest import attendre_que


def textes(suivi: moteur.Suivi) -> list[str]:
    return [evenement.texte for evenement in suivi.instantane().evenements]


@pytest.fixture
def demarrer(faux_sony):
    """Démarre le moteur avec des réglages choisis par le test."""
    fils: list[tuple[moteur.Commandes, threading.Thread, object]] = []

    def lancer(**options) -> tuple[moteur.Suivi, moteur.Commandes]:
        moteur.appliquer_reglages(
            reglages.Reglages(intervalle_verification=1, **options)
        )
        moteur.PAUSE_ENTRE_ACCEPTATIONS = 0.05
        suivi, commandes = moteur.Suivi(), moteur.Commandes()
        gestionnaire = tableau_de_bord.VersTableau(suivi)
        moteur.journal.addHandler(gestionnaire)
        fil = threading.Thread(
            target=moteur.tourner_en_continu,
            args=(moteur.Etat(), suivi, commandes),
            daemon=True,
        )
        fil.start()
        fils.append((commandes, fil, gestionnaire))
        return suivi, commandes

    yield lancer
    for commandes, fil, gestionnaire in fils:
        commandes.arreter()
        fil.join(5)
        moteur.journal.removeHandler(gestionnaire)
    moteur.appliquer_reglages(reglages.Reglages())


# ─── Listes noire et blanche ──────────────────────────────────────────────────


def test_liste_noire(demarrer, faux_sony):
    suivi, _ = demarrer(liste_noire=["PSEUDO_A"])
    assert attendre_que(lambda: "b" in faux_sony.acceptes)
    assert attendre_que(
        lambda: any("ignorée (liste noire)" in t for t in textes(suivi))
    )
    assert "a" not in faux_sony.acceptes
    # Signalée une seule fois, et pas comptée comme « en attente ».
    assert attendre_que(lambda: suivi.instantane().derniere_verification is not None)
    assert sum("ignorée" in t for t in textes(suivi)) == 1
    assert suivi.instantane().demandes_en_attente == 0


def test_liste_blanche(demarrer, faux_sony):
    suivi, _ = demarrer(liste_blanche=["a"])
    assert attendre_que(lambda: "a" in faux_sony.acceptes)
    assert attendre_que(
        lambda: any("pas dans la liste blanche" in t for t in textes(suivi))
    )
    assert "b" not in faux_sony.acceptes


def test_motif_ignore():
    moteur.appliquer_reglages(
        reglages.Reglages(liste_noire=["Mechant"], liste_blanche=["Gentil", "123"])
    )
    try:
        assert moteur.motif_ignore("mechant", "9") == "liste noire"
        assert moteur.motif_ignore("Gentil", "1") is None
        assert moteur.motif_ignore("Autre", "123") is None
        assert moteur.motif_ignore("Autre", "1") == "pas dans la liste blanche"
    finally:
        moteur.appliquer_reglages(reglages.Reglages())


# ─── Pause automatique et demandes en attente ─────────────────────────────────


def test_pause_automatique_apres_n_ajouts(demarrer, faux_sony):
    suivi, commandes = demarrer(pause_apres_ajouts=1)
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.PAUSE)
    assert commandes.pause.is_set()
    assert faux_sony.acceptes == ["a"]
    assert any("Pause automatique après 1 ajout" in t for t in textes(suivi))
    # Pendant la pause, la demande restante est listée avec son pseudo.
    assert attendre_que(
        lambda: [a.pseudo for a in suivi.instantane().attentes] == ["Pseudo_b"]
    )
    assert suivi.instantane().attentes[0].motif == "en pause"
    # À la reprise, le compteur repart de zéro : un ajout, puis nouvelle pause.
    commandes.basculer_pause()
    assert attendre_que(lambda: faux_sony.acceptes == ["a", "b"])
    assert attendre_que(lambda: commandes.pause.is_set())


def test_anciennete_des_demandes(faux_sony, demarrer):
    il_y_a_une_heure = datetime.now() - timedelta(hours=1)
    faux_sony.depuis = {"a": il_y_a_une_heure, "b": il_y_a_une_heure}
    suivi, commandes = demarrer()
    commandes.basculer_pause()
    assert attendre_que(lambda: len(suivi.instantane().attentes) == 2)
    assert suivi.instantane().attentes[0].depuis == il_y_a_une_heure


def test_date_de_demande_sony():
    moment = moteur._moment_sony("2026-11-10T20:48:01.552Z")
    assert moment is not None
    assert moment.tzinfo is None
    assert moteur._moment_sony("pas une date") is None
    assert moteur._moment_sony(None) is None


# ─── Amis retirés pendant l'arrêt ─────────────────────────────────────────────


def test_memoire_des_amis(dossier):
    moteur.memoriser_amis("compte_test", {"1", "2"})
    assert moteur.amis_memorises("compte_test") == {"1", "2"}
    # Un autre compte ne compare pas sa liste à celle-ci.
    assert moteur.amis_memorises("autre_compte") is None
    moteur.FICHIER_AMIS.write_text("pas du json", encoding="utf-8")
    assert moteur.amis_memorises("compte_test") is None


def test_ami_retire_pendant_l_arret(dossier, demarrer, faux_sony):
    anciens = {*faux_sony.ids, "parti"}
    moteur.FICHIER_AMIS.write_text(
        json.dumps({"compte": "compte_test", "amis": sorted(anciens)}),
        encoding="utf-8",
    )
    suivi, _ = demarrer()
    assert attendre_que(
        lambda: "Ami retiré pendant l'arrêt : Pseudo_parti" in textes(suivi)
    )
    assert suivi.instantane().retraits[0].pseudo == "Pseudo_parti"
    # La liste à jour est gardée pour le prochain lancement.
    assert attendre_que(
        lambda: "parti" not in (moteur.amis_memorises("compte_test") or {})
    )


# ─── Notifications Windows ────────────────────────────────────────────────────


def test_bulle_quand_le_code_est_refuse(dossier, secret, isolement, monkeypatch):
    def refuser(npsso):
        raise moteur.PSNAWPAuthenticationError("refusé")

    monkeypatch.setattr(moteur, "lire_npsso", lambda: secret)
    monkeypatch.setattr(moteur, "ouvrir_connexion", refuser)
    suivi, commandes = moteur.Suivi(), moteur.Commandes()
    assert moteur.connecter(suivi, commandes, attendre=False) is None
    assert isolement.bulles
    assert "code npsso" in isolement.bulles[0][0]
    # Notifications coupées dans les réglages : aucune bulle.
    isolement.bulles.clear()
    moteur.appliquer_reglages(reglages.Reglages(notifications=False))
    try:
        moteur.connecter(suivi, commandes, attendre=False)
    finally:
        moteur.appliquer_reglages(reglages.Reglages())
    assert not isolement.bulles


def test_bulle_quand_la_liste_est_pleine(isolement):
    moteur.signaler_liste_pleine(moteur.Etat(), 2000)
    assert any("pleine" in titre for titre, _ in isolement.bulles)


def test_bulle_apres_une_longue_coupure(demarrer, faux_sony, isolement, monkeypatch):
    monkeypatch.setattr(moteur, "attente_progressive", lambda erreurs: 0.05)
    faux_sony.coupure = True
    demarrer()
    assert attendre_que(lambda: any("hors ligne" in t for t, _ in isolement.bulles))
    assert len(isolement.bulles) == 1


# ─── Relecture du journal ─────────────────────────────────────────────────────


def test_relecture_des_dernieres_24_heures(dossier):
    maintenant = datetime.now()
    lignes = [
        (maintenant - timedelta(hours=30), "Demande acceptée : Trop_vieux"),
        (maintenant - timedelta(hours=20), "Demande acceptée : Hier_soir"),
        (maintenant - timedelta(hours=1), "Demande acceptée : Recent"),
        (maintenant - timedelta(hours=1), "Ami retiré pendant l'arrêt : Recent"),
    ]
    (dossier / "journal.txt").write_text(
        "".join(f"{moment:%Y-%m-%d %H:%M:%S}  {texte}\n" for moment, texte in lignes),
        encoding="utf-8",
    )
    ajouts = [a.pseudo for a in moteur.ajouts_recents_dans_journal()]
    assert ajouts == ["Hier_soir", "Recent"]
    assert [r.pseudo for r in moteur.retraits_recents_dans_journal()] == ["Recent"]


def test_statistiques_par_jour(dossier):
    aujourd_hui = datetime.now()
    hier = aujourd_hui - timedelta(days=1)
    il_y_a_10_jours = aujourd_hui - timedelta(days=10)
    (dossier / "journal.txt").write_text(
        f"{il_y_a_10_jours:%Y-%m-%d} 12:00:00  Demande acceptée : Vieux\n"
        f"{hier:%Y-%m-%d} 12:00:00  Demande acceptée : A\n"
        f"{hier:%Y-%m-%d} 12:00:01  Demande acceptée : B\n"
        f"{hier:%Y-%m-%d} 13:00:00  Ami retiré : A\n"
        f"{aujourd_hui:%Y-%m-%d} 00:00:00  Demande acceptée : C\n",
        encoding="utf-8",
    )
    statistiques = moteur.statistiques_par_jour(7)
    assert len(statistiques) == 7
    assert statistiques[0] == (aujourd_hui.date(), 1, 0)
    assert statistiques[1] == (hier.date(), 2, 1)
    assert sum(ajouts for _, ajouts, _ in statistiques) == 3


def test_compteurs_de_retraits():
    suivi = moteur.Suivi()
    suivi.retrait("x")
    suivi.retrait("y", datetime.now() - timedelta(days=2))
    instant = suivi.instantane()
    assert instant.retraits_session == 2
    assert instant.retraits_jour == 1


# ─── Réglages appliqués au moteur ─────────────────────────────────────────────


def test_reglages_appliques_au_moteur():
    try:
        moteur.appliquer_reglages(
            reglages.Reglages(
                intervalle_verification=30, pause_entre_acceptations=5, limite_amis=1500
            )
        )
        assert moteur.INTERVALLE_VERIFICATION == 30
        assert moteur.PAUSE_ENTRE_ACCEPTATIONS == 5
        assert moteur.LIMITE_AMIS_PSN == 1500
    finally:
        moteur.appliquer_reglages(reglages.Reglages())
    assert moteur.INTERVALLE_VERIFICATION == 15


def test_diagnostic_masque_le_code(dossier, secret):
    moteur.configurer_journal(ecran=False, fichier=False, diagnostic=True)
    try:
        moteur.journal.debug("détail technique avec %s", secret)
        for gestionnaire in moteur.journal.handlers:
            gestionnaire.flush()
        contenu = moteur.FICHIER_DIAGNOSTIC.read_text(encoding="utf-8")
    finally:
        for gestionnaire in list(moteur.journal.handlers):
            if getattr(gestionnaire, "baseFilename", "").endswith("diagnostic.txt"):
                gestionnaire.close()
                moteur.journal.removeHandler(gestionnaire)
        moteur.journal.setLevel("INFO")
    assert "détail technique avec [code masqué]" in contenu
    assert secret not in contenu
