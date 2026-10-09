#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI translations for PZ Updater."""

DEFAULT_LANGUAGE = "en"
LANGUAGES = ("en", "pl")   # order = order of the flag buttons in the header

# Language code -> flag drawn next to it (files live in assets/, see tools/make_flags.py)
FLAGS = {"en": "flag_gb.png", "pl": "flag_pl.png"}

STRINGS = {
    "en": {
        # header
        "app.title": "PZ Updater",
        "app.tagline": "Automatic updates for Project Zomboid mods that need a manual install",
        "app.signature": "by AdamowY",

        # panels
        "panel.mods.title": "Supported mods",
        "panel.mods.subtitle": "Updated by the app",
        "panel.manual.title": "Watched mods",
        "panel.manual.subtitle": "Notifications only — you install these by hand",
        "panel.manual.add": "＋ Add",

        # buttons
        "btn.check": "Check for updates",
        "btn.update": "Update",
        "btn.install": "Install",
        "btn.open_steam": "Open on Steam",
        "btn.steam": "↗ Steam",
        "btn.copy_id": "Copy ID",
        "btn.uninstall": "Uninstall",
        "btn.manual_done": "✓ Mark as updated",
        "btn.cancel": "Cancel",
        "btn.add": "Add",
        "btn.clear": "Clear",
        "btn.close": "Close",
        "btn.copy": "Copy",
        "btn.switch_to": "Switch to {}",

        # status badges
        "status.not_subscribed": "Not subscribed",
        "status.deprecated": "Obsolete",
        "status.subscribed_not_installed": "Subscribed, not installed",
        "status.needs_update": "Update available",
        "status.new_update": "New update",
        "status.up_to_date": "Up to date",
        "status.other_build": "In game: {}",
        "status.pending": "…",
        "status.subscribed": "✓ subscribed",
        "status.no_subscription": "not subscribed",
        "status.no_patch_build": "No files for game version {}",
        "status.build_unknown": "Game version unknown, start the game once",
        "status.build_unverified": "Start the game once to confirm the version",

        # card details line
        "detail.workshop": "Workshop {}",
        "detail.steam": "Steam: {}",
        "detail.version": "version {}",
        "detail.fix_obsolete": "newer ZombieBuddy already replaces the Extensions jar",
        "detail.beta_offered": "newer BETA",
        "detail.newer_than_beta": "newer than the BETA",
        "detail.files_ok": "✓ in game ({})",
        "detail.files_missing": "✗ mod files not in the game folder",
        "detail.files_partial": "⚠ {} of {} files match",
        "detail.files_unknown": "no file data",
        "detail.build": "game version {}",
        "detail.patch_wait": "the mod has no files for this version yet",
        "detail.patch_start_game": "start the game once so the app can read your version",

        # progress overlay
        "overlay.title": "Checking for updates…",
        "overlay.progress": "mod {} of {}",

        # status bar / results
        "msg.checking": "Checking for updates…",
        "msg.check_failed": "Check failed: {}",
        "msg.check_failed_details": "Update check failed: {}",
        "msg.to_install": "to install: {}",
        "msg.new_update": "new update: {}",
        "msg.all_up_to_date": "Everything is up to date.",
        "msg.installing_one": "Installing: {}…",
        "msg.updating_one": "Updating: {}…",
        "msg.installing_many": "Installing {} mods…",
        "msg.updating_many": "Updating {} mods…",
        "msg.no_game_dir": "⚠ Project Zomboid folder not found.",
        "msg.nothing_to_update": "⚠ No mods from the game folder to update.",
        "msg.update_failed": "Update failed: {}",
        "msg.result_ok": "OK",
        "msg.result_error": "FAILED",
        "msg.some_failed": "{} mod(s) not updated — click to see the log",
        "msg.id_copied": "Copied Workshop ID: {}",
        "msg.id_not_a_number": "⚠ Workshop ID must be a number.",
        "msg.already_on_list": "⚠ This mod is already on the list.",
        "msg.added_default_name": "⚠ Added with a default name (Steam lookup failed: {})",
        "msg.added": "✓ Added: {}",
        "msg.check_first": "⚠ Check for updates first (no Steam data yet).",
        "msg.unhandled_error": "Unhandled error:\n{}",
        "msg.error_toast": "Something went wrong — click to see the log",
        "msg.update_failed_log": "Failed to update — {}",
        "msg.start": "Start — Steam: {}",
        "msg.game_dir": "Game: {}",
        "msg.removing_one": "Removing: {}…",
        "msg.remove_failed": "Removal failed: {}",

        # action results
        "action.jar_missing": "{} not found in the mod folder.",
        "action.jar_replaced": "ZombieBuddy.jar replaced.",
        "action.no_version_folders": "No version folders in manual_installation.",
        "action.no_copy_folder": "Folder '{}' not found in {}.",
        "action.folder_copied": "Copied '{}' (version {}, {}).",
        "action.source_file_missing": "File '{}' is missing from the mod folder.",
        "action.files_copied": "Copied {} into the game folder.",
        "action.unknown_type": "Unknown mod type.",
        "action.no_game_build": "Could not tell which game version you have, start the game once.",
        "action.unverified_game_build": "The game was updated and has not been started since, start it once and try again.",
        "action.no_patch_build": "The mod has no files for game version {} yet, wait for the mod to update.",
        "action.no_patch_files": "The mod's folder is empty.",
        "action.patches_installed": "Copied {} (game version {}).",
        "action.patches_replaced": "Copied {} (game version {}), removed {} of the old files.",
        "action.patches_removed": "Removed {} from the game folder.",
        "action.patches_removed_kept": "Removed {}, kept {} (changed after the install).",
        "action.nothing_to_remove": "Nothing to remove.",

        # errors
        "error.steam_no_data": "Steam returned no data for workshop item {}.",

        # dialogs
        "dialog.add.title": "Add mod",
        "dialog.add.label": "Workshop ID of the mod:",
        "dialog.add.placeholder": "e.g. 3807349984",
        "dialog.remove.title": "Uninstall",
        "dialog.remove.body": "Remove the files of \"{}\" ({}) from the game folder?",
        "toast.title": "Something went wrong",
        "console.title": "Log — PZ Updater",
        "console.heading": "Errors and events",
        "console.empty": "(no entries)",

        # one-time notices (see pzupdater.NOTICE_KEYS)
        "notice.copied": "Copied",
        "notice.zombiebuddy_launch_options.title": "One more step for ZombieBuddy",
        "notice.zombiebuddy_launch_options.body":
            "The files are in the game folder, but the game ignores them until this "
            "launch option is set.\n\n"
            "In Steam: right-click Project Zomboid, choose Properties, then Launch "
            "Options, and paste the line below. The two dashes at the end belong to "
            "it, keep them.",
        "notice.zombiebuddy_launch_options.value": "-agentlib:zbNative --",

        # short remarks shown next to a mod's name (mod entry field "name_note")
        "mod.beta.note": "(optional, recommended)",

        # unsubscribe the other half of the pair
        "notice.unsub.text":
            "Two ZombieBuddy detected - unsubscribe from \"{}\" to avoid errors!",
    },
    "pl": {
        # header
        "app.title": "PZ Updater",
        "app.tagline": "Automatyczna aktualizacja modów Project Zomboid wymagających ręcznej instalacji",
        "app.signature": "by AdamowY",

        # panels
        "panel.mods.title": "Obsługiwane mody",
        "panel.mods.subtitle": "Program aktualizuje je automatycznie",
        "panel.manual.title": "Obserwowane mody",
        "panel.manual.subtitle": "Tylko powiadomienia — instalujesz ręcznie",
        "panel.manual.add": "＋ Dodaj",

        # buttons
        "btn.check": "Sprawdź aktualizacje",
        "btn.update": "Aktualizuj",
        "btn.install": "Zainstaluj",
        "btn.open_steam": "Otwórz na Steam",
        "btn.steam": "↗ Steam",
        "btn.copy_id": "Kopiuj ID",
        "btn.uninstall": "Odinstaluj",
        "btn.manual_done": "✓ Oznacz jako zaktualizowane",
        "btn.cancel": "Anuluj",
        "btn.add": "Dodaj",
        "btn.clear": "Wyczyść",
        "btn.close": "Zamknij",
        "btn.copy": "Kopiuj",
        "btn.switch_to": "Zmień na {}",

        # status badges
        "status.not_subscribed": "Brak subskrypcji",
        "status.deprecated": "Przestarzały",
        "status.subscribed_not_installed": "Zasubskrybowany, nie zainstalowany",
        "status.needs_update": "Do aktualizacji",
        "status.new_update": "Nowa aktualizacja",
        "status.up_to_date": "Aktualny",
        "status.other_build": "W grze: {}",
        "status.pending": "…",
        "status.subscribed": "✓ subskrybowany",
        "status.no_subscription": "brak subskrypcji",
        "status.no_patch_build": "Brak plików dla wersji {}",
        "status.build_unknown": "Nie znam wersji gry, uruchom grę raz",
        "status.build_unverified": "Uruchom grę raz, żeby potwierdzić wersję",

        # card details line
        "detail.workshop": "Workshop {}",
        "detail.steam": "Steam: {}",
        "detail.version": "wersja {}",
        "detail.fix_obsolete": "nowszy ZombieBuddy już zastępuje jar Extensions",
        "detail.beta_offered": "nowsza BETA",
        "detail.newer_than_beta": "nowsza niż BETA",
        "detail.files_ok": "✓ w grze ({})",
        "detail.files_missing": "✗ brak plików moda w grze",
        "detail.files_partial": "⚠ w grze {} z {} plików zgodnych",
        "detail.files_unknown": "brak danych o plikach",
        "detail.build": "wersja gry {}",
        "detail.patch_wait": "mod nie ma jeszcze plików dla tej wersji",
        "detail.patch_start_game": "uruchom grę raz, żeby apka poznała Twoją wersję",

        # progress overlay
        "overlay.title": "Sprawdzam aktualizacje…",
        "overlay.progress": "mod {} z {}",

        # status bar / results
        "msg.checking": "Sprawdzam aktualizacje…",
        "msg.check_failed": "Błąd sprawdzania: {}",
        "msg.check_failed_details": "Błąd sprawdzania aktualizacji: {}",
        "msg.to_install": "do instalacji: {}",
        "msg.new_update": "nowa aktualizacja: {}",
        "msg.all_up_to_date": "Wszystko aktualne.",
        "msg.installing_one": "Instaluję: {}…",
        "msg.updating_one": "Aktualizuję: {}…",
        "msg.installing_many": "Instaluję ({} mody)…",
        "msg.updating_many": "Aktualizuję ({} mody)…",
        "msg.no_game_dir": "⚠ Nie znaleziono folderu gry Project Zomboid.",
        "msg.nothing_to_update": "⚠ Brak modów w folderze gry do aktualizacji.",
        "msg.update_failed": "Błąd aktualizacji: {}",
        "msg.result_ok": "OK",
        "msg.result_error": "BŁĄD",
        "msg.some_failed": "{} mod(ów) nie zaktualizowano — kliknij, by zobaczyć log",
        "msg.id_copied": "Skopiowano Workshop ID: {}",
        "msg.id_not_a_number": "⚠ Workshop ID musi być liczbą.",
        "msg.already_on_list": "⚠ Ten mod jest już na liście.",
        "msg.added_default_name": "⚠ Dodano z domyślną nazwą (błąd pobierania: {})",
        "msg.added": "✓ Dodano: {}",
        "msg.check_first": "⚠ Najpierw sprawdź aktualizacje (brak danych ze Steama).",
        "msg.unhandled_error": "Nieobsłużony błąd:\n{}",
        "msg.error_toast": "Wystąpił błąd — kliknij, by zobaczyć log",
        "msg.update_failed_log": "Nie udało się zaktualizować — {}",
        "msg.start": "Start — Steam: {}",
        "msg.game_dir": "Gra: {}",
        "msg.removing_one": "Usuwam: {}…",
        "msg.remove_failed": "Błąd usuwania: {}",

        # action results
        "action.jar_missing": "Nie znaleziono {} w folderze moda.",
        "action.jar_replaced": "ZombieBuddy.jar podmieniony.",
        "action.no_version_folders": "Brak folderów wersji w manual_installation.",
        "action.no_copy_folder": "Brak folderu '{}' w {}.",
        "action.folder_copied": "Skopiowano '{}' (wersja {}, {}).",
        "action.source_file_missing": "Brak pliku '{}' w folderze moda.",
        "action.files_copied": "Skopiowano {} do folderu gry.",
        "action.unknown_type": "Nieznany typ.",
        "action.no_game_build": "Nie wiem, którą wersję gry masz, uruchom grę raz.",
        "action.unverified_game_build": "Gra została zaktualizowana i od tego czasu nie uruchomiona. Uruchom ją raz i spróbuj ponownie.",
        "action.no_patch_build": "Mod nie ma jeszcze plików dla wersji gry {}, poczekaj na jego aktualizację.",
        "action.no_patch_files": "Folder moda jest pusty.",
        "action.patches_installed": "Wgrano {} (wersja gry {}).",
        "action.patches_replaced": "Wgrano {} (wersja gry {}), usunięto {} starych plików.",
        "action.patches_removed": "Usunięto {} z folderu gry.",
        "action.patches_removed_kept": "Usunięto {}, zostawiono {} (zmienione po instalacji).",
        "action.nothing_to_remove": "Nie ma czego usuwać.",

        # errors
        "error.steam_no_data": "Steam nie zwrócił danych dla warsztatu {}.",

        # dialogs
        "dialog.add.title": "Dodaj mod",
        "dialog.add.label": "Workshop ID moda:",
        "dialog.add.placeholder": "np. 3807349984",
        "dialog.remove.title": "Odinstaluj",
        "dialog.remove.body": "Usunąć pliki moda \"{}\" ({}) z folderu gry?",
        "toast.title": "⚠ Wystąpił błąd",
        "console.title": "Log — PZ Updater",
        "console.heading": "Log błędów i zdarzeń",
        "console.empty": "(brak wpisów)",

        # one-time notices (see pzupdater.NOTICE_KEYS)
        "notice.copied": "Skopiowano",
        "notice.zombiebuddy_launch_options.title": "Jeszcze jeden krok dla ZombieBuddy",
        "notice.zombiebuddy_launch_options.body":
            "Pliki są już w folderze gry, ale gra wczyta je dopiero po ustawieniu tej "
            "opcji startowej.\n\n"
            "W Steamie: kliknij Project Zomboid prawym przyciskiem, wybierz "
            "Właściwości, potem Opcje uruchamiania i wklej poniższą linię. Dwie "
            "kreski na końcu są jej częścią, nie usuwaj ich.",
        "notice.zombiebuddy_launch_options.value": "-agentlib:zbNative --",

        # short remarks shown next to a mod's name (mod entry field "name_note")
        "mod.beta.note": "(opcjonalny, zalecany)",

        # unsubscribe the other half of the pair
        "notice.unsub.text":
            "Wykryto dwa ZombieBuddy — odsubskrybuj „{}”, żeby uniknąć błędów!",
    },
}


def files_plural(count, lang=DEFAULT_LANGUAGE):
    """Number of files in the language's own plural form ("2 files", "2 pliki")."""
    if lang == "pl":
        if count == 1:
            return "1 plik"
        if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
            return f"{count} pliki"
        return f"{count} plików"
    return f"{count} file" if count == 1 else f"{count} files"


class Translator:
    """Looks up UI strings for one language (falls back to English, then to the key)."""

    def __init__(self, language=DEFAULT_LANGUAGE):
        self.language = language if language in STRINGS else DEFAULT_LANGUAGE

    def set_language(self, language):
        self.language = language if language in STRINGS else DEFAULT_LANGUAGE

    def __call__(self, key, *args):
        text = STRINGS[self.language].get(key) or STRINGS[DEFAULT_LANGUAGE].get(key) or key
        if not args:
            return text
        try:
            return text.format(*args)
        except (IndexError, KeyError):   # a broken placeholder must not kill the UI
            return text

    def files(self, count):
        return files_plural(count, self.language)

    def help_text(self, spec):
        """Pick the help text of a mod: {"en": ..., "pl": ...} with plain-string fallback."""
        if isinstance(spec, dict):
            return spec.get(self.language) or spec.get(DEFAULT_LANGUAGE) or ""
        return spec or ""
