# Contribuer à PSN Amis

Merci de vouloir aider ! Ce guide explique comment signaler un problème, proposer une idée ou modifier le code.

## Signaler, proposer, demander

- **Un problème :** ouvre un ticket [« Signaler un problème »](https://github.com/LASCAMPIA67/psn-amis/issues/new?template=bug.yml).
- **Une idée :** ouvre un ticket [« Proposer une idée »](https://github.com/LASCAMPIA67/psn-amis/issues/new?template=idee.yml).
- **Une question :** passe par les [discussions](https://github.com/LASCAMPIA67/psn-amis/discussions).
- **Une faille de sécurité :** jamais en public, voir [SECURITY.md](SECURITY.md).

N'écris jamais ton code npsso, ni aucune information personnelle (pseudos d'autres joueurs, chemins de ton PC…). Les lignes de `journal.txt` peuvent être utiles : relis-les avant de les coller.

## Préparer ton PC

- Windows 10 ou 11 (le tableau de bord utilise la console Windows).
- [uv](https://docs.astral.sh/uv/) : il installe Python 3.15 et les bibliothèques tout seul.
- [Git](https://git-scm.com/) et, si possible, [GitHub CLI](https://cli.github.com/).
- Un éditeur qui suit [EditorConfig](https://editorconfig.org/). Avec Visual Studio Code, les extensions conseillées sont proposées à l'ouverture du dossier (Python, Ruff, EditorConfig, markdownlint, TOML).

Puis, dans le dossier du projet :

```shell
uv sync          # crée .venv avec Python 3.15, les bibliothèques et les outils de développement
uv run pytest    # lance les tests
```

Pour découvrir l'application sans compte : `uv run python -m psn_amis --demo` (faux compte, aucune requête). Pour tester en vrai, il te faut ton propre code npsso : lance `Lancer PSN Amis.cmd`, l'assistant te le demande et le range dans le Gestionnaire d'identification de Windows. Il n'y a aucun code dans le dépôt, et `npsso.txt` est ignoré par Git. **Ne lance jamais de suppression d'amis sur un vrai compte pour tester** : utilise le mode démonstration.

## Règles du code

- Python 3.15, paquet `src/psn_amis/`. Le moteur (`moteur.py`) et la gestion des amis (`amis.py`, `gestion.py`, `nettoyage.py`, `demandes.py`, `psn.py`) ne dépendent ni de Qt ni de Rich ; `controleur.py` pilote le moteur sans Qt ; l'interface est dans `app.py` et `ui/`, le mode console dans `console.py` et `tableau_de_bord.py`.
- **Un seul fil parle à Sony** : le moteur. L'interface ne fait jamais de requête elle-même ; elle demande des opérations à `Gestion`, que le moteur exécute entre deux vérifications. Elle ne touche jamais aux widgets depuis un autre fil (signaux Qt, voir `ui/commun.py`).
- Noms, textes et commentaires **en français**, avec des phrases simples. L'application vouvoie ; la documentation du dépôt tutoie.
- Les réglages modifiables par l'utilisateur sont déclarés **une seule fois**, dans `reglages.py` : valeur par défaut, bornes ou choix, libellé, description et effet d'un changement. La page Paramètres et `reglages.toml` en sont tirés. Les réglages techniques restent en haut de `moteur.py`.
- La version est écrite à un seul endroit : `src/psn_amis/__init__.py` (`outils/verifier_version.py` contrôle `pyproject.toml` et `CHANGELOG.md`).
- Ne jamais casser la sécurité : le code npsso n'est jamais affiché ni journalisé (tout message passe par `FormatMasque`), seuls les serveurs de Sony peuvent être contactés pour le compte (`AdaptateurSony`), la seule autre requête (version sur GitHub) reste coupée par défaut, aucune suppression d'ami sans confirmation (ou nettoyage activé), jamais un ami protégé ni le compte connecté, jamais une demande d'ami proche acceptée ou refusée (le refus de PSNAWP supprimerait l'ami).
- Les tests ne touchent jamais au vrai coffre de Windows ni aux vraies notifications : `tests/conftest.py` les remplace pour tous les tests, et les tests qui lancent le vrai programme écrivent un `reglages.toml` avec `coffre_windows = false`.
- Le code est mis en forme et vérifié par [Ruff](https://docs.astral.sh/ruff/) (règles dans `pyproject.toml`, 88 colonnes). Les données venant de Sony (pseudos…) sont affichées avec `Text(...)`, jamais interprétées comme du balisage Rich.
- Tout ce qui parle à Sony passe par `moteur.py` ou `psn.py` et se teste avec le faux Sony (`tests/conftest.py`, `src/psn_amis/simulation.py`) : aucun test ne doit avoir besoin d'Internet ni d'un vrai compte. Les tests de la fenêtre tournent hors écran (`QT_QPA_PLATFORM=offscreen`).
- Les captures d'écran de `docs/images/` sont faites avec des données inventées : `outils/captures_fenetre.py` pour la fenêtre (PNG), `outils/captures.py` pour la console (SVG).

## Vérifier avant d'envoyer

Depuis le dossier du projet :

```shell
uv run ruff check .                   # qualité du code
uv run ruff format .                  # mise en forme
uv run pytest                         # tests (environ 2 minutes)
uv run outils/verifier_version.py     # version identique dans __init__.py, pyproject.toml et CHANGELOG.md
uv run outils/construire.py           # Windows : exécutables, démarrage réel, installateur
uv run outils/tester_installation.py  # Windows : installe, met à niveau, désinstalle pour de vrai
uv run outils/captures.py             # redessine les captures d'écran, si l'affichage a changé
uv run outils/icone.py                # redessine l'icône, si outils/icone.py a changé
```

Essaie ensuite la fenêtre en démonstration (`uv run python -m psn_amis --demo`), puis en vrai avec ton compte : `Lancer PSN Amis.cmd`.

Les mêmes vérifications tournent sur GitHub à chaque envoi, avec en plus [markdownlint](https://github.com/DavidAnson/markdownlint-cli2) (documents) et [actionlint](https://github.com/rhysd/actionlint) (workflows).

## Messages de commit

Le projet suit [Conventional Commits](https://www.conventionalcommits.org/fr/v1.0.0/), avec une description en français :

| Type | Quand l'utiliser |
| --- | --- |
| `feat` | nouvelle fonction ou changement visible |
| `fix` | correction d'un problème |
| `docs` | documentation |
| `refactor` | code réorganisé, sans changement visible |
| `test` | tests |
| `build` | outils, bibliothèques, uv |
| `ci` | vérifications automatiques sur GitHub |
| `chore` | entretien |

Exemple : `feat: la touche C change le code npsso sans quitter`.

## Demandes de fusion

1. Crée une branche à partir de `main`.
2. Décris ton changement dans `CHANGELOG.md`, partie « Non publié ».
3. Ouvre la demande de fusion : le modèle te guide.
4. Les vérifications automatiques doivent être vertes. La fusion se fait en un seul commit (*squash*).

## Versions

PSN Amis suit le [versionnage sémantique](https://semver.org/lang/fr/) : `MAJEUR.MINEUR.CORRECTIF`.

- **CORRECTIF** (2.2.1) : uniquement des corrections.
- **MINEUR** (2.3.0) : de nouvelles fonctions, sans rien casser.
- **MAJEUR** (3.0.0) : des changements qui obligent à changer ses habitudes (touches, réglages, fichiers…).

Pour publier une version (mainteneur) :

1. Mets le même numéro dans `moteur.py` (`VERSION`), `pyproject.toml` (`version`) et `CHANGELOG.md` (nouveau titre daté, à la place de « Non publié »), puis `uv lock`.
2. Vérifie avec `uv run outils/verifier_version.py`, et envoie un commit `chore: version X.Y.Z`.
3. Pose l'étiquette et envoie-la : `git tag vX.Y.Z` puis `git push origin vX.Y.Z`. Le workflow « Publication » vérifie, teste et crée la publication GitHub, avec les notes tirées du journal des modifications.
