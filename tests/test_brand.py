"""Brand assets served to HACS and to the Home Assistant frontend.

Since Home Assistant 2026.3, `brand/` inside the integration overrides the CDN with no
manifest change (`Integration.has_branding` is just `"brand" in self._top_level_files`),
and HACS refuses to list an integration whose `brand/icon.png` is missing. So a renamed or
resized file here breaks the listing rather than just looking wrong, which is worth
catching before a release rather than in the HACS job.

Unlike ha-daitem's ink-on-transparency logo, the MiGo app icon is a filled, opaque square -
there is nothing under it a dark theme would need to show through, so no `dark_icon*.png`
pair is provided. Home Assistant's own fallback chain (`IMAGE_FALLBACKS` in
`homeassistant.components.brands.const`) serves `icon.png`/`icon@2x.png` for the dark-theme
slots whenever the dark variant is absent, which is exactly the desired behavior here.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

BRAND = Path(__file__).parent.parent / "custom_components" / "migo_netatmo" / "brand"

EXPECTED_SIZES = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
}


def _png_header(path: Path) -> tuple[int, int, int]:
    """Return width, height and PNG colour type, straight from the IHDR chunk."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height, data[25]


@pytest.mark.parametrize(("filename", "size"), EXPECTED_SIZES.items())
def test_brand_asset_is_a_png_of_the_expected_size(filename: str, size: tuple[int, int]) -> None:
    path = BRAND / filename
    assert path.is_file(), f"{filename} is missing; HACS and the frontend both read this directory"

    width, height, colour_type = _png_header(path)
    assert (width, height) == size
    # Colour type 6 is RGBA. The icon itself is opaque, but the brand image format still
    # has to carry an alpha channel for Home Assistant to accept it.
    assert colour_type == 6, f"{filename} has no alpha channel"


def test_no_stray_dark_variant_without_its_pair() -> None:
    """A half-added dark variant would be worse than none: mismatched light/dark icons.

    Guards against someone dropping in a dark_icon.png later without also adding
    dark_icon@2x.png (or vice versa) and not noticing, since the fallback chain would
    silently paper over the gap in the running app.
    """
    dark_files = {"dark_icon.png", "dark_icon@2x.png"}
    present = {f.name for f in BRAND.glob("dark_icon*.png")}
    assert present in (set(), dark_files), f"Partial dark variant set: {present}. Add both files or neither."
