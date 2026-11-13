# Sécurité

## Versions suivies

Seule la dernière version publiée reçoit des corrections de sécurité.

| Version | Corrections de sécurité |
| --- | --- |
| 2.5.x | oui |
| 2.4.x et avant | non |

## Signaler une faille

**N'ouvre pas de ticket public.** Utilise le signalement privé de GitHub : onglet **Security**, puis **Report a vulnerability**, ou directement [ce formulaire](https://github.com/LASCAMPIA67/psn-amis/security/advisories/new).

Décris le problème, comment le reproduire et son effet possible. Tu recevras une réponse dans les 7 jours. Une fois la faille corrigée et publiée, elle sera décrite publiquement, avec tes remerciements si tu le souhaites.

## Le code npsso

Le code npsso donne accès à **tout** ton compte PlayStation, comme un mot de passe. PSN Amis le traite ainsi :

- Il est gardé dans le **Gestionnaire d'identification de Windows** (entrée « PSN Amis/npsso »), chiffré avec ta session Windows : un autre compte Windows du même PC ne peut pas le lire. Avec `coffre_windows = false` dans `reglages.toml`, il est gardé à la place dans `npsso.txt`, dans le dossier du programme, réservé à ton compte Windows (droits NTFS). L'assistant de connexion le saisit sans l'afficher.
- Un `npsso.txt` présent au démarrage est rangé dans le coffre, puis supprimé seulement après avoir relu le code dans le coffre sans erreur.
- Il n'est **jamais** affiché, ni écrit dans `journal.txt`, ni dans un message d'erreur : s'il apparaissait par accident, il serait remplacé par `[code masqué]`.
- Il ne quitte ton PC que vers les serveurs d'authentification de Sony, pour obtenir une autorisation d'accès temporaire.
- `npsso.txt` est ignoré par Git (`.gitignore`) : il ne peut pas être publié par erreur, même depuis une copie du dépôt. Le dossier `.claude/` contient aussi une règle qui interdit à Claude Code de lire ce fichier.
- Si tu penses que ton code a fui : déconnecte-toi de playstation.com dans ce navigateur et change ton mot de passe. L'ancien code cesse alors de fonctionner. Pour l'effacer de ton PC : **Panneau de configuration › Gestionnaire d'identification › Informations d'identification Windows**, entrée **PSN Amis/npsso**.

## Ce que fait PSN Amis

Pour évaluer les risques, voici exactement ce que fait le programme :

- **Internet :** pour ton compte, il ne contacte que les serveurs de Sony (`sony.com`, `playstation.com`, `playstation.net`), à travers la bibliothèque [PSNAWP](https://github.com/isFakeAccount/psnawp). Toute autre adresse est bloquée avant l'envoi. Il lit les demandes d'amis reçues, la liste d'amis et les profils publics des joueurs concernés ; il accepte des demandes d'amis. Il ne retire jamais d'amis et n'accepte jamais une demande de partage du vrai nom.
- **Vérification de version (coupée au départ) :** avec `verifier_mises_a_jour = true` dans `reglages.toml`, une seule requête est envoyée au démarrage à `api.github.com` pour lire le numéro de la dernière version publiée. Elle ne contient ni code, ni pseudo, ni identifiant. Rien n'est téléchargé ni installé : PSN Amis affiche seulement un message.
- **Fichiers :** dans son dossier, il écrit `journal.txt` (dates, heures et pseudos des joueurs acceptés ou retirés), `amis.json` (identifiants des amis connus, pour repérer ceux qui partent pendant l'arrêt), `reglages.toml` (copié de l'exemple au premier lancement), `accepter_amis.lock` (verrou), et `diagnostic.txt` seulement avec l'option `--diagnostic` (détails techniques, code toujours masqué). Il écrit aussi le petit fichier de suivi des requêtes de PSNAWP dans le dossier temporaire de Windows. Les outils facultatifs écrivent un export CSV du journal (`outils/exporter_journal.py`) et des raccourcis sur le Bureau ou au démarrage de Windows (`Raccourcis PSN Amis.cmd`).
- **Système :** il baisse sa propre priorité, règle le mode de sa console le temps du tableau de bord (et le remet à la sortie), peut ouvrir `journal.txt` dans le Bloc-notes à ta demande (touche <kbd>J</kbd>), lit et écrit son entrée du Gestionnaire d'identification de Windows, et lance Windows PowerShell en arrière-plan pour afficher une bulle de notification (code à renouveler, liste pleine, longue coupure ; réglage `notifications`).
- **Rien d'autre :** aucune télémétrie, aucune mise à jour automatique, aucun compte créé ailleurs.

## Bibliothèques

Les versions exactes de toutes les bibliothèques sont figées dans `uv.lock` et installées par `uv sync --locked`. Dependabot propose leurs mises à jour chaque mois, et les actions GitHub des workflows sont figées par empreinte de commit.
