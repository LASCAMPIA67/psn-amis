"""Un faux PlayStation Network en mémoire, pour les tests et le mode démonstration.

Aucune requête ne part : les demandes, les amis et les pseudos sont inventés. Des pannes
peuvent être programmées pour vérifier le comportement de PSN Amis (coupure, limite de
Sony, réponse ambiguë...).
"""

from __future__ import annotations

import random
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from psnawp_api.core import PSNAWPNotFoundError

from psn_amis import demandes as types_demandes
from psn_amis.psn import AMI, Relation

COMPTE_DEMO = "1000000000000000001"
PSEUDO_DEMO = "MonCompte-PSN"
PSEUDOS = (
    "NightOwl-77",
    "Kyra_Sniper",
    "xX_Pixel_Xx",
    "LunaBreeze",
    "TacticalTaco",
    "Mister_Joystick",
    "ZeroLag_FR",
    "Captain_Combo",
    "SilentFox_92",
    "Nova-Strike",
    "PandaRush",
    "Echo_Delta",
)


def introuvable(compte: str) -> PSNAWPNotFoundError:
    return PSNAWPNotFoundError(f'{{"error": {{"message": "{compte} introuvable"}}}}')


@dataclass
class JoueurSimule:
    sony: SonySimule
    account_id: str
    online_id: str

    def accept_friend_request(self) -> None:
        self.sony.accepter(self.account_id)


class SonySimule:
    """L'état de Sony : amis, demandes reçues, pseudos ; et les pannes programmées."""

    def __init__(
        self,
        compte: str = COMPTE_DEMO,
        pseudo: str = PSEUDO_DEMO,
        nombre_amis: int = 0,
    ) -> None:
        self.compte = compte
        self.pseudo_compte = pseudo
        self._verrou = threading.RLock()
        self.pseudos: dict[str, str] = {compte: pseudo}
        self.amis: set[str] = set()
        # Compte -> demande brute, comme Sony la renvoie.
        self.demandes: dict[str, dict[str, Any]] = {}
        # Opération ("relation", "supprimer"...) -> exception à lever (une fois ou
        # toujours), éventuellement pour un compte précis.
        self.pannes: dict[tuple[str, str | None], tuple[Exception, bool]] = {}
        self.appels: list[tuple[str, str]] = []
        # Appelé avant chaque opération (pour simuler un changement en cours de route).
        self.avant: Callable[[str, str], None] = lambda operation, compte: None
        self._suivant = 2_000_000_000_000_000_000
        for _ in range(nombre_amis):
            self.amis.add(self.nouveau_joueur())

    # ─── Fabrication des données ───

    def nouveau_joueur(self, pseudo: str | None = None) -> str:
        with self._verrou:
            self._suivant += 1
            compte = str(self._suivant)
            numero = len(self.pseudos)
            self.pseudos[compte] = pseudo or (
                f"{PSEUDOS[numero % len(PSEUDOS)]}_{numero:04d}"
            )
            return compte

    def recevoir(
        self,
        compte: str | None = None,
        relation: str | None = "requested",
        partage: str | None = None,
        il_y_a: timedelta = timedelta(minutes=1),
    ) -> str:
        with self._verrou:
            compte = compte or self.nouveau_joueur()
            brut: dict[str, Any] = {
                "accountId": compte,
                "requestedDate": (datetime.now().astimezone() - il_y_a).isoformat(),
            }
            if relation is not None:
                brut["relation"] = relation
            if partage is not None:
                brut["personalDetailSharing"] = partage
            self.demandes[compte] = brut
            return compte

    def panne(
        self,
        operation: str,
        erreur: Exception,
        compte: str | None = None,
        toujours: bool = False,
    ) -> None:
        self.pannes[(operation, compte)] = (erreur, toujours)

    def _appel(self, operation: str, compte: str) -> None:
        self.avant(operation, compte)
        with self._verrou:
            self.appels.append((operation, compte))
            for cle in ((operation, compte), (operation, None)):
                if cle in self.pannes:
                    erreur, toujours = self.pannes[cle]
                    if not toujours:
                        del self.pannes[cle]
                    raise erreur

    # ─── Ce que le moteur appelle (mêmes signatures que moteur.py) ───

    def demandes_recues(self, connexion: object = None) -> Any:
        from psn_amis import moteur

        self._appel("demandes", "")
        with self._verrou:
            triees: dict[types_demandes.TypeDemande, list[str]] = {
                sorte: [] for sorte in types_demandes.TypeDemande
            }
            depuis = {}
            for compte, brut in self.demandes.items():
                triees[types_demandes.classer(brut)].append(compte)
                depuis[compte] = datetime.fromisoformat(brut["requestedDate"]).replace(
                    tzinfo=None
                )
            sortes = types_demandes.TypeDemande
            return moteur.Demandes(
                triees[sortes.ORDINAIRE],
                triees[sortes.AMI_PROCHE],
                depuis,
                triees[sortes.AVEC_VRAI_NOM],
                triees[sortes.NON_RECONNUE],
            )

    def liste_amis(self, connexion: object = None) -> tuple[set[str], int]:
        self._appel("liste", "")
        with self._verrou:
            return set(self.amis), len(self.amis)

    def trouver_joueur(self, connexion: object, compte: str) -> JoueurSimule:
        return JoueurSimule(self, compte, self.pseudos.get(compte, f"inconnu_{compte}"))

    def accepter(self, compte: str) -> None:
        self._appel("accepter", compte)
        with self._verrou:
            if compte not in self.demandes:
                raise introuvable(compte)
            del self.demandes[compte]
            self.amis.add(compte)

    # ─── ClientPSN (gestion des amis) ───

    def relation(self, compte: str) -> Relation:
        self._appel("relation", compte)
        with self._verrou:
            if compte not in self.pseudos:
                raise introuvable(compte)
            return Relation(compte, AMI if compte in self.amis else "no")

    def supprimer(self, compte: str) -> None:
        self._appel("supprimer", compte)
        with self._verrou:
            # Comme Sony : la même opération retire un ami ou refuse une demande.
            self.amis.discard(compte)
            self.demandes.pop(compte, None)

    def refuser(self, compte: str) -> None:
        self.supprimer(compte)

    def pseudo(self, compte: str) -> str:
        self._appel("pseudo", compte)
        with self._verrou:
            if compte not in self.pseudos:
                raise introuvable(compte)
            return self.pseudos[compte]

    def chercher(self, pseudo: str) -> tuple[str, str]:
        self._appel("chercher", pseudo)
        with self._verrou:
            for compte, nom in self.pseudos.items():
                if nom.casefold() == pseudo.casefold():
                    return compte, nom
        raise introuvable(pseudo)


@dataclass
class ConnexionSimulee:
    sony: SonySimule
    pseudo: str = PSEUDO_DEMO
    compte_id: str = COMPTE_DEMO

    def expire_bientot(self) -> bool:
        return False

    def renouveler_acces_si_besoin(self) -> None:
        pass

    def fermer(self) -> None:
        pass


def animer(sony: SonySimule, arret: threading.Event, cadence: float = 20.0) -> None:
    """Démonstration : de nouvelles demandes arrivent de temps en temps."""
    hasard = random.Random(42)  # noqa: S311 (démonstration, pas de sécurité)
    while not arret.wait(cadence * (0.5 + hasard.random())):
        sony.recevoir()
