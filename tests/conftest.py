import logging
import os
import sys

import pytest

from psd2svg.core.font_utils import FontInfo

logger = logging.getLogger(__name__)


def get_fixture(name: str) -> str:
    """Get a fixture by name."""
    return os.path.join(os.path.dirname(__file__), "fixtures", name)


def has_font(family: str) -> bool:
    """Check if a font family is available on the system.

    This function is intended for future rendering tests where the exact font
    matters (e.g., comparing rendered output against reference images). For
    tests that validate SVG attribute generation, font checks are typically
    unnecessary as font substitution happens automatically via fontconfig.

    Args:
        family: Font family name to check.

    Returns:
        True if the font is available, False otherwise.
    """
    try:
        # Try platform font resolution (works on all platforms)
        font_info = FontInfo.resolve(family)
        if font_info is None:
            return False
        # Check if the resolved font family matches what we requested
        # (case-insensitive comparison to handle different naming conventions)
        return font_info.family.lower() == family.lower()
    except Exception as e:
        logger.debug(f"Error checking font availability: {e}")
        return False


# Pytest markers for font-dependent tests
requires_noto_sans = pytest.mark.skipif(
    not has_font("Noto Sans"),
    reason="Noto Sans font not installed",
)

requires_noto_sans_jp = pytest.mark.skipif(
    not has_font("Noto Sans JP"),
    reason="Noto Sans JP font not installed",
)

requires_noto_sans_cjk = pytest.mark.skipif(
    not has_font("Noto Sans CJK JP"),
    reason="Noto Sans CJK JP font not installed",
)

requires_noto_sans_arabic = pytest.mark.skipif(
    not has_font("Noto Sans Arabic"),
    reason="Noto Sans Arabic font not installed",
)

requires_noto_sans_devanagari = pytest.mark.skipif(
    not has_font("Noto Sans Devanagari"),
    reason="Noto Sans Devanagari font not installed",
)

requires_noto_sans_thai = pytest.mark.skipif(
    not has_font("Noto Sans Thai"),
    reason="Noto Sans Thai font not installed",
)

requires_noto_sans_hebrew = pytest.mark.skipif(
    not has_font("Noto Sans Hebrew"),
    reason="Noto Sans Hebrew font not installed",
)

requires_arial = pytest.mark.skipif(
    not has_font("Arial"),
    reason="Arial font not installed",
)


# Fonts the Linux workflow installs explicitly, from ttf-mscorefonts-installer.
# That package downloads and extracts through an update-notifier hook that can
# fail while apt still exits 0, so a missing font there means a broken runner,
# not an inapplicable test.
_CI_REQUIRED_FONTS = ("Arial", "Times New Roman")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Fail the run when CI is missing a font it is supposed to provide."""
    if os.environ.get("CI") != "true" or sys.platform != "linux":
        return
    missing = [family for family in _CI_REQUIRED_FONTS if not has_font(family)]
    if missing:
        raise pytest.UsageError(
            "the font install step failed silently; fontconfig cannot resolve: "
            + ", ".join(missing)
        )


# Check if playwright is available
def has_playwright() -> bool:
    """Check if playwright is installed."""
    try:
        import playwright  # noqa: F401, PLC0415

        return True
    except ImportError:
        return False


requires_playwright = pytest.mark.skipif(
    not has_playwright(),
    reason="Playwright not installed",
)


# Check if scikit-image is available
def has_skimage() -> bool:
    """Check if scikit-image is installed."""
    try:
        import skimage  # noqa: F401, PLC0415

        return True
    except ImportError:
        return False


requires_skimage = pytest.mark.skipif(
    not has_skimage(),
    reason="scikit-image not installed",
)
