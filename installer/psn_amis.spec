# Recette PyInstaller de PSN Amis (https://pyinstaller.org/en/stable/spec-files.html).
#
# Ne pas lancer directement : utiliser « uv run outils/construire.py », qui prépare
# d'abord build/version_info.txt et les licences.
#
# Mode « dossier » (onedir) : démarrage rapide, moins de fausses alertes antivirus qu'un
# exécutable unique, et bibliothèques Qt (LGPL) gardées en fichiers séparés,
# remplaçables par l'utilisateur. Deux exécutables partagent les mêmes fichiers :
# - « PSN Amis.exe » : la fenêtre (sans console) ;
# - « PSN Amis console.exe » : le tableau de bord en couleur des versions 2.x.
from pathlib import Path

RACINE = Path(SPECPATH).parent  # noqa: F821 (fourni par PyInstaller)
CONSTRUCTION = RACINE / "build"
ICONE = RACINE / "src" / "psn_amis" / "ressources" / "icone.ico"

analyse = Analysis(  # noqa: F821
    [str(RACINE / "installer" / "lanceur.py")],
    pathex=[str(RACINE / "src")],
    datas=[
        (str(RACINE / "src" / "psn_amis" / "ressources"), "psn_amis/ressources"),
        (str(CONSTRUCTION / "LICENCES-TIERS.txt"), "."),
        (str(RACINE / "LICENSE"), "."),
    ],
    hiddenimports=[
        "psn_amis.app",
        "psn_amis.console",
        "psn_amis.demo",
        "psn_amis.tableau_de_bord",
    ],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtNetwork",
        "PySide6.QtOpenGL",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtPdf",
    ],
    noarchive=False,
)


def utile(entree) -> bool:
    """Retire ce dont une interface Qt Widgets en français n'a pas besoin."""
    destination = entree[0].replace("\\", "/")
    # Rendu OpenGL logiciel (20 Mo) : inutile, l'interface est dessinée sans OpenGL.
    if destination.endswith("opengl32sw.dll"):
        return False
    # Traductions de Qt : seulement le français.
    return "/translations/" not in destination or destination.endswith("_fr.qm")


analyse.binaries = [e for e in analyse.binaries if utile(e)]
analyse.datas = [e for e in analyse.datas if utile(e)]
pyz = PYZ(analyse.pure)  # noqa: F821

options = {
    "exclude_binaries": True,
    "debug": False,
    "strip": False,
    # UPX désactivé : il provoque des fausses alertes antivirus et casse parfois Qt.
    "upx": False,
    "icon": str(ICONE),
    "version": str(CONSTRUCTION / "version_info.txt"),
}
fenetre = EXE(pyz, analyse.scripts, [], name="PSN Amis", console=False, **options)  # noqa: F821
console = EXE(  # noqa: F821
    pyz, analyse.scripts, [], name="PSN Amis console", console=True, **options
)
COLLECT(  # noqa: F821
    fenetre,
    console,
    analyse.binaries,
    analyse.datas,
    strip=False,
    upx=False,
    name="PSN Amis",
)
