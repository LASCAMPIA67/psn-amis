"""Non-régression des anomalies de la recette utilisateur du 2026-11-13 (AN1 à AN17).

Chaque test renvoie au numéro du registre des anomalies (PROGRESSION.local.md).
Tout se passe avec le faux Sony : aucune requête réelle, aucun vrai compte.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWizard

from psn_amis import moteur, reglages
from psn_amis.controleur import EtatMoteur
from psn_amis.gestion import Gestion
from psn_amis.simulation import COMPTE_DEMO
from psn_amis.ui import composants
from psn_amis.ui.composants import Animations
from psn_amis.ui.fenetre import AZERTY, PAGES
from tests.conftest import attendre_que
from tests.test_interface import (  # noqa: F401 (fixtures partagées)
    application,
    attendre_qt,
    fenetre,
    sony,
)


def toasts(fenetre) -> list[str]:
    return [t.titre.text() for t in fenetre.notifications.actives()]


# ─── AN4 : raccourcis, un par rubrique, y compris AZERTY ─────────────────────


def test_an4_chaque_raccourci_mene_a_sa_rubrique(fenetre):
    Animations.definir("coupees")
    try:
        actions = {a.text(): a for a in fenetre.actions()}
        for rang, (nom, raccourci, _, _) in enumerate(PAGES):
            action = actions[nom]
            sequences = [s.toString() for s in action.shortcuts()]
            assert raccourci in sequences
            assert len(action.shortcuts()) == 2  # chiffre et touche AZERTY
            fenetre.aller(0 if rang else 1)
            action.trigger()
            assert fenetre.pages.currentIndex() == rang, nom
    finally:
        Animations.definir("activees")


@pytest.mark.parametrize("rang", range(6))
def test_an4_touches_azerty_au_clavier(fenetre, rang):
    """Ctrl + touche de la rangée supérieure AZERTY (sans Maj), même depuis un champ."""
    Animations.definir("coupees")
    try:
        fenetre.activateWindow()
        fenetre.aller(3 if rang != 3 else 0)
        fenetre.amis.recherche.setFocus()
        QTest.keyClick(fenetre, AZERTY[rang], Qt.KeyboardModifier.ControlModifier)
        QApplication.processEvents()
        assert fenetre.pages.currentIndex() == rang
    finally:
        Animations.definir("activees")


def test_an4_raccourcis_existants_gardes(fenetre):
    sequences = {s.toString() for a in fenetre.actions() for s in a.shortcuts()}
    assert {"Ctrl+R", "Ctrl+Q", "Ctrl+P", "F5"} <= sequences


# ─── AN3 : « Listes noire et blanche » ouvre Paramètres › Demandes ───────────


def test_an3_listes_ouvrent_l_onglet_demandes(fenetre):
    fenetre.demandes.findChild(type(fenetre.amis.supprimer_coches), "")  # page prête
    fenetre.ouvrir_listes()
    assert fenetre.pages.currentIndex() == 4
    onglets = fenetre.reglages_page.onglets
    assert onglets.tabToolTip(onglets.currentIndex()) == "Demandes"


# ─── AN1 / AN2 : protéger depuis la sélection, liste des protégés ────────────


def page_prete(fenetre):
    fenetre.aller(2)
    page = fenetre.amis
    assert attendre_qt(
        lambda: (page.actualiser() or True) and page.modele.rowCount() == 30
    )
    return page


def test_an1_proteger_les_amis_coches(fenetre, sony):
    page = page_prete(fenetre)
    for rang in (0, 1):
        page.modele.setData(
            page.modele.index(rang, 0),
            Qt.CheckState.Checked.value,
            Qt.ItemDataRole.CheckStateRole,
        )
    comptes = {page.modele.lignes[0].compte, page.modele.lignes[1].compte}
    assert page.bouton_proteger.isEnabled()
    page.bouton_proteger.click()
    proteges = {p.compte for p in fenetre.controleur.gestion.vue().proteges}
    assert comptes <= proteges
    assert "2 amis protégés" in toasts(fenetre)
    # Une seconde fois : rien de nouveau, et c'est dit clairement.
    page.bouton_proteger.click()
    assert "Aucune nouvelle protection" in toasts(fenetre)


def test_an1_proteger_la_selection_sans_case(fenetre):
    page = page_prete(fenetre)
    assert not page.bouton_proteger.isEnabled()  # rien de choisi : bouton inactif
    index = page.proxy.index(3, 0)
    page.table.selectionModel().select(
        index,
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    compte = page.modele.lignes[page.proxy.mapToSource(index).row()].compte
    assert page.bouton_proteger.isEnabled()
    page.bouton_proteger.click()
    assert compte in {p.compte for p in fenetre.controleur.gestion.vue().proteges}
    page.bouton_deproteger.click()
    assert compte not in {p.compte for p in fenetre.controleur.gestion.vue().proteges}
    assert "1 protection retirée" in toasts(fenetre)


def test_an1_coches_gardees_malgre_filtre_et_tri(fenetre):
    page = page_prete(fenetre)
    page.modele.setData(
        page.modele.index(5, 0),
        Qt.CheckState.Checked.value,
        Qt.ItemDataRole.CheckStateRole,
    )
    compte = page.modele.lignes[5].compte
    page.recherche.setText("zzz-introuvable")
    page.table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
    page.bouton_proteger.click()
    proteges = {p.compte for p in fenetre.controleur.gestion.vue().proteges}
    # Seul l'ami coché (par son identifiant de compte) est protégé.
    assert proteges == {compte}


def test_an2_retirer_un_protege_selectionne(fenetre, sony):
    page = page_prete(fenetre)
    assert not page.bouton_retirer.isEnabled()
    # Message « aucun ami protégé » : ni sélectionnable ni retirable.
    assert page.liste_proteges.item(0).flags() == Qt.ItemFlag.NoItemFlags
    fenetre.controleur.gestion.proteger("Ami", min(sony.amis))
    page.actualiser()
    page.liste_proteges.setCurrentRow(0)
    assert page.liste_proteges.currentItem().isSelected()
    assert page.bouton_retirer.isEnabled()
    page.bouton_retirer.click()
    assert fenetre.controleur.gestion.vue().proteges == ()
    assert "Protection retirée" in toasts(fenetre)
    assert "QListWidget::item:selected" in QApplication.instance().styleSheet()


# ─── AN5 : retour de « Vérifier maintenant » ─────────────────────────────────


def test_an5_verifier_maintenant_visible(fenetre):
    assert attendre_qt(fenetre.action_verifier.isEnabled)
    fenetre.action_verifier.trigger()
    assert "Vérification lancée" in toasts(fenetre)
    fenetre.controleur.attendre_arret(10)
    fenetre.verifier_maintenant()
    assert "Moteur arrêté" in toasts(fenetre)


# ─── AN6 / AN7 : états et compteurs ──────────────────────────────────────────


def test_an6_moteur_arrete_jamais_acceptation_active(fenetre):
    assert attendre_qt(lambda: "en cours" in fenetre.tableau.automatisation._texte)
    fenetre.controleur.attendre_arret(10)
    fenetre.aller(0)
    fenetre.actualiser()
    assert fenetre.tableau.automatisation._texte == "Moteur arrêté : aucune acceptation"
    assert "non vérifiées" in fenetre.tableau.carte_attente.detail.text()


def test_an6_pause_et_reglage_coupe(fenetre):
    fenetre.pause()
    fenetre.aller(0)
    assert attendre_qt(
        lambda: fenetre.tableau.automatisation._texte == "Acceptations en pause"
    )
    fenetre.pause()


def test_an7_libelles_des_compteurs(fenetre):
    fenetre.aller(0)
    fenetre.actualiser()
    detail = fenetre.tableau.carte_acceptees.detail.text()
    assert "depuis l'ouverture de PSN Amis" in detail
    assert "depuis l'ouverture" in fenetre.tableau.carte_supprimes.detail.text()


def test_an7_suppressions_du_jour_relues_au_demarrage(dossier):
    maintenant = datetime.now()
    hier = maintenant.replace(year=maintenant.year - 1)
    (dossier / "journal.txt").write_text(
        f"{maintenant:%Y-%m-%d %H:%M:%S}  Ami supprimé par PSN Amis : Alice\n"
        f"{hier:%Y-%m-%d %H:%M:%S}  Ami supprimé par PSN Amis : Bob\n",
        encoding="utf-8",
    )
    suivi = moteur.Suivi(
        moteur.ajouts_recents_dans_journal(),
        moteur.retraits_recents_dans_journal(),
        moteur.suppressions_recentes_dans_journal(),
    )
    instant = suivi.instantane()
    assert instant.supprimes_jour == 1
    assert instant.supprimes_session == 0


# ─── AN8 : « Connexion PSN nécessaire » quand aucun code n'existe ────────────


def test_an8_aucun_code_connexion_requise(dossier, monkeypatch, isolement):
    def aucun():
        raise moteur.AucunCode("aucun code enregistré (test).")

    monkeypatch.setattr(moteur, "lire_npsso", aucun)
    suivi = moteur.Suivi()
    assert moteur.connecter(suivi, moteur.Commandes(), attendre=False) is None
    assert suivi.instantane().statut is moteur.Statut.CONNEXION_REQUISE
    # Pas de bulle Windows alarmante au premier lancement.
    assert isolement.bulles == []


def test_an8_code_refuse_reste_une_erreur(dossier, monkeypatch, isolement):
    def refuse():
        raise moteur.ProblemeNpsso("le code collé n'a pas le bon format.")

    monkeypatch.setattr(moteur, "lire_npsso", refuse)
    suivi = moteur.Suivi()
    moteur.connecter(suivi, moteur.Commandes(), attendre=False)
    assert suivi.instantane().statut is moteur.Statut.CODE_NPSSO
    assert len(isolement.bulles) == 1


# ─── AN9 / AN10 : boutons contextuels des paramètres, estimation ─────────────


def test_an9_boutons_selon_les_modifications(fenetre):
    page = fenetre.reglages_page
    page.recharger()
    assert not page.bouton_enregistrer.isVisibleTo(page)
    assert not page.bouton_annuler.isVisibleTo(page)
    # Les essais tournent avec un intervalle d'une seconde : différent du défaut.
    assert page.bouton_defaut.isVisibleTo(page)
    page.champs["intervalle_verification"].setValue(40)
    assert page.bouton_enregistrer.isVisibleTo(page)
    assert page.bouton_annuler.isVisibleTo(page)
    assert page.bouton_defaut.isVisibleTo(page)
    assert "•" in page.onglets.tabText(page._groupe_onglet["Moteur"])
    assert page.enregistrer()
    assert not page.bouton_enregistrer.isVisibleTo(page)
    assert not page.bouton_annuler.isVisibleTo(page)
    assert page.bouton_defaut.isVisibleTo(page)  # 40 ≠ défaut
    page.valeurs_par_defaut()
    assert page.bouton_enregistrer.isVisibleTo(page)
    page.recharger()


def test_an9_le_theme_ne_cree_pas_de_modification_fictive(fenetre):
    page = fenetre.reglages_page
    page.recharger()
    page.galerie.apercus["minuit"].click()
    assert fenetre.controleur.reglages.theme == "minuit"
    assert not page.a_des_modifications()
    assert not page.bouton_enregistrer.isVisibleTo(page)


def test_an9_aucune_perte_silencieuse(fenetre):
    """Un réglage changé ailleurs (page Demandes) ne touche pas le formulaire en cours."""
    page = fenetre.reglages_page
    page.recharger()
    page.champs["intervalle_verification"].setValue(45)
    fenetre._changer_reglage("acceptation_auto", False)
    assert page.champs["intervalle_verification"].value() == 45
    assert page.champs["acceptation_auto"].isChecked() is False
    assert page.a_des_modifications()
    # Fermer avec des modifications : confirmation demandée.
    page.recharger()


def test_an9_fermeture_avec_modifications_confirmee(fenetre, dialogues):
    page = fenetre.reglages_page
    page.champs["intervalle_verification"].setValue(50)
    fenetre.close()
    assert dialogues[-1][0] == "Paramètres non enregistrés"
    assert fenetre.isVisible()  # « Annuler » : la fenêtre reste
    page.recharger()


def test_an10_estimation_calculee(fenetre):
    page = fenetre.reglages_page
    page.champs["intervalle_verification"].setValue(30)
    assert "Avec 30 s : environ 4.0 requête(s)" in page.estimation.text()
    page.champs["intervalle_verification"].setValue(15)
    assert "Avec 15 s : environ 8.0" in page.estimation.text()
    assert "15" not in reglages.info("intervalle_verification")["description"]
    page.recharger()


# ─── AN11 / AN12 : assistant et dialogues ────────────────────────────────────


def test_an11_assistant_sans_fleche_d_en_tete(application):
    from psn_amis.ui.assistant import Assistant

    assistant = Assistant(reglages.Reglages(), lambda r: None)
    assert assistant.wizardStyle() == QWizard.WizardStyle.ClassicStyle
    assert assistant.testOption(QWizard.WizardOption.NoBackButtonOnStartPage)


def test_an12_confirmation_destructrice(application):
    dialogue = composants.Dialogue(
        None, "Supprimer ?", "Texte", "attention", "Supprimer", "Annuler", danger=True
    )
    assert dialogue.bouton_annuler.isDefault()
    assert not dialogue.bouton_ok.isDefault()
    assert dialogue.bouton_ok.objectName() == "danger"


def test_an12_confirmer_refuse_par_defaut(application, dialogues):
    assert composants.confirmer(None, "Titre", "Texte") is False
    assert dialogues == [("Titre", "Texte")]


# ─── AN13 / AN14 : petites et très grandes fenêtres ──────────────────────────


def test_an13_entete_reduit_progressivement(fenetre):
    fenetre.resize(1100, 700)
    QApplication.processEvents()
    boutons = fenetre._boutons_actions
    icone = Qt.ToolButtonStyle.ToolButtonIconOnly
    assert boutons["action_verifier"].toolButtonStyle() == icone
    assert boutons["action_pause"].toolButtonStyle() != icone
    fenetre.resize(900, 600)
    QApplication.processEvents()
    for bouton in boutons.values():
        assert bouton.toolButtonStyle() == icone
        assert bouton.accessibleName()
        assert bouton.toolTip()


def test_an13_onglets_courts(fenetre):
    onglets = fenetre.reglages_page.onglets
    titres = [onglets.tabText(i) for i in range(onglets.count())]
    assert titres == [
        "Apparence",
        "Moteur",
        "Demandes",
        "Amis",
        "Nettoyage",
        "Application",
    ]
    assert onglets.tabBar().usesScrollButtons()


def test_an14_largeur_de_lecture_limitee(fenetre):
    fenetre.resize(2560, 1400)
    fenetre.aller(0)
    QApplication.processEvents()
    # Le test n'a de sens que si la fenêtre est vraiment plus large que la limite.
    assert fenetre.tableau.parentWidget().width() > fenetre.LARGEUR_CONTENU + 200
    assert fenetre.tableau.width() == fenetre.LARGEUR_CONTENU
    fenetre.aller(2)
    QApplication.processEvents()
    assert fenetre.amis.width() > fenetre.LARGEUR_CONTENU  # Amis profite de la place


# ─── AN15 : activité lisible ─────────────────────────────────────────────────


def test_an15_retrait_suspendu(fenetre):
    from psn_amis.ui.commun import Message

    ligne = fenetre.console._ligne(
        Message(datetime.now(), 30, "", "Un avertissement long " * 20)
    )
    assert "text-indent:-" in ligne
    assert "line-height" in ligne


# ─── AN16 (P0) : aucun chemin ne supprime un ami protégé ─────────────────────


def test_an16_nettoyage_automatique_epargne_les_proteges(dossier):
    sony_local = __import__("psn_amis.simulation", fromlist=["SonySimule"]).SonySimule(
        nombre_amis=12
    )
    regles = replace(
        reglages.Reglages(),
        nettoyage_mode="automatique",
        nettoyage_seuil=10,
        nettoyage_cible=2,
        nettoyage_max_par_cycle=10,
        nettoyage_critere="premiere_observation",
        suppression_pause=3,
    )
    gestion = Gestion(dossier, lambda: regles)
    gestion.connecte(COMPTE_DEMO, "moi")
    gestion.observer(set(sony_local.amis), complete=True)
    proteges = sorted(sony_local.amis)[:4]
    for compte in proteges:
        gestion.proteger(sony_local.pseudos[compte], compte)
    from psn_amis.gestion import Outils

    gestion._nettoyage(
        Outils(client=sony_local, arret=lambda: False, rafraichir=lambda: None)
    )
    operation = gestion.vue().derniere_operation
    assert operation is not None
    assert operation.origine == "nettoyage"
    assert all(compte in sony_local.amis for compte in proteges)
    assert all(c.compte not in proteges for c in operation.cibles)


def test_an16_liste_incomplete_aucun_nettoyage(dossier):
    regles = replace(
        reglages.Reglages(),
        nettoyage_mode="automatique",
        nettoyage_seuil=1,
        nettoyage_cible=0,
    )
    gestion = Gestion(dossier, lambda: regles)
    gestion.connecte(COMPTE_DEMO, "moi")
    gestion.observer({"1", "2", "3"}, complete=False)
    from psn_amis.gestion import Outils

    appels: list[str] = []

    class Client:
        def __getattr__(self, nom):
            appels.append(nom)
            raise AssertionError("aucune requête ne doit partir")

    gestion._nettoyage(Outils(client=Client(), arret=lambda: False))
    assert gestion.vue().derniere_operation is None
    assert appels == []


def test_an16_proposition_assistee_recalculee_sans_protege(fenetre, sony, monkeypatch):
    """Un ami protégé après la proposition n'est pas dans la confirmation."""
    gestion = fenetre.controleur.gestion
    page = fenetre.amis
    from psn_amis.amis import Cible, Selection

    cibles = [Cible(c, sony.pseudos[c]) for c in sorted(sony.amis)[:3]]
    gestion._proposition = Selection("critère", cibles, 30, 0, 0, 0, 3)
    gestion.proteger(cibles[0].pseudo, cibles[0].compte)
    confirmees = []
    monkeypatch.setattr(
        page, "confirmer", lambda selection, origine: confirmees.append(selection)
    )
    page._voir_proposition()
    assert [c.compte for c in confirmees[0].cibles] == [c.compte for c in cibles[1:]]


def test_an16_moteur_arrete_rien_ne_part(fenetre, sony):
    fenetre.controleur.attendre_arret(10)
    assert fenetre.controleur.etat() is EtatMoteur.ARRETE
    avant = list(sony.appels)
    gestion = fenetre.controleur.gestion
    gestion.demander_suppression(gestion.selection_manuelle(sorted(sony.amis)[:2]))
    assert not attendre_que(lambda: len(sony.appels) > len(avant), delai=2)
    gestion.annuler()


def test_an11_assistant_ne_revient_pas(dossier, isolement):
    from psn_amis import app
    from psn_amis.__main__ import analyser

    choix = analyser([])
    assert app.proposer_assistant(choix)
    app.noter_assistant_vu()
    assert not app.proposer_assistant(choix)
    assert not app.proposer_assistant(analyser(["--demo"]))


def test_an12_aucune_fenetre_native_dans_les_pages():
    from pathlib import Path

    import psn_amis.ui as paquet

    for fichier in Path(paquet.__file__).parent.glob("*.py"):
        if fichier.name == "theme.py":  # feuille de style seulement
            continue
        assert "QMessageBox" not in fichier.read_text(encoding="utf-8"), fichier.name


def test_an17_console_rich_couvre_tous_les_statuts():
    from psn_amis.tableau_de_bord import APPARENCE
    from psn_amis.ui.commun import STATUTS

    assert set(APPARENCE) == set(moteur.Statut)
    assert set(STATUTS) == set(moteur.Statut)


def test_an15_defilement_garde_et_memoire_bornee(fenetre):
    from psn_amis.ui.commun import Message

    console = fenetre.console
    fenetre.aller(1)
    for rang in range(300):
        console.ajouter(Message(datetime.now(), 20, "", f"Ligne d'essai numéro {rang}"))
    QApplication.processEvents()
    barre = console.texte.verticalScrollBar()
    barre.setValue(0)  # l'utilisateur remonte lire le début
    console.ajouter(Message(datetime.now(), 20, "", "Nouvelle ligne"))
    QApplication.processEvents()
    assert barre.value() == 0
    assert console.texte.document().maximumBlockCount() > 0
