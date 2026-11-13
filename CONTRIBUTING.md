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

Pour tester en vrai, il te faut ton propre code npsso : lance `Lancer PSN Amis.cmd`, l'assistant te le demande et le range dans le Gestionnaire d'identification de Windows. Il n'y a aucun code dans le dépôt, et `npsso.txt` est ignoré par Git.

## Règles du code

- Python 3.15. Trois fichiers principaux : `moteur.py` (Sony, acceptations, état partagé), `tableau_de_bord.py` (affichage Rich, thèmes et clavier), `accepter_amis.py` (démarrage). Quatre petits modules autour : `reglages.py` (`reglages.toml`), `coffre.py` (Gestionnaire d'identification de Windows), `notifications.py` (bulles et bip), `mises_a_jour.py` (dernière version sur GitHub). Le moteur ne dépend pas de Rich.
- Noms, textes et commentaires **en français**, avec des phrases simples. L'application vouvoie ; la documentation du dépôt tutoie.
- Les réglages modifiables par l'utilisateur sont dans `reglages.py` (valeurs par défaut et bornes) et documentés dans `reglages.exemple.toml`, avec la même valeur par défaut : un test le vérifie. Les réglages techniques restent en haut de `moteur.py`.
- Ne jamais casser la sécurité : le code npsso n'est jamais affiché ni journalisé (tout message passe par `FormatMasque`), seuls les serveurs de Sony peuvent être contactés pour le compte (`AdaptateurSony`), la seule autre requête (version sur GitHub) reste coupée par défaut, le script ne retire jamais d'amis et n'accepte jamais une demande de partage du vrai nom.
- Les tests ne touchent jamais au vrai coffre de Windows ni aux vraies notifications : `tests/conftest.py` les remplace pour tous les tests, et les tests qui lancent le vrai programme écrivent un `reglages.toml` avec `coffre_windows = false`.
- Le code est mis en forme et vérifié par [Ruff](https://docs.astral.sh/ruff/) (règles dans `pyproject.toml`, 88 colonnes). Les données venant de Sony (pseudos…) sont affichées avec `Text(...)`, jamais interprétées comme du balisage Rich.
- Tout ce qui parle à Sony s'écrit dans `moteur.py` et se teste avec le faux Sony de `tests/conftest.py` : aucun test ne doit avoir besoin d'Internet ni d'un vrai compte.
- Les captures d'écran de `docs/images/` sont dessinées par `outils/captures.py` avec des données inventées : pour les refaire après un changement d'affichage, relance ce script.

## Vérifier avant d'envoyer

Depuis le dossier du projet :

```shell
uv run ruff check .                   # qualité du code
uv run ruff format .                  # mise en forme
uv run pytest                         # tests (environ 30 secondes)
uv run outils/verifier_version.py     # version identique dans moteur.py, pyproject.toml et CHANGELOG.md
uv run outils/captures.py             # redessine les captures d'écran, si l'affichage a changé
uv run outils/icone.py                # redessine l'icône, si outils/icone.py a changé
```

Teste ensuite en vrai, avec ton compte : `Lancer PSN Amis.cmd`.

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
