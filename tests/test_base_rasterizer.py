"""Tests for the dimension and DPI helpers shared by all rasterizers."""

from pathlib import Path

import pytest

from psd2svg.rasterizer.base_rasterizer import BaseRasterizer


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("100", 100.0),
        ("100px", 100.0),
        ("  100px  ", 100.0),
        ("100 px", None),
        ("100PX", 100.0),
        ("100.5", 100.5),
        ("-1e2", -100.0),
        ("72pt", 96.0),
        ("1pc", 16.0),
        ("1in", 96.0),
        ("25.4mm", 96.0),
        ("2.54cm", 96.0),
        ("50%", None),
        ("1e400", None),
        ("2em", None),
        ("", None),
        ("auto", None),
    ],
)
def test_parse_length(value: str, expected: float | None) -> None:
    """Test that absolute CSS lengths resolve to pixels and others to None."""
    result = BaseRasterizer._parse_length(value)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    ("root_attrs", "expected"),
    [
        ('width="100" height="50" viewBox="0 0 100 50"', (100.0, 50.0)),
        ('width="100px" height="50px"', (100.0, 50.0)),
        ('width="1in" height="0.5in"', (96.0, 48.0)),
        ('viewBox="0 0 200 150"', (200.0, 150.0)),
        ('viewBox="0, 0, 200, 150"', (200.0, 150.0)),
        # Percentages resolve against the viewBox, as resvg does.
        ('width="100%" height="100%" viewBox="0 0 200 150"', (200.0, 150.0)),
        ('width="50%" height="50%" viewBox="0 0 100 100"', (50.0, 50.0)),
        ('width="200%" height="200%" viewBox="0 0 100 100"', (200.0, 200.0)),
        # Each axis is resolved on its own, so sizing one keeps the other.
        ('width="200" viewBox="0 0 100 100"', (200.0, 100.0)),
        ('height="200" viewBox="0 0 100 100"', (100.0, 200.0)),
        ('width="200" height="50%" viewBox="0 0 100 100"', (200.0, 50.0)),
        ('width="100%" height="100%"', None),
        ('width="200"', None),
        ('width="0" height="0"', None),
        ('width="1e400" height="1e400"', None),
        ('viewBox="0 0 1e400 1e400"', None),
        ("", None),
    ],
)
def test_svg_dimensions(root_attrs: str, expected: tuple[float, float] | None) -> None:
    """Test the CSS pixel size read from a root <svg> element."""
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" {root_attrs}><rect/></svg>'
    assert BaseRasterizer._svg_dimensions(svg) == expected


@pytest.mark.parametrize(
    "body",
    [
        "<rect>",  # unclosed
        "<rect></bad>",  # mismatched end tag
        "<rect a=b/>",  # unquoted attribute
        "</svg>&&&<<<",  # junk after the root
    ],
)
def test_svg_dimensions_ignores_malformed_body(body: str) -> None:
    """Test that only the root start tag has to parse.

    The parser queues a later error behind the root start event, so the root
    is still reported.
    """
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">{body}'
    assert BaseRasterizer._svg_dimensions(svg) == (100.0, 50.0)


def test_svg_dimensions_malformed_before_root() -> None:
    """Test that an error ahead of the root leaves nothing to report."""
    assert (
        BaseRasterizer._svg_dimensions('<!bad><svg width="100" height="50"/>') is None
    )


def test_svg_dimensions_root_after_long_preamble() -> None:
    """Test a root start tag that ends past the first read chunk."""
    svg = (
        "<!--" + "x" * 20000 + "-->"
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"></svg>'
    )
    assert BaseRasterizer._svg_dimensions(svg) == (100.0, 50.0)


def test_svg_dimensions_malformed_root() -> None:
    """Test that a document with no parsable root element yields None."""
    assert BaseRasterizer._svg_dimensions("<svg width=") is None
    assert BaseRasterizer._svg_dimensions("") is None


def test_svg_dimensions_large_document() -> None:
    """Test that the root is read without parsing the rest of the document."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
        + "<rect/>" * 50000
        + "</svg"  # truncated on purpose
    )
    assert BaseRasterizer._svg_dimensions(svg) == (100.0, 50.0)


def test_svg_dimensions_root_across_chunk_boundary() -> None:
    """Test a root start tag split across reads with nothing following it."""
    # The attribute list straddles the read boundary, so the parser only
    # reports the root once the feed is closed.
    padding = " " * (8192 - len('<svg width="100" '))
    svg = f'<svg{padding} width="100" height="50"/>'
    assert BaseRasterizer._svg_dimensions(svg) == (100.0, 50.0)


def test_svg_file_dimensions(tmp_path: Path) -> None:
    """Test reading dimensions from a file."""
    path = tmp_path / "input.svg"
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="72pt" height="36pt">'
        "<rect/></svg>",
        encoding="utf-8",
    )
    assert BaseRasterizer._svg_file_dimensions(str(path)) == (96.0, 48.0)


def test_svg_file_dimensions_missing_file(tmp_path: Path) -> None:
    """Test that an unreadable file yields None rather than raising."""
    assert BaseRasterizer._svg_file_dimensions(str(tmp_path / "absent.svg")) is None


@pytest.mark.parametrize(
    ("dpi", "expected"),
    [(0, 1.0), (96, 1.0), (192, 2.0), (300, 3.125), (48, 0.5), (-1, 1.0)],
)
def test_dpi_scale(dpi: int, expected: float) -> None:
    """Test that 0 and 96 DPI both render 1:1."""
    assert BaseRasterizer._dpi_scale(dpi) == pytest.approx(expected)
