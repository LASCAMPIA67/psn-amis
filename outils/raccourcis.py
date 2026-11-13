"""Crée (ou retire) les raccourcis Windows de PSN Amis.

- Bureau : « PSN Amis », avec son icône, qui ouvre le tableau de bord.
- Démarrage de Windows (option --demarrage) : PSN Amis s'ouvre tout seul, en fenêtre
  réduite, à chaque ouverture de session.

Le plus simple : double-cliquez sur « Raccourcis PSN Amis.cmd ». Sinon, depuis le
dossier du projet :

    uv run outils/raccourcis.py                 raccourci sur le Bureau
    uv run outils/raccourcis.py --demarrage     Bureau + démarrage de Windows
    uv run outils/raccourcis.py --retirer       retire les deux raccourcis

Les raccourcis sont créés par Windows PowerShell (livré avec Windows), qui ne contacte
rien sur Internet.
"""

from __future__ import annotations

import argparse
import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
LANCEUR = RACINE / "Lancer PSN Amis.cmd"
ICONE = RACINE / "docs" / "images" / "icone.ico"
NOM = "PSN Amis.lnk"
# Style de fenêtre des raccourcis : 1 normale, 7 réduite.
FENETRE_NORMALE, FENETRE_REDUITE = 1, 7

# Les chemins arrivent par des variables d'environnement : aucun souci de guillemets,
# d'espaces ni d'accents dans les noms de dossiers.
SCRIPT_CREER = """
$shell = New-Object -ComObject WScript.Shell
$dossier = [Environment]::GetFolderPath($env:PSN_AMIS_DOSSIER)
$raccourci = $shell.CreateShortcut((Join-Path $dossier $env:PSN_AMIS_NOM))
$raccourci.TargetPath = $env:PSN_AMIS_LANCEUR
$raccourci.WorkingDirectory = $env:PSN_AMIS_RACINE
$raccourci.IconLocation = $env:PSN_AMIS_ICONE
$raccourci.WindowStyle = [int]$env:PSN_AMIS_FENETRE
$raccourci.Description = 'PSN Amis : acceptation automatique des demandes d''amis'
$raccourci.Save()
Write-Output (Join-Path $dossier $env:PSN_AMIS_NOM)
"""
SCRIPT_DOSSIER = "[Environment]::GetFolderPath($env:PSN_AMIS_DOSSIER)"


def powershell(script: str, **variables: str) -> str:
    """Lance un script Windows PowerShell et renvoie ce qu'il a écrit."""
    programme = shutil.which("powershell")
    if os.name != "nt" or programme is None:
        raise SystemExit("Les raccourcis ne peuvent être créés que sous Windows.")
    environnement = dict(os.environ)
    environnement.update(
        {f"PSN_AMIS_{cle}": valeur for cle, valeur in variables.items()}
    )
    encode = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    resultat = subprocess.run(  # noqa: S603 (programme de Windows, script fixe)
        [programme, "-NoProfile", "-NonInteractive", "-EncodedCommand", encode],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environnement,
        check=False,
    )
    if resultat.returncode != 0:
        raise SystemExit(f"Windows PowerShell a échoué : {resultat.stderr.strip()}")
    return resultat.stdout.strip()


def creer(dossier: str, fenetre: int) -> Path:
    """Crée le raccourci dans un dossier spécial de Windows (« Desktop », « Startup »)."""
    return Path(
        powershell(
            SCRIPT_CREER,
            DOSSIER=dossier,
            NOM=NOM,
            LANCEUR=str(LANCEUR),
            RACINE=str(RACINE),
            ICONE=f"{ICONE},0",
            FENETRE=str(fenetre),
        )
    )


def retirer(dossier: str) -> Path | None:
    """Retire le raccourci d'un dossier spécial ; renvoie son chemin s'il existait."""
    chemin = Path(powershell(SCRIPT_DOSSIER, DOSSIER=dossier)) / NOM
    if not chemin.exists():
        return None
    chemin.unlink()
    return chemin


def main() -> int:
    parametres = argparse.ArgumentParser(
        description="Crée ou retire les raccourcis Windows de PSN Amis."
    )
    choix = parametres.add_mutually_exclusive_group()
    choix.add_argument(
        "--demarrage",
        action="store_true",
        help="ajoute aussi le lancement automatique au démarrage de Windows",
    )
    choix.add_argument(
        "--retirer", action="store_true", help="retire les raccourcis créés"
    )
    options = parametres.parse_args()

    if options.retirer:
        for dossier, nom in (("Desktop", "Bureau"), ("Startup", "démarrage")):
            chemin = retirer(dossier)
            etat = f"retiré ({chemin})" if chemin else "absent"
            print(f"Raccourci {nom} : {etat}.")
        return 0

    if not LANCEUR.exists():
        raise SystemExit(f"Lanceur introuvable : {LANCEUR}")
    print(f"Raccourci sur le Bureau : {creer('Desktop', FENETRE_NORMALE)}")
    if options.demarrage:
        chemin = creer("Startup", FENETRE_REDUITE)
        print(f"Lancement au démarrage de Windows (fenêtre réduite) : {chemin}")
    print("Terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
