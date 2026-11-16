# SYNTHETIC — not game data

This folder is a made-up dataset in the same file layout the program reads from a real
extract. Every manufacturer, item, part, category id and serial in it is invented (the
serials were produced by this repo's own codec, so they decode, but they are not real
items). It exists so the tests and the demo work with nothing else installed.

Regenerate with `python scripts/make_synthetic.py` (deterministic). To use your own real
tables instead, build them with `python scripts/build_data.py` (see docs/runbooks/USER.md).
