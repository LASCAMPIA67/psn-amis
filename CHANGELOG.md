# Journal des modifications

Toutes les modifications notables de PSN Amis sont consignées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), et le projet respecte le [versionnage sémantique](https://semver.org/lang/fr/). Les versions antérieures à la 2.2.0 ont été construites avant la mise du projet sous Git : elles n'ont pas d'étiquette.

## [Non publié]

## [3.0.0] - 2026-11-13

PSN Amis devient une application Windows : un installateur, une fenêtre, et la gestion de la liste d'amis. Version majeure, car l'emplacement des données, le lancement et l'organisation du code changent (voir « Incompatibilités »).

### Ajouté

- **Installateur Windows** `PSN-Amis-Setup-3.0.0.exe` : installation sans droits administrateur, dossier au choix, raccourci Bureau facultatif, présence dans les applications installées, mise à niveau sur place. Python et uv ne sont plus nécessaires.
- **Désinstallation à trois niveaux** : le programme seulement (données gardées), le programme et les données, ou tout, y compris le code npsso du Gestionnaire d'identification. Seuls les fichiers de PSN Amis sont supprimés, dans un dossier reconnu par son fichier témoin.
- **Fenêtre de l'application** : tableau de bord (statut, compte, capacité de la liste, demandes, acceptations, suppressions, synchronisation, avertissements), console d'activité intégrée (couleurs, symboles, recherche, filtres, copie, export, effacement de l'affichage sans toucher au journal), demandes en attente, paramètres, à propos.
- **Commandes** : démarrer, arrêter, pause, vérifier maintenant, reconnecter, redémarrer le moteur, redémarrer l'application, quitter, avec raccourcis clavier (<kbd>F5</kbd>, <kbd>Ctrl</kbd>+<kbd>P</kbd>, <kbd>Ctrl</kbd>+<kbd>1</kbd> à <kbd>6</kbd>…).
- **Gestion des amis** : liste consultable, triable, filtrable et recherchable ; suppression individuelle ou multiple, sélection par nombre selon un critère explicite (les plus anciennement acceptés, les premiers vus, ordre alphabétique) ; aperçu avant suppression et confirmation explicite ; file d'attente avec pause entre deux suppressions, progression, arrêt, bilan et historique. Une suppression à la réponse ambiguë est marquée « à vérifier », jamais refaite à l'aveugle, puis confirmée d'après la liste renvoyée par Sony.
- **Amis protégés** (différents de la liste blanche des demandes) : jamais supprimés, vérifiés à la sélection, dans l'aperçu et juste avant chaque suppression ; suivis par identifiant de compte même si le joueur change de pseudo ; import et export.
- **Nettoyage de la liste** : manuel par défaut, assisté (proposition à confirmer) ou automatique, avec seuil, capacité cible, limites par nettoyage et par jour, délai entre deux nettoyages, plage horaire, arrêt d'urgence, et arrêt automatique si suppressions et acceptations tournent en boucle.
- **Demandes** : acceptation automatique désactivable ; refus des demandes de la liste noire (facultatif, après vérification que le joueur n'est pas déjà ami) ; traitement des demandes d'un type non reconnu (laissées en attente par défaut).
- **Paramètres modifiables dans l'application**, avec description, bornes, validation et indication de l'effet (immédiat, redémarrage du moteur ou de l'application) ; import, export, valeurs par défaut ; reprise des données d'une ancienne version.
- **Assistant de première utilisation** : présentation, avertissement sur l'API non officielle, connexion du compte avec vérification auprès de Sony, premiers réglages.
- **Mises à jour** : vérification au lancement (si autorisée) ou à la demande, fenêtre « Mise à jour disponible » avec les nouveautés, téléchargement de l'installateur officiel vérifié (HTTPS, adresses GitHub du projet, taille, empreinte SHA-256), signature Authenticode contrôlée, puis installation et relance automatiques.
- **Thème clair**, en plus des thèmes sombre, doux et daltonien.
- **Lancement avec Windows**, démarrage réduit, icône dans la zone de notification et choix du comportement de la croix (application installée).
- **Mode démonstration** `--demo` : faux compte, aucune connexion à Sony.
- Intégration continue : compilation de l'application, démarrage réel des exécutables, construction et test de l'installateur ; publication automatique de l'installateur et de `SHA256SUMS.txt` sur une étiquette `vX.Y.Z`.

### Modifié

- **Données de l'utilisateur dans `%LOCALAPPDATA%\PSN Amis`**, séparées du programme ; données de chaque compte PSN rangées à part.
- `reglages.toml` est désormais écrit par l'application (écriture atomique, ancienne version gardée dans `reglages.toml.bak`) et porte un numéro de format ; `reglages.exemple.toml` disparaît : le fichier créé explique lui-même chaque réglage.
- Le code est rangé dans le paquet `src/psn_amis/` ; la version est définie dans `src/psn_amis/__init__.py`.
- Le journal garde un nombre d'archives réglable (`journaux_archives`).
- Les demandes d'ami proche venues d'un ami existant sont signalées avec un message plus clair.

### Sécurité

- Les demandes d'ami proche (partage du vrai nom) ne sont **jamais** acceptées automatiquement, ni refusées : la seule opération de refus de PSNAWP supprimerait l'ami lui-même. Le refus automatique est indisponible et affiché comme tel.
- Le compte connecté n'est jamais une cible de suppression, et une suppression préparée pour un compte n'est jamais exécutée sur un autre.
- La saisie du code npsso est masquée, effacée du champ aussitôt, et le code n'apparaît jamais dans la console ni dans les exports.

### Incompatibilités et migration

- Lancement : la fenêtre s'ouvre par défaut. Le tableau de bord en couleur reste disponible avec `--console` (ou « PSN Amis console.exe »). Les options `--test`, `--simple`, `--configurer` et `--diagnostic` sont conservées.
- Depuis le code source, on lance `python -m psn_amis` (le lanceur `Lancer PSN Amis.cmd` le fait) ; `accepter_amis.py` n'existe plus.
- Au premier lancement depuis le code source, `reglages.toml`, `amis.json` et le journal de la version 2.x sont **copiés** dans `%LOCALAPPDATA%\PSN Amis` ; les anciens fichiers ne sont pas modifiés. Depuis l'application installée : Paramètres → « Reprendre les données d'une ancienne version ». Le code npsso déjà rangé dans le coffre de Windows est réutilisé tel quel.

## [2.5.0] - 2026-11-13

### Ajouté

- **Réglages dans `reglages.toml`**, créé au premier lancement à partir de `reglages.exemple.toml`, qui explique chaque réglage. Un réglage mal écrit est signalé dans l'activité, et sa valeur par défaut est utilisée.
- **Code npsso dans le coffre de Windows** (Gestionnaire d'identification), chiffré avec la session Windows. Un `npsso.txt` existant y est rangé au démarrage, puis supprimé une fois le code relu sans erreur. Réglage `coffre_windows = false` pour garder le fichier.
- **Pause minutée** : touches <kbd>1</kbd>, <kbd>2</kbd> et <kbd>3</kbd> pour 5, 10 ou 30 minutes, avec le compte à rebours de la reprise dans le statut.
- **Pause automatique** après un nombre d'ajouts choisi (`pause_apres_ajouts`).
- **Demandes en attente** pendant la pause : pseudo de chacun et depuis quand il attend.
- **Liste noire et liste blanche** de pseudos (`liste_noire`, `liste_blanche`) ; chaque demande ignorée est signalée une fois.
- **Amis retirés pendant l'arrêt** : la liste d'amis est gardée dans `amis.json`, et comparée au démarrage suivant.
- **Bulles de notification Windows** pour le code à renouveler, la liste pleine et les longues coupures (`notifications`).
- **Bip à chaque ajout** : touche <kbd>S</kbd>, réglage `son`, symbole ♪ dans l'en-tête.
- **Aide** (touche <kbd>H</kbd>) : touches, symboles, et bilan des 7 derniers jours tiré du journal.
- **Défilement de l'activité** avec les flèches, <kbd>Pg.préc.</kbd>, <kbd>Pg.suiv.</kbd> et <kbd>Origine</kbd> ; l'affichage ne bouge pas quand un nouveau message arrive.
- **Histogramme des 24 dernières heures** en haut de « Derniers ajouts ».
- Les **retraits du jour** dans la carte « Aujourd'hui », le **rythme par heure** dans « Depuis le lancement », et le temps écoulé depuis le dernier ajout dans le statut.
- **Trois thèmes** de couleurs : sombre, doux et daltonien (`theme`).
- **Raccourcis Windows** : `Raccourcis PSN Amis.cmd` ajoute PSN Amis au Bureau, avec sa nouvelle icône, et au démarrage de Windows (fenêtre réduite), ou retire ces raccourcis.
- **Export du journal en CSV** pour Excel ou LibreOffice : `outils/exporter_journal.py`.
- **Vérification de nouvelle version** sur GitHub au démarrage, coupée au départ (`verifier_mises_a_jour`).
- **Option `--diagnostic`** : écrit aussi `diagnostic.txt`, avec les détails techniques des erreurs (code npsso toujours masqué).
- La présentation en anglais : `README.en.md`.

### Modifié

- Les ajouts et retraits des dernières 24 heures sont relus dans le journal au démarrage (et plus seulement ceux du jour).
- Les touches du bas de l'écran raccourcissent leurs libellés pour laisser la place à un message, au lieu de le couper.
- Les pseudos des demandeurs sont gardés en mémoire d'une vérification à l'autre : moins de requêtes à Sony.

## [2.4.1] - 2026-11-12

### Corrigé

- Un test automatique n'avait pas été mis à jour avec la 2.4.0, dont la publication a donc été refusée par les vérifications. Même programme, test corrigé.

## [2.4.0] - 2026-11-12

### Ajouté

- Dans « Derniers ajouts », un joueur qui a depuis quitté la liste d'amis est marqué d'un **▼** orange après son pseudo, avec « retiré » à la place de l'ancienneté. Les retraits du jour sont relus dans `journal.txt` au démarrage, comme les ajouts.

## [2.3.1] - 2026-11-11

### Corrigé

- Le lanceur s'arrêtait quand une bibliothèque de développement (Ruff ouvert par Visual Studio Code, par exemple) ne pouvait pas être retirée pendant la mise à jour. Il n'enlève plus rien, et si la mise à jour est impossible sur le moment, il démarre avec les bibliothèques déjà installées.

## [2.3.0] - 2026-11-11

### Ajouté

- Dans le panneau Activité, les messages des jours précédents sont datés (« 10/11 23:59 »), pour un tableau de bord qui reste ouvert plusieurs jours.

### Modifié

- Le lanceur met à jour Python et les bibliothèques à chaque démarrage quand uv est présent (un instant si rien n'a changé) : après une mise à jour de PSN Amis, il suffit de relancer.
- Pendant la saisie d'un code npsso (touche <kbd>C</kbd>), la console retrouve son réglage normal : le collage par clic droit fonctionne aussi, et <kbd>Ctrl</kbd> + <kbd>C</kbd> annule la saisie.
- Les textes du programme et la présentation parlent de l'outil lui-même, sans supposer un usage particulier.

## [2.2.0] - 2026-11-11

Première version publiée sur GitHub. Le compte connecté est celui dont vient le code npsso : n'importe qui peut utiliser PSN Amis avec son propre compte PlayStation.

### Ajouté

- L'assistant de connexion : au premier lancement, PSN Amis demande le code npsso (saisie masquée), le vérifie et l'enregistre dans `npsso.txt`, lisible seulement par le compte Windows. La touche <kbd>C</kbd> du tableau de bord permet de changer de code, donc de compte, sans quitter ; en ligne de commande, `accepter_amis.py --configurer`.
- Les demandes de **partage du vrai nom**, envoyées par des joueurs déjà amis, sont reconnues et mises à part : jamais acceptées, signalées une seule fois. Avant, elles étaient prises pour des demandes d'ami, et Sony les refusait toutes les 30 minutes (« Friend relation mismatch »).
- Le numéro de version dans l'en-tête du tableau de bord.
- Les tests automatiques (pytest) : faux Sony en mémoire, dessin de l'écran à onze tailles, lancement réel dans un autre processus.
- Le dépôt GitHub : présentation, captures d'écran, journal des modifications, guide de contribution, sécurité, code de conduite, vérifications automatiques, publication des versions et Dependabot.

### Modifié

- Le tableau de bord s'adapte à la taille de la fenêtre et au zoom (<kbd>Ctrl</kbd> + molette) : quatre cartes sur une rangée, cartes compactes en 2 × 2, ou simple résumé ; gros chiffres seulement si la hauteur le permet ; en-tête et touches raccourcis quand la place manque.
- Les messages du panneau Activité sont affichés en entier, sur plusieurs lignes si besoin, et jamais coupés en deux.
- L'autorisation d'accès Sony (valable environ une heure) est renouvelée deux minutes avant son expiration : plus de « connexion expirée » passagère.
- Les coches ✔ et les croix ✖ deviennent ✓ et ✗ : Windows dessinait les premières en émoji, deux fois trop larges et collées au texte.
- Les refus de Sony sont décrits en une phrase courte.

### Corrigé

- Le masquage du code npsso pouvait laisser dépasser un caractère quand un ancien code, plus court, avait été lu avant le bon.
- « 100 % » n'est plus affiché pour une liste d'amis presque pleine : le pourcentage est arrondi vers le bas.

## [2.1.0] - 2026-11-10

### Ajouté

- La liste d'amis est recomptée auprès de Sony à chaque vérification : chaque ami qui n'y est plus (il vous a retiré, ou vous l'avez retiré) donne une ligne « ▼ Ami retiré : pseudo » dans Activité et dans `journal.txt`.
- La carte Amis indique le remplissage en pourcentage et depuis quand le chiffre est à jour.

### Corrigé

- Le nombre d'amis n'était demandé à Sony qu'au démarrage, puis augmenté de 1 à chaque acceptation : il ne baissait jamais.

## [2.0.0] - 2026-11-10

### Ajouté

- Le tableau de bord en couleur dans la console, dessiné avec Rich : statut avec voyant et compte à rebours, ajouts du jour en gros chiffres (relus dans le journal au démarrage), ajouts depuis le lancement, jauge d'amis sur 2 000, derniers ajouts avec l'heure, fil d'activité, titre de fenêtre avec le nombre d'ajouts.
- Les touches : <kbd>P</kbd> pause, <kbd>V</kbd> vérifier maintenant, <kbd>J</kbd> ouvrir le journal, <kbd>Q</kbd> deux fois pour quitter. <kbd>Ctrl</kbd> + <kbd>C</kbd> devient une simple touche : plus de question « Terminer le programme de commandes ? ».
- `Lancer PSN Amis.cmd` : un double-clic ouvre la console ; la première fois, il installe Python et les bibliothèques avec uv.
- La fermeture de la fenêtre avec la croix est notée dans le journal.
- Le moteur est relancé tout seul s'il s'arrêtait par accident.

### Modifié

- Vérification toutes les 15 secondes, au lieu de 60.
- Le code est découpé en trois fichiers : `moteur.py` (Sony et acceptations), `tableau_de_bord.py` (affichage), `accepter_amis.py` (démarrage).
- Le projet est géré avec uv (`pyproject.toml`, `uv.lock`) et tourne sous Python 3.15 ; le code est vérifié par Ruff.
- Le processus tourne en priorité basse : les autres programmes passent avant.

## [1.0.0] - 2026-11-10

### Ajouté

- Première version : un script qui accepte les demandes d'amis reçues, affiche chaque pseudo accepté avec l'heure et l'écrit dans `journal.txt`.
- Le code npsso est lu dans `npsso.txt`, jamais affiché ni journalisé (il est masqué dans tous les messages) ; seuls les serveurs de Sony peuvent être contactés ; chaque requête a un délai maximal.
- Coupures Internet et pannes de Sony : nouvel essai automatique, avec une attente progressive. Code npsso expiré : marche à suivre affichée, nouveau code repéré tout seul.
- Liste d'amis pleine : signalée clairement, reprise automatique dès qu'une place se libère. Le script ne retire jamais d'amis.
- Une seule instance à la fois, grâce à un fichier verrou.

[Non publié]: https://github.com/LASCAMPIA67/psn-amis/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/LASCAMPIA67/psn-amis/compare/v2.5.0...v3.0.0
[2.5.0]: https://github.com/LASCAMPIA67/psn-amis/compare/v2.4.1...v2.5.0
[2.4.1]: https://github.com/LASCAMPIA67/psn-amis/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/LASCAMPIA67/psn-amis/compare/v2.3.1...v2.4.0
[2.3.1]: https://github.com/LASCAMPIA67/psn-amis/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/LASCAMPIA67/psn-amis/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/LASCAMPIA67/psn-amis/releases/tag/v2.2.0
