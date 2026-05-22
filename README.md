# Power Timer

Power Timer existe ici sous deux formes:

- une application GTK4/libadwaita en Python 3, conservée comme version autonome;
- une extension GNOME Shell GJS, qui est la version destinée à extensions.gnome.org.

La version soumise à GNOME Extensions repose sur [metadata.json](metadata.json) et [extension.js](extension.js).

## Extension GNOME Shell

La soumission GNOME cible GNOME Shell 46 et 50.

Construire l'archive de soumission:

```bash
bash build-extension.sh
```

L'archive finale est générée dans `build/power-timer@threeaxe.zip`.

Pour tester localement dans GNOME Shell:

```bash
gnome-extensions install --force build/power-timer@threeaxe.zip
gnome-extensions enable power-timer@threeaxe
```

## Version autonome

Power Timer est une application GNOME en Python 3, GTK4 et libadwaita qui permet de programmer des actions système depuis une interface moderne.

## Fonctions

- Extinction et redémarrage via un minuteur interne, puis exécution finale de `systemctl poweroff` ou `systemctl reboot`
- Veille avec `systemctl suspend`
- Veille prolongée avec `systemctl hibernate`
- Veille hybride avec `systemctl hybrid-sleep`
- Compte à rebours en temps réel
- Boutons rapides 15 min, 30 min, 1 h, 2 h, 3 h, 4 h, 5 h et 6 h
- Notifications système avant l'exécution
- Désactivation automatique des modes non pris en charge
- Icône de zone de notification pour rouvrir l'application quand la fenêtre est réduite ou fermée

## Dépendances de la version autonome

Installez les paquets Debian suivants :

- `python3`
- `python3-gi`
- `python3-setproctitle`
- `zenity`
- `gir1.2-gtk-4.0`
- `gir1.2-adw-1`
- `gir1.2-gtk-3.0`
- `gir1.2-ayatanaappindicator3-0.1`

Selon votre environnement, `sudo` doit aussi être disponible si vous ne lancez pas l'application en root.

## Installation de la version autonome

Après génération du paquet, installez-le avec :

```bash
sudo apt install ./build/power-timer_1.0.0_all.deb
```

Vous pouvez aussi utiliser `dpkg -i`, puis corriger les dépendances avec `sudo apt -f install` si nécessaire.

## Build du .deb

Le script `build.sh` prépare un répertoire de staging, copie les fichiers attendus, applique les permissions utiles et génère le paquet avec `dpkg-deb`.

```bash
bash build.sh
```

Le paquet final est généré dans `build/power-timer_1.0.0_all.deb`.

## Permissions requises

Power Timer doit pouvoir exécuter des commandes système sans interaction terminal.

Quand vous lancez le binaire installé `power-timer`, le logiciel démarre normalement en mode utilisateur et se réduit dans la zone de notification quand elle est disponible. L'authentification root n'est demandée que pour une instance root explicite ou quand une action système le nécessite.

Le bouton Root dans le header relance une copie distincte de l'application avec élévation, sans mélanger la session utilisateur et la session root.

Si vous exécutez directement [app.py](app.py), l'application reste en mode utilisateur et s'appuie sur `sudo -n` pour les actions système; dans ce cas, vous devez autoriser les commandes voulues via `sudoers` ou lancer l'application en root.

Quand le support AppIndicator est présent, fermer la fenêtre la cache dans la zone de notification au lieu de quitter. Le menu du tray permet de rouvrir ou quitter l'application.

L'application expose aussi un vrai nom de processus (`power-timer`), un menu d'application, et des raccourcis standard comme `F1` pour la boîte de dialogue À propos et `Ctrl+Q` pour quitter.

### Option 1, simple

Lancer l'application avec des privilèges suffisants, par exemple en root.

### Option 2, recommandée

Autoriser les commandes nécessaires sans mot de passe via `/etc/sudoers` en utilisant `visudo` :

```sudoers
votre_utilisateur ALL=(root) NOPASSWD: /sbin/shutdown
votre_utilisateur ALL=(root) NOPASSWD: /bin/systemctl suspend
votre_utilisateur ALL=(root) NOPASSWD: /bin/systemctl hibernate
votre_utilisateur ALL=(root) NOPASSWD: /bin/systemctl hybrid-sleep
```

L'application utilise `sudo -n` lorsqu'elle n'est pas exécutée en root, donc elle échoue proprement si la règle est absente.

L'arrêt et le redémarrage passent par `systemctl ... --check-inhibitors=no` au moment de l'exécution finale pour ignorer les inhibiteurs actifs quand vous avez choisi explicitement le mode root.

## Compatibilité

- L'hibernation dépend du matériel, du noyau et de la configuration du swap.
- Certains postes n'exposent pas `disk` dans `/sys/power/state`; dans ce cas, le bouton d'hibernation est désactivé.
- La veille hybride n'est pas supportée partout.
- Si `systemctl` ou `shutdown` est introuvable, les actions correspondantes sont désactivées et un message utilisateur est affiché.

## Installation des fichiers

Le paquet installe :

- `/usr/bin/power-timer` (lanceur qui peut demander une authentification root via `pkexec` ou `sudo`)
- `/usr/share/power-timer/app.py`
- `/usr/share/applications/power-timer.desktop`
- `/usr/share/icons/hicolor/256x256/apps/power-timer.png`
