# Sécurité

## Versions suivies

Seule la dernière version publiée reçoit des corrections de sécurité.

| Version | Corrections de sécurité |
| --- | --- |
| 3.0.x | oui |
| 2.5.x et avant | non |

## Signaler une faille

**N'ouvre pas de ticket public.** Utilise le signalement privé de GitHub : onglet **Security**, puis **Report a vulnerability**, ou directement [ce formulaire](https://github.com/LASCAMPIA67/psn-amis/security/advisories/new).

Décris le problème, comment le reproduire et son effet possible. Tu recevras une réponse dans les 7 jours. Une fois la faille corrigée et publiée, elle sera décrite publiquement, avec tes remerciements si tu le souhaites.

## Le code npsso

Le code npsso donne accès à **tout** ton compte PlayStation, comme un mot de passe. PSN Amis le traite ainsi :

- Il est gardé dans le **Gestionnaire d'identification de Windows** (entrée « PSN Amis/npsso »), chiffré avec ta session Windows : un autre compte Windows du même PC ne peut pas le lire. Avec le réglage « Code npsso dans le coffre de Windows » désactivé, il est gardé à la place dans `%LOCALAPPDATA%\PSN Amis\npsso.txt`, réservé à ton compte Windows (droits NTFS). Il n'est **jamais** rangé dans le dossier d'installation.
- Il est saisi dans un champ masqué, effacé du champ dès la validation, vérifié auprès de Sony, puis rangé.
- Il n'est **jamais** affiché, ni écrit dans le journal, la console d'activité, un message d'erreur ou un export : s'il apparaissait par accident, il serait remplacé par `[code masqué]`. Les exports de réglages ne le contiennent pas.
- Il ne quitte ton PC que vers les serveurs d'authentification de Sony, pour obtenir une autorisation d'accès temporaire.
- La désinstallation ne le retire que si tu le demandes (niveau 3, ou case cochée au niveau 2), et ne retire que cette entrée du Gestionnaire d'identification.
- Si tu penses que ton code a fui : déconnecte-toi de playstation.com dans ce navigateur et change ton mot de passe. L'ancien code cesse alors de fonctionner.

## Ce que fait PSN Amis

Pour évaluer les risques, voici exactement ce que fait le programme :

- **Sony :** pour ton compte, il ne contacte que les serveurs de Sony (`sony.com`, `playstation.com`, `playstation.net`), à travers la bibliothèque [PSNAWP](https://github.com/isFakeAccount/psnawp), au plus une requête toutes les 3 secondes. Toute autre adresse est bloquée avant l'envoi. Il lit les demandes reçues, la liste d'amis et les profils publics des joueurs concernés ; il accepte des demandes d'amis ; à ta demande seulement (ou avec un nettoyage que tu as activé), il supprime des amis, ou refuse les demandes de ta liste noire si tu l'as choisi. Il n'accepte et ne refuse jamais une demande d'ami proche (partage du vrai nom).
- **Suppressions :** jamais un ami protégé, jamais le compte connecté, jamais pour un autre compte que celui pour lequel l'opération a été préparée. La relation d'amitié est vérifiée auprès de Sony juste avant chaque suppression ; une suppression sans réponse claire n'est jamais refaite automatiquement. Chaque opération est notée dans `comptes\<identifiant>\operations.jsonl`.
- **GitHub (seulement si tu l'autorises) :** une requête à `api.github.com` pour lire la dernière version publiée. Elle ne contient ni code, ni pseudo, ni identifiant. Le téléchargement d'une mise à jour n'a lieu qu'après ton clic sur « Installer la mise à jour » : seulement depuis les adresses GitHub du projet, en HTTPS, avec vérification de la taille et de l'empreinte SHA-256 (annoncée par l'API GitHub et par `SHA256SUMS.txt`). Ces empreintes viennent de GitHub comme le fichier : elles prouvent qu'il est intact, pas à elles seules qu'il est authentique. Si l'installateur est signé, sa signature Authenticode est contrôlée avant le lancement ; une signature invalide bloque l'installation.
- **Fichiers :** les données sont dans `%LOCALAPPDATA%\PSN Amis` : `reglages.toml` (et `.bak`), `journal.txt` et ses archives (dates, heures et pseudos des joueurs acceptés, partis ou supprimés), `amis.json`, le dossier `comptes\` (amis connus, amis protégés, historique des opérations, compteurs du nettoyage), `mises_a_jour\` (installateur téléchargé), le verrou `psn-amis.lock`, le fichier témoin `psn-amis.donnees`, et `diagnostic.txt` seulement avec `--diagnostic` (détails techniques, code toujours masqué). PSNAWP écrit aussi un petit fichier de suivi des requêtes dans le dossier temporaire de Windows, effacé à la fermeture.
- **Système :** installation et fonctionnement sans droits administrateur. Il baisse sa propre priorité, lit et écrit son entrée du Gestionnaire d'identification, lance Windows PowerShell en arrière-plan pour une bulle de notification (code à renouveler, liste pleine, longue coupure, nettoyage), et, si tu l'actives, ajoute une valeur « PSN Amis » dans `HKEY_CURRENT_USER\…\Run` pour démarrer avec Windows.
- **Rien d'autre :** aucune télémétrie, aucun serveur local, aucun port ouvert, aucune mise à jour installée sans ton accord.

## Désinstallation

Le programme de désinstallation ne supprime que des fichiers et dossiers nommés de PSN Amis, et seulement dans un dossier de données qui contient le fichier témoin `psn-amis.donnees`. Un fichier ajouté par l'utilisateur est gardé, et le dossier n'est retiré que s'il est vide. Python, uv et les autres programmes ne sont jamais touchés.

## Distribution et bibliothèques

- L'installateur et ses empreintes sont construits par GitHub Actions à partir d'une étiquette `vX.Y.Z`, après les tests, la compilation, le démarrage réel des exécutables et un test complet d'installation et de désinstallation.
- L'installateur n'est **pas encore signé** par un certificat de signature de code : Windows SmartScreen peut le signaler. Ne désactive jamais SmartScreen ni ton antivirus ; télécharge PSN Amis uniquement depuis la page des versions du dépôt.
- Les versions exactes de toutes les bibliothèques sont figées dans `uv.lock` et installées par `uv sync --locked`. Dependabot propose leurs mises à jour chaque mois (14 jours après leur sortie), et les actions GitHub des workflows sont figées par empreinte de commit, avec des permissions minimales. Inno Setup est téléchargé depuis sa publication officielle et vérifié par son empreinte SHA-256.
