"""Emplacements des données, reprise des données 2.x et écriture des réglages."""

from __future__ import annotations

import json
import tomllib

import pytest

from psn_amis import chemins, migration, reglages

# ─── Emplacements ─────────────────────────────────────────────────────────────


def test_dossier_des_donnees_force_pour_les_tests(tmp_path, monkeypatch):
    monkeypatch.setenv(chemins.VARIABLE_DONNEES, str(tmp_path / "ailleurs"))
    assert chemins.dossier_donnees() == (tmp_path / "ailleurs").resolve()


def test_dossier_des_donnees_windows(tmp_path, monkeypatch):
    monkeypatch.delenv(chemins.VARIABLE_DONNEES, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert chemins.dossier_donnees() == tmp_path / "PSN Amis"


def test_le_programme_n_est_pas_le_dossier_des_donnees():
    # Lancé depuis le code : le code et les données sont deux dossiers distincts.
    assert chemins.dossier_paquet() != chemins.dossier_donnees()
    assert chemins.dossier_projet() is not None


def test_preparer_pose_le_fichier_temoin(tmp_path):
    dossier = chemins.preparer(tmp_path / "PSN Amis é")
    assert (dossier / chemins.MARQUEUR).is_file()
    chemins.preparer(dossier)  # deux fois : aucun problème


@pytest.mark.parametrize(
    ("entree", "sortie"),
    [("2721516955383184063", "2721516955383184063"), ("12/../34", "1234")],
)
def test_nom_de_compte_sur(entree, sortie):
    assert chemins.nom_de_compte_sur(entree) == sortie


@pytest.mark.parametrize("entree", ["", "..", "compte_test"])
def test_nom_de_compte_refuse(entree):
    with pytest.raises(ValueError, match="invalide"):
        chemins.nom_de_compte_sur(entree)


# ─── Reprise des données 2.x ──────────────────────────────────────────────────


@pytest.fixture
def ancien(tmp_path):
    dossier = tmp_path / "ancienne version"
    dossier.mkdir()
    (dossier / "reglages.toml").write_text("son = true\n", encoding="utf-8")
    (dossier / "journal.txt").write_text("ligne\n", encoding="utf-8")
    (dossier / "amis.json").write_text('{"compte": "x", "amis": []}', encoding="utf-8")
    return dossier


def test_migration_copie_sans_rien_deplacer(ancien, tmp_path):
    nouveau = tmp_path / "Données ç"
    rapport = migration.migrer(ancien, nouveau)
    assert sorted(rapport.copies) == ["amis.json", "journal.txt", "reglages.toml"]
    # Les anciens fichiers restent en place : ils servent de sauvegarde.
    assert (ancien / "reglages.toml").read_text(encoding="utf-8") == "son = true\n"
    assert (nouveau / "reglages.toml").read_text(encoding="utf-8") == "son = true\n"
    assert migration.deja_faite(nouveau)
    contenu = json.loads((nouveau / "migration.json").read_text(encoding="utf-8"))
    assert contenu["source"] == str(ancien)
    assert not list(nouveau.glob("*.copie"))


def test_migration_n_ecrase_jamais(ancien, tmp_path):
    nouveau = tmp_path / "nouveau"
    nouveau.mkdir()
    (nouveau / "reglages.toml").write_text("son = false\n", encoding="utf-8")
    rapport = migration.migrer(ancien, nouveau)
    assert rapport.gardes == ["reglages.toml"]
    assert (nouveau / "reglages.toml").read_text(encoding="utf-8") == "son = false\n"


def test_migration_une_seule_fois(ancien, tmp_path):
    nouveau = tmp_path / "nouveau"
    assert migration.migrer_si_besoin(ancien, nouveau) is not None
    (ancien / "journal.txt").write_text("autre\n", encoding="utf-8")
    assert migration.migrer_si_besoin(ancien, nouveau) is None
    assert (nouveau / "journal.txt").read_text(encoding="utf-8") == "ligne\n"


def test_migration_rien_a_reprendre(tmp_path):
    assert migration.migrer_si_besoin(tmp_path / "vide", tmp_path / "n") is None
    assert migration.migrer_si_besoin(None, tmp_path / "n") is None


def test_migration_signale_un_ancien_code(ancien, tmp_path):
    # Le contenu n'est jamais lu : seul le fichier est copié, pour le coffre.
    (ancien / "npsso.txt").write_bytes(b"x")
    rapport = migration.migrer(ancien, tmp_path / "nouveau")
    assert rapport.ancien_npsso
    assert "npsso.txt" in rapport.copies


# ─── Réglages : modification, écriture, migration, import et export ──────────


def test_modifier_valide_avant_d_appliquer():
    depart = reglages.Reglages()
    nouveaux, problemes = reglages.modifier(depart, intervalle_verification=30)
    assert problemes == []
    assert nouveaux.intervalle_verification == 30
    assert depart.intervalle_verification == 15
    refuses, problemes = reglages.modifier(depart, intervalle_verification=2, son=True)
    assert refuses is depart
    assert "entre 5 et 3600" in problemes[0]


def test_modifier_verifie_la_coherence():
    _, problemes = reglages.modifier(
        reglages.Reglages(), nettoyage_seuil=1500, nettoyage_cible=1600
    )
    assert "inférieure au seuil" in problemes[0]


def test_fichier_incoherent_laisse_le_nettoyage_en_manuel(tmp_path):
    fichier = tmp_path / "reglages.toml"
    fichier.write_text(
        'nettoyage_mode = "automatique"\nnettoyage_seuil = 100\n'
        "nettoyage_cible = 200\n",
        encoding="utf-8",
    )
    lus, problemes = reglages.charger(fichier)
    assert lus.nettoyage_mode == "manuel"
    assert "mode manuel" in problemes[0]


def test_ecriture_relue_a_l_identique(tmp_path):
    fichier = tmp_path / "reglages.toml"
    modifies, _ = reglages.modifier(
        reglages.Reglages(),
        liste_noire=['Joueur "spécial"', "Antislash\\"],
        theme="clair",
        pause_entre_acceptations=0.5,
        nettoyage_heures="22-06",
    )
    reglages.enregistrer(modifies, fichier)
    lus, problemes = reglages.charger(fichier)
    assert problemes == []
    assert lus == modifies
    # Chaque réglage est expliqué dans le fichier.
    texte = fichier.read_text(encoding="utf-8")
    assert "# Thème." in texte
    assert not (tmp_path / "reglages.toml.tmp").exists()


def test_enregistrer_garde_l_ancienne_version(tmp_path):
    fichier = tmp_path / "reglages.toml"
    fichier.write_text("son = true\n", encoding="utf-8")
    reglages.enregistrer(reglages.Reglages(), fichier)
    assert (tmp_path / "reglages.toml.bak").read_text(encoding="utf-8") == (
        "son = true\n"
    )


def test_ancien_format_mis_a_jour_avec_sauvegarde(tmp_path):
    fichier = tmp_path / "reglages.toml"
    fichier.write_text("intervalle_verification = 30\nson = true\n", encoding="utf-8")
    assert reglages.format_du_fichier(fichier) == 1
    assert reglages.mettre_a_jour_le_format(fichier)
    assert reglages.format_du_fichier(fichier) == reglages.VERSION_FORMAT
    lus, _ = reglages.charger(fichier)
    assert lus.intervalle_verification == 30
    assert lus.son is True
    sauvegarde = tmp_path / "reglages.v1.toml"
    assert "intervalle_verification = 30" in sauvegarde.read_text(encoding="utf-8")
    # Déjà au bon format : rien à faire.
    assert not reglages.mettre_a_jour_le_format(fichier)


def test_ancien_format_avec_erreur_jamais_reecrit(tmp_path):
    # Une valeur fautive n'est pas remplacée en silence par la valeur par défaut.
    fichier = tmp_path / "reglages.toml"
    fichier.write_text("intervalle_verification = 1\n", encoding="utf-8")
    assert not reglages.mettre_a_jour_le_format(fichier)
    assert fichier.read_text(encoding="utf-8") == "intervalle_verification = 1\n"


def test_export_puis_import(tmp_path):
    modifies, _ = reglages.modifier(reglages.Reglages(), son=True, limite_amis=1950)
    chemin = tmp_path / "export.toml"
    reglages.exporter(modifies, chemin)
    importes, problemes = reglages.importer(chemin)
    assert problemes == []
    assert importes == modifies
    # Aucun secret dans un export : seulement des réglages connus.
    connus = set(reglages.CHAMPS) | {reglages.CLE_VERSION}
    assert set(tomllib.loads(chemin.read_text(encoding="utf-8"))) <= connus


def test_chaque_reglage_est_decrit():
    for nom in reglages.CHAMPS:
        info = reglages.info(nom)
        assert info["libelle"]
        assert info["description"]
        assert isinstance(info["effet"], reglages.Effet)


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [("02-07", (2, 7)), ("22 - 6", (22, 6)), ("7-7", None), ("1-24", None), ("", None)],
)
def test_plage_horaire(texte, attendu):
    assert reglages.plage_horaire(texte) == attendu


# ─── Retrait du code par la désinstallation ───────────────────────────────────


def test_effacer_code_seulement_l_entree_de_psn_amis():
    from psn_amis import coffre
    from psn_amis.__main__ import main

    coffre.ecrire("x", "PSN Amis/test-desinstallation")
    assert main(["--effacer-code", "--cible", "PSN Amis/test-desinstallation"]) == 0
    assert coffre.lire("PSN Amis/test-desinstallation") is None
    # Toute autre entrée du coffre est refusée.
    assert main(["--effacer-code", "--cible", "Microsoft/compte"]) == 2
