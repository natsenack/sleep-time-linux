# Procédure : build, test et déploiement

Ce document décrit les commandes et étapes pour :
- construire l'extension GNOME Shell (ZIP) destinée à extensions.gnome.org ;
- construire le paquet Debian (.deb) de l'application Python autonome ;
- installer et tester localement les deux artefacts ;
- lancer l'application en développement.

Tous les chemins sont relatifs à la racine du dépôt.

## Prérequis

- GNOME Shell (ici testé sur la version 46)
- `gnome-extensions` (outil en ligne de commande)
- `zip`, `dpkg-deb` et outils standards Unix
- Python 3 et dépendances si vous voulez exécuter l'application autonome

## Fichiers clés ajoutés ou modifiés

- `metadata.json` : manifeste de l'extension GNOME Shell
- `extension.js` : code principal de l'extension GJS
- `build-extension.sh` : script de construction du ZIP de l'extension
- `build.sh` : script existant de construction du `.deb` (corrigé pour permissions et construction via `/tmp`)
- `Makefile` : cibles pratiques (`make run`, `make build-extension`, `make build-deb`, etc.)
- `LICENSE` : déclaration de licence (SPDX: GPL-2.0-or-later)

## Commandes utiles (exemples)

Construire l'archive de l'extension (ZIP) :

```bash
make build-extension
# ou
bash build-extension.sh
```

Le ZIP final sera : `build/power-timer@natsenack.github.io.zip`.

Installer et tester l'extension localement :

```bash
make install-extension
make enable-extension
# pour désactiver :
make disable-extension
# pour désinstaller :
make uninstall-extension
```

Construire le paquet Debian (.deb) de l'application Python :

```bash
make build-deb
# ou
bash build.sh
```

Le `.deb` final sera : `build/power-timer_1.0.0_all.deb`.

Installer le `.deb` manuellement :

```bash
sudo apt install ./build/power-timer_1.0.0_all.deb
```

Lancer l'application en développement (version Python) :

```bash
make run
# ou
bash launch.sh
```

Arrêter l'application (exemple) :

```bash
pkill power-timer
pkill -f tray_helper.py
```

## Vérifications après installation

- Pour l'extension GNOME :
  - vérifier la présence dans la liste des extensions : `gnome-extensions list`
  - contrôler l'état : `gnome-extensions info <uuid>`
  - tester `enable` / `disable` et ouvrir le menu de l'indicateur
- Pour le `.deb` :
  - vérifier les fichiers installés (ex. `/usr/bin/power-timer`, `/usr/share/power-timer/`)
  - vérifier les icônes et le `.desktop`

## Points de conformité GNOME (rappels)

- L'archive ZIP soumise à `extensions.gnome.org` doit contenir uniquement les fichiers nécessaires : `metadata.json`, `extension.js`, `LICENSE` et éventuellement `prefs.js`, `schemas/`, `locale/`, `stylesheet.css`.
- Ne pas inclure de scripts binaires ou exécutables modifiables par l'utilisateur pour des actions privilégiées.
- `extension.js` ne doit pas importer `Gtk`/`Adw`/`Gdk` (préférences seules peuvent utiliser GTK dans `prefs.js`).
- S'assurer que `enable()` / `disable()` nettoient tous les objets, signaux et sources de boucle.
- Licence : inclure une licence compatible (ici `GPL-2.0-or-later`).

## Remarques et prochaines étapes recommandées

- Tester l'extension dans une session GNOME Shell de test (nested session ou machine dédiée) pour éviter d'interrompre votre session principale.
- Si vous souhaitez soumettre sur `extensions.gnome.org` : vérifier le champ `shell-version` dans `metadata.json` et fournir un `url` public vers le dépôt GitHub pour le champ `url`.
- Si vous voulez inclure le texte complet de la GPL dans le dépôt, je peux l'ajouter dans `LICENSE` (actuellement une déclaration SPDX simple est présente).

---

Fichier de référence local : `build/power-timer@natsenack.github.io.zip` (archive GNOME) et `build/power-timer_1.0.0_all.deb` (paquet Debian).

Si vous voulez, je peux :
- ajouter une target `make install-deb` (installe le `.deb` construit) ;
- ajouter le texte complet de la licence `GPL-2.0-or-later` dans `LICENSE` ;
- générer une `prefs.js` GJS minimale pour exposer des préférences via le panneau GNOME.

Fin de la procédure.
