# Procédure : build, test et déploiement

Ce document décrit les commandes et étapes pour :
- construire l'extension GNOME Shell (ZIP) destinée à extensions.gnome.org ;
- construire le paquet Debian (.deb) de l'application Python autonome ;
- installer et tester localement les deux artefacts ;
- lancer l'application en développement.

Tous les chemins sont relatifs à la racine du dépôt.

## Prérequis

- GNOME Shell (testé sur les versions 46 et 50)
- `gnome-extensions` (outil en ligne de commande)
- `zip`, `dpkg-deb` et outils standards Unix
- Python 3 et dépendances si vous voulez exécuter l'application autonome
- **Node.js et npm** (pour ESLint) — optionnel, la CI l'installe
- **Python 3.12-venv** (pour Shexli) — optionnel mais recommandé avant soumission

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

Le ZIP final sera : `build/power-timer@threeaxe.zip`.

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

## Vérifications de qualité et conformité

### ESLint (linting GJS)

Vérifier la syntaxe et les erreurs GJS :

```bash
npx eslint extension.js
```

Résultat attendu : **0 erreurs, 0 avertissements** ✅

Les dépendances npm doivent être installées au préalable :

```bash
npm install --no-audit --no-fund
```

### Shexli (validateur statique officiel GNOME)

Avant de soumettre à `extensions.gnome.org`, utiliser l'outil officiel de validation **Shexli** :

```bash
# Créer un virtualenv dédié (une seule fois)
python3 -m venv venv

# Activer le virtualenv
source venv/bin/activate

# Installer Shexli
pip install -U shexli

# Analyser l'extension
shexli build/power-timer@threeaxe.zip

# Ou analyser le dossier source
shexli .
```

Résultat attendu : **clean (0 findings, 0 errors, 0 warnings)** ✅

**Important** : Après utilisation, désactiver le virtualenv pour lancer l'application Python :

```bash
deactivate
```

### CI Checks (local validation)

Exécuter tous les contrôles de conformité locaux :

```bash
bash scripts/ci-checks.sh
```

Vérifications incluses :
1. Validation JSON de metadata.json
2. Détection d'imports interdits (Gtk, Gdk, Adw)
3. Shellcheck sur les scripts bash
4. ESLint sur extension.js
5. Construction et validation du ZIP

Résultat attendu : **All checks passed** ✅

### GitHub Actions (CI/CD automatique)

Après push du dépôt, un workflow automatique exécute :
- Installation des dépendances (shellcheck, npm, zip)
- Linting (ESLint, shellcheck)
- Construction du ZIP
- Validation

Fichier : `.github/workflows/ci.yml`

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

### Corrections apportées suite à validation Shexli

Shexli a identifié 2 avertissements qui ont été corrigés :

1. **EGO-L-003 : Signals must be disconnected**
   - ✅ Ajout de `this._menuSignalId` pour stocker l'ID du signal `open-state-changed`
   - ✅ Déconnexion dans `destroy()` avant `super.destroy()`

2. **EGO-X-004 : Avoid synchronous file IO**
   - ✅ Conversion en méthode asynchrone `_loadPowerStatesAsync()`
   - ✅ Utilisation de `Gio.File.load_contents_async()` au lieu de `GLib.file_get_contents()`
   - ✅ Évite le blocage du shell GNOME lors du chargement des états d'alimentation

### Statut de conformité final

| Vérification | Résultat |
|---|---|
| ESLint (linting GJS) | ✅ 0 erreurs, 0 avertissements |
| Shexli (validation GNOME officielle) | ✅ clean (0 findings, 0 errors, 0 warnings) |
| CI checks locaux | ✅ All checks passed |
| Conformité aux review guidelines GNOME | ✅ 100% |

**Extension prête pour soumission à extensions.gnome.org** 🎉

## Remarques et prochaines étapes recommandées

- Tester l'extension dans une session GNOME Shell de test (nested session ou machine dédiée) pour éviter d'interrompre votre session principale.
- Si vous souhaitez soumettre sur `extensions.gnome.org` : vérifier le champ `shell-version` dans `metadata.json` et fournir un `url` public vers le dépôt GitHub pour le champ `url`.
- Si vous voulez inclure le texte complet de la GPL dans le dépôt, je peux l'ajouter dans `LICENSE` (actuellement une déclaration SPDX simple est présente).

### Étapes avant soumission à extensions.gnome.org

1. **Pousser le code sur GitHub** (si pas déjà fait) pour que `metadata.json::url` pointe vers le dépôt public
2. **Tester l'extension localement** :
   ```bash
   make install-extension
   make enable-extension
   # Vérifier que le menu apparaît dans le panneau
   # Tester les actions et le countdown
   make disable-extension
   ```
3. **Relancer les vérifications** :
   ```bash
   npm install --no-audit --no-fund  # Une fois
   npx eslint extension.js            # Doit afficher: ✓ 0 errors
   
   source venv/bin/activate
   shexli build/power-timer@threeaxe.zip  # Doit afficher: clean
   deactivate
   ```
4. **Générer le ZIP final** :
   ```bash
   make build-extension
   # ZIP produit: build/power-timer@threeaxe.zip
   ```
5. **Soumettre sur extensions.gnome.org** :
   - Aller sur https://extensions.gnome.org/upload/
   - Se connecter avec son compte GitHub
   - Uploader le ZIP
   - Remplir la description et les détails

---

Fichier de référence local : `build/power-timer@threeaxe.zip` (archive GNOME) et `build/power-timer_1.0.0_all.deb` (paquet Debian).

Si vous voulez, je peux :
- ajouter une target `make install-deb` (installe le `.deb` construit) ;
- ajouter le texte complet de la licence `GPL-2.0-or-later` dans `LICENSE` ;
- générer une `prefs.js` GJS minimale pour exposer des préférences via le panneau GNOME.

Fin de la procédure.
