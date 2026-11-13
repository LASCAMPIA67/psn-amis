"""Pilotage du moteur par l'application : démarrer, arrêter, redémarrer, régler.

Aucune dépendance à Qt : l'interface appelle ces méthodes, qui ne bloquent jamais
longtemps (l'arrêt du moteur est demandé, puis constaté plus tard). Un seul fil moteur
peut exister à la fois : redémarrer attend la fin du précédent avant d'en lancer un
nouveau, ce qui empêche deux automatisations simultanées.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from psn_amis import moteur, reglages
from psn_amis.gestion import Gestion
from psn_amis.reglages import Effet, Reglages

journal = logging.getLogger("psn_amis")


class EtatMoteur(StrEnum):
    ARRETE = "arrêté"
    EN_MARCHE = "en marche"
    ARRET_EN_COURS = "arrêt en cours"


@dataclass
class ResultatReglages:
    enregistre: bool
    problemes: list[str] = field(default_factory=list)
    # Ce qu'il faut faire pour que tout s'applique.
    effets: set[Effet] = field(default_factory=set)


class Controleur:
    def __init__(
        self,
        suivi: moteur.Suivi,
        fichier_reglages: Path,
        dossier_donnees: Path,
        reglages_initiaux: Reglages,
    ) -> None:
        self.suivi = suivi
        self.fichier_reglages = fichier_reglages
        self._reglages = reglages_initiaux
        self._verrou = threading.Lock()
        self._fil: threading.Thread | None = None
        self.commandes = moteur.Commandes()
        self._relancer_apres_arret = False
        self.gestion = Gestion(
            dossier_donnees, lambda: self._reglages, self._couper_nettoyage
        )
        # Appelé (depuis n'importe quel fil) quand les réglages changent.
        self.reglages_changes: Callable[[Reglages], None] = lambda nouveaux: None

    # ─── Moteur ───

    @property
    def reglages(self) -> Reglages:
        return self._reglages

    def etat(self) -> EtatMoteur:
        with self._verrou:
            return self._etat()

    def _etat(self) -> EtatMoteur:
        if self._fil is None or not self._fil.is_alive():
            return EtatMoteur.ARRETE
        if self.commandes.arret.is_set():
            return EtatMoteur.ARRET_EN_COURS
        return EtatMoteur.EN_MARCHE

    def demarrer(self) -> bool:
        """Lance le moteur s'il est arrêté ; False s'il tourne ou s'arrête encore."""
        with self._verrou:
            if self._etat() is not EtatMoteur.ARRETE:
                return False
            pause = self.commandes.pause.is_set()
            self.commandes = moteur.Commandes()
            if pause:
                self.commandes.pause.set()
            self._fil = threading.Thread(
                target=self._tourner,
                args=(self.commandes,),
                name="moteur-psn-amis",
                daemon=True,
            )
            self._fil.start()
        journal.info("Moteur démarré.")
        return True

    def _tourner(self, commandes: moteur.Commandes) -> None:
        try:
            moteur.tourner_en_continu(
                moteur.Etat(), self.suivi, commandes, self.gestion
            )
        finally:
            self.suivi.statut(moteur.Statut.DEMARRAGE, "Moteur arrêté")
            relancer = False
            with self._verrou:
                relancer = self._relancer_apres_arret
                self._relancer_apres_arret = False
            if relancer:
                # Le fil actuel se termine juste après : on attend qu'il soit fini.
                threading.Thread(
                    target=self._relancer, name="relance-moteur", daemon=True
                ).start()

    def _relancer(self) -> None:
        fil = self._fil
        if fil is not None and fil is not threading.current_thread():
            fil.join(30)
        if not self.demarrer():
            journal.error("Le moteur n'a pas pu redémarrer : réessayez « Démarrer ».")

    def arreter(self) -> None:
        """Demande l'arrêt (après l'opération en cours) ; ne bloque pas."""
        with self._verrou:
            self._relancer_apres_arret = False
            if self._etat() is EtatMoteur.EN_MARCHE:
                self.commandes.arreter()
                journal.info("Arrêt du moteur demandé.")

    def redemarrer(self) -> None:
        """Arrête proprement le moteur puis le relance, sans fermer la fenêtre."""
        with self._verrou:
            etat = self._etat()
            if etat is EtatMoteur.ARRETE:
                relancer_tout_de_suite = True
            else:
                relancer_tout_de_suite = False
                self._relancer_apres_arret = True
                self.commandes.arreter()
        journal.info("Redémarrage du moteur...")
        if relancer_tout_de_suite:
            self.demarrer()

    def attendre_arret(self, delai: float) -> bool:
        """Arrête et attend la fin du moteur (fermeture de l'application)."""
        with self._verrou:
            self._relancer_apres_arret = False
            self.commandes.arreter()
            fil = self._fil
        if fil is not None:
            fil.join(delai)
        return self.etat() is EtatMoteur.ARRETE

    # ─── Commandes ───

    def basculer_pause(self) -> bool:
        en_pause = self.commandes.basculer_pause()
        journal.info(
            "Pause : les nouvelles demandes attendent."
            if en_pause
            else "Reprise : les demandes en attente vont être acceptées."
        )
        return en_pause

    def en_pause(self) -> bool:
        return self.commandes.pause.is_set()

    def verifier_maintenant(self) -> None:
        self.commandes.verifier_maintenant()

    def reconnecter(self) -> None:
        self.commandes.demander_reconnexion()

    # ─── Réglages ───

    def appliquer(self, nouveaux: Reglages) -> ResultatReglages:
        """Vérifie, enregistre et applique de nouveaux réglages."""
        problemes = reglages.coherence(nouveaux)
        if problemes:
            return ResultatReglages(False, problemes)
        anciens = self._reglages
        effets = {
            reglages.info(nom)["effet"]
            for nom in reglages.CHAMPS
            if getattr(anciens, nom) != getattr(nouveaux, nom)
        }
        try:
            reglages.enregistrer(nouveaux, self.fichier_reglages)
        except OSError as erreur:
            return ResultatReglages(False, [f"Enregistrement impossible : {erreur}"])
        self._reglages = nouveaux
        moteur.appliquer_reglages(nouveaux)
        # L'intervalle s'applique dès la prochaine attente.
        self.commandes.verifier_maintenant()
        effets.discard(Effet.IMMEDIAT)
        self.reglages_changes(nouveaux)
        return ResultatReglages(True, [], effets)

    def _couper_nettoyage(self, raison: str) -> None:
        """Arrêt d'urgence du nettoyage (cycle détecté ou bouton)."""
        if self._reglages.nettoyage_mode == "manuel":
            return
        nouveaux, _ = reglages.modifier(self._reglages, nettoyage_mode="manuel")
        resultat = self.appliquer(nouveaux)
        if not resultat.enregistre:
            journal.error("Nettoyage non coupé : %s", "; ".join(resultat.problemes))

    def arret_d_urgence(self) -> None:
        """Coupe le nettoyage automatique et annule toutes les suppressions."""
        self.gestion.annuler()
        self._couper_nettoyage("arrêt d'urgence")
        journal.warning(
            "Arrêt d'urgence : suppressions annulées, nettoyage repassé en manuel."
        )
