"""Construit l'application Windows et son installateur, puis les vérifie.

Depuis le dossier du projet (Windows) :

    uv sync --locked --group construction
    uv run outils/construire.py                 tout : exécutables, installateur
    uv run outils/construire.py --sans-installateur

Étapes : version lue dans src/psn_amis/__init__.py → métadonnées Windows et licences
tierces → PyInstaller → démarrage réel des deux exécutables (mode démonstration, aucune
connexion à Sony) → Inno Setup → SHA256SUMS.txt.

Résultat dans dist/ : « PSN Amis/ » (application), PSN-Amis-Setup-X.Y.Z.exe et
SHA256SUMS.txt.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
CONSTRUCTION = RACINE / "build"
DISTRIBUTION = RACINE / "dist"
APPLICATION = DISTRIBUTION / "PSN Amis"

# Bibliothèques empaquetées dans l'application (pas les outils de développement).
EMBARQUEES = (
    "psnawp",
    "pyside6-essentials",
    "shiboken6",
    "rich",
    "markdown-it-py",
    "mdurl",
    "pygments",
    "requests",
    "urllib3",
    "certifi",
    "charset-normalizer",
    "idna",
    "pyrate-limiter",
    "pycountry",
    "typing-extensions",
)


def version() -> str:
    texte = (RACINE / "src" / "psn_amis" / "__init__.py").read_text(encoding="utf-8")
    trouve = re.search(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$', texte, re.MULTILINE)
    if trouve is None:
        raise SystemExit("Version introuvable dans src/psn_amis/__init__.py")
    return ".".join(trouve.groups())


def ecrire_version_windows(numero: str) -> None:
    """Métadonnées de l'exécutable (Propriétés → Détails dans l'Explorateur)."""
    morceaux = (*(int(n) for n in numero.split(".")), 0)
    texte = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={morceaux}, prodvers={morceaux}, mask=0x3f, flags=0x0,
    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040C04B0', [
      StringStruct('CompanyName', 'LASCAMPIA67'),
      StringStruct('FileDescription', 'PSN Amis'),
      StringStruct('FileVersion', '{numero}'),
      StringStruct('InternalName', 'PSN Amis'),
      StringStruct('LegalCopyright', 'Licence MIT - projet indépendant de Sony'),
      StringStruct('OriginalFilename', 'PSN Amis.exe'),
      StringStruct('ProductName', 'PSN Amis'),
      StringStruct('ProductVersion', '{numero}')])]),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])
  ]
)
"""
    (CONSTRUCTION / "version_info.txt").write_text(texte, encoding="utf-8")


def ecrire_licences() -> None:
    """Liste des bibliothèques redistribuées, avec leur version et leur licence."""
    lignes = [
        "PSN Amis — bibliothèques tierces redistribuées",
        "=" * 48,
        "",
        "PSN Amis est distribué sous licence MIT (fichier LICENSE).",
        "Python est distribué sous la licence de la Python Software Foundation.",
        "",
        "Qt / PySide6 (LGPL v3) : les bibliothèques Qt sont des fichiers séparés",
        "(dossier _internal\\PySide6), remplaçables par une version compatible.",
        "Code source : https://code.qt.io et https://download.qt.io/official_releases/",
        "",
    ]
    for nom in EMBARQUEES:
        try:
            meta = importlib.metadata.metadata(nom)
        except importlib.metadata.PackageNotFoundError:
            continue
        licence = (
            meta.get("License-Expression")
            or next(
                (
                    c.split("::")[-1].strip()
                    for c in meta.get_all("Classifier") or []
                    if c.startswith("License ::")
                ),
                None,
            )
            or (meta.get("License") or "voir le projet").splitlines()[0][:80]
        )
        site = meta.get("Home-page") or next(
            (u.split(",", 1)[-1].strip() for u in meta.get_all("Project-URL") or []),
            "",
        )
        lignes.append(f"- {meta['Name']} {meta['Version']} : {licence}  {site}")
    lignes.append("")
    (CONSTRUCTION / "LICENCES-TIERS.txt").write_text(
        "\n".join(lignes), encoding="utf-8"
    )


def executer(commande: list[str], **options) -> subprocess.CompletedProcess[str]:
    print("→", " ".join(f'"{c}"' if " " in c else c for c in commande), flush=True)
    return subprocess.run(commande, check=False, text=True, **options)  # noqa: S603


def pyinstaller() -> None:
    resultat = executer(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(RACINE / "installer" / "psn_amis.spec"),
            "--noconfirm",
            "--clean",
            "--log-level",
            "WARN",
            "--distpath",
            str(DISTRIBUTION),
            "--workpath",
            str(CONSTRUCTION / "pyinstaller"),
        ]
    )
    if resultat.returncode:
        raise SystemExit("PyInstaller a échoué.")


def verifier_executables(numero: str) -> None:
    """Le programme compilé doit vraiment démarrer, pas seulement exister.

    Chaque lancement part d'un dossier de données qui n'existe pas encore, comme
    sur un Windows vierge (aucune connexion à Sony : mode démonstration).
    """
    travail = Path(tempfile.mkdtemp(prefix="psn-amis-verification-"))
    environnement = dict(os.environ, PYTHONIOENCODING="utf-8")
    environnement.pop("PSN_AMIS_DONNEES", None)

    def premier_lancement(nom: str) -> Path:
        donnees = travail / nom / "AppData Local é" / "PSN Amis"
        environnement["PSN_AMIS_DONNEES"] = str(donnees)
        return donnees

    # Pas d'écran dans l'intégration continue : rendu hors écran.
    if os.environ.get("CI"):
        environnement["QT_QPA_PLATFORM"] = "offscreen"
    try:
        console = APPLICATION / "PSN Amis console.exe"
        sortie = executer(
            [str(console), "--version"],
            capture_output=True,
            env=environnement,
            timeout=120,
            encoding="utf-8",
        )
        if sortie.returncode or f"PSN Amis {numero}" not in sortie.stdout:
            raise SystemExit(f"« PSN Amis console.exe --version » : {sortie.stdout!r}")
        donnees = premier_lancement("console")
        sortie = executer(
            [str(console), "--test", "--demo"],
            capture_output=True,
            env=environnement,
            timeout=120,
            encoding="utf-8",
        )
        if sortie.returncode or "aucune demande n'a été acceptée" not in sortie.stdout:
            raise SystemExit(f"Mode console en démonstration : {sortie.stdout!r}")
        if not (donnees / "reglages.toml").is_file():
            raise SystemExit("Console : dossier des données non créé.")
        donnees = premier_lancement("fenetre")
        fenetre = executer(
            [str(APPLICATION / "PSN Amis.exe"), "--demo", "--verifier", "8"],
            env=environnement,
            timeout=180,
        )
        if fenetre.returncode:
            raise SystemExit(f"La fenêtre ne démarre pas (code {fenetre.returncode}).")
        journal = donnees / "journal.txt"
        texte = journal.read_text(encoding="utf-8") if journal.exists() else ""
        if "Connecté au compte PSN MonCompte-PSN" not in texte:
            raise SystemExit(
                "La fenêtre a démarré mais le moteur ne s'est pas connecté."
            )
        if (donnees / "psn-amis.lock").exists():
            raise SystemExit("Fenêtre : verrou non libéré à la fermeture.")
    finally:
        shutil.rmtree(travail, ignore_errors=True)
    print(
        "✔ Exécutables vérifiés : fenêtre et console démarrent au tout premier "
        "lancement (dossier de données absent, démonstration)."
    )


def iscc() -> Path:
    candidats = [
        shutil.which("iscc"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"),
        os.path.expandvars(r"%ProgramFiles%\Inno Setup 6\ISCC.exe"),
    ]
    for candidat in candidats:
        if candidat and Path(candidat).is_file():
            return Path(candidat)
    raise SystemExit(
        "Inno Setup 6 est introuvable : installez-le (https://jrsoftware.org/isinfo.php)."
    )


def installateur(numero: str) -> Path:
    resultat = executer(
        [
            str(iscc()),
            f"/DVersion={numero}",
            f"/DSource={APPLICATION}",
            f"/DRacine={RACINE}",
            f"/O{DISTRIBUTION}",
            "/Qp",
            str(RACINE / "installer" / "psn-amis.iss"),
        ]
    )
    sortie = DISTRIBUTION / f"PSN-Amis-Setup-{numero}.exe"
    if resultat.returncode or not sortie.is_file():
        raise SystemExit("Inno Setup a échoué.")
    return sortie


def empreintes(fichiers: list[Path]) -> Path:
    lignes = []
    for fichier in fichiers:
        calcul = hashlib.sha256(fichier.read_bytes()).hexdigest()
        lignes.append(f"{calcul}  {fichier.name}")
    chemin = DISTRIBUTION / "SHA256SUMS.txt"
    # Fins de ligne Unix : « sha256sum --check » (Linux, publication) refuse les CRLF.
    chemin.write_bytes(("\n".join(lignes) + "\n").encode("utf-8"))
    return chemin


def main() -> int:
    parametres = argparse.ArgumentParser(description="Construit PSN Amis pour Windows.")
    parametres.add_argument("--sans-installateur", action="store_true")
    parametres.add_argument(
        "--sans-verification",
        action="store_true",
        help="ne lance pas les exécutables (déconseillé)",
    )
    choix = parametres.parse_args()
    if os.name != "nt":
        raise SystemExit("La construction de l'application se fait sous Windows.")
    numero = version()
    print(f"PSN Amis {numero}")
    CONSTRUCTION.mkdir(exist_ok=True)
    ecrire_version_windows(numero)
    ecrire_licences()
    pyinstaller()
    if not choix.sans_verification:
        verifier_executables(numero)
    if choix.sans_installateur:
        return 0
    setup = installateur(numero)
    sommes = empreintes([setup])
    taille = setup.stat().st_size / 1_000_000
    print(f"✔ {setup.name} ({taille:.1f} Mo) et {sommes.name} dans {DISTRIBUTION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
