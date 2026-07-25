# Publishing to the HACS default store

Getting listed in the HACS default store is what removes the "add a custom
repository" step for users: the integration becomes searchable in HACS directly.

It takes two pull requests to repositories owned by other organisations, in a
strict order, plus a stable release in between. This document holds the exact
content of each step so none of it has to be re-derived.

Requirements below are taken from
[HACS: include your repository](https://hacs.xyz/docs/publish/include/).

## The blocking dependency

**`home-assistant/brands` has no entry for `migo_netatmo`.** A submission was
made and rejected on substance, see step 1. Everything else is ready, and this one
thing gates the rest, for a reason that is easy to miss:

HACS requires its own GitHub Action to pass *"without any errors or ignores"*.
Our workflow currently carries `ignore: brands` (`.github/workflows/validate.yaml`),
which exists precisely because the brands entry is missing. So the ignore cannot
be removed until the brands PR is merged, and the submission cannot be made while
the ignore is there.

This is also why the integration shows **"icon not available"** in HACS today.
Home Assistant and HACS resolve brand images from
`https://brands.home-assistant.io/_/<domain>/icon.png`, never from a file inside
the integration folder. A local `icon.png` cannot substitute, which is why the
one that used to sit in `custom_components/migo_netatmo/` was removed: it was
34 KB of every 94 KB downloaded, read by nothing.

## Step 1: submit to `home-assistant/brands`

### This was already attempted, and rejected on substance

[home-assistant/brands#8958](https://github.com/home-assistant/brands/pull/8958),
opened 2026-01-03, closed 2026-02-14 without merging. It added the two correct
file paths, so the structure was right. The assets were not. Review by @frenck:

> the provided brand assets are not correct; we collect manufacturer branding in
> this repository, in this case the branding of Saunier Duval seems to be
> different. Can you please make sure it matches?

The bot then converted the PR to a draft awaiting changes, no response was made,
and it was closed as stale six weeks later with an explicit invitation to reopen.

**The rejection has not been addressed.** `brands_assets/icon.png` is
byte-identical to the asset that was refused (both blob
`3a0c2f66eb75c1c5153ddf82d2756e70b3ca8503`). Resubmitting it as-is will be
refused again for the same reason.

### What brands actually wants

Manufacturer branding, not application branding. The submitted image is the MiGO
**app** icon; brands wants the **Saunier Duval** company logo. This is consistent
with the integration's own declaration, `const.py`:

```python
MANUFACTURER: Final = "Saunier Duval"
```

So the asset to supply is Saunier Duval's logo, sourced ideally from their own
brand or press resources. This is the established convention in that repository,
which is built almost entirely from manufacturer logos, so it is expected rather
than exceptional. It is still a trademark asset, and choosing which mark to use
is the maintainer's call, not something to settle from a search result.

There is no precedent to copy: brands has no entry for `vaillant`,
`myvaillant`, `saunier_duval` or `sdbg`. Only `netatmo` exists, as a core
integration. This submission would be the first for the Vaillant Group family.

### Requirements for the replacement assets

```
custom_integrations/migo_netatmo/icon.png      256x256, PNG
custom_integrations/migo_netatmo/icon@2x.png   512x512, PNG
```

Only `icon.png` is strictly required by the HACS check; `icon@2x.png` is worth
including for high-DPI displays. Per the
[brands requirements](https://github.com/home-assistant/brands#requirements):

- Trimmed, so there is minimal empty space or transparent padding at the edges.
- Interlaced (progressive) PNG is **preferred**, not required. Run through
  `optipng -i1` or `zopflipng` to match it.
- Must not use Home Assistant branding. Not a concern here.

### Reopening rather than starting over

The fork branch is intact: `tomahoax/brands`, branch `add-migo-netatmo`. Pushing
corrected assets to that branch and reopening #8958 keeps the review thread and
honours frenck's invitation, which is better than opening a fresh PR with no
context. Reply to the review, then use the **Ready for review** button, since the
bot drafted it and a draft is not reviewed.

The lesson from the first attempt is the cheap one: the PR did not fail because
of the assets alone, it died because nobody answered for six weeks.

## Step 2: remove the ignore, and confirm CI is green

Once the brands PR is **merged**, delete the `ignore: brands` input from the HACS
validation step in `.github/workflows/validate.yaml`, along with the comment
above it that explains why it was there. Push, and confirm the
`Validate HACS` job passes with no ignores.

Do not skip the confirmation. This is the check the default-store submission
runs, and a failure discovered in the submission PR is a failure discovered in
public.

## Step 3: cut a stable release

HACS requires *"a new GitHub release (not just a tag, a full release) after the
actions run successfully"*.

A pre-release does not satisfy this in spirit: HACS explicitly excludes
repositories that exist for alpha or beta testing, and a repository whose newest
release is a beta invites that reading. Cut a **stable** release, from `main`:

```bash
gh release create v1.0.0 --target main --title v1.0.0 --notes-from-tag
```

Two preconditions, both easy to get wrong:

- **`main` must be current.** HACS validation and human reviewers look at the
  default branch, which is `main`. Merge `dev` into `main` first. Historically
  `main` has lagged well behind, at one point carrying a `hacs.json` with no
  `zip_release` or `filename` at all, which would have been the configuration
  actually judged.
- **The release workflow validates the tag.** `.github/workflows/release.yaml`
  rejects anything that is not `vMAJOR.MINOR.PATCH[-prerelease]` before stamping,
  so a malformed tag fails the release rather than publishing a corrupt
  `manifest.json`.

## Step 4: submit to `hacs/default`

Fork [hacs/default](https://github.com/hacs/default), branch from `master`, and
add one line to the `integration` file. It is a JSON array of `owner/repo`
strings, sorted case-insensitively, so the entry goes here:

```json
  "tomaae/homeassistant-truenas",
  "tomahoax/ha-migo-netatmo",
  "tomasbedrich/home-assistant-hikconnect",
```

Position verified against the live file, which currently holds 2698 entries. The
`lint sorted` check will reject an entry appended at the end.

Requirements on the PR itself:

- Open it from a **personal** account, not an organisation, so it stays editable.
- Only the owner or a major contributor may submit.
- Branch from `master` in your fork, do not commit to `master` directly.

## Automated checks, and where this repository stands

| Check | Status |
| --- | --- |
| Repository is public, not archived, not a fork | ready |
| Description set | ready |
| Issues enabled | ready |
| Topics defined | ready (7) |
| Recognised licence | ready (MIT) |
| `hacs.json` contains at least a `name` | ready |
| Valid integration `manifest.json` | ready |
| Exactly one directory under `custom_components/` | ready |
| At least one release exists | ready |
| Submitter is owner or major contributor | ready |
| Valid JSON, correct alphabetical sorting | see step 4 |
| Hassfest passes | ready |
| **HACS Action passes with no ignores** | **blocked on step 1** |
| **Brands entry exists** | **blocked: PR #8958 rejected, wrong assets** |
| **A full release created after the actions pass** | see step 3 |

Also confirmed absent from `hacs/default`'s `removed`, `blacklist` and `critical`
lists, so there is no prior exclusion to clear.

## Step 5: after acceptance

These become wrong the moment the repository is accepted, and are easy to forget:

- **`README.md` badge** reads `HACS-Custom`. It should become
  `HACS-Default`, or the badge should be dropped.
- **`README.md` installation section** is written entirely around adding a custom
  repository, including a My Home Assistant `hacs_repository` redirect button and
  a step-by-step "Add the custom repository" flow. Users will no longer need any
  of it: they will search for the integration in HACS directly. Keep a short note
  for anyone still on a manually-added copy.
- **`docs/installation.md`** needs the same treatment.

## What this does not change

Being in the default store does not alter how the integration is installed
mechanically. `hacs.json` keeps `zip_release: true`, so HACS still downloads
`migo_netatmo.zip` from the release assets and extracts it into
`config/custom_components/migo_netatmo/`. The archive layout requirement, files
at the archive root rather than nested, is unchanged and is enforced by the
comment on the zip step in `release.yaml`.

Nor does it give you installation statistics. The download count HACS displays is
the GitHub asset download count for the currently selected release, which resets
every release. Real install counts come from Home Assistant's own analytics at
`https://analytics.home-assistant.io/custom_integrations.json`, which depends on
users opting into analytics, not on default-store membership. Being listed
matters because it drives discovery, and discovery is what moves both numbers.
