# The Herdr plugin marketplace: what it reads and when

Facts checked against Herdr 0.9.4 (October 2026). Sources, pinned to that release:

- Marketplace: https://raw.githubusercontent.com/herdrdev/herdr/v0.9.4/docs/next/website/src/content/docs/marketplace.mdx
- Plugins (install, update, trust): https://raw.githubusercontent.com/herdrdev/herdr/v0.9.4/docs/next/website/src/content/docs/plugins.mdx
- CLI reference (`herdr plugin …`): https://raw.githubusercontent.com/herdrdev/herdr/v0.9.4/docs/next/website/src/content/docs/cli-reference.mdx
- Newer releases: start again from https://herdr.dev/llms.txt.

## Contents

- How a plugin gets listed
- The index file
- What users get when you push
- Not listed?
- Repository settings that show on the card

## How a plugin gets listed

There is no submission and no review. The marketplace at https://herdr.dev/plugins is an automatic
index of GitHub repositories that are:

- public, not a fork, not archived;
- tagged with the topic `herdr-plugin`;
- holding, on the **default branch**, at least one `herdr-plugin.toml` whose required metadata parses:
  `id`, `name`, `version`, `min_herdr_version`. The index also records `description` and `platforms`.

Manifests may sit at the root or in subfolders, at any depth. Each valid manifest becomes a separately
installable row on the repository's single card. The index refreshes about every 30 minutes and rescans a
repository when its default-branch head changes. A malformed manifest is dropped silently; the index counts
these (`invalidManifestCount`) and duplicated manifests (`duplicateManifestCount`) without naming them,
so keep every `id` unique and every manifest parseable.

So any `herdr-plugin.toml` committed to `main` gets listed, test fixtures included. Keep fixtures in temp
dirs or out of the repository.

## The index file

`https://assets.herdr.dev/plugins/index.json` (the page loads it; the CDN refuses requests without a
User-Agent). The shape, trimmed to what matters here:

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-10-14T13:30:19.180Z",
  "source": {"query": "topic:herdr-plugin is:public", "invalidManifestCount": 4, "duplicateManifestCount": 7},
  "plugins": [
    {
      "fullName": "MrBogomips/herdr-tools",
      "description": "<the GitHub repository description>",
      "topics": ["herdr", "herdr-plugin"],
      "pushedAt": "2026-10-14T13:25:43Z",
      "headCommit": "<default-branch commit the listing was read from>",
      "manifests": [
        {"path": "sort-spaces/herdr-plugin.toml", "id": "mrbogomips.sort-spaces", "name": "Sort Spaces",
         "version": "0.2.0", "minHerdrVersion": "0.9.3", "description": "…", "platforms": ["macos", "linux"]}
      ],
      "firstSeenAt": "2026-10-14T13:00:22.479Z"
    }
  ]
}
```

`herdr_release.py status` reads it, finds the repository's entry, and compares `headCommit` with
`origin/main`:

| State | Meaning | What to do |
| --- | --- | --- |
| current | the listing was read from origin/main | nothing |
| pending | origin/main is newer than the last refresh | wait for the next refresh (time shown) |
| lagging | a refresh after the push still lists the old head | re-check after one more refresh, then run preflight |
| diverged | the listed head is not in origin/main's history | `git fetch`; look for a force push |
| missing | the repository is not in the index | see "Not listed?" |

## What users get when you push

- `herdr plugin install Owner/repo/<plugin>` clones the default branch, unless the user passes
  `--ref <tag|branch|sha>` to pin a revision.
- `herdr plugin update` refetches the ref recorded at install time and skips unchanged commits. Users who
  installed without `--ref` get every push to `main`, whatever the manifest version says. A version
  bump changes nothing for them; tests and CI before `main` are the real gate.
- Users who pinned a tag stay on it until they reinstall with a newer `--ref`. That is why pushed tags
  never move.
- `herdr plugin list` shows each install as `[github:Owner/repo/<plugin>@<sha>]`, which is how you check
  that an update landed.
- An update takes effect for new invocations right away. Running processes keep the old files, and
  `[[startup]]` hooks run again only at the next server start.
- Install and update fail when `min_herdr_version` is newer than the user's Herdr. Raising it locks out
  users on older versions, so it counts as a breaking change.

## Not listed?

Check, in this order:

1. `gh repo view --json visibility,isFork,isArchived,repositoryTopics`: the repository must be public, not
   a fork, not archived, and have the topic `herdr-plugin` (`gh repo edit --add-topic herdr-plugin`,
   after the user says yes).
2. The manifest is on the **default branch** (`git ls-tree -r --name-only origin/main | grep herdr-plugin.toml`).
   A plugin that is only on a PR branch is not listed yet.
3. `herdr_release.py preflight`: the required keys parse, versions are X.Y.Z, and no id is duplicated.
4. Time: a new topic or push waits for the next refresh (up to ~30 minutes, `generatedAt` + 30 min).
5. Still missing after two refreshes: the index can blacklist repositories (`source.blacklistedCount`).
   That is the maintainers' call; report it upstream at https://github.com/herdrdev/herdr/issues.

## Repository settings that show on the card

The card shows the GitHub repository **description**, star count, primary language and last push time.
Each plugin row shows the manifest `name` and `version`. When a release adds a plugin, the repository
description should mention it: `gh repo edit --description "…"`, after the user agrees to the wording.
