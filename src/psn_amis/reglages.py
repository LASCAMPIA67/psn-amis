"""Les réglages de PSN Amis, lus et écrits dans reglages.toml.

Une seule source de vérité : la classe Reglages ci-dessous. Chaque réglage y déclare sa
valeur par défaut, son type, ses bornes ou ses choix possibles, sa description et ce
qu'il faut pour qu'un changement s'applique (rien, redémarrage du moteur ou de
l'application). L'onglet Paramètres de l'application et le fichier reglages.toml
utilisent les mêmes règles de validation.

Un réglage absent prend sa valeur par défaut ; un réglage mal écrit est signalé
clairement et remplacé par sa valeur par défaut, sans arrêter PSN Amis. Le fichier est
écrit de façon atomique (fichier temporaire puis renommage), avec une copie de
l'ancienne version dans reglages.toml.bak.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import asdict, dataclass, field, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

# Version du format de reglages.toml. 1 : versions 2.x (sans ce numéro).
VERSION_FORMAT = 3
CLE_VERSION = "version_reglages"

THEMES = (
    "graphite",
    "minuit",
    "emeraude",
    "amethyste",
    "clair",
    "daltonien",
    "systeme",
)
# Anciens noms de thèmes (versions 2.x et format 2) : repris automatiquement.
ANCIENS_THEMES = {"sombre": "graphite", "doux": "minuit"}
ANIMATIONS = ("systeme", "activees", "coupees")


class Effet(StrEnum):
    """Ce qu'il faut pour qu'un changement de réglage prenne effet."""

    IMMEDIAT = "immédiat"
    MOTEUR = "redémarrage du moteur"
    APPLICATION = "redémarrage de l'application"


def _reglage(
    defaut: Any,
    groupe: str,
    libelle: str,
    description: str,
    *,
    bornes: tuple[float, float] | None = None,
    choix: tuple[str, ...] | None = None,
    effet: Effet = Effet.IMMEDIAT,
    unite: str = "",
) -> Any:
    meta = {
        "groupe": groupe,
        "libelle": libelle,
        "description": description,
        "bornes": bornes,
        "choix": choix,
        "effet": effet,
        "unite": unite,
    }
    if isinstance(defaut, list):
        return field(default_factory=lambda: list(defaut), metadata=meta)
    return field(default=defaut, metadata=meta)


MOTEUR = "Moteur"
DEMANDES = "Demandes"
AMIS = "Gestion des amis"
NETTOYAGE = "Nettoyage automatique"
APPLICATION = "Application"

CRITERES = ("plus_anciens_acceptes", "premiere_observation", "alphabetique")


@dataclass
class Reglages:
    """Tous les réglages, avec leurs valeurs par défaut et leur description."""

    # ─── Moteur ───
    acceptation_auto: bool = _reglage(
        True,
        MOTEUR,
        "Accepter automatiquement les demandes d'amis",
        "Les demandes d'amis ordinaires sont acceptées dès qu'elles arrivent.",
    )
    intervalle_verification: int = _reglage(
        15,
        MOTEUR,
        "Intervalle de vérification",
        "Secondes entre deux vérifications (demandes reçues, puis liste d'amis). "
        "Avec 15, PSN Amis fait 8 requêtes par minute quand il ne se passe rien ; "
        "PSNAWP, la bibliothèque utilisée, en autorise 20.",
        bornes=(5, 3600),
        unite="s",
    )
    pause_entre_acceptations: float = _reglage(
        2,
        MOTEUR,
        "Pause entre deux acceptations",
        "Secondes d'attente entre deux acceptations.",
        bornes=(0, 60),
        unite="s",
    )
    pause_apres_ajouts: int = _reglage(
        0,
        MOTEUR,
        "Pause automatique après",
        "Pause automatique après ce nombre d'ajouts depuis la dernière reprise "
        "(par exemple quand une partie est pleine). 0 : jamais.",
        bornes=(0, 10000),
        unite="ajouts",
    )
    limite_amis: int = _reglage(
        2000,
        MOTEUR,
        "Capacité de la liste d'amis",
        "Nombre maximum d'amis sur un compte PSN (limite officielle de Sony : 2000).",
        bornes=(1, 10000),
        unite="amis",
    )
    notifications: bool = _reglage(
        True,
        MOTEUR,
        "Notifications Windows",
        "Bulles de notification pour les événements importants seulement : code npsso "
        "à changer, liste d'amis pleine, coupure Internet qui dure, mise à jour.",
    )
    son: bool = _reglage(
        False, MOTEUR, "Son à chaque ajout", "Petit bip à chaque demande acceptée."
    )
    # ─── Demandes ───
    liste_noire: list[str] = _reglage(
        [],
        DEMANDES,
        "Liste noire",
        "Pseudos (ou identifiants de compte) dont les demandes ne sont jamais "
        "acceptées. Majuscules et minuscules sans importance.",
    )
    liste_noire_refuser: bool = _reglage(
        False,
        DEMANDES,
        "Refuser les demandes de la liste noire",
        "Au lieu de les laisser en attente, les demandes de la liste noire sont "
        "refusées (opération PSNAWP documentée : refus d'une demande reçue). Jamais "
        "appliqué à un joueur qui est déjà votre ami.",
    )
    liste_blanche: list[str] = _reglage(
        [],
        DEMANDES,
        "Liste blanche d'acceptation",
        "Si elle n'est pas vide, seules les demandes de ces pseudos (ou identifiants) "
        "sont acceptées. Ne protège pas contre la suppression : voir « Amis protégés ».",
    )
    demandes_non_reconnues: str = _reglage(
        "laisser",
        DEMANDES,
        "Demandes d'un type non reconnu",
        "Que faire d'une demande dont Sony indique un type inconnu de PSN Amis : la "
        "laisser en attente (prudent) ou l'accepter comme une demande ordinaire.",
        choix=("laisser", "accepter"),
    )
    refuser_demandes_ami_proche: bool = _reglage(
        False,
        DEMANDES,
        "Refuser automatiquement les demandes d'ami proche",
        "Indisponible : la bibliothèque PSNAWP ne propose aucune opération pour refuser "
        "une demande d'ami proche sans supprimer l'ami lui-même. Ces demandes restent "
        "en attente ; répondez-y depuis votre console ou l'appli PlayStation.",
    )
    # ─── Gestion des amis ───
    suppression_pause: float = _reglage(
        10,
        AMIS,
        "Pause entre deux suppressions",
        "Secondes d'attente entre deux suppressions d'amis. Chaque suppression coûte "
        "deux requêtes (vérification puis suppression).",
        bornes=(3, 600),
        unite="s",
    )
    suppression_max: int = _reglage(
        100,
        AMIS,
        "Suppressions par opération",
        "Nombre maximum d'amis supprimés en une seule opération.",
        bornes=(1, 500),
        unite="amis",
    )
    # ─── Nettoyage automatique ───
    nettoyage_mode: str = _reglage(
        "manuel",
        NETTOYAGE,
        "Mode de nettoyage",
        "manuel : vous choisissez tout. assisté : quand la liste dépasse le seuil, "
        "PSN Amis prépare une sélection et vous demande confirmation. automatique : "
        "PSN Amis supprime lui-même, dans les limites ci-dessous. Les amis protégés "
        "ne sont jamais concernés.",
        choix=("manuel", "assiste", "automatique"),
    )
    nettoyage_seuil: int = _reglage(
        1900,
        NETTOYAGE,
        "Seuil de déclenchement",
        "Le nettoyage est proposé quand la liste atteint ce nombre d'amis.",
        bornes=(10, 10000),
        unite="amis",
    )
    nettoyage_cible: int = _reglage(
        1700,
        NETTOYAGE,
        "Capacité cible",
        "Nombre d'amis visé après le nettoyage (inférieur au seuil).",
        bornes=(0, 10000),
        unite="amis",
    )
    nettoyage_max_par_cycle: int = _reglage(
        25,
        NETTOYAGE,
        "Suppressions par nettoyage",
        "Nombre maximum de suppressions lors d'un même nettoyage.",
        bornes=(1, 200),
        unite="amis",
    )
    nettoyage_max_par_jour: int = _reglage(
        100,
        NETTOYAGE,
        "Suppressions par jour",
        "Nombre maximum de suppressions automatiques par jour.",
        bornes=(1, 1000),
        unite="amis",
    )
    nettoyage_intervalle: int = _reglage(
        60,
        NETTOYAGE,
        "Délai entre deux nettoyages",
        "Minutes minimum entre deux nettoyages, pour éviter un cycle "
        "suppression / acceptation trop rapide.",
        bornes=(10, 1440),
        unite="min",
    )
    nettoyage_critere: str = _reglage(
        "plus_anciens_acceptes",
        NETTOYAGE,
        "Critère de sélection",
        "plus_anciens_acceptes : les amis acceptés par PSN Amis il y a le plus "
        "longtemps (date connue). premiere_observation : les amis vus en premier par "
        "PSN Amis dans votre liste (ce n'est pas la date d'amitié réelle). "
        "alphabetique : ordre alphabétique des pseudos.",
        choix=CRITERES,
    )
    nettoyage_heures: str = _reglage(
        "",
        NETTOYAGE,
        "Heures autorisées",
        "Plage horaire pendant laquelle le nettoyage automatique est permis, par "
        "exemple « 02-07 » (de 2 h à 7 h). Vide : à toute heure.",
    )
    # ─── Application ───
    theme: str = _reglage(
        "graphite",
        APPLICATION,
        "Thème",
        "graphite (Graphite Premium), minuit (Bleu Minuit), emeraude (Émeraude), "
        "amethyste (Améthyste), clair (Clair Élégant), daltonien (contraste pour "
        "daltoniens) ou systeme (suit le mode clair ou sombre de Windows). "
        "S'applique tout de suite.",
        choix=THEMES,
    )
    animations: str = _reglage(
        "systeme",
        APPLICATION,
        "Animations",
        "systeme : suit le réglage « Effets d'animation » de Windows. activees : "
        "transitions et effets discrets. coupees : aucune animation (affichage "
        "instantané).",
        choix=ANIMATIONS,
    )
    verifier_mises_a_jour: bool = _reglage(
        False,
        APPLICATION,
        "Vérifier les mises à jour au lancement",
        "Demande à GitHub si une nouvelle version stable existe. C'est la seule "
        "requête qui ne va pas chez Sony ; elle n'envoie rien d'autre que la demande.",
    )
    demarrage_windows: bool = _reglage(
        False,
        APPLICATION,
        "Lancer PSN Amis avec Windows",
        "Ouvre PSN Amis à l'ouverture de votre session Windows.",
    )
    demarrage_reduit: bool = _reglage(
        False,
        APPLICATION,
        "Démarrer réduit",
        "La fenêtre démarre réduite (dans la zone de notification si elle est activée).",
    )
    zone_notification: bool = _reglage(
        False,
        APPLICATION,
        "Icône dans la zone de notification",
        "Affiche une icône près de l'horloge ; la fenêtre réduite s'y range.",
    )
    fermeture: str = _reglage(
        "quitter",
        APPLICATION,
        "Fermeture de la fenêtre",
        "quitter : la croix arrête PSN Amis. reduire : la croix range la fenêtre dans "
        "la zone de notification et PSN Amis continue.",
        choix=("quitter", "reduire"),
    )
    journaux_archives: int = _reglage(
        3,
        APPLICATION,
        "Archives du journal",
        "Nombre d'anciens journaux gardés (1 Mo chacun) avant suppression du plus "
        "ancien.",
        bornes=(1, 20),
        effet=Effet.APPLICATION,
    )
    coffre_windows: bool = _reglage(
        True,
        APPLICATION,
        "Code npsso dans le coffre de Windows",
        "Garde le code npsso dans le Gestionnaire d'identification de Windows (chiffré "
        "par votre session) plutôt que dans un fichier npsso.txt.",
        effet=Effet.MOTEUR,
    )


CHAMPS = {champ.name: champ for champ in fields(Reglages)}
# Bornes des réglages numériques : (minimum, maximum).
BORNES = {
    nom: c.metadata["bornes"] for nom, c in CHAMPS.items() if c.metadata["bornes"]
}
ENTIERS = {nom for nom, c in CHAMPS.items() if c.type == "int"}


def info(nom: str) -> dict[str, Any]:
    """Libellé, description, bornes, choix et effet d'un réglage."""
    return dict(CHAMPS[nom].metadata)


# ─── Validation ───────────────────────────────────────────────────────────────


def verifier(cle: str, valeur: object) -> str | None:
    """Le message d'erreur pour une valeur inacceptable, ou None si elle convient."""
    if cle not in CHAMPS:
        return f"réglage inconnu « {cle} »."
    defaut = getattr(Reglages(), cle)
    meta = CHAMPS[cle].metadata
    if isinstance(defaut, bool):
        if not isinstance(valeur, bool):
            return f"« {cle} » doit valoir true ou false."
        return None
    if isinstance(defaut, int | float):
        if isinstance(valeur, bool) or not isinstance(valeur, int | float):
            return f"« {cle} » doit être un nombre."
        if cle in ENTIERS and valeur != int(valeur):
            return f"« {cle} » doit être un nombre entier."
        minimum, maximum = meta["bornes"]
        if not minimum <= valeur <= maximum:
            return (
                f"« {cle} » doit être entre {minimum:g} et {maximum:g}, pas {valeur}."
            )
        return None
    if isinstance(defaut, str):
        if not isinstance(valeur, str):
            return f"« {cle} » doit être un texte entre guillemets."
        choix = meta["choix"]
        if choix and valeur.strip().lower() not in choix:
            return (
                f"« {cle} » doit être {', '.join(choix[:-1])} ou {choix[-1]}, "
                f"pas « {valeur} »."
            )
        if (
            cle == "nettoyage_heures"
            and valeur.strip()
            and plage_horaire(valeur) is None
        ):
            return (
                "« nettoyage_heures » doit ressembler à « 02-07 » (heures de 0 à 23)."
            )
        return None
    if isinstance(defaut, list):
        if not isinstance(valeur, list) or not all(isinstance(v, str) for v in valeur):
            return f"« {cle} » doit être une liste de pseudos entre guillemets."
        return None
    return None


def normaliser(cle: str, valeur: Any) -> Any:
    if isinstance(valeur, str):
        valeur = valeur.strip()
        return valeur.lower() if CHAMPS[cle].metadata["choix"] else valeur
    if cle in ENTIERS and not isinstance(valeur, bool):
        return int(valeur)
    if isinstance(valeur, list):
        vus: list[str] = []
        for v in (v.strip() for v in valeur):
            if v and v.casefold() not in {x.casefold() for x in vus}:
                vus.append(v)
        return vus
    return valeur


def coherence(reglages: Reglages) -> list[str]:
    """Problèmes qui portent sur plusieurs réglages à la fois."""
    problemes = []
    if reglages.nettoyage_cible >= reglages.nettoyage_seuil:
        problemes.append(
            "La capacité cible du nettoyage doit être inférieure au seuil de "
            "déclenchement."
        )
    if reglages.nettoyage_seuil > reglages.limite_amis:
        problemes.append(
            "Le seuil de nettoyage ne peut pas dépasser la capacité de la liste d'amis."
        )
    return problemes


def modifier(reglages: Reglages, **changements: Any) -> tuple[Reglages, list[str]]:
    """Renvoie (nouveaux réglages, problèmes). Rien n'est modifié s'il y a un problème."""
    problemes = []
    propres = {}
    for cle, valeur in changements.items():
        probleme = verifier(cle, valeur)
        if probleme:
            problemes.append(probleme)
        else:
            propres[cle] = normaliser(cle, valeur)
    if problemes:
        return reglages, problemes
    nouveaux = replace(reglages, **propres)
    problemes = coherence(nouveaux)
    return (reglages, problemes) if problemes else (nouveaux, [])


def plage_horaire(texte: str) -> tuple[int, int] | None:
    """« 02-07 » → (2, 7) ; None si le texte n'est pas une plage valide."""
    morceaux = texte.replace(" ", "").split("-")
    if len(morceaux) != 2 or not all(m.isdigit() for m in morceaux):
        return None
    debut, fin = (int(m) for m in morceaux)
    if not (0 <= debut <= 23 and 0 <= fin <= 23) or debut == fin:
        return None
    return debut, fin


# ─── Lecture ──────────────────────────────────────────────────────────────────


def charger(chemin: Path) -> tuple[Reglages, list[str]]:
    """Lit le fichier et renvoie (réglages, liste des problèmes rencontrés).

    Un problème ne bloque rien : le réglage fautif garde sa valeur par défaut.
    """
    reglages = Reglages()
    try:
        brut = chemin.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return reglages, []
    except OSError as erreur:
        return reglages, [f"{chemin.name} : impossible de lire le fichier ({erreur})."]
    try:
        donnees = tomllib.loads(brut)
    except tomllib.TOMLDecodeError as erreur:
        return reglages, [f"{chemin.name} : le fichier est mal écrit ({erreur})."]
    return depuis_dictionnaire(donnees, chemin.name)


def depuis_dictionnaire(
    donnees: dict[str, Any], origine: str = "reglages.toml"
) -> tuple[Reglages, list[str]]:
    donnees = migrer(dict(donnees))
    reglages = Reglages()
    problemes: list[str] = []
    for cle, valeur in donnees.items():
        if cle == CLE_VERSION:
            continue
        probleme = verifier(cle, valeur)
        if probleme:
            garde = "ignoré" if cle not in CHAMPS else "valeur par défaut gardée"
            problemes.append(f"{origine} : {probleme} ({garde})")
            continue
        setattr(reglages, cle, normaliser(cle, valeur))
    for probleme in coherence(reglages):
        problemes.append(f"{origine} : {probleme} (nettoyage laissé en mode manuel)")
        reglages.nettoyage_mode = "manuel"
    return reglages, problemes


def migrer(donnees: dict[str, Any]) -> dict[str, Any]:
    """Met des réglages d'un ancien format au format actuel (VERSION_FORMAT).

    Format 1 (versions 2.x) : mêmes noms, mêmes valeurs ; seul le numéro de format
    manque. Format 3 : les thèmes « sombre » et « doux » deviennent « graphite » et
    « minuit » (repris même dans un fichier modifié à la main).
    """
    version = donnees.get(CLE_VERSION, 1)
    if not isinstance(version, int) or version < 1:
        version = 1
    theme = donnees.get("theme")
    if isinstance(theme, str) and theme.strip().lower() in ANCIENS_THEMES:
        donnees["theme"] = ANCIENS_THEMES[theme.strip().lower()]
    donnees[CLE_VERSION] = VERSION_FORMAT
    return donnees


def format_du_fichier(chemin: Path) -> int | None:
    """Le numéro de format d'un reglages.toml existant (1 s'il n'en a pas)."""
    try:
        donnees = tomllib.loads(chemin.read_text(encoding="utf-8-sig"))
    except OSError, tomllib.TOMLDecodeError:
        return None
    version = donnees.get(CLE_VERSION, 1)
    return version if isinstance(version, int) else 1


# ─── Écriture ─────────────────────────────────────────────────────────────────


def _valeur_toml(valeur: Any) -> str:
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, int):
        return str(valeur)
    if isinstance(valeur, float):
        return str(int(valeur)) if valeur.is_integer() else repr(valeur)
    if isinstance(valeur, str):
        echappe = valeur.replace("\\", "\\\\").replace('"', '\\"')
        echappe = "".join(c if c >= " " else f"\\u{ord(c):04x}" for c in echappe)
        return f'"{echappe}"'
    if isinstance(valeur, list):
        return "[" + ", ".join(_valeur_toml(v) for v in valeur) + "]"
    raise TypeError(f"type non pris en charge : {type(valeur).__name__}")


def _commentaire(texte: str, largeur: int = 86) -> list[str]:
    lignes: list[str] = []
    courante = "#"
    for mot in texte.split():
        if len(courante) + 1 + len(mot) > largeur:
            lignes.append(courante)
            courante = "#"
        courante += " " + mot
    lignes.append(courante)
    return lignes


def en_texte(reglages: Reglages) -> str:
    """Le contenu complet de reglages.toml, chaque réglage expliqué en commentaire."""
    lignes = [
        "# Réglages de PSN Amis.",
        "#",
        "# Le plus simple est de les changer dans l'onglet Paramètres de l'application.",
        "# Ce fichier peut aussi être modifié avec le Bloc-notes, application fermée.",
        "# Un réglage absent garde sa valeur par défaut ; un réglage mal écrit est",
        "# signalé au démarrage, et sa valeur par défaut est utilisée.",
        "",
        f"{CLE_VERSION} = {VERSION_FORMAT}",
    ]
    groupe_courant = None
    for nom, champ in CHAMPS.items():
        meta = champ.metadata
        if meta["groupe"] != groupe_courant:
            groupe_courant = meta["groupe"]
            lignes += ["", f"# ─── {groupe_courant} ───"]
        lignes.append("")
        texte = f"{meta['libelle']}. {meta['description']}"
        if meta["bornes"]:
            minimum, maximum = meta["bornes"]
            texte += f" Entre {minimum:g} et {maximum:g}."
        if meta["choix"]:
            texte += " Choix : " + ", ".join(f'"{c}"' for c in meta["choix"]) + "."
        lignes += _commentaire(texte)
        lignes.append(f"{nom} = {_valeur_toml(getattr(reglages, nom))}")
    return "\n".join(lignes) + "\n"


def ecrire_atomique(chemin: Path, texte: str) -> None:
    """Écrit un fichier sans jamais laisser une version à moitié écrite."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_name(chemin.name + ".tmp")
    with temporaire.open("w", encoding="utf-8", newline="\n") as fichier:
        fichier.write(texte)
        fichier.flush()
        os.fsync(fichier.fileno())
    temporaire.replace(chemin)


def enregistrer(reglages: Reglages, chemin: Path) -> None:
    """Enregistre les réglages ; l'ancienne version est gardée dans reglages.toml.bak."""
    if chemin.exists():
        shutil.copy2(chemin, chemin.with_name(chemin.name + ".bak"))
    ecrire_atomique(chemin, en_texte(reglages))


def creer_si_absent(chemin: Path) -> bool:
    """Crée reglages.toml avec les valeurs par défaut s'il n'existe pas ; True si créé."""
    if chemin.exists():
        return False
    ecrire_atomique(chemin, en_texte(Reglages()))
    return True


def mettre_a_jour_le_format(chemin: Path) -> bool:
    """Réécrit un reglages.toml d'un ancien format, après en avoir gardé une copie.

    La copie s'appelle reglages.v1.toml (selon l'ancien numéro) et n'est jamais
    remplacée. Les valeurs fautives ne sont pas perdues : le fichier n'est réécrit que
    s'il se lit sans aucun problème. Renvoie True si le fichier a été réécrit.
    """
    ancien = format_du_fichier(chemin)
    if ancien is None or ancien >= VERSION_FORMAT:
        return False
    lus, problemes = charger(chemin)
    if problemes:
        return False
    sauvegarde = chemin.with_name(f"reglages.v{ancien}.toml")
    if not sauvegarde.exists():
        shutil.copy2(chemin, sauvegarde)
    ecrire_atomique(chemin, en_texte(lus))
    return True


# ─── Import et export ─────────────────────────────────────────────────────────


def exporter(reglages: Reglages, chemin: Path) -> None:
    """Exporte les réglages (aucun secret : le code npsso n'est pas un réglage)."""
    ecrire_atomique(chemin, en_texte(reglages))


def importer(chemin: Path) -> tuple[Reglages, list[str]]:
    """Lit un fichier exporté ; à l'appelant de décider s'il l'applique."""
    return charger(chemin)


def en_dictionnaire(reglages: Reglages) -> dict[str, Any]:
    return asdict(reglages)
