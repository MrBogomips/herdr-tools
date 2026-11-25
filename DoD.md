# Definition of Done

## Requirements

- [ ] herdr-jump tests pass: `lua herdr-jump/tests/run.lua`
- [ ] herdr-jump picker tests pass: `sh herdr-jump/tests/test_picker_js.sh`
- [ ] Site tests pass: `cd site && /usr/bin/python3 -m unittest`
- [ ] When a Python plugin changed:
  - [ ] its tests pass from its folder with `/usr/bin/python3 -m unittest`
  - [ ] `herdr_api.py` and `test_herdr_api.py` are byte-identical in every plugin
- [ ] Features and multi-file work merged into `main` through a pull request
- [ ] CI on `main` passes
- [ ] When a change is visible to the user (keys, picker, menu, config, behaviour):
  - [ ] the plugin's or companion's `README.md` documents it (Use cases, Keys, Symbols, Configure, limits)
  - [ ] the screenshots in `<plugin>/docs/` show the current interface
  - [ ] the alt texts and captions describe the new screenshots
  - [ ] the site page `site/pages/<plugin>.html` matches the README
- [ ] No tool attribution in commits, tags or pull requests

## On Done

- Merge without asking a simple pull request, with `gh pr merge <n> --rebase --delete-branch`, once CI passes
  and nothing is requested or unresolved. Simple means all of these:
  - it touches one plugin or companion, or only documentation;
  - it changes no `herdr-plugin.toml`, `.github/`, `.claude/`, `install.sh` or vendored `herdr_api.py`;
  - it adds or changes no key binding, setting or stored data format;
  - it changes at most about 200 lines outside tests and screenshots.
- Any other pull request: the user merges.
- Never touch: tags `*-v*` (releases only with the herdr-publish skill)
