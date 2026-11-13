"""Mode démonstration (--demo) : PSN Amis avec un faux compte, sans jamais contacter Sony.

Utile pour découvrir l'application, faire des captures d'écran ou vérifier un
exécutable compilé : aucun code npsso n'est lu, aucune requête ne part, et les données
vont dans un dossier temporaire (jamais le vrai dossier des données).
"""

from __future__ import annotations

import os
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

from psn_amis import chemins
from psn_amis.simulation import ConnexionSimulee, SonySimule, animer

# Faux Sony partagé par toute l'application pendant la démonstration.
SONY: SonySimule | None = None
_arret = threading.Event()


def dossier() -> Path:
    return Path(tempfile.gettempdir()) / "psn-amis-demo"


def preparer() -> Path:
    """À appeler avant de charger le moteur : données dans un dossier temporaire."""
    cible = dossier()
    os.environ[chemins.VARIABLE_DONNEES] = str(cible)
    chemins.preparer(cible)
    reglages = cible / "reglages.toml"
    if not reglages.exists():
        reglages.write_text(
            "coffre_windows = false\nnotifications = false\n"
            "intervalle_verification = 5\npause_entre_acceptations = 1\n"
            "suppression_pause = 3\n",
            encoding="utf-8",
        )
    return cible


def fabriquer() -> SonySimule:
    """Un compte de démonstration avec des amis et quelques demandes en attente."""
    sony = SonySimule(nombre_amis=180)
    for minutes in (2, 9, 27):
        sony.recevoir(il_y_a=timedelta(minutes=minutes))
    # Une demande d'ami proche venue d'un ami existant : jamais touchée.
    ami = min(sony.amis)
    sony.recevoir(ami, relation="friend", partage="requested")
    return sony


def brancher() -> SonySimule:
    """Remplace les fonctions du moteur qui parlent à Sony par le faux Sony."""
    global SONY
    from psn_amis import moteur

    sony = fabriquer()
    SONY = sony
    connexion = ConnexionSimulee(sony)
    moteur.lire_npsso = lambda: "demo"
    moteur.code_present = lambda: True
    moteur.ouvrir_connexion = lambda npsso: connexion
    moteur.demandes_recues = sony.demandes_recues
    moteur.liste_amis = sony.liste_amis
    moteur.trouver_joueur = sony.trouver_joueur
    moteur.client_psn = lambda connexion: sony
    moteur.signaler_nouvelle_version = lambda: None
    dossier_compte = chemins.dossier_donnees() / "comptes" / sony.compte
    if not (dossier_compte / "amis_connus.json").exists():
        dossier_compte.mkdir(parents=True, exist_ok=True)
        historique_de_demo(dossier_compte, sony)
    threading.Thread(
        target=animer, args=(sony, _arret), name="demo", daemon=True
    ).start()
    return sony


def arreter() -> None:
    _arret.set()


def historique_de_demo(registre_dossier: Path, sony: SonySimule) -> None:
    """Quelques dates d'acceptation connues, pour que les critères aient à travailler."""
    from psn_amis.amis import Registre

    registre = Registre(registre_dossier / "amis_connus.json")
    debut = datetime.now() - timedelta(days=40)
    for rang, compte in enumerate(sorted(sony.amis)[:120]):
        registre.accepte(
            compte, sony.pseudos[compte], debut + timedelta(hours=7 * rang)
        )
    registre.enregistrer()
