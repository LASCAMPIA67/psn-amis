"""Le moteur et la gestion des amis ensemble, face au faux Sony : nettoyage, suppressions
demandées depuis l'interface, types de demandes (dont les demandes d'ami proche)."""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from psn_amis import gestion as gestion_module
from psn_amis import moteur, nettoyage, reglages
from psn_amis.amis import Critere, Resultat
from psn_amis.simulation import COMPTE_DEMO, ConnexionSimulee, SonySimule
from tests.conftest import attendre_que

# ─── Décision de nettoyage (16, 17, 18) ───────────────────────────────────────

MIDI = datetime(2026, 11, 13, 12, 0)


def regles(**changements) -> reglages.Reglages:
    base = reglages.Reglages(
        nettoyage_mode="automatique",
        nettoyage_seuil=100,
        nettoyage_cible=80,
        nettoyage_max_par_cycle=10,
        nettoyage_max_par_jour=15,
        nettoyage_intervalle=60,
    )
    return replace(base, **changements)


def test_16_nettoyage_desactive_par_defaut():
    assert reglages.Reglages().nettoyage_mode == "manuel"
    decision = nettoyage.decider(reglages.Reglages(), 5000, nettoyage.Memoire(), MIDI)
    assert decision.nombre == 0


def test_17_nettoyage_dans_les_limites():
    memoire = nettoyage.Memoire()
    # 130 amis, cible 80 : 50 de trop, mais 10 au plus par nettoyage.
    assert nettoyage.decider(regles(), 130, memoire, MIDI).nombre == 10
    # Seuil non atteint : rien.
    assert nettoyage.decider(regles(), 99, memoire, MIDI).nombre == 0
    # Quota du jour : 15, dont 10 déjà faits.
    memoire.noter(MIDI - timedelta(hours=2), 10)
    assert nettoyage.decider(regles(), 130, memoire, MIDI).nombre == 5
    memoire.noter(MIDI - timedelta(hours=1), 5)
    decision = nettoyage.decider(regles(), 130, memoire, MIDI)
    assert decision.nombre == 0
    assert "limite" in decision.raison
    # Le lendemain, le quota repart.
    lendemain = MIDI + timedelta(days=1)
    assert nettoyage.decider(regles(), 130, memoire, lendemain).nombre == 10


def test_17b_delai_et_heures_autorisees():
    memoire = nettoyage.Memoire()
    memoire.noter(MIDI - timedelta(minutes=30), 1)
    assert "délai" in nettoyage.decider(regles(), 130, memoire, MIDI).raison
    nuit = regles(nettoyage_heures="22-06")
    assert nettoyage.decider(nuit, 130, nettoyage.Memoire(), MIDI).nombre == 0
    assert (
        nettoyage.decider(nuit, 130, nettoyage.Memoire(), MIDI.replace(hour=23)).nombre
        == 10
    )
    assert nettoyage.dans_la_plage("22-06", MIDI.replace(hour=3))
    assert not nettoyage.dans_la_plage("02-07", MIDI.replace(hour=7))


def test_18_pas_de_boucle_suppression_acceptation():
    memoire = nettoyage.Memoire()
    reglage = regles(nettoyage_max_par_jour=1000, nettoyage_intervalle=10)
    moment = MIDI
    for _ in range(nettoyage.NETTOYAGES_MAX_24H):
        assert nettoyage.decider(reglage, 130, memoire, moment).nombre > 0
        memoire.noter(moment, 10)
        moment += timedelta(minutes=11)
    decision = nettoyage.decider(reglage, 130, memoire, moment)
    assert decision.nombre == 0
    assert decision.couper
    assert "boucle" in decision.raison


def test_memoire_du_nettoyage_sur_le_disque(tmp_path):
    memoire = nettoyage.Memoire()
    memoire.noter(MIDI, 7)
    memoire.ecrire(tmp_path / "nettoyage.json")
    relue = nettoyage.Memoire.lire(tmp_path / "nettoyage.json")
    assert relue.supprimes_jour == 7
    assert relue.dernier == MIDI
    assert nettoyage.Memoire.lire(tmp_path / "absent.json").supprimes_jour == 0


# ─── Le moteur avec la gestion des amis ───────────────────────────────────────


@pytest.fixture
def sony(monkeypatch, dossier, secret) -> SonySimule:
    sony = SonySimule(nombre_amis=30)
    connexion = ConnexionSimulee(sony)
    monkeypatch.setattr(moteur, "lire_npsso", lambda: secret)
    monkeypatch.setattr(moteur, "ouvrir_connexion", lambda npsso: connexion)
    monkeypatch.setattr(moteur, "demandes_recues", sony.demandes_recues)
    monkeypatch.setattr(moteur, "liste_amis", sony.liste_amis)
    monkeypatch.setattr(moteur, "trouver_joueur", sony.trouver_joueur)
    monkeypatch.setattr(moteur, "client_psn", lambda connexion: sony)
    monkeypatch.setattr(moteur, "INTERVALLE_VERIFICATION", 1)
    monkeypatch.setattr(moteur, "PAUSE_ENTRE_ACCEPTATIONS", 0.01)
    monkeypatch.setattr(
        moteur, "REGLAGES", replace(moteur.REGLAGES, suppression_pause=3)
    )
    return sony


class Moteur:
    def __init__(self, dossier, couper=None) -> None:
        self.suivi = moteur.Suivi()
        self.commandes = moteur.Commandes()
        self.coupures: list[str] = []
        self.gestion = gestion_module.Gestion(
            dossier,
            lambda: moteur.REGLAGES,
            couper or self.coupures.append,
        )
        self.messages: list[str] = []
        self._capture = _Capture(self.messages)
        moteur.journal.addHandler(self._capture)
        self.fil = threading.Thread(
            target=moteur.tourner_en_continu,
            args=(moteur.Etat(), self.suivi, self.commandes, self.gestion),
            daemon=True,
        )

    def __enter__(self) -> Moteur:
        self.fil.start()
        assert attendre_que(lambda: self.gestion.vue().liste_complete)
        return self

    def __exit__(self, *details) -> None:
        self.commandes.arreter()
        self.fil.join(10)
        moteur.journal.removeHandler(self._capture)
        assert not self.fil.is_alive()


class _Capture(moteur.logging.Handler):
    def __init__(self, messages: list[str]) -> None:
        super().__init__()
        self._messages = messages

    def emit(self, record) -> None:
        self._messages.append(record.getMessage())


def test_suppression_demandee_executee_par_le_moteur(sony, dossier):
    with Moteur(dossier) as m:
        vue = m.gestion.vue()
        assert vue.compte == COMPTE_DEMO
        assert len(vue.amis) == 30
        m.gestion.demander_pseudos(100)
        m.commandes.verifier_maintenant()
        assert attendre_que(lambda: m.gestion.vue().pseudos_manquants == 0)
        protege = min(sony.amis)
        m.gestion.proteger(sony.pseudos[protege])
        selection = m.gestion.selection(Critere.ALPHABETIQUE, 4)
        assert protege not in {c.compte for c in selection.cibles}
        m.gestion.demander_suppression(selection)
        m.commandes.verifier_maintenant()
        assert attendre_que(
            lambda: m.gestion.vue().derniere_operation is not None, delai=20
        )
        operation = m.gestion.vue().derniere_operation
        assert operation.bilan() == {Resultat.SUPPRIME: 4}
        assert protege in sony.amis
        assert attendre_que(lambda: m.suivi.instantane().supprimes_session == 4)
        # Une fois la liste recomptée, aucun « Ami retiré » en double.
        m.commandes.verifier_maintenant()
        assert attendre_que(lambda: len(m.gestion.vue().amis) == 26)
        assert not any(t.startswith("Ami retiré :") for t in m.messages)
        assert sum("Ami supprimé par PSN Amis" in t for t in m.messages) == 4


def test_annulation_de_la_file(sony, dossier, monkeypatch):
    monkeypatch.setattr(
        moteur, "REGLAGES", replace(moteur.REGLAGES, suppression_pause=30)
    )
    with Moteur(dossier) as m:
        selection = m.gestion.selection_manuelle(sorted(sony.amis)[:5])
        m.gestion.demander_suppression(selection)
        m.commandes.verifier_maintenant()
        assert attendre_que(lambda: m.gestion.vue().operation is not None)
        assert attendre_que(lambda: m.gestion.vue().operation.traites >= 1)
        m.gestion.annuler()
        assert attendre_que(
            lambda: m.gestion.vue().derniere_operation is not None, delai=10
        )
        operation = m.gestion.vue().derniere_operation
        assert operation.raison_arret == "annulée"
        assert operation.bilan()[Resultat.SUPPRIME] == 1
        assert len(sony.amis) == 29


def test_suppression_refusee_sans_liste_complete(dossier):
    gestion = gestion_module.Gestion(dossier, reglages.Reglages)
    with pytest.raises(ValueError, match="aucun compte"):
        gestion.selection(Critere.ALPHABETIQUE, 3)
    gestion.connecte(COMPTE_DEMO, "moi")
    gestion.observer({"1", "2"}, complete=False)
    selection = gestion.selection_manuelle(["1"])
    with pytest.raises(ValueError, match="entièrement"):
        gestion.demander_suppression(selection)


def test_limite_par_operation(dossier):
    gestion = gestion_module.Gestion(
        dossier, lambda: reglages.Reglages(suppression_max=2)
    )
    gestion.connecte(COMPTE_DEMO, "moi")
    gestion.observer({"1", "2", "3"}, complete=True)
    with pytest.raises(ValueError, match="au plus 2"):
        gestion.demander_suppression(gestion.selection_manuelle(["1", "2", "3"]))


def test_changement_de_compte_vide_la_file(dossier):
    gestion = gestion_module.Gestion(dossier, reglages.Reglages)
    gestion.connecte(COMPTE_DEMO, "moi")
    gestion.observer({"1", "2"}, complete=True)
    gestion.proteger("Alice", "1")
    gestion.demander_suppression(gestion.selection_manuelle(["2"]))
    assert gestion.vue().en_file == 1
    gestion.connecte("2000", "autre")
    vue = gestion.vue()
    assert vue.en_file == 0
    assert vue.proteges == ()
    # Les protections de chaque compte restent à part.
    gestion.connecte(COMPTE_DEMO, "moi")
    assert [p.compte for p in gestion.vue().proteges] == ["1"]


def test_operation_interrompue_signalee_jamais_reprise(dossier):
    gestion = gestion_module.Gestion(dossier, reglages.Reglages)
    gestion.connecte(COMPTE_DEMO, "moi")
    historique = gestion._compte.historique
    historique.noter({"type": "debut", "operation": "x1", "nombre": 3})
    neuve = gestion_module.Gestion(dossier, reglages.Reglages)
    neuve.connecte(COMPTE_DEMO, "moi")
    assert neuve.vue().interrompue["operation"] == "x1"
    assert neuve.vue().en_file == 0
    # Signalée une seule fois.
    encore = gestion_module.Gestion(dossier, reglages.Reglages)
    encore.connecte(COMPTE_DEMO, "moi")
    assert encore.vue().interrompue is None


def test_nettoyage_automatique_par_le_moteur(sony, dossier, monkeypatch):
    monkeypatch.setattr(
        moteur,
        "REGLAGES",
        replace(
            moteur.REGLAGES,
            suppression_pause=3,
            nettoyage_mode="automatique",
            nettoyage_seuil=25,
            nettoyage_cible=20,
            nettoyage_max_par_cycle=3,
            nettoyage_critere="premiere_observation",
        ),
    )
    monkeypatch.setattr(gestion_module.amis_module, "attente_interruptible", _instant)
    with Moteur(dossier) as m:
        # 30 amis, seuil 25 : 3 suppressions au plus par nettoyage.
        assert attendre_que(lambda: m.gestion.vue().derniere_operation is not None)
        operation = m.gestion.vue().derniere_operation
        assert operation.origine == "nettoyage"
        assert operation.bilan() == {Resultat.SUPPRIME: 3}
        # Puis le délai entre deux nettoyages empêche d'enchaîner.
        m.commandes.verifier_maintenant()
        assert attendre_que(lambda: len(sony.amis) == 27)
        assert len(sony.amis) == 27


def test_nettoyage_assiste_propose_sans_supprimer(sony, dossier, monkeypatch):
    monkeypatch.setattr(
        moteur,
        "REGLAGES",
        replace(
            moteur.REGLAGES,
            nettoyage_mode="assiste",
            nettoyage_seuil=25,
            nettoyage_cible=20,
            nettoyage_critere="premiere_observation",
        ),
    )
    with Moteur(dossier) as m:
        assert attendre_que(lambda: m.gestion.vue().proposition is not None)
        assert len(m.gestion.vue().proposition.cibles) == 10
        assert len(sony.amis) == 30
        assert not [a for a in sony.appels if a[0] == "supprimer"]


def _instant(est_arrete, secondes, pas=0.2):
    return est_arrete()


# ─── Demandes (§ 20.3) ────────────────────────────────────────────────────────


def test_demande_ordinaire_acceptee(sony, dossier):
    nouveau = sony.recevoir()
    with Moteur(dossier) as m:
        assert attendre_que(lambda: nouveau in sony.amis)
        fiche = m.gestion._compte.registre.toutes()[nouveau]
        assert fiche.accepte_le is not None


def test_demande_d_ami_proche_jamais_touchee(sony, dossier, monkeypatch):
    # Test critique : un ami existant demande à partager son vrai nom. Même avec le
    # refus automatique demandé, l'ami n'est jamais supprimé.
    monkeypatch.setattr(
        moteur,
        "REGLAGES",
        replace(moteur.REGLAGES, refuser_demandes_ami_proche=True),
    )
    ami = min(sony.amis)
    sony.recevoir(ami, relation="friend", partage="requested")
    with Moteur(dossier) as m:
        m.commandes.verifier_maintenant()
        assert attendre_que(
            lambda: len([a for a in sony.appels if a[0] == "liste"]) > 2
        )
        assert ami in sony.amis
        assert ami in sony.demandes
        assert not [a for a in sony.appels if a[0] in ("supprimer", "accepter")]
        assert any("n'est pas disponible" in t for t in m.messages)


def test_demande_avec_vrai_nom_jamais_acceptee(sony, dossier):
    inconnu = sony.recevoir(relation="requested", partage="requested")
    with Moteur(dossier) as m:
        m.commandes.verifier_maintenant()
        assert attendre_que(lambda: any("vrais noms" in t for t in m.messages))
        assert inconnu not in sony.amis
        assert ("accepter", inconnu) not in sony.appels


def test_type_inconnu_laisse_en_attente(sony, dossier):
    bizarre = sony.recevoir(relation="nouveau_type")
    with Moteur(dossier) as m:
        assert attendre_que(lambda: any("non reconnu" in t for t in m.messages))
        assert bizarre not in sony.amis


def test_type_inconnu_accepte_si_reglage(sony, dossier, monkeypatch):
    monkeypatch.setattr(
        moteur,
        "REGLAGES",
        replace(moteur.REGLAGES, demandes_non_reconnues="accepter"),
    )
    bizarre = sony.recevoir(relation="nouveau_type")
    with Moteur(dossier):
        assert attendre_que(lambda: bizarre in sony.amis)


def test_acceptation_automatique_coupee(sony, dossier, monkeypatch):
    monkeypatch.setattr(
        moteur, "REGLAGES", replace(moteur.REGLAGES, acceptation_auto=False)
    )
    nouveau = sony.recevoir()
    with Moteur(dossier) as m:
        assert attendre_que(lambda: m.suivi.instantane().demandes_en_attente == 1)
        assert nouveau not in sony.amis
        assert (
            m.suivi.instantane().attentes[0].motif == "acceptation automatique coupée"
        )


def test_liste_noire_refusee_seulement_si_demandee(sony, dossier, monkeypatch):
    indesirable = sony.recevoir()
    pseudo = sony.pseudos[indesirable]
    monkeypatch.setattr(
        moteur,
        "REGLAGES",
        replace(moteur.REGLAGES, liste_noire=[pseudo], liste_noire_refuser=True),
    )
    with Moteur(dossier) as m:
        assert attendre_que(lambda: indesirable not in sony.demandes)
        assert indesirable not in sony.amis
        # La relation est vérifiée avant le refus.
        rang = sony.appels.index(("supprimer", indesirable))
        assert sony.appels[rang - 1] == ("relation", indesirable)
        assert any("refusée (liste noire)" in t for t in m.messages)


def test_erreur_api_pendant_le_refus(sony, dossier, monkeypatch):
    indesirable = sony.recevoir()
    monkeypatch.setattr(
        moteur,
        "REGLAGES",
        replace(
            moteur.REGLAGES,
            liste_noire=[sony.pseudos[indesirable]],
            liste_noire_refuser=True,
        ),
    )
    sony.panne(
        "relation",
        moteur.PSNAWPClientError('{"error": {"message": "x"}}'),
        indesirable,
        toujours=True,
    )
    with Moteur(dossier) as m:
        assert attendre_que(
            lambda: any("ignorée (liste noire)" in t for t in m.messages)
        )
        assert indesirable in sony.demandes
        assert ("supprimer", indesirable) not in sony.appels
