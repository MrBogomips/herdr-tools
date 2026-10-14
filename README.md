# herdr-tools

[![tests](https://github.com/MrBogomips/herdr-tools/actions/workflows/test.yml/badge.svg)](https://github.com/MrBogomips/herdr-tools/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Herdr](https://img.shields.io/badge/herdr-%E2%89%A5%200.9.3-6c71c4.svg)](https://herdr.dev)

Plugins for the [Herdr](https://herdr.dev) terminal multiplexer, for people who keep a lot of
spaces open: one per customer, project and side quest. Each plugin installs on its own, so take
only the ones you want.

| Plugin | What it does | Install |
| --- | --- | --- |
| [sort-spaces](sort-spaces/) | Sorts the spaces sidebar into `~`, head (`+`), default and bottom (`-`) groups, then by name; on a key, or by itself when a space is created or renamed | `herdr plugin install MrBogomips/herdr-tools/sort-spaces` |
| [space-colors](space-colors/) | Colours each space name by its customer prefix (stable hash or sticky least-used colour, or regex rules), from a preset palette such as Catppuccin or Dracula (up to 15 colours), so every space of one customer shares a colour | `herdr plugin install MrBogomips/herdr-tools/space-colors` |

## Better together: a naming scheme

Name spaces `CUSTOMER - project`, mark the ones you always want on top with ` +` and the parking
lot with ` -`:

```
● ▌~                   home
● ▌LUMON +             head group, always on top
○ ▌ACME - api          ┐ one colour per customer (space-colors hashes "ACME"),
○ ▌ACME - web          ┘ side by side (sort-spaces sorts by name)
● ▌Globex - etl
○ ▌Initech - crm
○ ▌SYS -               bottom group
```

With sort-spaces' `"auto_sort": "both"` and space-colors' `"assign": "sticky"`, a new or renamed
space lands in its place with its customer's colour, with no key to press; customers keep apart
colours as long as there are fewer of them than colours (15 at most).

## Install

Every plugin lives in its own folder with its manifest (`herdr-plugin.toml`), code, tests and
README. Herdr installs a single folder of a GitHub repository:

```bash
herdr plugin install MrBogomips/herdr-tools/<plugin>   # one plugin
herdr plugin update                                    # update installed plugins
herdr plugin uninstall mrbogomips.<plugin>             # remove one
```

Herdr shows the manifest and the commands it will run before installing. Plugins are ordinary
code running as your user, so read them first; these are short Python scripts.

Requirements:

- Herdr 0.9.3 or newer, on macOS or Linux.
- `python3` 3.9 or newer on the `PATH`. The system Python of macOS is enough; the plugins use the
  standard library only, so there is nothing else to install.

Each plugin's README explains its key bindings and its `config.json`, which lives in
`herdr plugin config-dir <plugin id>`.

## Develop

```bash
git clone https://github.com/MrBogomips/herdr-tools
herdr plugin link "$PWD/herdr-tools/space-colors"   # run your working copy
cd herdr-tools/space-colors && python3 -m unittest -v
```

- One folder per plugin: `herdr-plugin.toml`, `README.md`, `config.example.json`, the code and
  its `test_*.py` next to it. Plugin ids are `mrbogomips.<folder>`.
- `herdr_api.py` (socket client, config loading, locking, toasts) is copied into every plugin so
  each one installs alone. Edit it in one plugin and copy it to the others; CI fails while the
  copies differ.
- Code stays compatible with Python 3.9 (`/usr/bin/python3` on macOS) and uses the standard
  library only. CI runs every plugin's tests on macOS with the system Python and on Ubuntu.
- `herdr api schema --json` prints the socket API of your Herdr build; the
  [plugin docs](https://herdr.dev/docs/plugins/) describe manifests, hooks and actions.

## License

[MIT](LICENSE)
