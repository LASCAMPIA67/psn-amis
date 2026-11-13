"""La fenêtre Qt face au faux Sony, sans écran (plateforme Qt « offscreen »)."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import replace
from datetime import datetime

import pytest
import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from psn_amis import moteur, reglages
from psn_amis.amis import Resultat
from psn_amis.controleur import Controleur, EtatMoteur
from psn_amis.simulation import ConnexionSimulee, SonySimule
from psn_amis.ui import amis as page_amis
from psn_amis.ui.assistant import Assistant, SaisieCode
from psn_amis.ui.commun import Message, PontJournal, VersInterface
from psn_amis.ui.console import MAXIMUM
from psn_amis.ui.fenetre import Fenetre
from tests.conftest import FAUX_CODE


@pytest.fixture(scope="session")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def attendre_qt(condition, delai: float = 15.0) -> bool:
    """Laisse tourner Qt jusqu'à ce que la condition soit vraie."""
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if condition():
            return True
        time.sleep(0.02)
    return False


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
    return sony


@pytest.fixture
def fenetre(application, sony, dossier, monkeypatch):
    depart = replace(moteur.REGLAGES, suppression_pause=3)
    monkeypatch.setattr(moteur, "REGLAGES", depart)
    pont = PontJournal()
    gestionnaire = VersInterface(pont)
    moteur.journal.addHandler(gestionnaire)
    controleur = Controleur(moteur.Suivi(), dossier / "reglages.toml", dossier, depart)
    relances: list[bool] = []
    fenetre = Fenetre(
        controleur, pont, application.windowIcon(), lambda: relances.append(True)
    )
    fenetre.relances = relances  # type: ignore[attr-defined]
    fenetre.show()
    controleur.demarrer()
    assert attendre_qt(lambda: controleur.gestion.vue().liste_complete)
    yield fenetre
    controleur.attendre_arret(10)
    fenetre._quitter_pour_de_bon = True
    fenetre.close()
    moteur.journal.removeHandler(gestionnaire)


def test_ouverture_navigation_et_etats(fenetre):
    assert fenetre.isVisible()
    assert attendre_qt(lambda: "En marche" in fenetre.tableau.statut.text())
    assert fenetre.tableau.amis.text() == "30 / 2000"
    for rang in range(6):
        fenetre.aller(rang)
        fenetre.actualiser()
        assert fenetre.pages.currentIndex() == rang
    assert "MonCompte-PSN" in fenetre.tableau.compte.text()


def test_fermeture(fenetre):
    fenetre.quitter()
    assert not fenetre.isVisible()


def test_pause_et_reprise(fenetre):
    fenetre.pause()
    assert fenetre.controleur.en_pause()
    assert fenetre.action_pause.text() == "Reprendre"
    assert attendre_qt(lambda: "pause" in fenetre.tableau.statut.text().lower())
    fenetre.pause()
    assert not fenetre.controleur.en_pause()


def test_redemarrage_du_moteur_sans_doublon(fenetre):
    controleur = fenetre.controleur
    ancien = controleur._fil
    controleur.redemarrer()
    maximum = 0

    def compter() -> bool:
        nonlocal maximum
        vivants = [f for f in threading.enumerate() if f.name == "moteur-psn-amis"]
        maximum = max(maximum, len(vivants))
        return (
            controleur._fil is not ancien and controleur.etat() is EtatMoteur.EN_MARCHE
        )

    assert attendre_qt(compter)
    assert maximum == 1
    assert not ancien.is_alive()


def test_arret_puis_demarrage(fenetre):
    controleur = fenetre.controleur
    fenetre.arreter_moteur()
    assert attendre_qt(lambda: controleur.etat() is EtatMoteur.ARRETE)
    fenetre.actualiser()
    assert fenetre.action_demarrer.isEnabled()
    assert not fenetre.action_arreter.isEnabled()
    assert controleur.demarrer()
    assert not controleur.demarrer()  # déjà en marche : pas de second moteur


def test_redemarrer_l_application_demande_la_relance(fenetre):
    fenetre.redemarrer_application()
    assert fenetre.relances == [True]


def test_parametres_valides_enregistres(fenetre, dossier):
    page = fenetre.reglages_page
    page.champs["intervalle_verification"].setValue(30)
    page.champs["son"].setChecked(True)
    assert page.enregistrer()
    assert fenetre.controleur.reglages.intervalle_verification == 30
    assert moteur.INTERVALLE_VERIFICATION == 30
    relus, problemes = reglages.charger(dossier / "reglages.toml")
    assert problemes == []
    assert relus.son is True
    assert "appliqué immédiatement" in page.message.text()


def test_parametres_invalides_refuses(fenetre, dossier):
    page = fenetre.reglages_page
    page.champs["nettoyage_seuil"].setValue(1000)
    page.champs["nettoyage_cible"].setValue(1500)
    assert not page.enregistrer()
    assert "Rien n'a été enregistré" in page.message.text()
    assert fenetre.controleur.reglages.nettoyage_seuil == 1900
    assert not (dossier / "reglages.toml").exists()


def test_parametre_qui_demande_un_redemarrage(fenetre):
    page = fenetre.reglages_page
    page.champs["journaux_archives"].setValue(5)
    assert page.enregistrer()
    assert "redémarrage de l'application" in page.message.text()


def test_refus_ami_proche_non_modifiable(fenetre):
    assert not fenetre.reglages_page.champs["refuser_demandes_ami_proche"].isEnabled()


def test_console_recherche_effacement_et_memoire(fenetre, dossier):
    console = fenetre.console
    assert attendre_qt(lambda: "Connecté au compte" in console.en_texte())
    console.recherche.setText("connecté")
    assert all("onnecté" in m.texte for m in console.messages_affiches())
    console.recherche.clear()
    console.effacer_affichage()
    assert console.en_texte() == ""
    moteur.journal.info("Après effacement")
    assert attendre_qt(lambda: "Après effacement" in console.en_texte())
    for numero in range(MAXIMUM + 50):
        console.ajouter(Message(datetime.now(), logging.INFO, "", f"message {numero}"))
    assert len(console._messages) == MAXIMUM


def test_console_jamais_de_code(fenetre):
    moteur.journal.info("Essai %s", FAUX_CODE)
    assert attendre_qt(lambda: "Essai" in fenetre.console.en_texte())
    assert FAUX_CODE not in fenetre.console.en_texte()
    assert "[code masqué]" in fenetre.console.en_texte()


def test_l_interface_ne_bloque_pas_pendant_un_appel_lent(fenetre, sony):
    sony.avant = lambda operation, compte: (
        time.sleep(3) if operation == "liste" else None
    )
    fenetre.controleur.verifier_maintenant()
    time.sleep(0.3)
    declenche: list[float] = []
    debut = time.monotonic()
    QTimer.singleShot(100, lambda: declenche.append(time.monotonic() - debut))
    assert attendre_qt(lambda: bool(declenche), delai=2)
    assert declenche[0] < 1.0
    sony.avant = lambda operation, compte: None


def test_hors_ligne_affiche(fenetre, sony):
    sony.panne("liste", requests.ConnectionError("coupure"), toujours=True)
    fenetre.controleur.verifier_maintenant()
    assert attendre_qt(lambda: "Hors ligne" in fenetre.tableau.statut.text(), delai=20)


def test_suppression_depuis_la_page_amis(fenetre, sony, monkeypatch):
    fenetre.aller(2)
    page = fenetre.amis
    assert attendre_qt(
        lambda: (page.actualiser() or True) and page.modele.rowCount() == 30
    )
    modele = page.modele
    for rang in (0, 1):
        modele.setData(
            modele.index(rang, 0),
            Qt.CheckState.Checked.value,
            Qt.ItemDataRole.CheckStateRole,
        )
    assert page.coches.text() == "2 cochés"
    vus: list[page_amis.Apercu] = []

    def accepter(dialogue):
        vus.append(dialogue)
        assert not dialogue.supprimer.isEnabled()  # tant que la case n'est pas cochée
        dialogue.comprendre.setChecked(True)
        assert dialogue.supprimer.isEnabled()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(page_amis.Apercu, "exec", accepter)
    page._supprimer_coches()
    assert vus[0].supprimer.text() == "Supprimer 2 amis"
    assert attendre_qt(
        lambda: fenetre.controleur.gestion.vue().derniere_operation is not None,
        delai=20,
    )
    assert fenetre.controleur.gestion.vue().derniere_operation.bilan() == {
        Resultat.SUPPRIME: 2
    }
    assert len(sony.amis) == 28


def test_protection_depuis_la_page_amis(fenetre, sony):
    page = fenetre.amis
    pseudo = sony.pseudos[min(sony.amis)]
    page.nouveau_protege.setText(pseudo)
    page._ajouter_protege()
    vue = fenetre.controleur.gestion.vue()
    assert any(p.pseudo.casefold() == pseudo.casefold() for p in vue.proteges)


def test_apercu_sans_rien_supprimable(application):
    from psn_amis.amis import Selection

    dialogue = page_amis.Apercu(Selection("critère", [], 10, 10, 0, 0, 5))
    dialogue.comprendre.setChecked(True)
    assert not dialogue.supprimer.isEnabled()


def test_saisie_du_code_jamais_affichee(application, dossier, sans_coffre, monkeypatch):
    monkeypatch.setattr(
        "psn_amis.ui.assistant._verifier_connexion", lambda: "MonCompte"
    )
    saisie = SaisieCode()
    saisie.champ.setText(FAUX_CODE)
    saisie.enregistrer()
    assert saisie.champ.text() == ""
    assert saisie.enregistre
    assert FAUX_CODE not in saisie.message.text()
    assert attendre_qt(lambda: saisie.pseudo == "MonCompte")


def test_code_invalide_explique(application, dossier, sans_coffre):
    saisie = SaisieCode()
    saisie.champ.setText("abc")
    saisie.enregistrer()
    assert not saisie.enregistre
    assert "pas un code valide" in saisie.message.text()


def test_assistant_applique_les_premiers_reglages(application):
    appliques: list[reglages.Reglages] = []
    assistant = Assistant(reglages.Reglages(), appliques.append)
    assistant.theme.setCurrentIndex(assistant.theme.findData("clair"))
    assistant.accept()
    assert appliques[0].theme == "clair"
    assert appliques[0].verifier_mises_a_jour is True


def test_quitter_pendant_une_suppression_demande_confirmation(
    fenetre, sony, monkeypatch
):
    monkeypatch.setattr(
        moteur, "REGLAGES", replace(moteur.REGLAGES, suppression_pause=30)
    )
    gestion = fenetre.controleur.gestion
    gestion.demander_suppression(gestion.selection_manuelle(sorted(sony.amis)[:3]))
    fenetre.controleur.verifier_maintenant()
    assert attendre_qt(lambda: gestion.vue().operation is not None)
    questions: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: questions.append(a[1]) or QMessageBox.StandardButton.No,
    )
    fenetre.close()
    assert questions == ["Quitter PSN Amis"]
    assert fenetre.isVisible()
    gestion.annuler()


def test_nettoyage_coupe_par_le_moteur_visible_dans_la_fenetre(fenetre):
    controleur = fenetre.controleur
    automatique, _ = reglages.modifier(
        controleur.reglages, nettoyage_mode="automatique"
    )
    assert controleur.appliquer(automatique).enregistre
    fenetre.reglages_page.recharger()
    # Comme le moteur quand il détecte un cycle : depuis un autre fil que l'interface.
    fil = threading.Thread(target=controleur._couper_nettoyage, args=("cycle",))
    fil.start()
    fil.join(5)
    assert controleur.reglages.nettoyage_mode == "manuel"
    champ = fenetre.reglages_page.champs["nettoyage_mode"]
    assert attendre_qt(lambda: champ.currentData() == "manuel")
