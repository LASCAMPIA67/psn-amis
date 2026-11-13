"""Lancement avec Windows : clé Run du registre, simulée (le vrai registre n'est
jamais touché)."""

from __future__ import annotations

import sys
import types

import pytest

from psn_amis import systeme


class FauxRegistre(types.SimpleNamespace):
    """Imite winreg pour la seule clé Run de l'utilisateur."""

    HKEY_CURRENT_USER = object()
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self, cle_existe: bool) -> None:
        super().__init__()
        self.cle_existe = cle_existe
        self.valeurs: dict[str, str] = {}

    def _cle(self):
        registre = self

        class Cle:
            def __enter__(self):
                return registre

            def __exit__(self, *_):
                return False

        return Cle()

    def OpenKey(self, racine, chemin, *_):
        assert chemin == systeme.CLE_RUN
        if not self.cle_existe:
            raise FileNotFoundError(2, "clé absente")
        return self._cle()

    def CreateKeyEx(self, racine, chemin, *_):
        assert chemin == systeme.CLE_RUN
        self.cle_existe = True
        return self._cle()

    def SetValueEx(self, _cle, nom, _reserve, _type, valeur):
        self.valeurs[nom] = valeur

    def DeleteValue(self, _cle, nom):
        if nom not in self.valeurs:
            raise FileNotFoundError(2, "valeur absente")
        del self.valeurs[nom]

    def QueryValueEx(self, _cle, nom):
        if nom not in self.valeurs:
            raise FileNotFoundError(2, "valeur absente")
        return self.valeurs[nom], self.REG_SZ


@pytest.fixture
def registre(monkeypatch):
    def fabriquer(cle_existe: bool) -> FauxRegistre:
        faux = FauxRegistre(cle_existe)
        monkeypatch.setitem(sys.modules, "winreg", faux)
        monkeypatch.setattr(systeme, "demarrage_possible", lambda: True)
        monkeypatch.setattr(systeme.os, "name", "nt")
        return faux

    return fabriquer


def test_activer_sans_cle_run_la_cree(registre):
    """Session Windows neuve : la clé Run n'existe pas encore."""
    faux = registre(cle_existe=False)
    assert systeme.demarrage_avec_windows(True)
    assert faux.cle_existe
    assert "--reduit" in faux.valeurs[systeme.NOM_RUN]
    assert systeme.demarre_avec_windows()


def test_desactiver_sans_cle_run_rien_a_retirer(registre):
    faux = registre(cle_existe=False)
    assert systeme.demarrage_avec_windows(False)
    assert not faux.cle_existe  # rien créé pour rien


def test_activer_puis_desactiver(registre):
    faux = registre(cle_existe=True)
    assert systeme.demarrage_avec_windows(True)
    assert systeme.demarrage_avec_windows(False)
    assert faux.valeurs == {}
    assert not systeme.demarre_avec_windows()
