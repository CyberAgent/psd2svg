"""Tests for including hidden PSD layers in SVG output."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from psd_tools import PSDImage
from psd_tools.api import layers

import psd2svg.__main__ as cli
from psd2svg import SVGDocument, convert
from psd2svg.core.converter import Converter
from tests.conftest import get_fixture

TEST_PSD = "clipping/shape-with-invisible-clip.psd"


def test_hidden_layers_are_omitted_by_default() -> None:
    """Keep the existing behavior when the option is not supplied."""
    psdimage = PSDImage.open(get_fixture(TEST_PSD))

    document = SVGDocument.from_psd(psdimage, enable_title=True)

    assert [title.text for title in document.svg.findall(".//title")] == ["Background"]
    assert document.svg.findall(".//text") == []


def test_include_hidden_layers_converts_hidden_clipping_stack() -> None:
    """Include a hidden clipping base and both its visible and hidden clips."""
    psdimage = PSDImage.open(get_fixture(TEST_PSD))

    document = SVGDocument.from_psd(
        psdimage,
        enable_title=True,
        include_hidden_layers=True,
    )

    titles = [title.text for title in document.svg.findall(".//title")]
    assert "Star 1" in titles
    assert [node.text for node in document.svg.findall(".//text")] == ["B", "B"]


def test_include_hidden_layers_expands_inverted_group_mask() -> None:
    """Cover hidden children with an inverted group mask's white rectangle."""
    converter = Converter(PSDImage.new("RGB", (100, 100)), include_hidden_layers=True)
    group = Mock(spec=layers.Group)
    group.name = "Masked group"
    group.kind = "group"
    group.bbox = (10, 10, 40, 40)
    group.has_mask.return_value = True
    group.mask.disabled = False
    group.mask.width = 20
    group.mask.height = 20
    group.mask.left = 10
    group.mask.top = 10
    group.mask.background_color = 255
    group.mask.topil.return_value = None

    with patch.object(
        layers.Group,
        "extract_bbox",
        return_value=(10, 10, 90, 90),
    ) as extract_bbox:
        converter.apply_mask(group, converter.create_node("g"))

    extract_bbox.assert_called_once_with(group, include_invisible=True)
    rect = converter.svg.find(".//rect")
    assert rect is not None
    assert rect.attrib == {
        "x": "10",
        "y": "10",
        "width": "80",
        "height": "80",
        "fill": "#ffffff",
    }


def test_convert_include_hidden_layers(tmp_path: Path) -> None:
    """Expose the option through the convenience conversion API."""
    output_path = tmp_path / "hidden-layers.svg"

    convert(
        get_fixture(TEST_PSD),
        str(output_path),
        include_hidden_layers=True,
    )

    root = ET.parse(output_path).getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    assert [node.text for node in root.findall(".//svg:text", namespace)] == ["B", "B"]


def test_cli_include_hidden_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pass --include-hidden-layers from the CLI to convert()."""
    mock_convert = Mock()
    monkeypatch.setattr(cli, "convert", mock_convert)
    monkeypatch.setattr(
        sys,
        "argv",
        ["psd2svg", "input.psd", "output.svg", "--include-hidden-layers"],
    )

    cli.main()

    assert mock_convert.call_args.kwargs["include_hidden_layers"] is True
