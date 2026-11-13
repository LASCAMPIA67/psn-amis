"""Tableau de bord en couleur de PSN Amis, dans la console Windows.

Il lit l'état du moteur (moteur.Suivi) et redessine l'écran deux à quatre fois par
seconde. La mise en page suit la taille de la fenêtre, qui change aussi avec le zoom
(Ctrl+molette) : grandes cartes, cartes compactes, puis un simple résumé quand la
place manque. Les messages d'activité sont toujours affichés en entier.

Touches : P pause ou reprise, 1 2 3 pause de 5, 10 ou 30 min, V vérifier maintenant,
J ouvrir le journal, C changer le code npsso, H aide, S bip à chaque ajout,
flèches pour faire défiler l'activité, Q deux fois pour quitter (Ctrl+C quitte aussi).
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import math
import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.layout import Layout
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from psn_amis import moteur, notifications
from psn_amis.moteur import Commandes, Evenement, Instantane, Statut, Suivi, journal

# ─── Apparence ────────────────────────────────────────────────────────────────
# Trois jeux de couleurs, choisis dans reglages.toml (réglage « theme »).
THEMES: dict[str, Theme] = {
    "sombre": Theme(
        {
            "accent": "bold #3d9bff",
            "titre": "bold #f2f5fa",
            "discret": "#8a93a6",
            "info": "#8ec5ff",
            "succes": "bold #34d27b",
            "alerte": "bold #ffc24b",
            "erreur": "bold #ff5d5d",
            "fond_barre": "#2a3142",
            "fond_entete": "on #0f2747",
            "touche": "bold #0b1220 on #3d9bff",
            "nouveau": "bold #0b1220 on #34d27b",
            "retrait": "bold #ff8f6b",
        }
    ),
    # Couleurs moins vives, plus reposantes pour un affichage permanent.
    "doux": Theme(
        {
            "accent": "bold #7aa2c8",
            "titre": "bold #e6e9ef",
            "discret": "#7d8594",
            "info": "#a9c4de",
            "succes": "bold #8cc7a1",
            "alerte": "bold #e3c27a",
            "erreur": "bold #e08a8a",
            "fond_barre": "#2a3040",
            "fond_entete": "on #1d2a3a",
            "touche": "bold #10151f on #7aa2c8",
            "nouveau": "bold #10151f on #8cc7a1",
            "retrait": "bold #e0a48c",
        }
    ),
    # Palette d'Okabe et Ito : bleu, jaune, orange et violet, faciles à distinguer
    # sans le rouge et le vert.
    "daltonien": Theme(
        {
            "accent": "bold #b8c4ff",
            "titre": "bold #f2f5fa",
            "discret": "#9097a6",
            "info": "#a6d4f2",
            "succes": "bold #56b4e9",
            "alerte": "bold #f0e442",
            "erreur": "bold #e69f00",
            "fond_barre": "#2a3142",
            "fond_entete": "on #1f2547",
            "touche": "bold #0b1220 on #b8c4ff",
            "nouveau": "bold #0b1220 on #56b4e9",
            "retrait": "bold #cc79a7",
        }
    ),
}
THEME = THEMES["sombre"]
# Thèmes de la fenêtre → thème de la console (qui n'en a que trois).
THEME_CONSOLE = {
    "graphite": "sombre",
    "minuit": "doux",
    "emeraude": "doux",
    "amethyste": "sombre",
    "clair": "sombre",
    "daltonien": "daltonien",
    "systeme": "sombre",
}

# Pour chaque statut : symbole, libellé, couleur.
APPARENCE: dict[Statut, tuple[str, str, str]] = {
    Statut.DEMARRAGE: ("◌", "DÉMARRAGE", "info"),
    Statut.CONNEXION: ("↻", "CONNEXION À SONY", "info"),
    Statut.EN_MARCHE: ("●", "EN MARCHE", "succes"),
    Statut.VERIFICATION: ("●", "EN MARCHE", "succes"),
    Statut.PAUSE: ("‖", "EN PAUSE", "alerte"),
    Statut.HORS_LIGNE: ("▲", "HORS LIGNE", "alerte"),
    Statut.ATTENTE: ("▲", "EN ATTENTE", "alerte"),
    Statut.CODE_NPSSO: ("▲", "CODE NPSSO À CHANGER", "erreur"),
    Statut.LISTE_PLEINE: ("■", "LISTE D'AMIS PLEINE", "erreur"),
    Statut.ERREUR: ("▲", "ERREUR", "erreur"),
}
STATUTS_ANIMES = (Statut.DEMARRAGE, Statut.CONNEXION, Statut.VERIFICATION)

# Gros chiffres sur 3 lignes, dessinés avec des traits de tableau.
GROS_CHIFFRES = {
    "0": ("┏━┓", "┃ ┃", "┗━┛"),
    "1": (" ╻ ", " ┃ ", " ╹ "),
    "2": ("╺━┓", "┏━┛", "┗━╸"),
    "3": ("╺━┓", " ━┫", "╺━┛"),
    "4": ("╻ ╻", "┗━┫", "  ╹"),
    "5": ("┏━╸", "┗━┓", "╺━┛"),
    "6": ("┏━╸", "┣━┓", "┗━┛"),
    "7": ("╺━┓", "  ┃", "  ╹"),
    "8": ("┏━┓", "┣━┫", "┗━┛"),
    "9": ("┏━┓", "┗━┫", "╺━┛"),
}
# Hauteurs des barres de l'histogramme des dernières 24 heures.
BARRES = "▁▂▃▄▅▆▇█"
# Un ajout reste surligné en vert pendant ce nombre de secondes.
DUREE_SURBRILLANCE = 10
# Pauses minutées : touche -> minutes.
PAUSES_MINUTEES = {"1": 5, "2": 10, "3": 30}
# Défilement de l'activité : touche -> nombre de messages (None : retour en haut).
DEFILEMENT: dict[str, int | None] = {
    "haut": -1,
    "bas": 1,
    "page_haut": -5,
    "page_bas": 5,
    "debut": None,
}
# Touches spéciales : second caractère renvoyé par Windows -> nom.
TOUCHES_SPECIALES = {
    "H": "haut",
    "P": "bas",
    "I": "page_haut",
    "Q": "page_bas",
    "G": "debut",
}
JOURS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")


def apparence_evenement(evenement: Evenement) -> tuple[str, str]:
    """Symbole et couleur d'une ligne du panneau « Activité ».

    Pas de ✔ ni de ✖ : Windows les dessine en émoji (couleur imposée, deux cases de
    large, collés au mot suivant). ✓ et ✗ restent de vrais caractères de texte.
    """
    if evenement.genre == moteur.GENRE_AJOUT:
        return "✓", "succes"
    if evenement.genre == moteur.GENRE_RETRAIT:
        return "▼", "retrait"
    if evenement.niveau >= logging.ERROR:
        return "✗", "erreur"
    if evenement.niveau >= logging.WARNING:
        return "▲", "alerte"
    return "•", "info"


# ─── Mise en page selon la taille de la fenêtre ───────────────────────────────
@dataclass(frozen=True)
class Disposition:
    """Répartition de l'écran selon sa taille, en caractères.

    La taille change quand on redimensionne la fenêtre, mais aussi avec le zoom
    (Ctrl+molette) : plus les caractères sont gros, moins il en tient.
    """

    # Cartes par rangée : 4, 2, ou 1 (un simple résumé).
    colonnes: int
    gros_chiffres: bool
    entete_encadre: bool
    hauteur_entete: int
    hauteur_cartes: int
    # « Derniers ajouts » et « Activité » côte à côte, ou l'un sous l'autre.
    cote_a_cote: bool
    # Assez de hauteur pour afficher aussi « Derniers ajouts ».
    avec_ajouts: bool

    @classmethod
    def pour(cls, largeur: int, hauteur: int) -> Disposition:
        colonnes = 4 if largeur >= 100 else 2 if largeur >= 60 else 1
        gros = (colonnes == 4 and hauteur >= 24) or (colonnes == 2 and hauteur >= 34)
        entete_encadre = hauteur >= 22
        hauteur_entete = 3 if entete_encadre else 1
        if colonnes == 1:
            hauteur_cartes = 5
        else:
            rangee = 7 if gros else 5
            hauteur_cartes = rangee if colonnes == 4 else 2 * rangee
        reste = hauteur - hauteur_entete - hauteur_cartes - 1
        cote_a_cote = largeur >= 100
        return cls(
            colonnes=colonnes,
            gros_chiffres=gros,
            entete_encadre=entete_encadre,
            hauteur_entete=hauteur_entete,
            hauteur_cartes=hauteur_cartes,
            cote_a_cote=cote_a_cote,
            avec_ajouts=cote_a_cote or reste >= 16,
        )


# ─── Petits outils d'affichage ────────────────────────────────────────────────
def gros_nombre(nombre: int, style: str) -> Text:
    chiffres = str(nombre)
    if len(chiffres) > 5:
        return Text(f"\n{chiffres}\n", style=style, justify="center")
    lignes = (
        " ".join(GROS_CHIFFRES[chiffre][rang] for chiffre in chiffres)
        for rang in range(3)
    )
    return Text("\n".join(lignes), style=style, justify="center")


def nombre_carte(nombre: int, style: str, gros: bool) -> Text:
    """Gros chiffres s'il y a la place, sinon le nombre sur une seule ligne."""
    if gros:
        return gros_nombre(nombre, style)
    return Text(str(nombre), style=style, justify="center", no_wrap=True)


def il_y_a(moment: datetime, maintenant: datetime) -> str:
    secondes = int((maintenant - moment).total_seconds())
    if secondes < 5:
        return "à l'instant"
    if secondes < 60:
        return f"il y a {secondes} s"
    minutes = secondes // 60
    if minutes < 60:
        return f"il y a {minutes} min"
    heures, minutes = divmod(minutes, 60)
    return f"il y a {heures} h {minutes:02d}"


def duree_compacte(secondes: float) -> str:
    """« 40 s », « 12 min », « 1 h 24 » : tient dans une carte étroite."""
    minutes = int(secondes) // 60
    if minutes < 1:
        return f"{int(secondes)} s"
    heures, minutes = divmod(minutes, 60)
    return f"{heures} h {minutes:02d}" if heures else f"{minutes} min"


def duree_courte(secondes: float) -> str:
    secondes = math.ceil(max(secondes, 0))
    if secondes < 60:
        return f"{secondes} s"
    minutes, secondes = divmod(secondes, 60)
    return f"{minutes} min {secondes:02d} s"


def pluriel(nombre: int, mot: str) -> str:
    """« 1 retrait », « 2 retraits »."""
    return f"{nombre} {mot}" if nombre <= 1 else f"{nombre} {mot}s"


def rythme_par_heure(nombre: int, secondes: float) -> str | None:
    """« 4,2 » ajouts par heure, ou None si c'est trop tôt pour le dire (< 10 min)."""
    if nombre == 0 or secondes < 600:
        return None
    return f"{nombre * 3600 / secondes:.1f}".replace(".", ",")


def carte(
    titre: str,
    contenu: RenderableType,
    bordure: str = "accent",
    sous_titre: str | None = None,
) -> Panel:
    return Panel(
        contenu,
        title=Text(f" {titre} ", style="titre"),
        title_align="left",
        subtitle=Text(f" {sous_titre} ", style="discret") if sous_titre else None,
        subtitle_align="right",
        border_style=bordure,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def ligne_centree(*morceaux: tuple[str, str]) -> Text:
    """Une ligne de texte centrée, coupée avec « … » plutôt que renvoyée à la ligne."""
    return Text.assemble(*morceaux, justify="center", no_wrap=True, overflow="ellipsis")


def une_ligne(contenu: RenderableType) -> Table:
    """Garde un élément (animation, texte) sur une seule ligne, coupé avec « … »."""
    grille = Table.grid(expand=True)
    grille.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    grille.add_row(contenu)
    return grille


def barre(total: float, rempli: float, couleur: str, fin: str | None = None) -> Table:
    """Barre de progression sur sa propre ligne (seule, ProgressBar ne passe pas à la
    ligne et collerait le texte suivant à la barre)."""
    grille = Table.grid(expand=True)
    grille.add_column(ratio=1)
    grille.add_row(
        ProgressBar(
            total=total,
            completed=rempli,
            style="fond_barre",
            complete_style=couleur,
            finished_style=fin or couleur,
        )
    )
    return grille


def histogramme(instant: Instantane, maintenant: datetime) -> tuple[Text, int]:
    """Les ajouts des dernières 24 heures, heure par heure (la plus récente à droite),
    et leur total."""
    par_heure = [0] * 24
    for ajout in instant.derniers_ajouts:
        heures = int((maintenant - ajout.moment).total_seconds() // 3600)
        if 0 <= heures < 24:
            par_heure[23 - heures] += 1
    plus_haut = max(par_heure)
    dessin = Text(no_wrap=True)
    for nombre in par_heure:
        if nombre == 0:
            dessin.append(BARRES[0], style="fond_barre")
        else:
            niveau = math.ceil(nombre / plus_haut * len(BARRES)) - 1
            dessin.append(BARRES[niveau], style="succes")
    return dessin, sum(par_heure)


# ─── En-tête et cartes ────────────────────────────────────────────────────────
def entete(
    instant: Instantane,
    maintenant: datetime,
    disposition: Disposition,
    largeur: int,
    son: bool = False,
) -> RenderableType:
    gauche = Text.assemble(("◆ PSN AMIS", "accent"), (f" {moteur.VERSION}", "discret"))
    if largeur >= 90:
        gauche.append("   acceptation automatique des demandes d'amis", style="discret")
    droite = Text()
    if son and largeur >= 40:
        droite.append("♪ ", style="accent")
    if largeur >= 50:
        if largeur >= 70:
            droite.append("compte ", style="discret")
        droite.append(instant.pseudo_compte or "—", style="titre")
        droite.append("   ")
    droite.append(maintenant.strftime("%H:%M:%S"), style="accent")

    grille = Table.grid(expand=True)
    grille.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    grille.add_column(justify="right", no_wrap=True)
    grille.add_row(gauche, droite)
    if disposition.entete_encadre:
        return Panel(grille, box=box.HEAVY, border_style="accent", padding=(0, 1))
    # Peu de hauteur : une simple barre colorée d'une ligne.
    return Padding(grille, (0, 1), style="fond_entete")


def ligne_statut(instant: Instantane) -> Text:
    symbole, libelle, couleur = APPARENCE[instant.statut]
    actif = instant.statut in (Statut.EN_MARCHE, Statut.VERIFICATION)
    # Le voyant « bat » une fois par seconde quand tout va bien.
    allume = not actif or int(time.monotonic() * 2) % 2 == 0
    return Text.assemble(
        (f"{symbole} ", couleur if allume else "discret"),
        (libelle, couleur),
        no_wrap=True,
        overflow="ellipsis",
    )


def detail_affiche(instant: Instantane, maintenant: datetime) -> str:
    """Le texte sous le statut : « Dernier ajout il y a 3 min » quand tout est calme."""
    if instant.statut == Statut.EN_MARCHE and instant.derniers_ajouts:
        return f"Dernier ajout {il_y_a(instant.derniers_ajouts[0].moment, maintenant)}"
    return instant.detail


def ligne_detail(instant: Instantane, maintenant: datetime) -> RenderableType:
    if instant.statut in STATUTS_ANIMES:
        animation = Spinner(
            "dots", text=Text(f" {instant.detail}", style="info"), style="info"
        )
        return une_ligne(animation)
    return Text(
        detail_affiche(instant, maintenant),
        style="discret",
        no_wrap=True,
        overflow="ellipsis",
    )


@dataclass(frozen=True)
class Reprise:
    """Pause minutée (touches 1, 2, 3) : moment de la reprise et durée totale."""

    fin: float
    duree: float


def compte_a_rebours(
    instant: Instantane, reprise: Reprise | None = None
) -> list[RenderableType] | None:
    """Texte « Vérification dans 12 s » et sa barre, ou None s'il n'y a pas d'attente."""
    if instant.statut == Statut.PAUSE:
        if reprise is None:
            return None
        reste = max(reprise.fin - time.monotonic(), 0.0)
        return [
            Text(
                f"Reprise dans {duree_courte(reste)}",
                style="info",
                no_wrap=True,
                overflow="ellipsis",
            ),
            barre(reprise.duree, reprise.duree - reste, "alerte"),
        ]
    if instant.prochaine_verification is None:
        return None
    reste = max(instant.prochaine_verification - time.monotonic(), 0.0)
    verbe = (
        "Vérification"
        if instant.statut in (Statut.EN_MARCHE, Statut.LISTE_PLEINE)
        else "Nouvel essai"
    )
    couleur = APPARENCE[instant.statut][2]
    return [
        Text(
            f"{verbe} dans {duree_courte(reste)}",
            style="info",
            no_wrap=True,
            overflow="ellipsis",
        ),
        barre(instant.intervalle, instant.intervalle - reste, couleur),
    ]


def ligne_infos(instant: Instantane) -> Text:
    verification = instant.derniere_verification
    en_attente = instant.demandes_en_attente
    return Text.assemble(
        ("vérifié à ", "discret"),
        (verification.strftime("%H:%M:%S") if verification else "—", "info"),
        (" · ", "discret"),
        ("—" if en_attente is None else str(en_attente), "info"),
        (" en attente", "discret"),
        no_wrap=True,
        overflow="ellipsis",
    )


def carte_statut(
    instant: Instantane,
    gros: bool,
    maintenant: datetime | None = None,
    reprise: Reprise | None = None,
) -> Panel:
    maintenant = maintenant or datetime.now()
    couleur = APPARENCE[instant.statut][2]
    rebours = compte_a_rebours(instant, reprise)
    lignes: list[RenderableType] = [ligne_statut(instant)]
    if gros:
        lignes.append(ligne_detail(instant, maintenant))
        lignes += rebours or [Text(""), Text("")]
        lignes.append(ligne_infos(instant))
    else:
        lignes += rebours or [ligne_detail(instant, maintenant), Text("")]
    return carte("Statut", Group(*lignes), bordure=couleur)


def carte_jour(instant: Instantane, maintenant: datetime, gros: bool) -> Panel:
    nombre = instant.ajouts_jour
    dernier = next(
        (
            ajout
            for ajout in instant.derniers_ajouts
            if ajout.moment.date() == maintenant.date()
        ),
        None,
    )
    recent = (
        dernier is not None
        and (maintenant - dernier.moment).total_seconds() < DUREE_SURBRILLANCE
    )
    if dernier is None:
        info = ligne_centree(("aucun pour l'instant", "discret"))
    else:
        info = ligne_centree(
            ("dernier à ", "discret"), (dernier.moment.strftime("%H:%M:%S"), "info")
        )
    libelle = [("ajout" if nombre == 1 else "ajouts", "discret")]
    if instant.retraits_jour:
        libelle += [
            (" · ", "discret"),
            (pluriel(instant.retraits_jour, "retrait"), "retrait"),
        ]
    contenu = Group(nombre_carte(nombre, "succes", gros), ligne_centree(*libelle), info)
    return carte("Aujourd'hui", contenu, bordure="succes" if recent else "accent")


def carte_session(
    instant: Instantane, maintenant: datetime, gros: bool, largeur_carte: int
) -> Panel:
    nombre = instant.ajouts_session
    ecoule = (maintenant - instant.debut).total_seconds()
    libelle = [("ajout" if nombre == 1 else "ajouts", "discret")]
    rythme = rythme_par_heure(nombre, ecoule)
    if rythme:
        libelle += [(" · ", "discret"), (rythme, "info"), (" par heure", "discret")]
    contenu = Group(
        nombre_carte(nombre, "titre", gros),
        ligne_centree(*libelle),
        ligne_centree(
            ("lancé à ", "discret"),
            (instant.debut.strftime("%H:%M"), "info"),
            (f" · {duree_compacte(ecoule)}", "discret"),
        ),
    )
    # Carte étroite : un titre plus court, plutôt que coupé.
    titre = "Depuis le lancement" if largeur_carte >= 26 else "Cette session"
    return carte(titre, contenu)


def carte_amis(
    instant: Instantane, maintenant: datetime, gros: bool, largeur_carte: int
) -> Panel:
    limite = moteur.LIMITE_AMIS_PSN
    nombre = instant.nombre_amis
    if nombre is None:
        contenu = Group(
            ligne_centree(("—", "discret")),
            ligne_centree(("connexion en cours…", "discret")),
        )
        return carte("Amis", contenu)
    part = nombre / limite
    couleur = "succes" if part < 0.8 else "alerte" if part < 0.95 else "erreur"
    # Arrondi vers le bas : « 100 % » seulement quand la liste est vraiment pleine.
    pourcentage = math.floor(part * 100)
    titre = (
        f"Amis · {pourcentage} % de {limite}"
        if largeur_carte >= 24
        else f"Amis · {pourcentage} %"
    )
    compte_a = instant.amis_comptes_a
    fraicheur = il_y_a(compte_a, maintenant) if compte_a else "—"
    contenu = Group(
        nombre_carte(nombre, couleur, gros),
        barre(limite, min(nombre, limite), couleur, fin="erreur"),
        ligne_centree(("compté ", "discret"), (fraicheur, "info")),
    )
    return carte(titre, contenu, bordure=couleur if part >= 0.8 else "accent")


def carte_resume(
    instant: Instantane, maintenant: datetime, reprise: Reprise | None = None
) -> Panel:
    """Fenêtre très étroite : l'essentiel sur une seule carte de trois lignes."""
    couleur = APPARENCE[instant.statut][2]
    rebours = compte_a_rebours(instant, reprise)
    amis = "—" if instant.nombre_amis is None else str(instant.nombre_amis)
    chiffres = Text.assemble(
        ("aujourd'hui ", "discret"),
        (str(instant.ajouts_jour), "succes"),
        ("  session ", "discret"),
        (str(instant.ajouts_session), "titre"),
        ("  amis ", "discret"),
        (amis, "info"),
        no_wrap=True,
        overflow="ellipsis",
    )
    deuxieme = rebours[0] if rebours else ligne_detail(instant, maintenant)
    return carte(
        "PSN Amis", Group(ligne_statut(instant), deuxieme, chiffres), bordure=couleur
    )


# ─── Panneaux du bas ──────────────────────────────────────────────────────────
class ListeAjouts:
    """Contenu de « Derniers ajouts » : l'histogramme des dernières 24 heures, puis
    autant de lignes qu'il en tient en hauteur ; des colonnes disparaissent quand la
    largeur manque."""

    def __init__(self, instant: Instantane, maintenant: datetime) -> None:
        self._instant = instant
        self._maintenant = maintenant

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        ajouts = self._instant.derniers_ajouts
        if not ajouts:
            yield Text("En attente du premier ajout…", style="discret")
            return
        largeur = options.max_width
        hauteur = options.height if options.height is not None else len(ajouts) + 2
        avec_numero = largeur >= 36
        avec_anciennete = largeur >= 46

        # Histogramme sur la première ligne, s'il reste de la place pour la liste.
        if largeur >= 34 and hauteur >= 6:
            dessin, total = histogramme(self._instant, self._maintenant)
            ligne = Text("24 h ", style="discret", no_wrap=True, overflow="ellipsis")
            ligne.append_text(dessin)
            if largeur >= 46:
                ligne.append(f"  {pluriel(total, 'ajout')}", style="discret")
            yield ligne
            hauteur -= 1

        tableau = Table(
            box=None,
            expand=True,
            pad_edge=False,
            header_style="discret",
            padding=(0, 1),
        )
        if avec_numero:
            tableau.add_column("#", justify="right", style="discret", width=4)
        tableau.add_column("Heure", style="info", width=8, no_wrap=True)
        tableau.add_column(
            "Pseudo", style="titre", ratio=1, no_wrap=True, overflow="ellipsis"
        )
        if avec_anciennete:
            tableau.add_column("", style="discret", justify="right", no_wrap=True)

        # Dernier retrait connu de chaque pseudo : un ajout plus ancien que ce retrait
        # est marqué « ▼ » (le joueur a depuis quitté la liste d'amis).
        retraits: dict[str, datetime] = {}
        for retrait in self._instant.retraits:
            retraits.setdefault(retrait.pseudo, retrait.moment)

        numero = self._instant.ajouts_jour
        # Une ligne est prise par les titres des colonnes.
        for ajout in ajouts[: max(hauteur - 1, 1)]:
            du_jour = ajout.moment.date() == self._maintenant.date()
            age = (self._maintenant - ajout.moment).total_seconds()
            retire = retraits.get(ajout.pseudo, ajout.moment) > ajout.moment
            cellules: list[RenderableType] = []
            if avec_numero:
                cellules.append(Text(str(numero) if du_jour else ""))
            cellules.append(Text(ajout.moment.strftime("%H:%M:%S")))
            if retire:
                cellules.append(
                    Text.assemble((ajout.pseudo, "discret"), (" ▼", "retrait"))
                )
            else:
                cellules.append(Text(ajout.pseudo))
            if avec_anciennete:
                if retire:
                    cellules.append(Text("retiré", style="retrait"))
                else:
                    cellules.append(Text(il_y_a(ajout.moment, self._maintenant)))
            tableau.add_row(
                *cellules, style="nouveau" if age < DUREE_SURBRILLANCE else None
            )
            if du_jour:
                numero -= 1
        yield tableau


class ListeAttentes:
    """Contenu de « Demandes en attente » (pendant une pause) : pseudo et ancienneté."""

    def __init__(self, instant: Instantane, maintenant: datetime) -> None:
        self._instant = instant
        self._maintenant = maintenant

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        attentes = self._instant.attentes
        hauteur = options.height if options.height is not None else len(attentes) + 1
        tableau = Table(
            box=None,
            expand=True,
            pad_edge=False,
            header_style="discret",
            padding=(0, 1),
        )
        tableau.add_column(
            "Pseudo", style="titre", ratio=1, no_wrap=True, overflow="ellipsis"
        )
        tableau.add_column("Demande envoyée", style="discret", no_wrap=True)
        visibles = attentes[: max(hauteur - 1, 1)]
        if len(attentes) > len(visibles):
            # Dernière ligne : le nombre de demandes qui ne tiennent pas.
            visibles = visibles[:-1]
        for attente in visibles:
            depuis = il_y_a(attente.depuis, self._maintenant) if attente.depuis else "—"
            tableau.add_row(attente.pseudo, depuis)
        if len(attentes) > len(visibles):
            tableau.add_row(
                Text(f"… et {len(attentes) - len(visibles)} autre(s)", style="discret"),
                "",
            )
        yield tableau


class FilActivite:
    """Contenu de « Activité » : chaque message en entier, renvoyé à la ligne si
    besoin, du plus récent au plus ancien, autant qu'il en tient en hauteur.
    Un message qui ne tient plus en entier n'est pas affiché à moitié.
    `decalage` messages récents sont sautés (défilement avec les flèches)."""

    def __init__(self, evenements: tuple[Evenement, ...], decalage: int = 0) -> None:
        self._evenements = evenements
        self._decalage = decalage

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        largeur = options.max_width
        hauteur = options.height
        if hauteur is None:
            hauteur = 3 * len(self._evenements) + 1
        # « 23:59:59 ✓ » devant chaque message (« 10/11 23:59 ✓ » pour les jours
        # précédents), ou seulement « ✓ » si c'est étroit.
        avec_heure = largeur >= 40
        aujourd_hui = datetime.now().date()

        lignes: list[Text] = []
        for evenement in self._evenements[self._decalage :]:
            symbole, couleur = apparence_evenement(evenement)
            debut = Text()
            if avec_heure:
                if evenement.moment.date() == aujourd_hui:
                    horodatage = evenement.moment.strftime("%H:%M:%S")
                else:
                    horodatage = evenement.moment.strftime("%d/%m %H:%M")
                debut.append(f"{horodatage} ", "discret")
            debut.append(f"{symbole} ", couleur)
            marge = debut.cell_len
            style = "titre" if couleur == "succes" else ""
            morceaux = Text(evenement.texte, style=style).wrap(
                console, max(largeur - marge, 10)
            )
            if lignes and len(lignes) + len(morceaux) > hauteur:
                break
            for rang, morceau in enumerate(morceaux):
                prefixe = debut if rang == 0 else Text(" " * marge)
                ligne = prefixe + morceau
                ligne.no_wrap = True
                ligne.overflow = "ellipsis"
                lignes.append(ligne)
        if not lignes:
            lignes.append(Text("Rien à signaler pour l'instant.", style="discret"))
        yield from lignes[: max(hauteur, 1)]


def panneau_ajouts(instant: Instantane, maintenant: datetime) -> Panel:
    return carte("Derniers ajouts", ListeAjouts(instant, maintenant))


def panneau_attentes(instant: Instantane, maintenant: datetime) -> Panel:
    return carte(
        f"Demandes en attente · {len(instant.attentes)}",
        ListeAttentes(instant, maintenant),
        bordure="alerte",
        sous_titre="acceptées à la reprise",
    )


def panneau_activite(instant: Instantane, decalage: int = 0) -> Panel:
    if decalage:
        return carte(
            "Activité",
            FilActivite(instant.evenements, decalage),
            bordure="info",
            sous_titre=f"{decalage} plus récent(s) au-dessus · ↑ ou Origine",
        )
    return carte("Activité", FilActivite(instant.evenements))


def panneau_npsso(instant: Instantane) -> Panel:
    contenu = Group(
        Text("Le code npsso doit être remplacé.", style="erreur"),
        Text(instant.probleme_npsso or "", style="alerte"),
        Text(""),
        Text.assemble(
            ("Appuyez sur ", "titre"),
            (" C ", "touche"),
            (" pour coller un nouveau code directement ici.", "titre"),
        ),
        Text(""),
        Text("Pour obtenir ce code :", style="discret"),
        Text(moteur.ETAPES_CODE_NPSSO, style="titre"),
        Text(""),
        Text(
            "Attention : si votre écran est partagé ou enregistré, le code y serait "
            "visible. Le script reprend tout seul dès que le code est enregistré.",
            style="info",
        ),
    )
    return Panel(
        contenu,
        title=Text(" Action nécessaire ", style="erreur"),
        title_align="left",
        border_style="erreur",
        box=box.HEAVY,
        padding=(1, 2),
    )


def panneau_aide(interface: EtatInterface, largeur: int) -> Panel:
    """Touche H : les touches, les symboles et les 7 derniers jours."""
    touches = Table.grid(padding=(0, 1))
    touches.add_column(no_wrap=True)
    touches.add_column()
    son = "activé" if interface.son else "coupé"
    for touche, explication in (
        ("P", "Pause, ou reprise"),
        ("1 2 3", "Pause de 5, 10 ou 30 min, puis reprise toute seule"),
        ("V", "Vérifier maintenant"),
        ("J", "Ouvrir le journal (journal.txt)"),
        ("C", "Changer le code npsso (autre compte)"),
        ("S", f"Bip à chaque ajout (en ce moment : {son})"),
        ("↑ ↓", "Faire défiler l'activité (Pg.préc. et Pg.suiv. : plus vite)"),
        ("Origine", "Revenir aux messages les plus récents"),
        ("H", "Afficher ou cacher cette aide (Échap aussi)"),
        ("Q", "Quitter (deux fois de suite) ; Ctrl+C quitte aussi"),
    ):
        touches.add_row(Text.assemble((f" {touche} ", "touche")), Text(explication))

    symboles = Table.grid(padding=(0, 1))
    symboles.add_column(no_wrap=True)
    symboles.add_column()
    for symbole, style, explication in (
        ("✓", "succes", "Demande d'ami acceptée"),
        ("▼", "retrait", "Ami retiré (il vous a retiré, ou vous l'avez retiré)"),
        ("▲", "alerte", "Avertissement : le script réessaie tout seul"),
        ("✗", "erreur", "Erreur"),
        ("•", "info", "Information"),
        ("♪", "accent", "Le bip à chaque ajout est activé"),
    ):
        symboles.add_row(Text(symbole, style=style), Text(explication))

    jours = Table(box=box.SIMPLE_HEAD, header_style="discret", pad_edge=False)
    jours.add_column("Jour", no_wrap=True)
    jours.add_column("Ajouts", justify="right", style="succes")
    jours.add_column("Retraits", justify="right", style="retrait")
    for jour, ajouts, retraits in interface.statistiques:
        nom = "aujourd'hui" if jour == date.today() else JOURS[jour.weekday()]
        jours.add_row(f"{nom} {jour:%d/%m}", str(ajouts), str(retraits))
    if interface.statistiques:
        jours.add_row(
            Text("Total", style="titre"),
            str(sum(s[1] for s in interface.statistiques)),
            str(sum(s[2] for s in interface.statistiques)),
        )

    reglages = moteur.REGLAGES
    pied_aide = Text(
        f"Réglages : {moteur.FICHIER_REGLAGES.name} (thème {reglages.theme}, "
        f"vérification toutes les {moteur.INTERVALLE_VERIFICATION} s). "
        "Modifiez-le avec le Bloc-notes, puis relancez PSN Amis.",
        style="discret",
    )
    blocs = [
        Group(Text("Touches", style="accent"), touches),
        Group(Text("Symboles", style="accent"), symboles),
        Group(Text("7 derniers jours (journal.txt)", style="accent"), jours),
    ]
    if largeur >= 110:
        grille = Table.grid(expand=True, padding=(0, 3))
        grille.add_column(ratio=4)
        grille.add_column(ratio=3)
        grille.add_column(no_wrap=True)
        grille.add_row(*blocs)
        contenu = Group(grille, Text(""), pied_aide)
    else:
        contenu = Group(*(Group(bloc, Text("")) for bloc in blocs), pied_aide)
    return Panel(
        contenu,
        title=Text(" Aide · H ou Échap pour fermer ", style="titre"),
        title_align="left",
        border_style="accent",
        box=box.HEAVY,
        padding=(0, 1),
    )


def touches_du_pied(instant: Instantane, largeur_max: int) -> Text:
    """Les touches et leur libellé, du plus détaillé au plus court selon la place."""
    en_pause = instant.statut == Statut.PAUSE
    paliers: list[tuple[tuple[str, ...], str]] = [
        (
            (
                "Reprendre" if en_pause else "Pause",
                "Vérifier maintenant",
                "Journal",
                "Code npsso",
                "Aide",
                "Son",
                "Quitter",
            ),
            "   ",
        ),
        (
            (
                "Reprendre" if en_pause else "Pause",
                "Vérifier",
                "Journal",
                "Code",
                "Aide",
                "Son",
                "Quitter",
            ),
            "  ",
        ),
        (
            (
                "reprise" if en_pause else "pause",
                "vérif.",
                "journal",
                "code",
                "aide",
                "son",
                "quitter",
            ),
            " ",
        ),
        (("",) * 7, " "),
    ]
    for libelles, separation in paliers:
        touches = Text(no_wrap=True, overflow="ellipsis")
        for rang, (lettre, libelle) in enumerate(zip("PVJCHSQ", libelles, strict=True)):
            if rang:
                touches.append(separation)
            touches.append(f" {lettre} ", style="touche")
            if libelle:
                touches.append(f" {libelle}", style="discret")
        if touches.cell_len <= largeur_max:
            return touches
    return touches


def pied(instant: Instantane, interface: EtatInterface, largeur: int) -> Table | Text:
    if interface.confirmation_quitter():
        return Text(
            "  Appuyez encore sur Q pour quitter (toute autre touche annule)",
            style="alerte",
            no_wrap=True,
            overflow="ellipsis",
        )
    message = interface.message_actuel()
    # Un message à droite : les libellés des touches raccourcissent pour lui laisser
    # de la place.
    reserve = len(message) + 2 if message else 0
    touches = touches_du_pied(instant, largeur - reserve)
    droite = Text(message or "", style="info")
    grille = Table.grid(expand=True)
    grille.add_column(no_wrap=True)
    grille.add_column(justify="right", ratio=1, no_wrap=True, overflow="ellipsis")
    grille.add_row(touches, droite)
    return grille


def construire_ecran(
    instant: Instantane, interface: EtatInterface, largeur: int, hauteur: int
) -> Layout:
    maintenant = datetime.now()
    disposition = Disposition.pour(largeur, hauteur)
    reprise = interface.reprise()
    ecran = Layout()
    ecran.split_column(
        Layout(
            entete(instant, maintenant, disposition, largeur, son=interface.son),
            size=disposition.hauteur_entete,
        ),
        Layout(name="cartes", size=disposition.hauteur_cartes),
        Layout(name="corps", ratio=1),
        Layout(pied(instant, interface, largeur), size=1),
    )

    gros = disposition.gros_chiffres
    if disposition.colonnes == 1:
        ecran["cartes"].update(carte_resume(instant, maintenant, reprise))
    else:
        # Largeur approximative d'une carte, pour choisir des titres qui tiennent.
        largeur_carte = largeur * 2 // 9 if disposition.colonnes == 4 else largeur // 2
        cartes = [
            carte_statut(instant, gros, maintenant, reprise),
            carte_jour(instant, maintenant, gros),
            carte_session(instant, maintenant, gros, largeur_carte),
            carte_amis(instant, maintenant, gros, largeur_carte),
        ]
        if disposition.colonnes == 4:
            ecran["cartes"].split_row(
                Layout(cartes[0], ratio=3),
                Layout(cartes[1], ratio=2),
                Layout(cartes[2], ratio=2),
                Layout(cartes[3], ratio=2),
            )
        else:
            ecran["cartes"].split_column(Layout(name="haut"), Layout(name="bas"))
            ecran["haut"].split_row(Layout(cartes[0]), Layout(cartes[1]))
            ecran["bas"].split_row(Layout(cartes[2]), Layout(cartes[3]))

    corps = ecran["corps"]
    if interface.aide:
        corps.update(panneau_aide(interface, largeur))
        return ecran
    if instant.probleme_npsso:
        corps.update(panneau_npsso(instant))
        return ecran
    # En pause, les demandes qui attendent remplacent « Derniers ajouts ».
    if instant.statut == Statut.PAUSE and instant.attentes:
        haut = panneau_attentes(instant, maintenant)
    else:
        haut = panneau_ajouts(instant, maintenant)
    activite = panneau_activite(instant, interface.decalage(instant.evenements))
    if disposition.cote_a_cote:
        corps.split_row(Layout(haut, ratio=2), Layout(activite, ratio=3))
    elif disposition.avec_ajouts:
        corps.split_column(Layout(haut, ratio=2), Layout(activite, ratio=3))
    else:
        corps.update(activite)
    return ecran


def titre_fenetre(instant: Instantane) -> str:
    libelle = APPARENCE[instant.statut][1].lower()
    pluriel_ajouts = "s" if instant.ajouts_jour > 1 else ""
    return f"PSN Amis · {instant.ajouts_jour} ajout{pluriel_ajouts} aujourd'hui · {libelle}"


# ─── Journal → panneau « Activité » ───────────────────────────────────────────
class VersTableau(logging.Handler):
    """Envoie les messages du journal dans le panneau « Activité » (code masqué)."""

    IGNORES = frozenset({moteur.GENRE_AIDE, moteur.GENRE_RAPPEL})

    def __init__(self, suivi: Suivi) -> None:
        super().__init__(level=logging.INFO)
        self._suivi = suivi
        self.setFormatter(moteur.FormatMasque("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        genre = getattr(record, "genre", "")
        if genre in self.IGNORES:
            return
        # Même règle que les gestionnaires de logging de Python : une erreur de mise
        # en forme est signalée à handleError, jamais propagée.
        try:
            texte = self.format(record)
        except Exception:  # noqa: BLE001
            self.handleError(record)
            return
        premiere_ligne = texte.splitlines()[0].strip(" =") if texte else ""
        self._suivi.evenement(
            datetime.fromtimestamp(record.created),
            record.levelno,
            genre or "info",
            premiere_ligne,
        )


# ─── Clavier ──────────────────────────────────────────────────────────────────
@dataclass
class EtatInterface:
    quitter_avant: float = 0.0
    message: str = ""
    message_jusqua: float = 0.0
    # Panneau d'aide (touche H) et ses statistiques des 7 derniers jours.
    aide: bool = False
    statistiques: list[tuple[date, int, int]] = field(default_factory=list)
    # Bip à chaque ajout (touche S).
    son: bool = False
    # Pause minutée (touches 1, 2, 3).
    reprise_a: float | None = None
    duree_pause: float = 0.0
    # Défilement de l'activité : le message affiché tout en haut (None : le plus
    # récent). Repéré par le message lui-même, pour que l'affichage ne bouge pas
    # quand de nouveaux messages arrivent.
    ancre: Evenement | None = None
    evenements: tuple[Evenement, ...] = ()

    def confirmation_quitter(self) -> bool:
        return time.monotonic() < self.quitter_avant

    def informer(self, texte: str, secondes: float = 4.0) -> None:
        self.message = texte
        self.message_jusqua = time.monotonic() + secondes

    def message_actuel(self) -> str | None:
        return self.message if time.monotonic() < self.message_jusqua else None

    def reprise(self) -> Reprise | None:
        if self.reprise_a is None:
            return None
        return Reprise(self.reprise_a, self.duree_pause)

    def decalage(self, evenements: tuple[Evenement, ...] | None = None) -> int:
        """Nombre de messages récents sautés par le défilement."""
        if evenements is not None:
            self.evenements = evenements
        if self.ancre is None:
            return 0
        for rang, evenement in enumerate(self.evenements):
            if evenement is self.ancre:
                return rang
        # Message trop ancien, sorti de la liste : retour en haut.
        self.ancre = None
        return 0

    def defiler(self, pas: int | None) -> None:
        """Fait défiler l'activité de `pas` messages ; None revient en haut."""
        if pas is None or not self.evenements:
            self.ancre = None
            return
        rang = min(max(self.decalage() + pas, 0), len(self.evenements) - 1)
        self.ancre = self.evenements[rang] if rang else None


class Clavier:
    """Lit le clavier sans bloquer et règle la console le temps du tableau de bord :
    - Ctrl+C devient une touche normale (pas de question « Terminer le programme
      de commandes ? » à la fermeture) ;
    - un clic dans la fenêtre ne fige plus l'affichage (« Édition rapide » coupée).
    Le réglage d'origine est remis en place à la sortie."""

    ENTREE_STANDARD = -10
    TRAITEMENT_CTRL_C = 0x0001
    SAISIE_SOURIS = 0x0010
    EDITION_RAPIDE = 0x0040
    OPTIONS_ETENDUES = 0x0080
    OBJET_SIGNALE = 0

    def __init__(self) -> None:
        self._k32: ctypes.WinDLL | None = None
        self._entree: int | None = None
        self._mode_initial: int | None = None
        if os.name == "nt":
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetStdHandle.argtypes = (ctypes.c_int32,)
            k32.GetStdHandle.restype = ctypes.c_void_p
            k32.GetConsoleMode.argtypes = (
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint32),
            )
            k32.SetConsoleMode.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
            k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
            k32.WaitForSingleObject.restype = ctypes.c_uint32
            k32.FlushConsoleInputBuffer.argtypes = (ctypes.c_void_p,)
            self._k32 = k32

    def __enter__(self) -> Clavier:
        if self._k32 is not None:
            entree = self._k32.GetStdHandle(self.ENTREE_STANDARD)
            mode = ctypes.c_uint32()
            if entree and self._k32.GetConsoleMode(entree, ctypes.byref(mode)):
                self._entree = entree
                self._mode_initial = mode.value
                self._appliquer()
        return self

    def __exit__(self, *details: object) -> None:
        self._restaurer()

    def _appliquer(self) -> None:
        """Réglage « tableau de bord » : Ctrl+C simple touche, ni édition rapide ni souris."""
        if self._k32 is None or not self._entree or self._mode_initial is None:
            return
        retires = self.TRAITEMENT_CTRL_C | self.SAISIE_SOURIS | self.EDITION_RAPIDE
        nouveau = (self._mode_initial | self.OPTIONS_ETENDUES) & ~retires
        self._k32.SetConsoleMode(self._entree, nouveau)

    def _restaurer(self) -> None:
        if self._k32 is None or not self._entree or self._mode_initial is None:
            return
        self._k32.SetConsoleMode(self._entree, self._mode_initial)

    @contextlib.contextmanager
    def mode_initial(self) -> Iterator[None]:
        """Rend provisoirement à la console son réglage d'origine, le temps d'une saisie :
        le collage par clic droit marche, et Ctrl+C interrompt la saisie."""
        self._restaurer()
        try:
            yield
        finally:
            self._appliquer()

    def touches(self, attente_ms: int) -> list[str]:
        """Attend au plus attente_ms qu'une touche soit pressée ; renvoie les touches.

        Les flèches, Pg.préc., Pg.suiv. et Origine sont renvoyées par leur nom
        (« haut », « page_bas »...), Échap par « echap ».
        Un changement de taille de la fenêtre (ou du zoom) réveille aussi l'attente :
        l'écran est alors redessiné tout de suite à la nouvelle taille.
        """
        if self._k32 is None or not self._entree:
            time.sleep(attente_ms / 1000)
            return []
        import msvcrt

        if (
            self._k32.WaitForSingleObject(self._entree, attente_ms)
            != self.OBJET_SIGNALE
        ):
            return []
        if not msvcrt.kbhit():
            # Autres événements (taille de fenêtre, focus...) : on les jette pour ne
            # pas réveiller le programme en boucle.
            self._k32.FlushConsoleInputBuffer(self._entree)
            return []
        lues: list[str] = []
        while msvcrt.kbhit():
            touche = msvcrt.getwch()
            if touche in ("\x00", "\xe0"):
                # Touche spéciale : un second caractère dit laquelle.
                nom = TOUCHES_SPECIALES.get(msvcrt.getwch())
                if nom:
                    lues.append(nom)
                continue
            lues.append("echap" if touche == "\x1b" else touche)
        return lues


def ouvrir_journal(interface: EtatInterface) -> None:
    if not moteur.FICHIER_JOURNAL.exists():
        interface.informer("Le journal est encore vide.")
        return
    try:
        os.startfile(moteur.FICHIER_JOURNAL)  # noqa: S606 (ouvre le Bloc-notes)
        interface.informer("Journal ouvert.")
    except OSError:
        interface.informer("Impossible d'ouvrir le journal.")


def pause_minutee(minutes: int, interface: EtatInterface, commandes: Commandes) -> None:
    """Touches 1, 2, 3 : pause, puis reprise automatique au bout de `minutes`."""
    if not commandes.pause.is_set():
        commandes.basculer_pause()
    interface.duree_pause = minutes * 60
    interface.reprise_a = time.monotonic() + interface.duree_pause
    heure = datetime.fromtimestamp(time.time() + interface.duree_pause)
    journal.info(
        "Pause de %d min : reprise automatique à %s.", minutes, f"{heure:%H:%M}"
    )


def reprendre_si_l_heure_est_venue(
    interface: EtatInterface, commandes: Commandes
) -> None:
    """Fin d'une pause minutée : relance les acceptations."""
    if interface.reprise_a is None or time.monotonic() < interface.reprise_a:
        return
    interface.reprise_a = None
    if commandes.pause.is_set():
        commandes.basculer_pause()
        journal.info(
            "Fin de la pause minutée : les demandes sont de nouveau acceptées."
        )


def traiter_touche(
    touche: str, interface: EtatInterface, commandes: Commandes
) -> str | None:
    """Applique une touche.

    Renvoie la raison de l'arrêt si l'utilisateur quitte, « configurer » s'il veut
    coller un nouveau code npsso (touche C), None sinon.
    """
    if touche == "\x03":
        return "Ctrl+C"
    lettre = touche.lower()
    if lettre == "q":
        if interface.confirmation_quitter():
            return "touche Q"
        interface.quitter_avant = time.monotonic() + 3
        return None
    # Toute autre touche annule la demande de fermeture.
    interface.quitter_avant = 0.0
    if lettre in DEFILEMENT:
        interface.defiler(DEFILEMENT[lettre])
    elif lettre == "p":
        interface.reprise_a = None
        if commandes.basculer_pause():
            journal.info("Pause : les nouvelles demandes attendent (touche P).")
        else:
            journal.info("Reprise : les demandes sont de nouveau acceptées.")
    elif lettre in PAUSES_MINUTEES:
        pause_minutee(PAUSES_MINUTEES[lettre], interface, commandes)
    elif lettre == "v":
        commandes.verifier_maintenant()
        interface.informer("Vérification demandée…")
    elif lettre == "j":
        ouvrir_journal(interface)
    elif lettre == "h":
        interface.aide = not interface.aide
        if interface.aide:
            interface.statistiques = moteur.statistiques_par_jour(7)
    elif lettre == "echap":
        interface.aide = False
    elif lettre == "s":
        interface.son = not interface.son
        interface.informer(
            "Bip à chaque ajout : activé." if interface.son else "Bip coupé."
        )
        if interface.son:
            notifications.bip()
    elif lettre == "c":
        return "configurer"
    return None


def changer_le_code(
    ecran: Live,
    console: Console,
    clavier: Clavier,
    commandes: Commandes,
    interface: EtatInterface,
) -> None:
    """Touche C : quitte l'écran du tableau de bord le temps de coller un nouveau code,
    puis y revient. Avec un code valide, le moteur se reconnecte à ce compte."""
    ecran.stop()
    try:
        console.clear()
        console.print(
            f"[accent]◆ PSN AMIS[/] [discret]{moteur.VERSION}[/]  ·  changer le code npsso"
        )
        # Console en mode normal pendant la saisie : collage par clic droit, Ctrl+C.
        with clavier.mode_initial():
            enregistre = moteur.assistant_npsso(
                dire=lambda texte: console.print(texte, markup=False, highlight=False)
            )
    finally:
        ecran.start(refresh=True)
    if enregistre:
        journal.info("Nouveau code npsso enregistré (touche C) : reconnexion à Sony.")
        commandes.demander_reconnexion()
        interface.informer("Nouveau code enregistré : reconnexion…")
    else:
        interface.informer("Code inchangé.")


# ─── Boucle d'affichage ───────────────────────────────────────────────────────
def lancer(
    suivi: Suivi,
    commandes: Commandes,
    demarrer_moteur: Callable[[], threading.Thread],
) -> str:
    """Affiche le tableau de bord jusqu'à ce que l'utilisateur quitte ; renvoie la raison."""
    reglages = moteur.REGLAGES
    console = Console(theme=THEMES.get(THEME_CONSOLE.get(reglages.theme, ""), THEME))
    interface = EtatInterface(son=reglages.son)
    titre_actuel = ""
    with (
        Clavier() as clavier,
        Live(console=console, screen=True, auto_refresh=False) as ecran,
    ):
        fil = demarrer_moteur()
        relance: float | None = None
        ajouts_vus = 0
        while True:
            instant = suivi.instantane()
            # Bip pour chaque nouvel ajout (touche S).
            if instant.ajouts_session > ajouts_vus and interface.son:
                notifications.bip()
            ajouts_vus = instant.ajouts_session
            # Taille relue à chaque image : elle suit le redimensionnement et le zoom.
            largeur, hauteur = console.size
            ecran.update(
                construire_ecran(instant, interface, largeur, hauteur), refresh=True
            )
            titre = titre_fenetre(instant)
            if titre != titre_actuel:
                console.set_window_title(titre)
                titre_actuel = titre

            # Rafraîchissement plus rapide seulement quand une animation tourne.
            attente = 250 if instant.statut in STATUTS_ANIMES else 500
            for touche in clavier.touches(attente):
                action = traiter_touche(touche, interface, commandes)
                if action == "configurer":
                    changer_le_code(ecran, console, clavier, commandes, interface)
                elif action:
                    return action
            reprendre_si_l_heure_est_venue(interface, commandes)

            # Si le moteur s'est arrêté par accident, on le relance après 10 s.
            if not fil.is_alive() and not commandes.arret.is_set():
                if relance is None:
                    journal.error(
                        "Le moteur s'est arrêté de façon inattendue : "
                        "redémarrage dans 10 secondes."
                    )
                    relance = time.monotonic() + 10
                elif time.monotonic() >= relance:
                    fil = demarrer_moteur()
                    relance = None
