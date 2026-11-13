"""Gestion des amis face au faux Sony : protections, sélection et suppressions.

Les numéros (1) à (18) renvoient aux scénarios de suppression du cahier des charges.
Aucun test n'envoie de requête : tout passe par simulation.SonySimule.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import requests
from psnawp_api.core import PSNAWPTooManyRequestsError, PSNAWPUnauthorizedError

from psn_amis import amis
from psn_amis.amis import (
    Contexte,
    Critere,
    Historique,
    Operation,
    Protections,
    Registre,
    Resultat,
    Verdict,
)
from psn_amis.simulation import COMPTE_DEMO, SonySimule


@pytest.fixture
def sony() -> SonySimule:
    return SonySimule(nombre_amis=8)


@pytest.fixture
def dossier(tmp_path):
    return tmp_path


@pytest.fixture
def registre(dossier, sony) -> Registre:
    registre = Registre(dossier / "amis_connus.json")
    debut = datetime(2026, 1, 1)
    for rang, compte in enumerate(sorted(sony.amis)):
        registre.accepte(compte, sony.pseudos[compte], debut + timedelta(days=rang))
    return registre


@pytest.fixture
def protections(dossier) -> Protections:
    return Protections(dossier / "amis_proteges.json")


@pytest.fixture
def historique(dossier) -> Historique:
    return Historique(dossier / "operations.jsonl")


def contexte(sony, registre, protections, historique, **options) -> Contexte:
    supprimes: list[str] = []
    valeurs = {
        "client": sony,
        "compte_connecte": COMPTE_DEMO,
        "registre": registre,
        "protections": protections,
        "historique": historique,
        "attendre": lambda secondes: False,
        "annulee": lambda: False,
        "pause": 0,
        "supprime": supprimes.append,
    }
    valeurs.update(options)
    ctx = Contexte(**valeurs)
    ctx.supprimes = supprimes  # type: ignore[attr-defined]
    return ctx


def operation_sur(sony, comptes, proprietaire=COMPTE_DEMO) -> Operation:
    return Operation(
        proprietaire,
        [amis.Cible(c, sony.pseudos.get(c)) for c in comptes],
        "test",
    )


def resultats(operation: Operation) -> list[Resultat]:
    return [ligne.resultat for ligne in operation.lignes]


# ─── Suppressions ─────────────────────────────────────────────────────────────


def test_01_suppression_d_un_ami(sony, registre, protections, historique):
    cible = min(sony.amis)
    ctx = contexte(sony, registre, protections, historique)
    operation = amis.executer(operation_sur(sony, [cible]), ctx)
    assert resultats(operation) == [Resultat.SUPPRIME]
    assert cible not in sony.amis
    # Vérification de la relation avant la suppression, rien d'autre.
    assert sony.appels == [("relation", cible), ("supprimer", cible)]
    assert ctx.supprimes == [cible]
    assert operation.etat == "terminée"


def test_02_suppression_de_plusieurs_amis(sony, registre, protections, historique):
    cibles = sorted(sony.amis)[:3]
    attentes: list[float] = []
    ctx = contexte(
        sony,
        registre,
        protections,
        historique,
        pause=7,
        attendre=lambda s: attentes.append(s) or False,
    )
    operation = amis.executer(operation_sur(sony, cibles), ctx)
    assert resultats(operation) == [Resultat.SUPPRIME] * 3
    # Une pause entre deux suppressions, pas après la dernière.
    assert attentes == [7, 7]


def test_03_selection_par_nombre(sony, registre, protections):
    selection = amis.selectionner(
        sony.amis, registre, protections, COMPTE_DEMO, Critere.PLUS_ANCIENS_ACCEPTES, 3
    )
    attendus = sorted(sony.amis)[:3]  # acceptés les 1er, 2 et 3 janvier
    assert [c.compte for c in selection.cibles] == attendus
    assert selection.supprimables == 3
    assert selection.requetes == 6
    assert "plus longtemps" in selection.critere


def test_04_tous_les_amis_proteges(sony, registre, protections, historique):
    for compte in sony.amis:
        protections.ajouter(sony.pseudos[compte], compte)
    selection = amis.selectionner(
        sony.amis, registre, protections, COMPTE_DEMO, Critere.ALPHABETIQUE, 5
    )
    assert selection.cibles == []
    assert selection.proteges == len(sony.amis)
    # Même si l'interface se trompait : le service refuse de supprimer.
    operation = amis.executer(
        operation_sur(sony, sorted(sony.amis)),
        contexte(sony, registre, protections, historique),
    )
    assert set(resultats(operation)) == {Resultat.PROTEGE}
    assert not [a for a in sony.appels if a[0] == "supprimer"]


def test_05_protection_ajoutee_pendant_l_operation(
    sony, registre, protections, historique
):
    premier, second = sorted(sony.amis)[:2]

    def proteger_le_second(operation, compte):
        if operation == "supprimer" and compte == premier:
            protections.ajouter(sony.pseudos[second], second)

    sony.avant = proteger_le_second
    operation = amis.executer(
        operation_sur(sony, [premier, second]),
        contexte(sony, registre, protections, historique),
    )
    assert resultats(operation) == [Resultat.SUPPRIME, Resultat.PROTEGE]
    assert second in sony.amis


def test_06_changement_de_pseudo(sony, registre, protections, historique):
    cible = min(sony.amis)
    protections.ajouter(sony.pseudos[cible], cible)
    # Le joueur change de pseudo : la protection suit son identifiant.
    sony.pseudos[cible] = "NouveauPseudo"
    assert protections.verdict(cible, "NouveauPseudo") is Verdict.PROTEGE
    operation = amis.executer(
        operation_sur(sony, [cible]), contexte(sony, registre, protections, historique)
    )
    assert resultats(operation) == [Resultat.PROTEGE]


def test_06b_protection_textuelle_relit_le_pseudo(
    sony, registre, protections, historique
):
    cible = min(sony.amis)
    # Protégé par pseudo seulement ; le registre connaît un ancien pseudo.
    registre.nommer(cible, "AncienPseudo")
    sony.pseudos[cible] = "Protege_42"
    protections.ajouter("protege_42")
    operation = amis.executer(
        operation_sur(sony, [cible]), contexte(sony, registre, protections, historique)
    )
    assert resultats(operation) == [Resultat.PROTEGE]
    assert cible in sony.amis


def test_07_compte_inexistant(sony, registre, protections, historique):
    operation = amis.executer(
        operation_sur(sony, ["9999"]), contexte(sony, registre, protections, historique)
    )
    assert resultats(operation) == [Resultat.DEJA_RETIRE]
    assert ("supprimer", "9999") not in sony.appels


def test_08_erreur_reseau_avant_la_suppression(sony, registre, protections, historique):
    premier, second = sorted(sony.amis)[:2]
    sony.panne("relation", requests.ConnectionError("coupure"), premier)
    operation = amis.executer(
        operation_sur(sony, [premier, second]),
        contexte(sony, registre, protections, historique),
    )
    assert resultats(operation) == [Resultat.ERREUR, Resultat.SUPPRIME]
    assert premier in sony.amis


def test_08b_erreurs_reseau_repetees_arretent(sony, registre, protections, historique):
    cibles = sorted(sony.amis)[:5]
    sony.panne("relation", requests.ConnectionError("coupure"), toujours=True)
    operation = amis.executer(
        operation_sur(sony, cibles), contexte(sony, registre, protections, historique)
    )
    assert resultats(operation) == [Resultat.ERREUR] * 3 + [Resultat.NON_TRAITE] * 2
    assert operation.raison_arret == "erreurs réseau répétées"


def test_09_reponse_ambigue(sony, registre, protections, historique):
    cible = min(sony.amis)
    sony.panne("supprimer", requests.Timeout("délai dépassé"), cible)
    operation = amis.executer(
        operation_sur(sony, [cible]), contexte(sony, registre, protections, historique)
    )
    assert resultats(operation) == [Resultat.A_VERIFIER]
    # Jamais renvoyée à l'aveugle.
    assert sony.appels.count(("supprimer", cible)) == 1
    assert historique.a_verifier() == {cible: operation.identifiant}


def test_10_limite_de_requetes(sony, registre, protections, historique):
    cibles = sorted(sony.amis)[:3]
    sony.panne(
        "relation", PSNAWPTooManyRequestsError('{"error": {"code": 1}}'), cibles[1]
    )
    operation = amis.executer(
        operation_sur(sony, cibles), contexte(sony, registre, protections, historique)
    )
    assert resultats(operation) == [
        Resultat.SUPPRIME,
        Resultat.NON_TRAITE,
        Resultat.NON_TRAITE,
    ]
    assert operation.raison_arret == "Sony demande de ralentir"


def test_11_arret_pendant_une_suppression(sony, registre, protections, historique):
    cibles = sorted(sony.amis)[:4]
    ctx = contexte(
        sony,
        registre,
        protections,
        historique,
        attendre=lambda s: True,  # arrêt demandé pendant la première pause
    )
    operation = amis.executer(operation_sur(sony, cibles), ctx)
    assert resultats(operation) == [Resultat.SUPPRIME] + [Resultat.NON_TRAITE] * 3
    assert operation.raison_arret == "annulée"
    assert operation.etat == "arrêtée"


def test_12_changement_de_compte(sony, registre, protections, historique):
    cible = min(sony.amis)
    operation = amis.executer(
        operation_sur(sony, [cible], proprietaire="5555"),
        contexte(sony, registre, protections, historique),
    )
    assert resultats(operation) == [Resultat.NON_TRAITE]
    assert "autre compte" in operation.raison_arret
    assert sony.appels == []


def test_12b_le_compte_connecte_n_est_jamais_une_cible(
    sony, registre, protections, historique
):
    operation = amis.executer(
        operation_sur(sony, [COMPTE_DEMO]),
        contexte(sony, registre, protections, historique),
    )
    assert resultats(operation) == [Resultat.REFUSE]
    selection = amis.selection_manuelle(
        [COMPTE_DEMO], sony.amis | {COMPTE_DEMO}, registre, protections, COMPTE_DEMO
    )
    assert selection.cibles == []


def test_13_liste_partielle_jamais_une_preuve(historique):
    historique.noter({"type": "ligne", "compte": "1", "resultat": "à vérifier"})
    assert amis.reconcilier(historique, set(), liste_complete=False) == {}
    assert historique.a_verifier() == {"1": ""}
    assert amis.reconcilier(historique, set(), liste_complete=True) == {
        "1": Resultat.CONFIRME
    }
    assert historique.a_verifier() == {}


def test_13b_reconciliation_toujours_ami(historique):
    historique.noter({"type": "ligne", "compte": "1", "resultat": "à vérifier"})
    assert amis.reconcilier(historique, {"1"}, liste_complete=True) == {
        "1": Resultat.TOUJOURS_AMI
    }


def test_14_suppression_deja_effectuee(sony, registre, protections, historique):
    cible = min(sony.amis)
    sony.amis.discard(cible)
    operation = amis.executer(
        operation_sur(sony, [cible]), contexte(sony, registre, protections, historique)
    )
    assert resultats(operation) == [Resultat.DEJA_RETIRE]
    # Pas de DELETE : il aurait pu refuser une demande d'ami en attente.
    assert ("supprimer", cible) not in sony.appels


def test_15_redemarrage_apres_interruption(sony, registre, protections, historique):
    historique.noter({"type": "debut", "operation": "abc", "nombre": 10})
    historique.noter({"type": "ligne", "operation": "abc", "compte": "1"})
    interrompue = historique.interrompue()
    assert interrompue is not None
    assert interrompue["operation"] == "abc"
    historique.noter({"type": "fin", "operation": "abc", "etat": "interrompue"})
    assert historique.interrompue() is None


def test_session_expiree_arrete_l_operation(sony, registre, protections, historique):
    cibles = sorted(sony.amis)[:2]
    sony.panne("relation", PSNAWPUnauthorizedError('{"error": {"code": 1}}'))
    operation = amis.executer(
        operation_sur(sony, cibles), contexte(sony, registre, protections, historique)
    )
    assert operation.raison_arret == "session Sony expirée"
    assert set(resultats(operation)) == {Resultat.NON_TRAITE}


def test_historique_complet(sony, registre, protections, historique):
    cible = min(sony.amis)
    operation = amis.executer(
        operation_sur(sony, [cible]), contexte(sony, registre, protections, historique)
    )
    types = [e["type"] for e in historique.evenements()]
    assert types == ["debut", "ligne", "fin"]
    assert historique.supprimes_le(datetime.now().date().isoformat()) == 1
    assert historique.evenements()[-1]["bilan"] == {"supprimé": 1}
    assert operation.bilan() == {Resultat.SUPPRIME: 1}


# ─── Protections ──────────────────────────────────────────────────────────────


def test_protections_par_identifiant_et_par_pseudo(protections):
    protections.ajouter("Alice", "111")
    protections.ajouter("bob")
    assert protections.verdict("111", "AutreNom") is Verdict.PROTEGE
    assert protections.verdict("222", "BOB") is Verdict.PROTEGE
    assert protections.verdict("333", "Charlie") is Verdict.LIBRE
    # Pseudo inconnu face à une protection textuelle : doute, donc pas de suppression.
    assert protections.verdict("333", None) is Verdict.DOUTE
    # Correspondance approximative jamais retenue.
    assert protections.verdict("333", "bob2") is Verdict.LIBRE


def test_protection_textuelle_devient_precise(protections):
    protections.ajouter("Bob")
    assert protections.textuelles()
    protections.ajouter("Bob", "444")
    assert not protections.textuelles()
    assert [p.cle for p in protections.toutes()] == ["444"]


def test_protections_gardees_sur_le_disque(dossier, protections):
    protections.ajouter("Alice", "111", note="ma sœur")
    relues = Protections(dossier / "amis_proteges.json")
    assert relues.verdict("111", None) is Verdict.PROTEGE
    assert relues.toutes()[0].note == "ma sœur"
    assert relues.retirer("111")
    assert Protections(dossier / "amis_proteges.json").toutes() == []


def test_import_et_export_des_protections(dossier, protections):
    protections.ajouter("Alice", "111")
    protections.exporter(dossier / "export.json")
    autre = Protections(dossier / "autre.json")
    assert autre.importer(dossier / "export.json") == 1
    assert autre.verdict("111", None) is Verdict.PROTEGE
    (dossier / "liste.txt").write_text(
        "Bob\n# commentaire\n\nCharlie  # ami\n", encoding="utf-8"
    )
    assert autre.importer(dossier / "liste.txt") == 2


def test_fichier_abime_mis_de_cote(dossier):
    (dossier / "amis_proteges.json").write_text("{pas du json", encoding="utf-8")
    assert Protections(dossier / "amis_proteges.json").toutes() == []
    assert (dossier / "amis_proteges.json.abime").exists()


# ─── Sélection ────────────────────────────────────────────────────────────────


def test_selection_jamais_arbitraire(sony, registre, protections):
    # Un ami sans date d'acceptation connue n'est pas choisi par ce critère.
    inconnu = sony.nouveau_joueur()
    sony.amis.add(inconnu)
    selection = amis.selectionner(
        sony.amis,
        registre,
        protections,
        COMPTE_DEMO,
        Critere.PLUS_ANCIENS_ACCEPTES,
        100,
    )
    assert inconnu not in {c.compte for c in selection.cibles}
    assert selection.sans_donnee == 1
    assert "Seulement" in selection.avertissements[0]


def test_selection_exclut_les_incertains(sony, registre, protections):
    inconnu = sony.nouveau_joueur()
    sony.amis.add(inconnu)
    protections.ajouter("QuelquUn")
    selection = amis.selectionner(
        sony.amis, registre, protections, COMPTE_DEMO, Critere.PREMIERE_OBSERVATION, 50
    )
    assert selection.incertains == 1
    assert inconnu not in {c.compte for c in selection.cibles}


def test_registre_garde_les_dates(dossier, sony, registre):
    registre.observer(sony.amis, datetime(2026, 5, 1))
    registre.enregistrer()
    relu = Registre(dossier / "amis_connus.json")
    fiche = relu.toutes()[min(sony.amis)]
    assert fiche.accepte_le == datetime(2026, 1, 1)
    assert fiche.premiere_observation == datetime(2026, 1, 1)
    assert fiche.derniere_observation == datetime(2026, 5, 1)
