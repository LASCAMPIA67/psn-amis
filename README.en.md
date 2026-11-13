# PSN Amis

**Accepts PlayStation Network friend requests for you, and helps you keep room in your friend list.**

[![Checks](https://github.com/LASCAMPIA67/psn-amis/actions/workflows/verification.yml/badge.svg)](https://github.com/LASCAMPIA67/psn-amis/actions/workflows/verification.yml)
[![Latest release](https://img.shields.io/github/v/release/LASCAMPIA67/psn-amis?label=version)](https://github.com/LASCAMPIA67/psn-amis/releases/latest)
[![MIT licence](https://img.shields.io/github/license/LASCAMPIA67/psn-amis?label=licence)](LICENSE)

🇫🇷 [Lire cette page en français](README.md)

> [!NOTE]
> The application itself speaks French: its windows, messages and settings are in French. This page explains what you need to use it anyway.

![The PSN Amis window: status, connected account, friend count and list capacity, pending requests, accepted requests, removed friends, synchronisation and latest additions](docs/images/fenetre-tableau-de-bord.png)

**[⬇ Download the latest release](https://github.com/LASCAMPIA67/psn-amis/releases/latest)** (`PSN-Amis-Setup-x.y.z.exe`, Windows 10 and 11, 64-bit)

> PSN Amis is an independent project, **not affiliated with Sony Interactive Entertainment or PlayStation**. It relies on an unofficial PlayStation API: read [Limits and disclaimer](#limits-and-disclaimer) first.

## What PSN Amis does

- **Accepts incoming friend requests automatically**, every 15 seconds, one at a time.
- **Shows everything it does**: a clear dashboard and a colour-coded activity console.
- **Helps you manage your friend list** (Sony's limit is 2,000): browse, search, protect, remove one friend or many, always with a preview and an explicit confirmation.
- **Can clean up the list for you**, if you turn it on: when the list reaches a threshold, it proposes (or performs) a limited number of removals, never touching protected friends.
- **Never touches close-friend requests** (real-name sharing).
- Installs like any Windows application, updates itself on request, and uninstalls cleanly.

## Installation

1. Download **`PSN-Amis-Setup-x.y.z.exe`** from the [releases page](https://github.com/LASCAMPIA67/psn-amis/releases/latest).
2. Run it. Windows SmartScreen may warn you because the installer is not yet signed with a paid certificate: make sure it comes from this GitHub page, then choose **More info › Run anyway**. Never disable SmartScreen or your antivirus.
3. Pick the folder (default: `%LOCALAPPDATA%\Programs\PSN Amis`) and, if you like, a Desktop shortcut.

No administrator rights are needed, and **nothing else has to be installed** (no Python, no tools). To check the download, compare `Get-FileHash .\PSN-Amis-Setup-x.y.z.exe` (PowerShell) with `SHA256SUMS.txt` from the release.

## First time: connect your account

A first-run wizard asks for your **npsso code**, a sign-in token Sony gives your browser:

1. In your browser, sign in at [playstation.com](https://www.playstation.com).
2. In the same browser, open <https://ca.account.sony.com/api/v1/ssocookie>.
3. Copy the 64-character code (without quotes), paste it into the wizard, and click **Enregistrer et vérifier**.

PSN Amis checks the code with Sony, shows the connected account, and stores the code in the **Windows Credential Manager**. It is never displayed. It expires after about two months: replace it from **Paramètres › Changer le code npsso**.

## Using it

The left bar has six pages: **Tableau de bord** (dashboard), **Activité** (activity console), **Amis** (friends), **Demandes** (requests), **Paramètres** (settings) and **À propos** (about). The toolbar starts, stops, pauses (<kbd>Ctrl</kbd>+<kbd>P</kbd>), checks now (<kbd>F5</kbd>), reconnects, restarts the engine or the whole application, and quits.

**Removing friends** (page **Amis**): tick friends, or choose a number and an explicit rule (*oldest accepted by PSN Amis*, *first seen by PSN Amis*, *alphabetical*), then preview. Nothing is removed until you tick the confirmation and click **Supprimer N amis**. Removals run one at a time with a pause; the friendship is re-checked with Sony right before each one; a removal without a clear answer is marked *to check* and never blindly retried. Dates are never invented: unknown ones read « Inconnue ».

**Protected friends** are never removed, by hand or by the clean-up; protection follows the account ID even if the player changes their name. This is separate from the requests *whitelist*.

**Automatic clean-up** is off by default (manual mode). *Assisted* mode proposes a selection to confirm; *automatic* mode removes within conservative limits (per clean-up, per day, minimum delay, allowed hours) and switches itself back to manual if removals and acceptances loop.

## Updates

If you allow it, PSN Amis asks GitHub for the latest stable release at launch (or use **À propos › Rechercher une mise à jour**). **Installer la mise à jour** downloads the official installer, checks its size and SHA-256 digest, closes PSN Amis cleanly, installs, and restarts it. Your data is kept.

## Uninstalling

From **Settings › Apps › Installed apps**, or **Start › PSN Amis › Désinstaller PSN Amis**. Three levels: program only (your data is kept), program and data (`%LOCALAPPDATA%\PSN Amis`), or everything including the stored npsso code. Only files created by PSN Amis are removed.

## Security and privacy

- Your npsso code only ever goes to Sony's sign-in servers; it is never shown or logged.
- For your account, only Sony's servers are contacted. The optional update check contacts GitHub and sends nothing else. **No telemetry.**
- No friend is ever removed without your consent, and never a protected friend or a close-friend request sender.

Details: [SECURITY.md](SECURITY.md) (in French).

## Limits and disclaimer

PSN Amis uses [PSNAWP](https://github.com/isFakeAccount/psnawp), an **unofficial** library. Sony may change its servers at any time, and its terms may not allow automation: heavy use could get an account suspended. PSN Amis keeps a moderate pace (at most one request every 3 seconds), but **you use it at your own risk**; no lasting compatibility or absence of sanctions can be promised.

## Developers

```shell
uv sync                                  # Python 3.15, libraries and tools
uv run python -m psn_amis --demo         # the window with a fake account (no requests)
uv run pytest                            # tests, no Internet, no real account
uv sync --group construction             # PyInstaller (plus Inno Setup 6, installed separately)
uv run outils/construire.py              # executables + installer + SHA256SUMS.txt
uv run outils/tester_installation.py     # real install, upgrade and uninstall test
```

See [CONTRIBUTING.md](CONTRIBUTING.md) (in French).

## Licence

PSN Amis is released under the [MIT licence](LICENSE). Bundled libraries (including Qt, LGPL v3) are listed in `LICENCES-TIERS.txt` in the installation folder. PSN Amis is affiliated neither with Sony Interactive Entertainment nor with the PSNAWP project. “PlayStation” and “PlayStation Network” are trademarks of Sony Interactive Entertainment.
