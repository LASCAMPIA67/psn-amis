"""Refonte visuelle : thèmes, composants, animations, navigation et géométrie.

Ces tests ne remplacent pas une relecture humaine : ils vérifient ce qui peut l'être
automatiquement (thèmes complets et lisibles, application et persistance du thème,
boutons jamais tronqués, états vides, captures non vides).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QAbstractButton, QApplication, QScrollArea, QWidget

from psn_amis import reglages
from psn_amis.controleur import Controleur
from psn_amis.ui import composants, icones, theme
from psn_amis.ui.composants import Animations, Interrupteur
from tests.test_interface import (  # noqa: F401 (fixtures partagées)
    application,
    attendre_qt,
    fenetre,
    sony,
)

THEMES = [cle for cle in theme.ORDRE if cle != "systeme"]


# ─── Thèmes ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("cle", THEMES)
def test_theme_complet_et_lisible(cle):
    p = theme.PALETTES[cle]
    for champ in theme.jetons(p).values():
        if isinstance(champ, str) and champ.startswith("#"):
            assert QColor(champ).isValid()
    # Contrastes WCAG 2.1 : texte 4,5:1, éléments graphiques et états 3:1.
    assert theme.contraste(p.texte, p.fond) >= 4.5
    assert theme.contraste(p.texte, p.surface) >= 4.5
    assert theme.contraste(p.discret, p.surface) >= 4.5
    assert theme.contraste(p.discret, p.fond_lateral) >= 4.5
    assert theme.contraste(p.sur_accent, p.accent) >= 4.5
    assert theme.contraste(p.fond, p.erreur) >= 4.5
    for etat in (p.accent, p.succes, p.attention, p.erreur, p.info, p.tertiaire):
        assert theme.contraste(etat, p.surface) >= 3


@pytest.mark.parametrize("cle", [*THEMES, "systeme"])
def test_feuille_de_style_entierement_resolue(application, cle):
    feuille = theme.feuille_de_style(cle)
    assert "%(" not in feuille
    assert feuille.count("{") == feuille.count("}")


def test_themes_vraiment_differents():
    fonds = {theme.PALETTES[c].fond for c in THEMES}
    accents = {theme.PALETTES[c].accent for c in THEMES}
    surfaces = {theme.PALETTES[c].surface for c in THEMES}
    assert len(fonds) == len(accents) == len(surfaces) == len(THEMES)
    assert any(not theme.PALETTES[c].sombre for c in THEMES)


def test_theme_systeme_suit_windows(monkeypatch):
    monkeypatch.setattr(theme, "windows_en_sombre", lambda: True)
    assert theme.resoudre("systeme") == "graphite"
    monkeypatch.setattr(theme, "windows_en_sombre", lambda: False)
    assert theme.resoudre("systeme") == "clair"
    assert theme.resoudre("inconnu") == "graphite"


def test_chaque_theme_a_un_nom_et_une_description():
    assert set(theme.ORDRE) == set(reglages.THEMES)
    for cle in theme.ORDRE:
        assert theme.NOMS[cle]
        assert theme.DESCRIPTIONS[cle]


# ─── Réglages : migration des anciens thèmes ─────────────────────────────────


@pytest.mark.parametrize(
    ("ancien", "nouveau"), [("sombre", "graphite"), ("doux", "minuit")]
)
def test_anciens_noms_de_themes_repris(tmp_path, ancien, nouveau):
    fichier = tmp_path / "reglages.toml"
    fichier.write_text(f'version_reglages = 2\ntheme = "{ancien}"\n', encoding="utf-8")
    assert reglages.mettre_a_jour_le_format(fichier)
    lus, problemes = reglages.charger(fichier)
    assert problemes == []
    assert lus.theme == nouveau
    # Sauvegarde de l'ancien fichier avant la réécriture.
    assert 'theme = "' + ancien in (tmp_path / "reglages.v2.toml").read_text(
        encoding="utf-8"
    )


def test_reglage_des_animations_valide():
    nouveaux, problemes = reglages.modifier(reglages.Reglages(), animations="coupees")
    assert problemes == []
    assert nouveaux.animations == "coupees"
    _, problemes = reglages.modifier(reglages.Reglages(), animations="toujours")
    assert problemes


# ─── Icônes et composants ─────────────────────────────────────────────────────


@pytest.mark.parametrize("nom", sorted(icones.TRACES))
def test_chaque_icone_se_dessine(application, nom):
    image = icones.pixmap(nom, "#ffffff", 24, 2.0).toImage()
    assert image.width() == 48
    opaques = sum(
        image.pixelColor(x, y).alpha() > 0
        for x in range(0, 48, 2)
        for y in range(0, 48, 2)
    )
    assert opaques > 10


def test_icone_inconnue_refusee():
    with pytest.raises(KeyError):
        icones.svg("absente", "#000000")


def test_interrupteur(application):
    interrupteur = Interrupteur("Option")
    assert not interrupteur.isChecked()
    interrupteur.setChecked(True)
    assert interrupteur.isChecked()
    assert interrupteur.position == 1.0
    interrupteur.click()
    assert not interrupteur.isChecked()
    assert interrupteur.sizeHint().width() > Interrupteur.LARGEUR + 20
    # Un clic n'importe où sur le texte bascule aussi.
    assert interrupteur.hitButton(QPoint(interrupteur.sizeHint().width() - 4, 5))


def test_animations_coupees_affichage_instantane(application, monkeypatch):
    Animations.definir("coupees")
    try:
        widget = QWidget()
        composants.fondu_entrant(widget)
        assert widget.graphicsEffect() is None
    finally:
        Animations.definir("activees")
    monkeypatch.setattr(composants.systeme, "animations_windows", lambda: False)
    Animations.definir("systeme")
    assert not Animations.actives()
    Animations.definir("activees")
    assert Animations.actives()


# ─── Fenêtre : thème en direct, persistance, navigation ──────────────────────


def test_changement_de_theme_immediat_et_enregistre(fenetre, dossier):
    application = QApplication.instance()
    page = fenetre.reglages_page
    page.galerie.apercus["emeraude"].click()
    assert fenetre.controleur.reglages.theme == "emeraude"
    assert application.palette().window().color() == QColor(
        theme.PALETTES["emeraude"].fond
    )
    assert theme.PALETTES["emeraude"].accent in application.styleSheet()
    assert page.galerie.valeur() == "emeraude"
    # Notification de confirmation.
    assert any(
        t.titre.text() == "Thème appliqué" for t in fenetre.notifications.actives()
    )
    # Gardé au redémarrage : relu dans reglages.toml.
    relus, _ = reglages.charger(dossier / "reglages.toml")
    assert relus.theme == "emeraude"
    nouveau = Controleur(
        fenetre.controleur.suivi, dossier / "reglages.toml", dossier, relus
    )
    assert nouveau.reglages.theme == "emeraude"


@pytest.mark.parametrize("cle", [*THEMES, "systeme"])
def test_tous_les_themes_s_appliquent(fenetre, cle):
    fenetre.reglages_page.galerie.apercus[cle].click()
    assert fenetre.controleur.reglages.theme == cle
    attendu = theme.palette(cle)
    assert QApplication.instance().palette().window().color() == QColor(attendu.fond)


def test_navigation_par_boutons_et_raccourcis(fenetre):
    Animations.definir("coupees")
    try:
        for rang, (nom, _, _, sous_titre) in enumerate(composants_pages()):
            fenetre._boutons_nav[rang].click()
            assert fenetre.pages.currentIndex() == rang
            assert fenetre.titre_page.text() == nom
            assert fenetre.sous_titre_page.text() == sous_titre
            assert fenetre._boutons_nav[rang].isChecked()
    finally:
        Animations.definir("activees")


def composants_pages():
    from psn_amis.ui.fenetre import PAGES

    return PAGES


def test_etats_vides_explicatifs(fenetre):
    fenetre.aller(3)
    fenetre.actualiser()
    assert fenetre.demandes.vide.isVisibleTo(fenetre)
    assert "Aucune demande" in fenetre.demandes.vide.titre.text()


def test_actions_critiques_identifiables(fenetre):
    assert fenetre.amis.supprimer_coches.objectName() == "danger"
    urgence = [
        b
        for b in fenetre.reglages_page.findChildren(QAbstractButton)
        if "Arrêt d'urgence" in b.text()
    ]
    assert urgence
    assert urgence[0].objectName() == "secondaire_danger"


@pytest.mark.parametrize("taille", [(900, 600), (1280, 800), (1920, 1080)])
def test_aucun_bouton_tronque(fenetre, taille):
    """À la taille minimale et en Full HD, chaque bouton visible a sa place."""
    Animations.definir("coupees")
    fenetre.resize(*taille)
    try:
        for rang in range(6):
            fenetre.aller(rang)
            for _ in range(3):
                QApplication.processEvents()
            page = fenetre.pages.currentWidget()
            # Aucun défilement horizontal : tout tient dans la largeur.
            for zone in page.findChildren(QScrollArea):
                if zone.isVisibleTo(fenetre) and zone.widgetResizable():
                    assert zone.horizontalScrollBar().maximum() == 0, (rang, taille)
            # Commandes de l'en-tête : en entier, ou icône seule en fenêtre étroite.
            for bouton in fenetre._boutons_actions.values():
                if bouton.isVisibleTo(fenetre):
                    assert bouton.width() >= bouton.minimumSizeHint().width() - 1
                    if taille[0] < fenetre.LARGEUR_COMPACTE:
                        assert (
                            bouton.toolButtonStyle()
                            == Qt.ToolButtonStyle.ToolButtonIconOnly
                        )
                        assert bouton.toolTip()
            for bouton in page.findChildren(QAbstractButton):
                if not bouton.isVisibleTo(fenetre) or not bouton.text():
                    continue
                if bouton.metaObject().className() in ("ApercuTheme", "QCheckBox"):
                    continue
                assert bouton.width() >= bouton.minimumSizeHint().width() - 1, (
                    rang,
                    bouton.text(),
                    bouton.width(),
                    bouton.minimumSizeHint().width(),
                )
    finally:
        Animations.definir("activees")


@pytest.mark.parametrize("cle", THEMES)
def test_captures_de_reference_non_vides(fenetre, tmp_path, cle):
    """Une capture par page et par thème (gardée dans le dossier du test), non vide."""
    Animations.definir("coupees")
    try:
        fenetre.reglages_page.galerie.apercus[cle].click()
        fenetre.resize(1280, 800)
        for rang in range(6):
            fenetre.aller(rang)
            QApplication.processEvents()
            image: QImage = fenetre.grab().toImage()
            image.save(str(tmp_path / f"{cle}-{rang}.png"))
            couleurs = {
                image.pixelColor(x, y).name()
                for x in range(0, image.width(), 40)
                for y in range(0, image.height(), 40)
            }
            assert len(couleurs) > 4
            # Le fond de la fenêtre est bien celui du thème.
            fond = image.pixelColor(image.width() - 6, image.height() // 2).name()
            assert fond in {theme.PALETTES[cle].fond, theme.PALETTES[cle].surface}
    finally:
        Animations.definir("activees")


def test_focus_visible_au_clavier(fenetre):
    bouton = fenetre._boutons_nav[2]
    assert bouton.focusPolicy() & Qt.FocusPolicy.TabFocus
    assert "QPushButton#nav:focus" in QApplication.instance().styleSheet()
