# PZ Updater

Programik do aktualizowania modów Project Zomboid (Build 42), które wymagają ręcznej instalacji.

Sam znajduje Steama, grę i folder workshop, sprawdza datę ostatniej aktualizacji moda na Steamie i podmienia pliki.

## Aktualizuje

- ZombieBuddy
- Temporary Fix for ZombieBuddy
- Better Car Physics

## Budowanie

```bash
.buildenv/Scripts/python.exe -m PyInstaller --onefile --windowed --name PZUpdater --collect-all customtkinter --icon icon.ico --add-data "icon.ico;." --clean pzupdater.py
```
