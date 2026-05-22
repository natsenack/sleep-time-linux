# Commandes de déploiement

## Construire l'extension GNOME Shell
```bash
bash build-extension.sh
```

L'archive est générée dans `build/power-timer@threeaxe.zip`.

## Lancer l'application en développement
```bash
bash launch.sh
```

## Construire le paquet Debian
```bash
bash build.sh
```

## Installer le paquet
```bash
sudo apt install ./build/power-timer_1.0.0_all.deb
```

## Réinstaller le paquet
```bash
sudo apt install --reinstall ./build/power-timer_1.0.0_all.deb
```