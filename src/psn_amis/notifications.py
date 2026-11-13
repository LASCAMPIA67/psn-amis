"""Bulles de notification Windows et petit bip.

Les bulles passent par Windows PowerShell (livré avec Windows 10 et 11), lancé en
arrière-plan : elles n'attendent rien et ne peuvent pas gêner PSN Amis. Sur un autre
système, ces fonctions ne font rien.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import threading
from xml.sax.saxutils import escape

# Identité sous laquelle Windows range les bulles (celle de PowerShell, toujours connue).
IDENTITE = (
    r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
)

_WINRT = "ContentType = WindowsRuntime"
_SCRIPT = "\n".join(
    (
        "[Windows.UI.Notifications.ToastNotificationManager, "
        f"Windows.UI.Notifications, {_WINRT}] > $null",
        "[Windows.Data.Xml.Dom.XmlDocument, "
        f"Windows.Data.Xml.Dom.XmlDocument, {_WINRT}] > $null",
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument",
        '$xml.LoadXml(\'<toast><visual><binding template="ToastGeneric">'
        "<text>{titre}</text><text>{texte}</text></binding></visual></toast>')",
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml",
        "[Windows.UI.Notifications.ToastNotificationManager]"
        "::CreateToastNotifier('{identite}').Show($toast)",
    )
)


def _powershell() -> str | None:
    if os.name != "nt":
        return None
    return shutil.which("powershell")


def notifier(titre: str, texte: str) -> bool:
    """Affiche une bulle Windows en arrière-plan ; False si ce n'est pas possible ici."""
    powershell = _powershell()
    if powershell is None:
        return False
    script = _SCRIPT.format(
        titre=escape(titre).replace("'", "&apos;"),
        texte=escape(texte).replace("'", "&apos;"),
        identite=IDENTITE,
    )
    # -EncodedCommand : le script passe tel quel, sans souci de guillemets ni d'accents.
    encode = base64.b64encode(script.encode("utf-16-le")).decode("ascii")

    def lancer() -> None:
        subprocess.run(  # noqa: S603
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                encode,
            ],
            capture_output=True,
            check=False,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    threading.Thread(target=lancer, name="notification", daemon=True).start()
    return True


def bip() -> bool:
    """Un petit bip, sans bloquer ; False si ce n'est pas possible ici."""
    if os.name != "nt":
        return False
    import winsound

    threading.Thread(
        target=winsound.Beep, args=(1046, 90), name="bip", daemon=True
    ).start()
    return True
