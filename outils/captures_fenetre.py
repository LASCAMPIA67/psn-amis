"""Captures d'écran de la fenêtre, en mode démonstration (faux compte, aucune requête).

Depuis le dossier du projet :

    uv run outils/captures_fenetre.py --sortie docs/images
    uv run outils/captures_fenetre.py --theme clair --sortie captures

Fonctionne aussi sans écran (QT_QPA_PLATFORM=offscreen, intégration continue).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

PAGES = ("tableau-de-bord", "activite", "amis", "demandes", "parametres", "a-propos")


def main() -> int:
    parametres = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parametres.add_argument("--sortie", type=Path, default=RACINE / "captures")
    parametres.add_argument("--theme", default="graphite")
    parametres.add_argument("--attente", type=float, default=8.0)
    parametres.add_argument("--taille", default="1280x800", help="largeur x hauteur")
    choix = parametres.parse_args()

    # Données de démonstration dans un dossier neuf, effacé à la fin.
    donnees = Path(tempfile.mkdtemp(prefix="psn-amis-captures-"))
    os.environ["PSN_AMIS_DONNEES"] = str(donnees)
    (donnees / "reglages.toml").write_text(
        f'coffre_windows = false\nnotifications = false\ntheme = "{choix.theme}"\n'
        "intervalle_verification = 5\npause_entre_acceptations = 0.5\n",
        encoding="utf-8",
    )

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from psn_amis import demo, moteur
    from psn_amis.controleur import Controleur
    from psn_amis.ui import theme
    from psn_amis.ui.commun import PontJournal, VersInterface
    from psn_amis.ui.fenetre import Fenetre

    application = QApplication(sys.argv[:1])
    reglages, _ = moteur.charger_reglages()
    demo.brancher()
    pont = PontJournal()
    moteur.configurer_journal(ecran=False, fichier=True)
    moteur.journal.addHandler(VersInterface(pont))
    controleur = Controleur(moteur.Suivi(), moteur.FICHIER_REGLAGES, donnees, reglages)
    theme.appliquer(application, choix.theme)
    fenetre = Fenetre(
        controleur,
        pont,
        application.windowIcon(),
        lambda: None,
        ["Mode démonstration : faux compte, aucune connexion à Sony."],
    )
    largeur, hauteur = (int(v) for v in choix.taille.lower().split("x"))
    fenetre.resize(largeur, hauteur)
    fenetre.show()
    controleur.demarrer()

    def patienter(secondes: float) -> None:
        boucle = QEventLoop()
        QTimer.singleShot(int(secondes * 1000), boucle.quit)
        boucle.exec()

    patienter(choix.attente)
    controleur.gestion.demander_pseudos(60)
    controleur.verifier_maintenant()
    patienter(3)
    choix.sortie.mkdir(parents=True, exist_ok=True)
    for rang, nom in enumerate(PAGES):
        fenetre.aller(rang)
        fenetre.actualiser()
        patienter(0.6)
        chemin = choix.sortie / f"fenetre-{nom}-{choix.theme}.png"
        fenetre.grab().save(str(chemin))
        print(chemin)
    controleur.attendre_arret(10)
    demo.arreter()
    fenetre.quitter()
    shutil.rmtree(donnees, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
