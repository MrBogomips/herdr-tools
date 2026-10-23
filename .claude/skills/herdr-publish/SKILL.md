---
name: herdr-publish
description: Publish and release the Herdr plugins of the herdr-tools repo on the Herdr plugin marketplace (herdr.dev/plugins). Decides each plugin's semver bump, syncs manifest metadata, runs the marketplace preflight, tags it (e.g. `space-herder-v0.1.1`) with release notes, pushes, then checks that the marketplace index and `herdr plugin update` show the new version. Use whenever the user wants to ship, release, publish, list or bump a plugin of this repo, add a new plugin to the marketplace, cut or push a plugin release tag, check whether herdr.dev/plugins shows the latest version, or ask why a plugin is missing from the marketplace. Also covers terse asks after changing a plugin ("ship it", "rilascia space-herder", "pubblica il plugin"). Not for driving Herdr panes or workspaces, and not for tagging other projects.
---

# Publishing herdr-tools plugins

## How the marketplace works, and what that leaves to you

The marketplace has no submission step. It indexes public GitHub repos with the topic `herdr-plugin`,
reads every `herdr-plugin.toml` on the default branch, and refreshes about every 30 minutes. This repo is
already listed.

Users who run `herdr plugin update` get **every commit pushed to `main`**, whatever the manifest says. So
publishing a change means getting it onto `main`, and what reaches `main` must already be tested.

The manifest `version` is the label on the card. A tag `<plugin>-vX.Y.Z` is a point users can pin with
`herdr plugin install … --ref`. Your job around each push is:

- pick an honest version;
- keep the indexed metadata true;
- pass the preflight;
- leave an annotated tag with notes;
- confirm the marketplace and the local install picked the push up.

`references/marketplace.md` covers the index format, the index states, what users experience, and what
to do when the repo is not listed. Read it when a listing looks wrong or a user asks how pinning works.

## The helper script

`scripts/herdr_release.py` sits next to this file. It is read-only: it never commits, tags, fetches or
pushes, so every change stays a visible command the user can approve. Run it from the repository, or pass
`-C <repo>`:

```bash
python3 <skill-dir>/scripts/herdr_release.py status [plugin…]      # where each plugin stands
python3 <skill-dir>/scripts/herdr_release.py preflight [plugin…]   # fit to publish? runs the tests too
python3 <skill-dir>/scripts/herdr_release.py notes <plugin>        # release notes for the tag message
```

Other flags:

- `--json` prints machine-readable output.
- `--index <file>` replaces the live index; `--no-index` skips it.
- `preflight --no-tests` skips the tests.

It reads the index from `$HERDR_PLUGIN_INDEX` when that variable is set.

## Workflow

### 1. Orient

Run `git fetch origin --tags`, then `status`. It reports:

- **Git gate**: clean tree, and `main` equal to `origin/main`. Fix anything flagged before releasing:
  unpushed commits on `main` would ship unreviewed along with the release.
- **Index state**: current, pending, lagging, diverged or missing.
- **Each plugin**: last tag, commits since it (with the kinds of files they touch), suggested bump with
  reasons, manifest description next to its README row.

Tell the user in a few lines what is live, what is unreleased, and what you propose.

Plugin states:

| State | Meaning |
| --- | --- |
| `untagged` | No release tag yet. `status` names the commit for the first tag (see "First tag"). |
| `released` | Nothing shipped since the tag; docs and tests don't count. Say so and stop: users already get docs changes via `plugin update`. |
| `unreleased` | Shipped files changed since the tag; `next` is the suggested version. |
| `tag-pending` | The bump is committed on `main`; tag the commit shown. The release covers the commits listed under "in this release, since". Commits listed under "after the bump" wait for the next release. |
| `awaiting-merge` | The bump, or a whole new plugin, is on a branch that is not merged yet. Merge it, then tag the commit that lands on `main`. |
| `error` | Fix the listed problem first, e.g. a bump that is not committed yet, or a manifest behind the latest tag. |

`status` also warns when it could not reach origin to check a tag, and when a tag is lightweight or
missing from origin.

### 2. Decide the version

Treat the suggestion as a starting point. Read the diff since the tag
(`git diff <plugin>-vX.Y.Z..HEAD -- <plugin>/`) and decide. The heuristic sees files and manifest
contracts, but not behaviour.

Semver from the user's side:

- **Breaking**: something users set up stops working.
  - Examples: a removed or renamed action id (their key bindings name `<plugin id>.<action>`), a removed
    or renamed `config.json` key, a key whose meaning changed, a raised `min_herdr_version`, a dropped
    platform.
  - While the version is 0.x, breaking bumps the minor (0.2.3 → 0.3.0); from 1.0 on, the major.
- **Minor**: new capability.
  - Examples: a new action, hook, config key or platform, or a `feat` commit.
- **Patch**: fixes and internal changes that ship.
- **No release**: only docs, tests or comments changed.

Explain your choice in one line per plugin. If a commit's type contradicts its files, say so: a `docs`
commit that changes code still ships.

### 3. Sync the metadata

- The index records the manifest `description`, and the README table row says the same thing to people.
  When a release adds or changes behaviour, update both so they tell the same story (they need not be
  word-for-word). `status` prints them side by side.
- `min_herdr_version` is the oldest Herdr actually verified with the plugin, not the newest one installed
  (`herdr status server` shows the running server, which can lag behind `herdr --version`).
- New plugin:
  - id `<owner lowercase>.<folder>` and a `platforms` list;
  - `config.example.json`, a README with install, key binding, config and limits;
  - `test_manifest.py`, and the vendored `herdr_api.py` / `test_herdr_api.py` copied byte-for-byte
    from an existing plugin;
  - a row in the root README table with its `herdr plugin install` command.

### 4. Preflight

Run `preflight <plugin…>`. It checks:

- the marketplace metadata, and that ids are unique in the repo and across the index;
- that no stray `herdr-plugin.toml` would be indexed;
- the README rows, and that the vendored copies are identical;
- `[[events]]` names against `herdr api schema --json`;
- each plugin's tests, run on `/usr/bin/python3` (Python 3.9, the oldest supported).

Errors block the release. Weigh each warning and mention it to the user.

On a pull request, it's the merge that publishes, so an error may sit on the branch for a while. Either fix
it on the branch, or put it at the top of the PR description so it's fixed before anyone merges. Never open
a PR that hides a known error.

### Bugs you find on the way

A release is a bad moment to change plugin code: the change would ship to every `plugin update` user
without its own review. When you spot a bug while publishing:

- say what it is and propose the fix;
- leave the fix as its own change, which the user decides on.

The release itself owns only its metadata: version, description, platforms and README rows.

### 5. Show the plan and get a yes

Pushing to a public repository is visible to everyone, and a pushed tag is permanent: users may pin it.
Show the user:

- each plugin with old → new version;
- the notes from `notes <plugin> --version X.Y.Z`;
- the exact commands from step 6.

Then wait for an explicit yes. A yes covers this plan only. Ask again if the plan changes.

### 6. Land it

**A. Releasing work that is already on `main`** (the usual case after a PR merge). Run this in the main
checkout; a linked worktree cannot switch to `main`.

```bash
git switch main && git pull --ff-only
# edit <plugin>/herdr-plugin.toml: version = "X.Y.Z" (plus any description or README row sync)
git commit -m "chore(<plugin>): release vX.Y.Z" -- <plugin>/herdr-plugin.toml README.md
python3 <skill-dir>/scripts/herdr_release.py notes <plugin> --version X.Y.Z > <scratch>/notes.txt
git tag -a <plugin>-vX.Y.Z -F <scratch>/notes.txt
git push --atomic origin main <plugin>-vX.Y.Z
```

- Several plugins can share one commit, `chore(release): space-herder v0.1.1, auto-tab-name v0.2.1`, with
  one tag each, all in the same atomic push.
- A commit that touches only version lines, descriptions and README rows goes straight to `main`, as the
  project policy allows for trivial changes.
- Write the notes file outside the repository (a scratch or temp dir), so it doesn't dirty the tree.

**B. A new plugin, or code that is not on `main` yet**, goes through a pull request (project policy).

- You may bump the version inside the PR.
- Tag only after the merge, on the commit that landed in `main`. A squash merge creates a new commit, so a
  tag made on the branch would point outside `main`.
- Before the merge, `status` shows the plugin as `awaiting-merge`.
- After the merge, run `git pull --ff-only` on `main`. `status` then names the commit to tag: as
  `tag-pending` for a bumped plugin, or as `untagged` for a new one. Tag exactly that commit, not HEAD,
  since later commits may have landed on `main`. Then push the tag alone:

  ```bash
  git tag -a <plugin>-vX.Y.Z <commit> -F <scratch>/notes.txt
  git push origin <plugin>-vX.Y.Z
  ```
- For a new plugin, after the merge also update the GitHub repository description so the card mentions
  it, and check the topic is still there (`references/marketplace.md`, last section). Confirm the wording
  of each `gh` write with the user.

**Rules for every push:**

- Never use `git push --tags`: it also pushes stray local tags.
- Never use `--force`.
- Never move or delete a pushed tag. If a release is broken, fix forward with a new patch release.
- Commit messages follow the conventional format used here, `<type>(<scope>): <description>`.
- Commits, tags and PR bodies carry no tool attribution: no `Co-Authored-By` or session trailers, and no
  links to AI services.

### 7. Verify

- Run `status` right after the push. Expect `pending` with the time of the next refresh. Don't sit
  waiting for up to 30 minutes: offer to check again after that time. If you can schedule a follow-up,
  offer that.
- Once the index is `current`, check that the listed version matches the manifest. A plugin `not listed`
  after a refresh points to a manifest problem (`preflight`) or the checklist in
  `references/marketplace.md`.
- Offer to update the user's own install with `herdr plugin update <plugin id> --yes`, then check
  `herdr plugin list` for `@<new sha>`. `[[startup]]` hooks run again only at the next server start.

### First tag (plugins without one)

When `status` says `untagged`, it names the commit for `<plugin>-v<version>`:

- **A plugin the index already lists:** the commit the index read, if the plugin folder has not changed
  since. That is what users were offered.
- **Otherwise:** the commit on `origin/main` that set the version. For a new plugin, that is the commit
  its merge landed as.

Tag that commit with the manifest's version (step 6B shows how). Any changes after it then show up as
`unreleased`; release them with steps 2–6. If `status` names no commit, the plugin is not on `origin/main`
yet: merge it first.

## Finish with a short report

Keep it short:

- What shipped: plugin, version, tag, commit.
- What the index shows and when to expect the refresh.
- The command users run to get it: `herdr plugin update`, or `herdr plugin install Owner/repo/<plugin>`
  for newcomers.
- Anything left for the user, such as merging a PR, an unverified warning, or a later re-check.
