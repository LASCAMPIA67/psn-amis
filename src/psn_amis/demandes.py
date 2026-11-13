"""Les sortes de demandes reçues, et ce que PSN Amis a le droit d'en faire.

Sony renvoie dans la même liste (receivedRequests) plusieurs sortes de demandes. Chaque
demande porte notamment « relation » et parfois « personalDetailSharing » :

- demande d'ami ordinaire : relation « requested » (ou absente, comme en 2.x) ;
- demande d'ami proche venue d'un ami existant (partage du vrai nom) : relation
  « friend ». L'accepter comme une demande d'ami échoue (« Friend relation mismatch »),
  et la seule opération de refus de PSNAWP (DELETE /me/friends/{compte}) supprimerait
  l'amitié : PSN Amis n'y touche donc jamais ;
- demande d'ami accompagnée d'une demande de partage du vrai nom :
  personalDetailSharing « requested ». PSN Amis ne sait pas si l'accepter accepterait
  aussi le partage du vrai nom : elle reste en attente (jamais acceptée
  automatiquement) ;
- toute autre valeur de « relation » : type non reconnu, traité selon le réglage
  « demandes_non_reconnues » (laissée en attente par défaut).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

# Refus d'une demande d'ami proche sans supprimer l'ami : aucune opération vérifiée
# n'existe dans PSNAWP 3.1. Ne passer à True qu'avec une opération distincte, vérifiée,
# et des tests qui prouvent que l'amitié est conservée.
REFUS_AMI_PROCHE_DISPONIBLE = False
EXPLICATION_REFUS_AMI_PROCHE = (
    "Le refus automatique des demandes d'ami proche n'est pas disponible : PSNAWP ne "
    "propose aucune opération pour les refuser sans supprimer l'ami lui-même. Ces "
    "demandes restent en attente ; répondez-y depuis votre console ou l'appli "
    "PlayStation."
)


class TypeDemande(StrEnum):
    ORDINAIRE = "demande d'ami"
    AMI_PROCHE = "demande d'ami proche (vrai nom), d'un ami existant"
    AVEC_VRAI_NOM = "demande d'ami avec partage du vrai nom"
    NON_RECONNUE = "type non reconnu"


RELATIONS_ORDINAIRES = (None, "requested")


def classer(demande: dict[str, Any]) -> TypeDemande:
    relation = demande.get("relation")
    if relation == "friend":
        return TypeDemande.AMI_PROCHE
    if demande.get("personalDetailSharing") == "requested":
        return TypeDemande.AVEC_VRAI_NOM
    if relation in RELATIONS_ORDINAIRES:
        return TypeDemande.ORDINAIRE
    return TypeDemande.NON_RECONNUE


class ProcheNonDisponible(Exception):
    """Le refus d'une demande d'ami proche est impossible sans risque."""


def refuser_ami_proche(*_: object) -> None:
    """Point d'accroche pour une future opération vérifiée ; refuse toujours d'agir."""
    raise ProcheNonDisponible(EXPLICATION_REFUS_AMI_PROCHE)
