"""Les opérations PlayStation utilisées par la gestion des amis.

Elles passent toutes par PSNAWP (API PlayStation non officielle) et par son limiteur de
débit (1 requête toutes les 3 secondes) ; elles ne sont appelées que depuis le fil du
moteur, qui coordonne toutes les requêtes envoyées à Sony.

Points vérifiés dans le code de PSNAWP 3.1 :
- `relation` : GET /me/friends/{compte}/summary renvoie « friendRelation » (« friend »
  pour un ami), sans le pseudo ;
- `supprimer` et `refuser` : DELETE /me/friends/{compte}, la seule opération de PSNAWP
  (User.remove_friend) ; elle refuse une demande reçue ou supprime un ami. Elle ne doit
  donc jamais servir à refuser une demande d'ami proche (venue d'un ami existant) ;
- `pseudo` : GET /{compte}/profiles ; `chercher` : profil par pseudo (onlineId).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from psnawp_api.models import User
from psnawp_api.utils import API_PATH, BASE_PATH

AMI = "friend"


class ReponseInattendue(Exception):
    """Sony a répondu quelque chose que PSN Amis ne sait pas interpréter."""


@dataclass(frozen=True)
class Relation:
    compte: str
    # « friend » pour un ami ; autre valeur ou vide sinon.
    relation: str

    @property
    def est_ami(self) -> bool:
        return self.relation == AMI


class ClientPSN(Protocol):
    """Ce dont la gestion des amis a besoin ; voir simulation.py pour le faux client."""

    def relation(self, compte: str) -> Relation: ...

    def supprimer(self, compte: str) -> None: ...

    def refuser(self, compte: str) -> None: ...

    def pseudo(self, compte: str) -> str: ...

    def chercher(self, pseudo: str) -> tuple[str, str]: ...


class ClientPSNAWP:
    """Le vrai client, branché sur une connexion PSNAWP déjà ouverte."""

    def __init__(self, psnawp: Any) -> None:
        self._auth = psnawp.authenticator

    def _adresse_amitie(self, compte: str) -> str:
        return (
            f"{BASE_PATH['profile_uri']}"
            f"{API_PATH['manage_friendship'].format(account_id=compte)}"
        )

    def relation(self, compte: str) -> Relation:
        adresse = (
            f"{BASE_PATH['profile_uri']}"
            f"{API_PATH['friends_summary'].format(account_id=compte)}"
        )
        try:
            reponse = self._auth.get(url=adresse).json()
        except ValueError as erreur:
            raise ReponseInattendue("réponse illisible") from erreur
        if not isinstance(reponse, dict) or not isinstance(
            reponse.get("friendRelation"), str
        ):
            raise ReponseInattendue("relation d'amitié absente de la réponse")
        return Relation(compte, reponse["friendRelation"])

    def supprimer(self, compte: str) -> None:
        self._auth.delete(url=self._adresse_amitie(compte))

    def refuser(self, compte: str) -> None:
        self._auth.delete(url=self._adresse_amitie(compte))

    def pseudo(self, compte: str) -> str:
        return User.from_account_id(self._auth, compte).online_id

    def chercher(self, pseudo: str) -> tuple[str, str]:
        joueur = User.from_online_id(self._auth, pseudo)
        return joueur.account_id, joueur.online_id
