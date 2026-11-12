"""L'état partagé avec l'affichage (Suivi), les ordres du clavier (Commandes) et la
relecture du journal au démarrage."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

import moteur


def test_compteurs_du_suivi():
    suivi = moteur.Suivi()
    suivi.connecte("compte_test", 10)
    suivi.demandes_trouvees(2)
    suivi.ajout("Joueur1")
    suivi.ajout("Joueur2")
    instant = suivi.instantane()
    assert instant.ajouts_session == 2
    assert instant.ajouts_jour == 2
    assert instant.nombre_amis == 12
    assert instant.demandes_en_attente == 0
    assert instant.derniers_ajouts[0].pseudo == "Joueur2"
    assert instant.amis_comptes_a is not None


def test_compteur_du_jour_remis_a_zero_a_minuit():
    suivi = moteur.Suivi()
    suivi.ajout("Joueur1")
    suivi._jour -= timedelta(days=1)
    assert suivi.instantane().ajouts_jour == 0
    assert suivi.instantane().ajouts_session == 1


def test_amis_renvoie_l_ancien_chiffre():
    suivi = moteur.Suivi()
    suivi.connecte("compte_test", 10)
    assert suivi.amis(8) == 10
    assert suivi.instantane().nombre_amis == 8


def test_attente_normale():
    commandes = moteur.Commandes()
    depart = time.monotonic()
    assert commandes.attendre(0.3) is False
    assert time.monotonic() - depart >= 0.28


def test_touche_v_reveille_l_attente():
    commandes = moteur.Commandes()
    threading.Timer(0.2, commandes.verifier_maintenant).start()
    depart = time.monotonic()
    assert commandes.attendre(5) is True
    assert time.monotonic() - depart < 1


def test_arret_reveille_toujours():
    commandes = moteur.Commandes()
    commandes.arreter()
    assert commandes.attendre(5) is True
    assert commandes.attendre(5) is True


def test_pause_bascule():
    commandes = moteur.Commandes()
    assert commandes.basculer_pause() is True
    assert commandes.pause.is_set()
    assert commandes.basculer_pause() is False


def test_relecture_des_ajouts_du_jour(dossier):
    maintenant = datetime.now()
    hier = maintenant - timedelta(days=1)
    (dossier / "journal.txt.1").write_text(
        f"{maintenant:%Y-%m-%d} 08:00:00  Demande acceptée : Ancien\n", encoding="utf-8"
    )
    (dossier / "journal.txt").write_text(
        f"{hier:%Y-%m-%d} 23:59:00  Demande acceptée : Hier\n"
        f"{maintenant:%Y-%m-%d} 09:00:00  Demande acceptée : Matin\n"
        f"{maintenant:%Y-%m-%d} 09:00:05  Connecté au compte PSN x (3 amis).\n"
        f"{maintenant:%Y-%m-%d} 09:30:00  Ami retiré : Matin\n",
        encoding="utf-8",
    )
    lus = moteur.ajouts_du_jour_dans_journal()
    assert [ajout.pseudo for ajout in lus] == ["Ancien", "Matin"]
    retraits = moteur.retraits_du_jour_dans_journal()
    assert [retrait.pseudo for retrait in retraits] == ["Matin"]
    instant = moteur.Suivi(lus, retraits).instantane()
    assert instant.ajouts_jour == 2
    assert instant.derniers_ajouts[0].pseudo == "Matin"
    assert instant.retraits[0].pseudo == "Matin"


def test_retrait_note_dans_le_suivi():
    suivi = moteur.Suivi()
    suivi.ajout("Joueur1")
    suivi.retrait("Joueur1")
    instant = suivi.instantane()
    assert instant.retraits[0].pseudo == "Joueur1"
    assert instant.retraits[0].moment >= instant.derniers_ajouts[0].moment


def test_journal_absent(dossier):
    assert moteur.ajouts_du_jour_dans_journal() == []
