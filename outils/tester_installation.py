"""Teste l'installateur pour de vrai : installation, mise à niveau, désinstallations.

Depuis le dossier du projet, après « uv run outils/construire.py » (Windows) :

    uv run outils/tester_installation.py

Tout se passe dans des dossiers temporaires et pour l'utilisateur courant :
- installation dans un dossier dont le nom contient des espaces et des accents ;
- données de test dans un dossier temporaire (paramètre /DONNEES=), jamais
  %LOCALAPPDATA%\\PSN Amis ;
- code de test « PSN Amis/test-desinstallation » dans le Gestionnaire
  d'identification, jamais le vrai code de PSN Amis ;
- l'application installée n'est lancée qu'en mode démonstration (aucune connexion).
À la fin, PSN Amis est désinstallé : la machine revient à son état de départ.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from psn_amis import __version__, coffre  # noqa: E402

CLE = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    r"\{8F3B2C7A-5D41-4E9B-9C6E-2A7F1D3B4C59}_is1"
)
CIBLE_TEST = "PSN Amis/test-desinstallation"
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
SETUP = RACINE / "dist" / f"PSN-Amis-Setup-{__version__}.exe"
PROGRAMMES = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs"
BUREAU = Path(os.environ["USERPROFILE"]) / "Desktop"

resultats: list[tuple[bool, str]] = []


def verifier(condition: bool, texte: str) -> None:
    resultats.append((condition, texte))
    print(("  ✔ " if condition else "  ✖ ") + texte, flush=True)


def entree_registre() -> dict[str, str] | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE) as cle:
            valeurs = {}
            for nom in (
                "DisplayName",
                "DisplayVersion",
                "Publisher",
                "InstallLocation",
            ):
                valeurs[nom] = str(winreg.QueryValueEx(cle, nom)[0])
            return valeurs
    except OSError:
        return None


def demarrage_present() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN) as cle:
            winreg.QueryValueEx(cle, "PSN Amis")
    except OSError:
        return False
    return True


def installer(dossier: Path | None, journal: Path, *taches: str) -> int:
    commande = [
        str(SETUP),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        f"/LOG={journal}",
    ]
    if dossier is not None:
        commande.append(f"/DIR={dossier}")
    if taches:
        commande.append(f"/TASKS={','.join(taches)}")
    return subprocess.run(commande, check=False, timeout=300).returncode  # noqa: S603


def desinstaller(dossier: Path, journal: Path, *parametres: str) -> None:
    programme = dossier / "unins000.exe"
    subprocess.run(  # noqa: S603
        [
            str(programme),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            f"/LOG={journal}",
            *parametres,
        ],
        check=False,
        timeout=300,
    )
    # Le programme de désinstallation se relance depuis le dossier temporaire :
    # on attend que l'entrée de Windows disparaisse.
    fin = time.monotonic() + 120
    while time.monotonic() < fin and (entree_registre() or programme.exists()):
        time.sleep(0.5)


def donnees_de_test(dossier: Path) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "psn-amis.donnees").write_text("témoin", encoding="utf-8")
    (dossier / "reglages.toml").write_text("son = true\n", encoding="utf-8")
    (dossier / "journal.txt").write_text("journal de test\n", encoding="utf-8")
    (dossier / "journal.txt.1").write_text("archive\n", encoding="utf-8")
    compte = dossier / "comptes" / "1000000000000000001"
    compte.mkdir(parents=True, exist_ok=True)
    (compte / "amis_proteges.json").write_text('{"proteges": []}', encoding="utf-8")
    # Un fichier qui n'est pas à PSN Amis : il ne doit jamais être effacé.
    (dossier / "note-personnelle.txt").write_text("à moi", encoding="utf-8")


def main() -> int:
    if os.name != "nt" or not SETUP.is_file():
        raise SystemExit(f"Construisez d'abord l'installateur : {SETUP}")
    if entree_registre() is not None or demarrage_present():
        raise SystemExit(
            "PSN Amis est déjà installé (ou lancé avec Windows) : désinstallez-le "
            "avant ce test."
        )
    travail = Path(tempfile.mkdtemp(prefix="psn-amis-installation-"))
    dossier = travail / "Mes Programmes é à ü" / "PSN Amis"
    donnees = travail / "Données de test"
    journaux = travail / "journaux"
    journaux.mkdir()
    try:
        print("1. Installation dans un dossier avec espaces et accents")
        code = installer(dossier, journaux / "installation.log", "bureau")
        verifier(code == 0, f"installateur terminé (code {code})")
        exe = dossier / "PSN Amis.exe"
        verifier(exe.is_file(), "PSN Amis.exe installé")
        verifier((dossier / "PSN Amis console.exe").is_file(), "console installée")
        verifier((dossier / "LICENCES-TIERS.txt").is_file(), "licences tierces")
        verifier(
            (PROGRAMMES / "PSN Amis" / "PSN Amis.lnk").is_file(),
            "raccourci du menu Démarrer",
        )
        verifier(
            (PROGRAMMES / "PSN Amis" / "Désinstaller PSN Amis.lnk").is_file(),
            "désinstallation dans le menu Démarrer",
        )
        verifier((BUREAU / "PSN Amis.lnk").is_file(), "raccourci Bureau (demandé)")
        entree = entree_registre()
        verifier(entree is not None, "présent dans les applications installées")
        if entree:
            verifier(entree["DisplayVersion"] == __version__, "version affichée")
            verifier(entree["Publisher"] == "LASCAMPIA67", "éditeur affiché")
            verifier(
                Path(entree["InstallLocation"].rstrip("\\")) == dossier,
                "dossier d'installation enregistré",
            )

        print("2. Démarrage sans Python ni uv (environnement minimal)")
        minimal = {
            "SystemRoot": os.environ["SYSTEMROOT"],
            "PATH": str(Path(os.environ["SYSTEMROOT"]) / "System32"),
            "TEMP": str(travail),
            "TMP": str(travail),
            "LOCALAPPDATA": str(travail / "localappdata"),
            "APPDATA": str(travail / "appdata"),
            "USERPROFILE": os.environ["USERPROFILE"],
            "QT_QPA_PLATFORM": "offscreen",
            # Premier lancement : dossier des données absent, comme sur un PC neuf
            # (démonstration : aucune connexion à Sony).
            "PSN_AMIS_DONNEES": str(travail / "localappdata" / "PSN Amis"),
        }
        sortie = subprocess.run(  # noqa: S603
            [str(dossier / "PSN Amis console.exe"), "--test", "--demo"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=minimal,
            timeout=120,
            check=False,
        )
        verifier(
            sortie.returncode == 0 and "Mode test terminé" in sortie.stdout,
            "console installée : démonstration complète",
        )
        fenetre = subprocess.run(  # noqa: S603
            [str(exe), "--demo", "--verifier", "6"],
            env=minimal,
            timeout=120,
            check=False,
        )
        verifier(fenetre.returncode == 0, "fenêtre installée : démarrage et fermeture")
        verifier(
            (travail / "localappdata" / "PSN Amis" / "psn-amis.donnees").is_file(),
            "premier lancement : dossier des données créé",
        )

        print("3. Mise à niveau : même dossier, données conservées")
        donnees_de_test(donnees)
        code = installer(None, journaux / "mise-a-niveau.log")
        verifier(code == 0, "mise à niveau silencieuse terminée")
        entree = entree_registre()
        verifier(
            entree is not None
            and Path(entree["InstallLocation"].rstrip("\\")) == dossier,
            "dossier précédent réutilisé",
        )
        verifier(
            (donnees / "reglages.toml").read_text(encoding="utf-8") == "son = true\n",
            "données de l'utilisateur intactes",
        )

        print("4. Désinstallation standard (niveau 1)")
        # Comme l'option « Lancer PSN Amis avec Windows » de l'application installée.
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE
        ) as cle:
            winreg.SetValueEx(cle, "PSN Amis", 0, winreg.REG_SZ, f'"{exe}" --reduit')
        desinstaller(
            dossier, journaux / "niveau1.log", "/NIVEAU=1", f"/DONNEES={donnees}"
        )
        verifier(entree_registre() is None, "retiré des applications installées")
        verifier(not exe.exists(), "programme supprimé")
        verifier(not (PROGRAMMES / "PSN Amis").exists(), "raccourcis du menu retirés")
        verifier(not (BUREAU / "PSN Amis.lnk").exists(), "raccourci Bureau retiré")
        verifier((donnees / "reglages.toml").is_file(), "données conservées")
        verifier(not demarrage_present(), "lancement avec Windows retiré")

        print("5. Réinstallation, puis niveau 2 (programme et données)")
        verifier(installer(dossier, journaux / "reinstallation.log") == 0, "réinstallé")
        verifier((donnees / "reglages.toml").is_file(), "anciennes données retrouvées")
        # Sur certaines machines (intégration continue), le coffre est indisponible :
        # les vérifications du code sont alors sautées, et dites telles quelles.
        coffre_ok = coffre.ecrire("code-de-test-sans-valeur", CIBLE_TEST)
        if not coffre_ok:
            print("  (coffre de Windows indisponible : vérifications du code sautées)")
        desinstaller(
            dossier,
            journaux / "niveau2.log",
            "/NIVEAU=2",
            f"/DONNEES={donnees}",
            f"/CIBLE={CIBLE_TEST}",
        )
        verifier(not (donnees / "reglages.toml").exists(), "réglages supprimés")
        verifier(not (donnees / "journal.txt.1").exists(), "journaux supprimés")
        verifier(not (donnees / "comptes").exists(), "données des comptes supprimées")
        verifier(
            (donnees / "note-personnelle.txt").is_file(),
            "fichier étranger à PSN Amis conservé",
        )
        if coffre_ok:
            verifier(
                coffre.lire(CIBLE_TEST) is not None,
                "code enregistré conservé (niveau 2 sans case cochée)",
            )

        print("6. Réinstallation, puis niveau 3 (tout)")
        donnees_de_test(donnees)
        verifier(
            installer(dossier, journaux / "reinstallation2.log") == 0, "réinstallé"
        )
        desinstaller(
            dossier,
            journaux / "niveau3.log",
            "/NIVEAU=3",
            f"/DONNEES={donnees}",
            f"/CIBLE={CIBLE_TEST}",
        )
        if coffre_ok:
            verifier(coffre.lire(CIBLE_TEST) is None, "code de test retiré du coffre")
        verifier(not (donnees / "psn-amis.donnees").exists(), "fichier témoin retiré")
        verifier((donnees / "note-personnelle.txt").is_file(), "fichier étranger gardé")

        print("7. Garde-fou : dossier sans fichier témoin")
        etranger = travail / "Un autre dossier"
        etranger.mkdir()
        (etranger / "reglages.toml").write_text("à quelqu'un d'autre", encoding="utf-8")
        verifier(
            installer(dossier, journaux / "reinstallation3.log") == 0, "réinstallé"
        )
        desinstaller(
            dossier, journaux / "temoin.log", "/NIVEAU=2", f"/DONNEES={etranger}"
        )
        verifier(
            (etranger / "reglages.toml").is_file(), "rien supprimé sans fichier témoin"
        )
    finally:
        if entree_registre() is not None and (dossier / "unins000.exe").exists():
            desinstaller(dossier, journaux / "nettoyage.log", "/NIVEAU=1")
        coffre.effacer(CIBLE_TEST)
        # Valeur de test restée en cas d'échec : retirée si elle vise le dossier de test.
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_ALL_ACCESS
            ) as cle:
                if str(travail) in str(winreg.QueryValueEx(cle, "PSN Amis")[0]):
                    winreg.DeleteValue(cle, "PSN Amis")
        except OSError:
            pass
        echecs = [t for ok, t in resultats if not ok]
        if echecs:
            print(f"Journaux d'installation gardés dans {journaux}")
        else:
            shutil.rmtree(travail, ignore_errors=True)
    total = len(resultats)
    print(f"\n{total - len(echecs)} / {total} vérifications réussies.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
