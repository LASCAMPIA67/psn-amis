"""Le moteur face à un faux Sony : acceptations, pause, coupure, liste pleine, amis
retirés, demandes de partage du vrai nom, renouvellement de l'accès."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from psnawp_api.core import PSNAWPBadRequestError

from psn_amis import moteur
from tests.conftest import attendre_que

# ─── Tri des demandes reçues ──────────────────────────────────────────────────


def test_tri_des_demandes_recues():
    reponse = {
        "receivedRequests": [
            {
                "accountId": "1",
                "relation": "friend",
                "personalDetailSharing": "requested",
            },
            {"accountId": "2", "relation": "requested"},
            {"accountId": "3"},
            {"relation": "requested"},
        ]
    }
    api = SimpleNamespace(
        authenticator=SimpleNamespace(
            get=lambda **_: SimpleNamespace(json=lambda: reponse)
        )
    )
    demandes = moteur.demandes_recues(moteur.Connexion(api, "x"))
    assert demandes.amis == ["2", "3"]
    assert demandes.partages == ["1"]


# ─── Renouvellement anticipé de l'accès Sony ──────────────────────────────────


class FauxAcces:
    def __init__(self, expire_dans: float) -> None:
        self.token_response = {"access_token_expires_at": time.time() + expire_dans}
        self.appels = 0
        self.erreur: Exception | None = None

    @property
    def access_token_expiration_time(self) -> float:
        return self.token_response["access_token_expires_at"]

    def fetch_access_token_from_refresh(self) -> None:
        if self.erreur:
            raise self.erreur
        self.appels += 1
        self.token_response["access_token_expires_at"] = time.time() + 3600


@pytest.mark.parametrize(("expire_dans", "attendu"), [(3600, 0), (60, 1), (-5, 1)])
def test_renouvellement_anticipe(expire_dans, attendu):
    acces = FauxAcces(expire_dans)
    moteur.Connexion(
        SimpleNamespace(authenticator=acces), "x"
    ).renouveler_acces_si_besoin()
    assert acces.appels == attendu


def test_renouvellement_refuse_demande_une_reconnexion():
    acces = FauxAcces(60)
    acces.erreur = PSNAWPBadRequestError('{"error": {"message": "invalid_grant"}}')
    with pytest.raises(moteur.PSNAWPAuthenticationError):
        moteur.Connexion(
            SimpleNamespace(authenticator=acces), "x"
        ).renouveler_acces_si_besoin()


# ─── Le moteur complet ────────────────────────────────────────────────────────


def textes(suivi: moteur.Suivi) -> list[str]:
    return [evenement.texte for evenement in suivi.instantane().evenements]


def test_acceptations_et_statut(moteur_en_marche):
    suivi, _commandes, _fil = moteur_en_marche
    assert attendre_que(lambda: suivi.instantane().ajouts_session == 2)
    instant = suivi.instantane()
    assert instant.pseudo_compte == "compte_test"
    assert instant.nombre_amis == 12
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.EN_MARCHE)
    assert "Demande acceptée : Pseudo_a" in textes(suivi)
    assert any(e.genre == moteur.GENRE_AJOUT for e in suivi.instantane().evenements)
    assert not any("Bloc-notes" in t or "Ctrl+C" in t for t in textes(suivi))


def test_partage_du_vrai_nom_jamais_accepte(moteur_en_marche, faux_sony):
    suivi, _commandes, _fil = moteur_en_marche
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.EN_MARCHE)
    faux_sony.partages.append("ami3")
    assert attendre_que(lambda: any("demande d'ami proche" in t for t in textes(suivi)))
    time.sleep(2.5)
    assert sum("demande d'ami proche" in t for t in textes(suivi)) == 1
    assert "ami3" not in faux_sony.acceptes
    assert not any("refusée" in t for t in textes(suivi))
    assert suivi.instantane().demandes_en_attente == 0


def test_pause_et_reprise(moteur_en_marche, faux_sony):
    suivi, commandes, _fil = moteur_en_marche
    assert attendre_que(lambda: suivi.instantane().ajouts_session == 2)
    commandes.basculer_pause()
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.PAUSE)
    faux_sony.demandes.append("c")
    time.sleep(1.5)
    assert "c" not in faux_sony.acceptes
    commandes.basculer_pause()
    assert attendre_que(lambda: "c" in faux_sony.acceptes)


def test_coupure_internet_puis_reprise_avec_v(moteur_en_marche, faux_sony):
    suivi, commandes, _fil = moteur_en_marche
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.EN_MARCHE)
    faux_sony.coupure = True
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.HORS_LIGNE)
    assert suivi.instantane().prochaine_verification is not None
    faux_sony.coupure = False
    commandes.verifier_maintenant()
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.EN_MARCHE, 3)


def test_liste_pleine_puis_place_liberee(moteur_en_marche, faux_sony):
    suivi, commandes, _fil = moteur_en_marche
    assert attendre_que(lambda: suivi.instantane().ajouts_session == 2)
    faux_sony.total_force, faux_sony.refuser = 2003, True
    faux_sony.demandes.append("d")
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.LISTE_PLEINE)
    assert any("LISTE D'AMIS PLEINE" in t for t in textes(suivi))
    faux_sony.total_force, faux_sony.refuser = None, False
    commandes.verifier_maintenant()
    time.sleep(0.3)
    commandes.verifier_maintenant()
    assert attendre_que(lambda: "d" in faux_sony.acceptes)
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.EN_MARCHE)


def test_amis_retires_notes_une_fois(moteur_en_marche, faux_sony):
    suivi, _commandes, _fil = moteur_en_marche
    assert attendre_que(lambda: suivi.instantane().ajouts_session == 2)
    time.sleep(1.5)
    faux_sony.ids.discard("a")
    assert attendre_que(
        lambda: any(
            e.genre == moteur.GENRE_RETRAIT and e.texte == "Ami retiré : Pseudo_a"
            for e in suivi.instantane().evenements
        )
    )
    assert suivi.instantane().nombre_amis == len(faux_sony.ids)

    # Un ami accepté puis retiré avant le comptage suivant est aussi repéré.
    faux_sony.demandes.append("e")
    assert attendre_que(lambda: "e" in faux_sony.acceptes)
    faux_sony.ids.discard("e")
    assert attendre_que(lambda: "Ami retiré : Pseudo_e" in textes(suivi))
    time.sleep(2.5)
    assert sum(t.startswith("Ami retiré") for t in textes(suivi)) == 2


def test_reconnexion_apres_nouveau_code(moteur_en_marche):
    suivi, commandes, _fil = moteur_en_marche
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.EN_MARCHE)
    nombre_connexions = sum("Connecté au compte" in t for t in textes(suivi))
    commandes.demander_reconnexion()
    assert attendre_que(
        lambda: (
            sum("Connecté au compte" in t for t in textes(suivi))
            == nombre_connexions + 1
        )
    )
    assert not commandes.reconnecter.is_set()


def test_arret_rapide(moteur_en_marche):
    suivi, commandes, fil = moteur_en_marche
    assert attendre_que(lambda: suivi.instantane().statut == moteur.Statut.EN_MARCHE)
    depart = time.monotonic()
    commandes.arreter()
    fil.join(3)
    assert not fil.is_alive()
    assert time.monotonic() - depart < 2
