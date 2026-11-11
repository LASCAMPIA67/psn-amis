"""Tableau de bord en couleur de PSN Amis, dans la console Windows.

Il lit l'état du moteur (moteur.Suivi) et redessine l'écran deux à quatre fois par
seconde. La mise en page suit la taille de la fenêtre, qui change aussi avec le zoom
(Ctrl+molette) : grandes cartes, cartes compactes, puis un simple résumé quand la
place manque. Les messages d'activité sont toujours affichés en entier.

Touches : P pause ou reprise, V vérifier maintenant, J ouvrir le journal,
Q deux fois pour quitter (Ctrl+C quitte aussi).
"""

from __future__ import annotations

import ctypes
import logging
import math
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

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

import moteur
from moteur import Commandes, Evenement, Instantane, Statut, Suivi, journal

# ─── Apparence ────────────────────────────────────────────────────────────────
THEME = Theme(
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
)

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
# Un ajout reste surligné en vert pendant ce nombre de secondes.
DUREE_SURBRILLANCE = 10


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


def duree_lisible(secondes: float) -> str:
    minutes = int(secondes) // 60
    if minutes < 1:
        return f"{int(secondes)} s"
    heures, minutes = divmod(minutes, 60)
    return f"{heures} h {minutes:02d} min" if heures else f"{minutes} min"


def duree_courte(secondes: float) -> str:
    secondes = math.ceil(max(secondes, 0))
    if secondes < 60:
        return f"{secondes} s"
    minutes, secondes = divmod(secondes, 60)
    return f"{minutes} min {secondes:02d} s"


def carte(titre: str, contenu: RenderableType, bordure: str = "accent") -> Panel:
    return Panel(
        contenu,
        title=Text(f" {titre} ", style="titre"),
        title_align="left",
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


# ─── En-tête et cartes ────────────────────────────────────────────────────────
def entete(
    instant: Instantane, maintenant: datetime, disposition: Disposition, largeur: int
) -> RenderableType:
    gauche = Text.assemble(("◆ PSN AMIS", "accent"), (f" {moteur.VERSION}", "discret"))
    if largeur >= 90:
        gauche.append("   acceptation automatique des demandes d'amis", style="discret")
    droite = Text()
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


def ligne_detail(instant: Instantane) -> RenderableType:
    if instant.statut in STATUTS_ANIMES:
        animation = Spinner(
            "dots", text=Text(f" {instant.detail}", style="info"), style="info"
        )
        return une_ligne(animation)
    return Text(instant.detail, style="discret", no_wrap=True, overflow="ellipsis")


def compte_a_rebours(instant: Instantane) -> list[RenderableType] | None:
    """Texte « Vérification dans 12 s » et sa barre, ou None s'il n'y a pas d'attente."""
    if instant.prochaine_verification is None or instant.statut == Statut.PAUSE:
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


def carte_statut(instant: Instantane, gros: bool) -> Panel:
    couleur = APPARENCE[instant.statut][2]
    rebours = compte_a_rebours(instant)
    lignes: list[RenderableType] = [ligne_statut(instant)]
    if gros:
        lignes.append(ligne_detail(instant))
        lignes += rebours or [Text(""), Text("")]
        lignes.append(ligne_infos(instant))
    else:
        lignes += rebours or [ligne_detail(instant), Text("")]
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
    contenu = Group(
        nombre_carte(nombre, "succes", gros),
        ligne_centree(("ajout" if nombre == 1 else "ajouts", "discret")),
        info,
    )
    return carte("Aujourd'hui", contenu, bordure="succes" if recent else "accent")


def carte_session(
    instant: Instantane, maintenant: datetime, gros: bool, largeur_carte: int
) -> Panel:
    nombre = instant.ajouts_session
    depuis = duree_lisible((maintenant - instant.debut).total_seconds())
    contenu = Group(
        nombre_carte(nombre, "titre", gros),
        ligne_centree(("ajout" if nombre == 1 else "ajouts", "discret")),
        ligne_centree(
            ("lancé à ", "discret"),
            (instant.debut.strftime("%H:%M"), "info"),
            (f" · {depuis}", "discret"),
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


def carte_resume(instant: Instantane) -> Panel:
    """Fenêtre très étroite : l'essentiel sur une seule carte de trois lignes."""
    couleur = APPARENCE[instant.statut][2]
    rebours = compte_a_rebours(instant)
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
    deuxieme = rebours[0] if rebours else ligne_detail(instant)
    return carte(
        "PSN Amis", Group(ligne_statut(instant), deuxieme, chiffres), bordure=couleur
    )


# ─── Panneaux du bas ──────────────────────────────────────────────────────────
class ListeAjouts:
    """Contenu de « Derniers ajouts » : autant de lignes qu'il en tient en hauteur,
    et des colonnes qui disparaissent quand la largeur manque."""

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
        hauteur = options.height if options.height is not None else len(ajouts) + 1
        avec_numero = largeur >= 36
        avec_anciennete = largeur >= 46

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

        numero = self._instant.ajouts_jour
        # Une ligne est prise par les titres des colonnes.
        for ajout in ajouts[: max(hauteur - 1, 1)]:
            du_jour = ajout.moment.date() == self._maintenant.date()
            age = (self._maintenant - ajout.moment).total_seconds()
            cellules: list[RenderableType] = []
            if avec_numero:
                cellules.append(Text(str(numero) if du_jour else ""))
            cellules += [Text(ajout.moment.strftime("%H:%M:%S")), Text(ajout.pseudo)]
            if avec_anciennete:
                cellules.append(Text(il_y_a(ajout.moment, self._maintenant)))
            tableau.add_row(
                *cellules, style="nouveau" if age < DUREE_SURBRILLANCE else None
            )
            if du_jour:
                numero -= 1
        yield tableau


class FilActivite:
    """Contenu de « Activité » : chaque message en entier, renvoyé à la ligne si
    besoin, du plus récent au plus ancien, autant qu'il en tient en hauteur.
    Un message qui ne tient plus en entier n'est pas affiché à moitié."""

    def __init__(self, evenements: tuple[Evenement, ...]) -> None:
        self._evenements = evenements

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
        for evenement in self._evenements:
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


def panneau_activite(instant: Instantane) -> Panel:
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


def pied(instant: Instantane, interface: EtatInterface, largeur: int) -> Table | Text:
    if interface.confirmation_quitter():
        return Text(
            "  Appuyez encore sur Q pour quitter (toute autre touche annule)",
            style="alerte",
            no_wrap=True,
            overflow="ellipsis",
        )
    pause = "Reprendre" if instant.statut == Statut.PAUSE else "Pause"
    if largeur >= 96:
        libelles = (pause, "Vérifier maintenant", "Journal", "Code npsso", "Quitter")
    elif largeur >= 64:
        libelles = (pause, "Vérifier", "Journal", "Code", "Quitter")
    elif largeur >= 54:
        libelles = (pause.lower(), "vérif.", "journal", "code", "quitter")
    else:
        libelles = ("", "", "", "", "")
    # Moins de place : les touches se rapprochent.
    separation = "   " if largeur >= 64 else " "
    touches = Text(no_wrap=True, overflow="ellipsis")
    for rang, (lettre, libelle) in enumerate(zip("PVJCQ", libelles, strict=True)):
        if rang:
            touches.append(separation)
        touches.append(f" {lettre} ", style="touche")
        if libelle:
            touches.append(f" {libelle}", style="discret")

    message = interface.message_actuel()
    if message:
        droite = Text(message, style="info")
    else:
        droite = Text("journal.txt" if largeur >= 110 else "", style="discret")
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
    ecran = Layout()
    ecran.split_column(
        Layout(
            entete(instant, maintenant, disposition, largeur),
            size=disposition.hauteur_entete,
        ),
        Layout(name="cartes", size=disposition.hauteur_cartes),
        Layout(name="corps", ratio=1),
        Layout(pied(instant, interface, largeur), size=1),
    )

    gros = disposition.gros_chiffres
    if disposition.colonnes == 1:
        ecran["cartes"].update(carte_resume(instant))
    else:
        # Largeur approximative d'une carte, pour choisir des titres qui tiennent.
        largeur_carte = largeur * 2 // 9 if disposition.colonnes == 4 else largeur // 2
        cartes = [
            carte_statut(instant, gros),
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
    if instant.probleme_npsso:
        corps.update(panneau_npsso(instant))
    elif disposition.cote_a_cote:
        corps.split_row(
            Layout(panneau_ajouts(instant, maintenant), ratio=2),
            Layout(panneau_activite(instant), ratio=3),
        )
    elif disposition.avec_ajouts:
        corps.split_column(
            Layout(panneau_ajouts(instant, maintenant), ratio=2),
            Layout(panneau_activite(instant), ratio=3),
        )
    else:
        corps.update(panneau_activite(instant))
    return ecran


def titre_fenetre(instant: Instantane) -> str:
    libelle = APPARENCE[instant.statut][1].lower()
    pluriel = "s" if instant.ajouts_jour > 1 else ""
    return f"PSN Amis · {instant.ajouts_jour} ajout{pluriel} aujourd'hui · {libelle}"


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

    def confirmation_quitter(self) -> bool:
        return time.monotonic() < self.quitter_avant

    def informer(self, texte: str, secondes: float = 4.0) -> None:
        self.message = texte
        self.message_jusqua = time.monotonic() + secondes

    def message_actuel(self) -> str | None:
        return self.message if time.monotonic() < self.message_jusqua else None


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
                retires = (
                    self.TRAITEMENT_CTRL_C | self.SAISIE_SOURIS | self.EDITION_RAPIDE
                )
                nouveau = (mode.value | self.OPTIONS_ETENDUES) & ~retires
                self._k32.SetConsoleMode(entree, nouveau)
        return self

    def __exit__(self, *details: object) -> None:
        if self._k32 is not None and self._entree and self._mode_initial is not None:
            self._k32.SetConsoleMode(self._entree, self._mode_initial)

    def touches(self, attente_ms: int) -> list[str]:
        """Attend au plus attente_ms qu'une touche soit pressée ; renvoie les touches.

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
            # Touches spéciales (flèches, F1...) : deux caractères, ignorés.
            if touche in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue
            lues.append(touche)
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
    if lettre == "p":
        if commandes.basculer_pause():
            journal.info("Pause : les nouvelles demandes attendent (touche P).")
        else:
            journal.info("Reprise : les demandes sont de nouveau acceptées.")
    elif lettre == "v":
        commandes.verifier_maintenant()
        interface.informer("Vérification demandée…")
    elif lettre == "j":
        ouvrir_journal(interface)
    elif lettre == "c":
        return "configurer"
    return None


def changer_le_code(
    ecran: Live, console: Console, commandes: Commandes, interface: EtatInterface
) -> None:
    """Touche C : quitte l'écran du tableau de bord le temps de coller un nouveau code,
    puis y revient. Avec un code valide, le moteur se reconnecte à ce compte."""
    ecran.stop()
    try:
        console.clear()
        console.print(
            f"[accent]◆ PSN AMIS[/] [discret]{moteur.VERSION}[/]  ·  changer le code npsso"
        )
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
    console = Console(theme=THEME)
    interface = EtatInterface()
    titre_actuel = ""
    with (
        Clavier() as clavier,
        Live(console=console, screen=True, auto_refresh=False) as ecran,
    ):
        fil = demarrer_moteur()
        relance: float | None = None
        while True:
            instant = suivi.instantane()
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
                    changer_le_code(ecran, console, commandes, interface)
                elif action:
                    return action

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
