"""Intégration à Windows : démarrage avec la session, identité, instance unique, relance.

Tout se fait avec les droits de l'utilisateur (registre HKEY_CURRENT_USER) : aucune
élévation UAC n'est jamais demandée.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import sys
from pathlib import Path

from psn_amis import chemins

CLE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM_RUN = "PSN Amis"
# Identité de l'application pour Windows (barre des tâches, notifications).
IDENTITE = "LASCAMPIA67.PSNAmis"
# Mutex nommé : l'installateur (AppMutex d'Inno Setup) sait ainsi que PSN Amis est
# ouvert et propose de le fermer avant de remplacer ses fichiers.
MUTEX = "PSNAmis.Application"

_mutex: int | None = None


def commande_de_lancement(*options: str) -> list[str]:
    """La commande qui relance PSN Amis (exécutable installé, ou code source)."""
    if chemins.est_compile():
        return [sys.executable, *options]
    executable = Path(sys.executable)
    # pythonw.exe : pas de fenêtre de console derrière l'application.
    sans_console = executable.with_name("pythonw.exe")
    if sans_console.exists():
        executable = sans_console
    return [str(executable), "-m", "psn_amis", *options]


def demarrage_possible() -> bool:
    """Le lancement avec Windows n'est proposé que pour l'application installée."""
    return os.name == "nt" and chemins.est_compile()


def _texte_commande(morceaux: list[str]) -> str:
    return " ".join(f'"{m}"' if " " in m or not m else m for m in morceaux)


def demarrage_avec_windows(actif: bool) -> bool:
    """Ajoute ou retire PSN Amis du démarrage de la session ; True si c'est fait."""
    if not demarrage_possible():
        return False
    import winreg

    try:
        if actif:
            # Créée au besoin : sur une session Windows neuve, la clé Run peut
            # ne pas encore exister.
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, CLE_RUN, 0, winreg.KEY_SET_VALUE
            ) as cle:
                winreg.SetValueEx(
                    cle,
                    NOM_RUN,
                    0,
                    winreg.REG_SZ,
                    _texte_commande(commande_de_lancement("--reduit")),
                )
        else:
            with (
                winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, CLE_RUN, 0, winreg.KEY_SET_VALUE
                ) as cle,
                contextlib.suppress(FileNotFoundError),
            ):
                winreg.DeleteValue(cle, NOM_RUN)
    except FileNotFoundError:
        # Pas de clé Run : PSN Amis n'y figure donc pas, rien à retirer.
        return not actif
    except OSError:
        return False
    return True


def demarre_avec_windows() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_RUN) as cle:
            winreg.QueryValueEx(cle, NOM_RUN)
    except OSError:
        return False
    return True


def declarer_identite() -> None:
    """Regroupe les fenêtres de PSN Amis sous son icône dans la barre des tâches."""
    if os.name != "nt":
        return
    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(IDENTITE)


def creer_mutex(nom: str = MUTEX) -> None:
    """Crée le mutex nommé (gardé jusqu'à la fin du processus)."""
    global _mutex
    if os.name != "nt" or _mutex is not None:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    _mutex = kernel32.CreateMutexW(None, 0, nom)


def animations_windows() -> bool:
    """Le réglage Windows « Effets d'animation » (Accessibilité › Effets visuels).

    True s'il est activé, ou si on ne peut pas le savoir (autre système).
    """
    if os.name != "nt":
        return True
    spi_getclientareaanimation = 0x1042
    actif = ctypes.c_int(1)
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(
            spi_getclientareaanimation, 0, ctypes.byref(actif), 0
        )
    except AttributeError, OSError:
        return True
    return bool(actif.value) if ok else True
