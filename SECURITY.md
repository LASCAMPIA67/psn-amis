# Sécurité

## Versions suivies

Seule la dernière version publiée reçoit des corrections de sécurité.

| Version | Corrections de sécurité |
| --- | --- |
| 2.2.x | oui |
| 2.1.x et avant | non |

## Signaler une faille

**N'ouvre pas de ticket public.** Utilise le signalement privé de GitHub : onglet **Security**, puis **Report a vulnerability**, ou directement [ce formulaire](https://github.com/LASCAMPIA67/psn-amis/security/advisories/new).

Décris le problème, comment le reproduire et son effet possible. Tu recevras une réponse dans les 7 jours. Une fois la faille corrigée et publiée, elle sera décrite publiquement, avec tes remerciements si tu le souhaites.

## Le code npsso

Le code npsso donne accès à **tout** ton compte PlayStation, comme un mot de passe. PSN Amis le traite ainsi :

- Il est lu dans `npsso.txt`, dans le dossier du programme, et nulle part ailleurs. L'assistant de connexion le saisit sans l'afficher et réserve le fichier à ton compte Windows (droits NTFS).
- Il n'est **jamais** affiché, ni écrit dans `journal.txt`, ni dans un message d'erreur : s'il apparaissait par accident, il serait remplacé par `[code masqué]`.
- Il ne quitte ton PC que vers les serveurs d'authentification de Sony, pour obtenir une autorisation d'accès temporaire.
- `npsso.txt` est ignoré par Git (`.gitignore`) : il ne peut pas être publié par erreur, même depuis une copie du dépôt. Le dossier `.claude/` contient aussi une règle qui interdit à Claude Code de lire ce fichier.
- Si tu penses que ton code a fui : déconnecte-toi de playstation.com dans ce navigateur et change ton mot de passe. L'ancien code cesse alors de fonctionner.

## Ce que fait PSN Amis

Pour évaluer les risques, voici exactement ce que fait le programme :

- **Internet :** il ne contacte que les serveurs de Sony (`sony.com`, `playstation.com`, `playstation.net`), à travers la bibliothèque [PSNAWP](https://github.com/isFakeAccount/psnawp). Toute autre adresse est bloquée avant l'envoi. Il lit les demandes d'amis reçues, la liste d'amis et les profils publics des joueurs concernés ; il accepte des demandes d'amis. Il ne retire jamais d'amis et n'accepte jamais une demande de partage du vrai nom.
- **Fichiers :** il écrit `journal.txt` (dates, heures et pseudos des joueurs acceptés ou retirés) et `accepter_amis.lock` (verrou) dans son dossier, et le petit fichier de suivi des requêtes de PSNAWP dans le dossier temporaire de Windows. Il ne lit rien d'autre.
- **Système :** il baisse sa propre priorité, règle le mode de sa console le temps du tableau de bord (et le remet à la sortie), et peut ouvrir `journal.txt` dans le Bloc-notes à ta demande (touche <kbd>J</kbd>).
- **Rien d'autre :** aucune télémétrie, aucune mise à jour automatique, aucun compte créé ailleurs.

## Bibliothèques

Les versions exactes de toutes les bibliothèques sont figées dans `uv.lock` et installées par `uv sync --locked`. Dependabot propose leurs mises à jour chaque mois, et les actions GitHub des workflows sont figées par empreinte de commit.
