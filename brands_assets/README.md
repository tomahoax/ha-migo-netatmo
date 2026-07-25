# Brand assets

Staging area for a submission to
[home-assistant/brands](https://github.com/home-assistant/brands), which is what
makes an icon appear for this integration in Home Assistant and HACS. Nothing
here is read at runtime: Home Assistant resolves brand images from
`https://brands.home-assistant.io/_/<domain>/icon.png`, never from this
repository.

## Status: the current assets were rejected

> [!WARNING]
> `icon.png` and `icon@2x.png` in this directory are the **MiGO app icon**, and
> they were **refused** by
> [home-assistant/brands#8958](https://github.com/home-assistant/brands/pull/8958).
> Do not resubmit them unchanged.

The reason, from the review:

> we collect manufacturer branding in this repository, in this case the branding
> of Saunier Duval seems to be different. Can you please make sure it matches?

brands collects **manufacturer** branding, not application branding. The asset
needs to be the **Saunier Duval** logo, which is also what this integration
declares as its manufacturer in `const.py`.

The dimensions and format were never the problem, and are worth preserving in the
replacement:

| File | Required | Current |
| --- | --- | --- |
| `icon.png` | 256x256 PNG | 256x256 PNG RGBA, non-interlaced |
| `icon@2x.png` | 512x512 PNG | 512x512 PNG RGBA, non-interlaced |

Interlaced PNG is preferred by brands but not required.

See [docs/development/publishing.md](../docs/development/publishing.md) for the
full submission sequence, including why this blocks the HACS default store listing.
