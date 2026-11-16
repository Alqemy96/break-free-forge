# Security

## Reporting a problem

Open an issue on the project's hosting page describing the problem. For something sensitive (a way to make the
program write somewhere it should not, run something it should not, or listen where it should not), say only
that you have a security report and ask the maintainer for a private channel; do not post details publicly first.
Never include a save file, a key, an account id, or a console address in a report.

## What the design promises

- A save is only ever written as a COPY, with the original's sha256 recorded beside it. The original is never
  opened for writing, and the copy is re-read to prove it decrypts to the edited text.
- The web UI binds `127.0.0.1` by default and checks the `Host` and `Origin` headers (DNS-rebinding guard). Any
  other `--host` is refused unless `--allow-remote` is passed, and that flag is documented as risky.
- No outbound network connection exists anywhere in the code.
- No `eval`, `exec`, `pickle`, `marshal`, dynamic import of user-supplied names, or shell invocation is used.
  Only `lootpak-*` starts another program, from an argument list and a path you configured.
- Static file serving rejects `..`, backslashes, drive letters, dot-files and symlinks leaving its folder.
- Generated HTML code sheets contain no scripts and no external references; all text is escaped.
- The save key is read only from your `config.toml`, kept out of `repr()` and logs, and never printed.

## Intentionally NOT included, and why

| Not included | Why |
|---|---|
| Console save-transfer tools (mounting, exporting, resealing console saves) | They act on a console and its account. This project is offline file tooling; bring your own transfer method. |
| Cheat and code-patch tooling (memory patching, hooks, trainers) | Not part of this project; it risks online bans and gives a way to run code in someone's game. |
| The PS5 save key, and any hint of where or how to find it | A fixed key compiled into a game is something the publisher can rotate; publishing it invites that and shares a secret that is not ours. `config.example.toml` leaves it empty. |
| Game data (manifests, tables, paks, decoded files) | Gearbox / 2K material. Supply your own for private use. |
| The scraped community serial database | Authorship and terms unknown. |
| Any save file, account id, address, or user path | Private data. |
| Built web bundle (`web/static/`) | Minified output cannot be reviewed; build it from `ui/` yourself. |

## Network check (how to re-verify)

    grep -rnE "socket|http|urllib|requests|ftplib|smtplib|subprocess|webbrowser" src --include=*.py

Expected: `web/_server.py` (local listener, `webbrowser.open` of the local URL when `--open` is given) and
`modules/lootpak/_tools.py` (subprocess, no shell). Other hits are only the words "http" or "requests" in
comments, docstrings and variable names. Anything else is a bug.

## Your side

- Keep `config.toml` out of version control (it is git-ignored here).
- Do not run a `config.toml` or a loot-pak TOML written by someone else without reading it.
- Do not expose `serve` to a network.
- Edited saves can break a character; online play with edited saves can have consequences set by the game's
  publisher. You accept that risk.
