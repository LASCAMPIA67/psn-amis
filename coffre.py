"""Le coffre de Windows : le Gestionnaire d'identification, pour garder le code npsso.

Le code y est chiffré par Windows avec la session de l'utilisateur : aucun fichier à
protéger, et un autre compte Windows du même PC ne peut pas le lire. Sur un autre
système, le coffre est simplement indisponible et PSN Amis utilise npsso.txt.

Ce fichier ne contient que des appels à advapi32 (CredReadW, CredWriteW, CredDeleteW).
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

CIBLE = "PSN Amis/npsso"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


class _Filetime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _Filetime),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _advapi32() -> ctypes.WinDLL | None:
    if os.name != "nt":
        return None
    dll = ctypes.WinDLL("advapi32", use_last_error=True)
    dll.CredReadW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_Credential)),
    )
    dll.CredReadW.restype = wintypes.BOOL
    dll.CredWriteW.argtypes = (ctypes.POINTER(_Credential), wintypes.DWORD)
    dll.CredWriteW.restype = wintypes.BOOL
    dll.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
    dll.CredDeleteW.restype = wintypes.BOOL
    dll.CredFree.argtypes = (ctypes.c_void_p,)
    dll.CredFree.restype = None
    return dll


def disponible() -> bool:
    return os.name == "nt"


def lire(cible: str = CIBLE) -> str | None:
    """Le code gardé dans le coffre, ou None s'il n'y en a pas."""
    dll = _advapi32()
    if dll is None:
        return None
    pointeur = ctypes.POINTER(_Credential)()
    if not dll.CredReadW(cible, CRED_TYPE_GENERIC, 0, ctypes.byref(pointeur)):
        return None
    try:
        credential = pointeur.contents
        taille = credential.CredentialBlobSize
        if not taille:
            return None
        octets = ctypes.string_at(credential.CredentialBlob, taille)
        return octets.decode("utf-8", errors="ignore")
    finally:
        dll.CredFree(pointeur)


def ecrire(code: str, cible: str = CIBLE) -> bool:
    """Garde le code dans le coffre (remplace l'ancien) ; True si c'est fait."""
    dll = _advapi32()
    if dll is None:
        return False
    octets = code.encode("utf-8")
    tampon = (ctypes.c_ubyte * len(octets)).from_buffer_copy(octets)
    credential = _Credential()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = cible
    credential.Comment = "Code npsso de PSN Amis. Ne le partagez jamais."
    credential.CredentialBlobSize = len(octets)
    credential.CredentialBlob = ctypes.cast(tampon, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "npsso"
    return bool(dll.CredWriteW(ctypes.byref(credential), 0))


def effacer(cible: str = CIBLE) -> bool:
    """Retire le code du coffre ; True s'il n'y est plus (ou n'y était pas)."""
    dll = _advapi32()
    if dll is None:
        return False
    if dll.CredDeleteW(cible, CRED_TYPE_GENERIC, 0):
        return True
    return ctypes.get_last_error() == ERROR_NOT_FOUND
