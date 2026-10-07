# Contributing

Thanks for wanting to help. The two things that come up most often are adding a
mod and adding a language — both are small edits in one file.

## Adding a mod

The registry is `UPDATABLE_MODS` at the top of `pzupdater.py`. Add an entry
there; the app does the rest (finds the version folder, picks the newest one,
compares the result in the game folder).

A mod only belongs here if **subscribing on Steam is not enough** — if the mod
works right after subscribing, there is nothing to automate.

Common fields:

| Field | Meaning |
| --- | --- |
| `key` | short identifier, used in the code only |
| `name` | name shown in the window (the workshop title) |
| `workshop_id` | the numbers from the workshop URL |
| `type` | `files_copy`, `jar_replace` or `folder_copy` |
| `help` | one sentence per language, see `i18n.LANGUAGES` |

Then the fields for the chosen type:

```python
# files_copy — copy named files from a fixed folder of the mod
{
    "key": "some_mod",
    "name": "Some Mod",
    "workshop_id": "1234567890",
    "type": "files_copy",
    "src_dir": os.path.join("mods", "SomeMod", "libs"),
    "files": ["SomeMod.jar", "SomeMod.dll"],
    "help": {"en": "...", "pl": "..."},
}
```

```python
# jar_replace — find a jar somewhere in the workshop folder and overwrite a file
# in the game folder. Use it when the version subfolder changes between releases.
{
    "key": "some_fix",
    "name": "Some Fix",
    "workshop_id": "1234567890",
    "type": "jar_replace",
    "jar_name": "SomeMod.jar",
    "search_under": "mods",
    "target_rel": "SomeMod.jar",
    # optional: this mod becomes pointless once another one is newer
    "obsolete_if_newer_than": "3619862853",
    "help": {"en": "...", "pl": "..."},
}
```

```python
# folder_copy — copy a folder from the newest version folder of the mod,
# for mods that ship manual_installation/<game version>/<folder>
{
    "key": "some_manual_mod",
    "name": "Some Manual Mod",
    "workshop_id": "1234567890",
    "type": "folder_copy",
    "manual_dir": os.path.join("mods", "SomeMod", "manual_installation"),
    "copy_name": "zombie",
    "target_rel": "zombie",
    "help": {"en": "...", "pl": "..."},
}
```

```python
# class_patch — compiled .class files built for one game build each. The folder
# used is the one named after the build the game reports, never "the newest", and
# the app refuses to install when it cannot read that build or check it against
# projectzomboid.jar. What an install wrote is recorded, so the card can offer
# Uninstall and only those files are deleted again.
{
    "key": "some_patches",
    "name": "Some Mod - Optional Engine Patches",
    "workshop_id": "1234567890",
    "type": "class_patch",
    "src_dir": os.path.join("mods", "SomeMod", "manual_installation"),
    "copy_name": "zombie",
    "target_rel": "zombie",
    "help": {"en": "...", "pl": "..."},
}
```

Two things to check before opening a pull request:

1. The paths really match the current workshop download. Workshop layouts change
   (`mods/...` in older packs, `Contents/mods/...` in newer ones) — open the
   folder in `steamapps/workshop/content/108600/<workshop_id>/` and look.
2. Order matters if two mods write the same file: the one that has to win goes
   lower in the list, because mods are applied top to bottom. That is how
   ZombieBuddy Extensions overwrites the loader's own jar.

## Adding a language

1. Copy the `"en"` table in `i18n.py` to a new key (for example `"de"`), translate
   the values and add the code to `LANGUAGES`.
2. Add the flag: draw it in `tools/make_flags.py` (or supply a 28x20 PNG) and put
   the file name into `FLAGS`.
3. Add the `help` text of every mod for the new language.

The placeholder count has to match the English text — `tests/test_i18n.py` fails
if a translation forgets an argument, and if a key is missing from a table.

## Running the tests

```bash
.buildenv/Scripts/python.exe -m unittest discover -s tests -v
```

## Reporting a bug

Include:

- what you expected and what happened,
- the log from the app (click the status line at the bottom of the window),
- which paths the app detected, if the problem is about finding the game.

## Style

- Keep it plain: short comments that explain *why* something is done, not *what*
  the next line does.
- Match the surrounding code; no new dependencies unless they are really needed
  (the app ships as a single exe on purpose).
- Commit messages in English, please.
