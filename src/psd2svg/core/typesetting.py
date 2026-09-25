"""PSD TypeSetting data structures and utilities.

This module contains data classes and utilities for parsing Photoshop text layer
data (TypeToolObjectSetting). It wraps psd_tools EngineData structures and provides
a clean interface for accessing text properties, fonts, paragraphs, and styles.

The TypeSetting class is the main entry point, providing an iterator interface
over paragraph and style runs extracted from PSD text layers.
"""

import dataclasses
import logging
import math
from enum import IntEnum
from itertools import groupby
from typing import Any, Iterator, Literal

from psd_tools.psd.descriptor import Enumerated, RawData
from psd_tools.psd.engine_data import DictElement, EngineData
from psd_tools.psd.tagged_blocks import DescriptorBlock, TypeToolObjectSetting
from psd_tools.terminology import Key

from psd2svg import svg_utils
from psd2svg.core import color_utils, font_utils

logger = logging.getLogger(__name__)

_JAPANESE_FONT_SCRIPT = 1


class TextColorType(IntEnum):
    """Color space of an EngineData text color record.

    The record carries an alpha component followed by one component per
    channel, so grayscale has two values, ARGB four and ACMYK five.
    """

    GRAY = 0
    ARGB = 1
    ACMYK = 2


class TextWrappingMode(IntEnum):
    """Text wrapping mode values."""

    NONE = 0  # No wrapping, use native SVG <text> (current behavior)
    FOREIGN_OBJECT = 1  # Use <foreignObject> with XHTML for text wrapping


class Justification(IntEnum):
    """Text justification values from Photoshop."""

    LEFT = 0
    RIGHT = 1
    CENTER = 2
    JUSTIFY_LAST_LEFT = 3
    JUSTIFY_LAST_RIGHT = 4
    JUSTIFY_LAST_CENTER = 5
    JUSTIFY_ALL = 6


class ShapeType(IntEnum):
    """Text shape type values from Photoshop."""

    POINT = 0
    BOUNDING_BOX = 1


class WritingDirection(IntEnum):
    """Text writing direction values from Photoshop."""

    HORIZONTAL_TB = 0
    VERTICAL_RL = 2


class FontCaps(IntEnum):
    """Font capitalization style values from Photoshop."""

    NORMAL = 0
    SMALL_CAPS = 1
    ALL_CAPS = 2


class FontBaseline(IntEnum):
    """Font baseline values from Photoshop.

    In Photoshop, script scale is 0.583 and position is +/- 0.333 for
    superscript and subscript.
    """

    ROMAN = 0
    SUPERSCRIPT = 1
    SUBSCRIPT = 2


@dataclasses.dataclass
class Paragraph:
    """Paragraph of text with associated style."""

    style: "ParagraphSheet"
    spans: list["Span"]

    def __iter__(self) -> Iterator["Span"]:
        """Iterate over spans."""
        return iter(self.spans)

    @property
    def justification(self) -> Justification:
        """Get justification value from paragraph style."""
        return Justification(self.style.justification)

    def get_text_anchor(self) -> str | None:
        """Get SVG text-anchor value based on justification."""
        mapping = {
            Justification.LEFT: None,  # Start is default
            Justification.RIGHT: "end",
            Justification.CENTER: "middle",
            Justification.JUSTIFY_LAST_LEFT: None,  # Start is default
            Justification.JUSTIFY_LAST_RIGHT: "end",
            Justification.JUSTIFY_LAST_CENTER: "middle",
            Justification.JUSTIFY_ALL: None,  # Justify all does not map to text-anchor
        }
        return mapping.get(self.justification, None)

    def compute_leading(self) -> float:
        """Compute leading value for the paragraph.

        Returns the maximum leading value among all spans in the paragraph.
        Each span determines its own leading based on its auto_leading flag,
        scaled by this paragraph's auto leading percentage where it applies.
        """
        return max(
            span.style.compute_leading(self.style.auto_leading) for span in self.spans
        )


@dataclasses.dataclass
class Span:
    """Span of text with associated style."""

    start: int
    end: int
    text: str
    style: "StyleSheet"


@dataclasses.dataclass
class Transform:
    """Affine transform matrix."""

    xx: float
    yx: float
    xy: float
    yy: float
    tx: float
    ty: float

    def to_svg_matrix(self) -> str | None:
        """Convert to SVG matrix string."""
        # Avoid circular import: typesetting -> svg_utils -> typesetting
        from psd2svg import svg_utils  # noqa: PLC0415

        if (self.xx, self.yx, self.xy, self.yy) == (1.0, 0.0, 0.0, 1.0):
            if (self.tx, self.ty) == (0.0, 0.0):
                return None  # Identity transform
            return "translate({})".format(svg_utils.seq2str((self.tx, self.ty)))
        return "matrix({})".format(
            svg_utils.seq2str((self.xx, self.yx, self.xy, self.yy, self.tx, self.ty))
        )

    def is_translation_only(self, tolerance: float = 1e-6) -> bool:
        """Check if the transform is only a translation.

        Args:
            tolerance: Maximum allowed deviation from identity matrix values.
                       Defaults to 1e-6 to account for floating-point precision.

        Returns:
            True if the transform is a translation (rotation/scale components
            form identity matrix).
        """
        return (
            abs(self.xx - 1.0) < tolerance
            and abs(self.yx - 0.0) < tolerance
            and abs(self.xy - 0.0) < tolerance
            and abs(self.yy - 1.0) < tolerance
        )


@dataclasses.dataclass
class Rectangle:
    """Rectangle data."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        """Get width of the rectangle."""
        return self.right - self.left

    @property
    def height(self) -> float:
        """Get height of the rectangle."""
        return self.bottom - self.top


@dataclasses.dataclass
class ParagraphSheet:
    """Paragraph sheet data."""

    name: str
    default_style_sheet: int
    properties: dict

    @classmethod
    def from_dict(cls, data: dict) -> "ParagraphSheet":
        if "ParagraphSheet" in data:
            data = data["ParagraphSheet"]
        return cls(
            name=data.get("Name", ""),
            default_style_sheet=data.get("DefaultStyleSheet", 0),
            properties=dict(data.get("Properties", {})),
        )

    def __getitem__(self, key: str) -> Any:
        return self.properties.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)

    @property
    def justification(self) -> Justification:
        """Get justification value."""
        return Justification(self.properties.get("Justification", 0))

    @property
    def first_line_indent(self) -> float:
        """Get first line indent value."""
        return float(self.properties.get("FirstLineIndent", 0.0))

    @property
    def start_indent(self) -> float:
        """Get start indent value."""
        return float(self.properties.get("StartIndent", 0.0))

    @property
    def end_indent(self) -> float:
        """Get end indent value."""
        return float(self.properties.get("EndIndent", 0.0))

    @property
    def space_before(self) -> float:
        """Get space before value."""
        return float(self.properties.get("SpaceBefore", 0.0))

    @property
    def space_after(self) -> float:
        """Get space after value."""
        return float(self.properties.get("SpaceAfter", 0.0))

    @property
    def auto_hyphenate(self) -> bool:
        """Whether auto hyphenation is enabled."""
        return bool(self.properties.get("AutoHyphenate", False))

    @property
    def hyphenation_word_size(self) -> int:
        """Get hyphenation word size."""
        return int(self.properties.get("HyphenationWordSize", 6))

    @property
    def pre_hyphen(self) -> int:
        """Get pre-hyphen characters count."""
        return int(self.properties.get("PreHyphen", 2))

    @property
    def post_hyphen(self) -> int:
        """Get post-hyphen characters count."""
        return int(self.properties.get("PostHyphen", 2))

    @property
    def consecutive_hyphens(self) -> int:
        """Get consecutive hyphens limit."""
        return int(self.properties.get("ConsecutiveHyphens", 8))

    @property
    def zone(self) -> float:
        """Get zone value."""
        return float(self.properties.get("Zone", 36.0))

    @property
    def word_spacing(self) -> tuple[float, float, float]:
        """Get word spacing as (min, desired, max)."""
        ws = self.properties.get("WordSpacing", [1.0, 1.0, 2.0])
        return (float(ws[0]), float(ws[1]), float(ws[2]))

    @property
    def letter_spacing(self) -> tuple[float, float, float]:
        """Get letter spacing as (min, desired, max)."""
        ls = self.properties.get("LetterSpacing", [0.0, 0.0, 0.05])
        return (float(ls[0]), float(ls[1]), float(ls[2]))

    @property
    def glyph_spacing(self) -> tuple[float, float, float]:
        """Get glyph spacing as (min, desired, max)."""
        gs = self.properties.get("GlyphSpacing", [1.0, 1.0, 1.0])
        return (float(gs[0]), float(gs[1]), float(gs[2]))

    @property
    def auto_leading(self) -> float:
        """Auto leading scale."""
        return float(self.properties.get("AutoLeading", 1.2))

    @property
    def leading_type(self) -> int:
        """Get leading type value."""
        return int(self.properties.get("LeadingType", 0))

    @property
    def hanging(self) -> bool:
        """Whether hanging punctuation is enabled."""
        return bool(self.properties.get("Hanging", False))

    @property
    def kinsoku_order(self) -> int:
        """Get kinsoku order value."""
        return int(self.properties.get("KinsokuOrder", 0))

    @property
    def every_line_composer(self) -> bool:
        """Whether every line composer is enabled."""
        return bool(self.properties.get("EveryLineComposer", False))


@dataclasses.dataclass
class StyleSheet:
    """Style sheet data."""

    name: str
    style_sheet_data: dict

    @classmethod
    def from_dict(cls, data: dict) -> "StyleSheet":
        if "StyleSheet" in data:
            data = data["StyleSheet"]
        return cls(
            name=data.get("Name", ""),
            style_sheet_data=dict(data.get("StyleSheetData", {})),
        )

    def __getitem__(self, key: str) -> Any:
        return self.style_sheet_data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self.style_sheet_data.get(key, default)

    @property
    def font(self) -> int:
        """Get font index."""
        return int(self.style_sheet_data.get("Font", 0))

    @property
    def font_size(self) -> float:
        """Get font size value."""
        return float(self.style_sheet_data.get("FontSize", 12.0))

    @property
    def faux_bold(self) -> bool:
        """Whether faux bold is enabled."""
        return bool(self.style_sheet_data.get("FauxBold", False))

    @property
    def faux_italic(self) -> bool:
        """Whether faux italic is enabled."""
        return bool(self.style_sheet_data.get("FauxItalic", False))

    @property
    def auto_leading(self) -> bool:
        """Whether auto leading is enabled."""
        return bool(self.style_sheet_data.get("AutoLeading", True))

    @property
    def leading(self) -> float:
        """Get leading value."""
        return float(self.style_sheet_data.get("Leading", 0.0))

    @property
    def horizontal_scale(self) -> float:
        """Get horizontal scale value in the range (0.0, 1.0)."""
        return float(self.style_sheet_data.get("HorizontalScale", 1.0))

    @property
    def vertical_scale(self) -> float:
        """Get vertical scale value in the range (0.0, 1.0)."""
        return float(self.style_sheet_data.get("VerticalScale", 1.0))

    @property
    def tracking(self) -> int:
        """Get tracking value."""
        return int(self.style_sheet_data.get("Tracking", 0))

    @property
    def auto_kerning(self) -> bool:
        """Whether auto kerning is enabled."""
        return bool(self.style_sheet_data.get("AutoKerning", True))

    @property
    def kerning(self) -> int:
        """Get kerning value."""
        return int(self.style_sheet_data.get("Kerning", 0))

    @property
    def baseline_shift(self) -> float:
        """Get baseline shift value."""
        return float(self.style_sheet_data.get("BaselineShift", 0.0))

    @property
    def font_caps(self) -> FontCaps:
        """Get font capitalization style."""
        return FontCaps(self.style_sheet_data.get("FontCaps", 0))

    @property
    def font_baseline(self) -> FontBaseline:
        """Font baseline."""
        return FontBaseline(self.style_sheet_data.get("FontBaseline", 0))

    @property
    def underline(self) -> bool:
        """Whether underline is enabled."""
        return bool(self.style_sheet_data.get("Underline", False))

    @property
    def strikethrough(self) -> bool:
        """Whether strikethrough is enabled."""
        return bool(self.style_sheet_data.get("Strikethrough", False))

    @property
    def ligatures(self) -> bool:
        """Whether ligatures are enabled."""
        return bool(self.style_sheet_data.get("Ligatures", True))

    @property
    def discretionary_ligatures(self) -> bool:
        """Whether discretionary ligatures are enabled."""
        return bool(self.style_sheet_data.get("DLigatures", False))

    @property
    def baseline_direction(self) -> int:
        """Get baseline direction value."""
        return int(self.style_sheet_data.get("BaselineDirection", 0))

    @property
    def no_break(self) -> bool:
        """Whether no-break is enabled."""
        return bool(self.style_sheet_data.get("NoBreak", False))

    @property
    def tsume(self) -> float:
        """Get tsume (character tightening) value.

        Values between 0 (no tightening) and 1 (maximum tightening). This is
        an East-Asian typography feature.
        """
        return float(self.style_sheet_data.get("Tsume", 0.0))

    @property
    def fill_color(self) -> tuple[float, float, float, float]:
        """Get fill color as ARGB tuple with values between 0 and 1."""
        color = self.style_sheet_data.get("FillColor", None)
        if color is None:
            return (1.0, 0.0, 0.0, 0.0)  # Default black
        return _color_to_argb(color, (1.0, 0.0, 0.0, 0.0))

    @property
    def stroke_color(self) -> tuple[float, float, float, float]:
        """Get stroke color as ARGB tuple with values between 0 and 1."""
        color = self.style_sheet_data.get("StrokeColor", None)
        if color is None:
            return (0.0, 0.0, 0.0, 0.0)  # Default transparent
        return _color_to_argb(color, (0.0, 0.0, 0.0, 0.0))

    @property
    def fill_flag(self) -> bool:
        """Whether fill is enabled."""
        return bool(self.style_sheet_data.get("FillFlag", True))

    @property
    def stroke_flag(self) -> bool:
        """Whether stroke is enabled."""
        return bool(self.style_sheet_data.get("StrokeFlag", False))

    def get_fill_color(self) -> str | None:
        """Get fill color as hex string."""
        if not self.fill_flag:
            return None
        return _get_hex_color_from_argb(self.fill_color)

    def get_stroke_color(self) -> str | None:
        """Get stroke color as hex string."""
        if not self.stroke_flag:
            return None
        return _get_hex_color_from_argb(self.stroke_color)

    def compute_leading(self, auto_leading_scale: float) -> float:
        """Compute leading value for line height.

        Args:
            auto_leading_scale: The containing paragraph's auto leading
                percentage, applied only when this span uses auto leading.

        Returns:
            Leading value in pixels (line height for CSS).

        Note:
            Auto leading derives the line height from the font size, ignoring
            the stored ``Leading``. Photoshop leaves whatever value the span
            last had in that field, so it carries no meaning here.

            Manual leading uses the stored value as-is, unscaled.
        """
        if self.auto_leading:
            return self.font_size * auto_leading_scale
        return self.leading


class RunLengthIndex:
    """Get run index from character index using run length array.

    Example::

        rli = RunLengthIndex([4, 2, 5])
        rli(0) -> 0
        rli(3) -> 0
        rli(4) -> 1
        rli(5) -> 1
        rli(6) -> 2
        rli(10) -> 2
    """

    def __init__(self, run_length_array: list[int]):
        self._run_length_array = run_length_array
        self._cumulative_lengths = []
        cumulative = 0
        for length in run_length_array:
            cumulative += length
            self._cumulative_lengths.append(cumulative)

    @property
    def boundaries(self) -> list[int]:
        """Get the boundaries array."""
        return self._cumulative_lengths

    def __call__(self, index: int) -> int:
        """Get the run index for the given character index."""
        if index < 0:
            raise IndexError("Character index cannot be negative.")
        for run_index, cumulative_length in enumerate(self._cumulative_lengths):
            if index < cumulative_length:
                return run_index
        raise IndexError("Character index out of range.")


class TypeSetting:
    """Type tool object setting wrapper.

    Example::

        setting = TypeSetting(type_tool_object_setting)
        for span in setting:
            print(span.start, span.end, span.text, span.paragraph, span.style)
    """

    def __init__(self, setting: TypeToolObjectSetting):
        assert isinstance(setting, TypeToolObjectSetting)
        self._setting = setting

        assert "EngineData" in self._setting.text_data
        raw_data = self._setting.text_data["EngineData"]
        assert isinstance(raw_data, RawData)
        self._engine_data: EngineData = raw_data.value  # type: ignore

    @property
    def transform(self) -> Transform:
        """Affine transform matrix."""
        return Transform(*self._setting.transform)

    @property
    def bounds(self) -> Rectangle:
        """Text bounds rectangle.

        This is a user-defined bounds that may differ from the bounding box.
        Use bounds for positioning the text content by justification settings.
        """
        desc = self._setting.text_data.get("bounds")
        if not desc:
            logger.debug("Bounds not found in text data.")
            return Rectangle(0.0, 0.0, 0.0, 0.0)
        return Rectangle(
            left=float(desc[Key.Left].value),
            top=float(desc[Key.Top].value),
            right=float(desc[Key.Right].value),
            bottom=float(desc[Key.Bottom].value),
        )

    @property
    def bounding_box(self) -> Rectangle:
        """Text bounding box rectangle.

        This is a bounding box around the text content.
        """
        desc = self._setting.text_data.get("boundingBox")
        if not desc:
            logger.debug("Bounding box not found in text data.")
            return Rectangle(0.0, 0.0, 0.0, 0.0)
        return Rectangle(
            left=float(desc[Key.Left].value),
            top=float(desc[Key.Top].value),
            right=float(desc[Key.Right].value),
            bottom=float(desc[Key.Bottom].value),
        )

    @property
    def engine_data(self) -> EngineData:
        """Engine data dictionary."""
        return self._engine_data

    @property
    def resources(self) -> DictElement:
        """Resource dictionary from engine data."""
        assert "ResourceDict" in self.engine_data
        return self.engine_data["ResourceDict"]

    @property
    def document_resources(self) -> DictElement:
        """Document resource dictionary from engine data."""
        assert "DocumentResources" in self.engine_data
        return self.engine_data["DocumentResources"]

    @property
    def font_set(self) -> list[dict]:
        """List of font info dictionaries from resources."""
        return [dict(fs) for fs in self.resources.get("FontSet", [])]

    @property
    def paragraph_sheets(self) -> list[ParagraphSheet]:
        """List of paragraph sheets from resources."""
        return [
            ParagraphSheet(
                name=ps.get("Name", ""),
                default_style_sheet=ps.get("DefaultStyleSheet", 0),
                properties=dict(ps.get("Properties", {})),
            )
            for ps in self.resources.get("ParagraphSheetSet", [])
        ]

    @property
    def style_sheets(self) -> list[StyleSheet]:
        """List of style sheets from resources."""
        return [
            StyleSheet(
                name=ss.get("Name", ""),
                style_sheet_data=dict(ss.get("StyleSheetData", {})),
            )
            for ss in self.resources.get("StyleSheetSet", [])
        ]

    @property
    def engine_dict(self) -> DictElement:
        """Engine dictionary from engine data."""
        assert "EngineDict" in self.engine_data
        return self.engine_data["EngineDict"]

    @property
    def text(self) -> str:
        """Text content from engine data."""
        assert "Editor" in self.engine_dict
        assert "Text" in self.engine_dict["Editor"]
        return str(self.engine_dict["Editor"]["Text"].value)

    @property
    def _shapes(self) -> list[DictElement]:
        """Shapes dictionary from engine data."""
        assert "Rendered" in self.engine_dict
        rendered = self.engine_dict["Rendered"]
        assert "Shapes" in rendered
        return list(rendered["Shapes"]["Children"])

    @property
    def _shape(self) -> DictElement | None:
        """First shape dictionary from engine data."""
        shapes = self._shapes
        if not shapes:
            logger.debug("No shapes found.")
            return None
        elif len(shapes) > 1:
            logger.debug("Multiple shapes found, using the first one.")
        return shapes[0]

    @property
    def shape_type(self) -> ShapeType:
        """Shape type from engine data."""
        shape = self._shape
        assert shape is not None
        assert "ShapeType" in shape
        return ShapeType(shape["ShapeType"].value)

    @property
    def writing_direction(self) -> WritingDirection:
        """Writing direction from engine data.

        Values are:
        - 0: Horizontal Top to Bottom
        - 2: Vertical Right to Left

        NOTE: There could be other values, need to verify.
        """
        assert "Rendered" in self.engine_dict
        rendered = self.engine_dict["Rendered"]
        assert "Shapes" in rendered
        assert "WritingDirection" in rendered["Shapes"]
        return WritingDirection(rendered["Shapes"]["WritingDirection"].value)

    @property
    def point_base(self) -> tuple[float, float]:
        """Point base from shape structure in engine data."""
        if self.shape_type != ShapeType.POINT:
            return (0.0, 0.0)  # Not a point shape
        shape = self._shape
        assert shape is not None
        assert "Cookie" in shape
        assert "Photoshop" in shape["Cookie"]
        assert "PointBase" in shape["Cookie"]["Photoshop"]
        point_base = shape["Cookie"]["Photoshop"]["PointBase"]
        return (point_base[0].value, point_base[1].value)

    @property
    def box_bounds(self) -> Rectangle:
        """Box bounds from shape structure in engine data."""
        if self.shape_type != ShapeType.BOUNDING_BOX:
            return Rectangle(0, 0, 0, 0)  # Not a bounding box shape
        shape = self._shape
        assert shape is not None
        assert "Cookie" in shape
        assert "Photoshop" in shape["Cookie"]
        assert "BoxBounds" in shape["Cookie"]["Photoshop"]
        bounds = shape["Cookie"]["Photoshop"]["BoxBounds"]
        return Rectangle(
            left=float(bounds[0].value),
            top=float(bounds[1].value),
            right=float(bounds[2].value),
            bottom=float(bounds[3].value),
        )

    @property
    def warp_version(self) -> int:
        """Warp version."""
        return int(self._setting.warp_version)

    @property
    def _warp(self) -> DescriptorBlock:
        """Warp descriptor block from type tool object setting."""
        warp = self._setting.warp
        assert isinstance(warp, DescriptorBlock)
        assert warp.classID == b"warp"
        return warp

    @property
    def warp_style(self) -> str | None:
        """Warp style.

        Example warp content::

            warp=DescriptorBlock(b'warp'){
                'warpStyle': (b'warpStyle', b'warpArc'),
                'warpValue': -100.0,
                'warpPerspective': 0.0,
                'warpPerspectiveOther': 0.0,
                'warpRotate': (b'Ornt', b'Hrzn')
            }
        """
        # NOTE: Check for other warp styles, and make an enum if needed.
        warp_style = self._warp.get("warpStyle", None)
        if warp_style is None:
            return None
        assert isinstance(warp_style, Enumerated)
        assert warp_style.typeID == b"warpStyle"
        return warp_style.enum.decode("ascii")

    @property
    def warp_value(self) -> float:
        """Warp value from warp descriptor."""
        warp_value = self._warp.get("warpValue", 0.0)
        return float(warp_value)

    @property
    def warp_perspective(self) -> float:
        """Warp perspective from warp descriptor."""
        perspective = self._warp.get("warpPerspective", 0.0)
        return float(perspective)

    @property
    def warp_perspective_other(self) -> float:
        """Warp perspective other from warp descriptor."""
        perspective_other = self._warp.get("warpPerspectiveOther", 0.0)
        return float(perspective_other)

    @property
    def warp_rotate(self) -> Literal["Hrzn", "Vrtc"] | None:
        """Warp rotate from warp descriptor."""
        warp_rotate = self._warp.get("warpRotate", None)
        if warp_rotate is None:
            return None
        assert isinstance(warp_rotate, Enumerated)
        assert warp_rotate.typeID == b"Ornt"
        return warp_rotate.enum.decode("ascii")  # type: ignore

    @property
    def left(self) -> float:
        """Left offset likely in normalized coordinate space."""
        # NOTE: Not sure what coordinate space this is in.
        return float(self._setting.left / (2 << 32 - 1))

    @property
    def top(self) -> float:
        """Top offset likely in normalized coordinate space."""
        # NOTE: Not sure what coordinate space this is in.
        return float(self._setting.top / (2 << 32 - 1))

    @property
    def right(self) -> float:
        """Right offset likely in normalized coordinate space."""
        # NOTE: Not sure what coordinate space this is in.
        return float(self._setting.right / (2 << 32 - 1))

    @property
    def bottom(self) -> float:
        """Bottom offset likely in normalized coordinate space."""
        # NOTE: Not sure what coordinate space this is in.
        return float(self._setting.bottom / (2 << 32 - 1))

    @property
    def superscript_size(self) -> float:
        """Superscript size from document resources."""
        assert "SuperscriptSize" in self.document_resources
        return float(self.document_resources["SuperscriptSize"].value)

    @property
    def subscript_size(self) -> float:
        """Subscript size from document resources."""
        assert "SubscriptSize" in self.document_resources
        return float(self.document_resources["SubscriptSize"].value)

    @property
    def superscript_position(self) -> float:
        """Superscript position from document resources."""
        assert "SuperscriptPosition" in self.document_resources
        return float(self.document_resources["SuperscriptPosition"].value)

    @property
    def subscript_position(self) -> float:
        """Subscript position from document resources."""
        assert "SubscriptPosition" in self.document_resources
        return float(self.document_resources["SubscriptPosition"].value)

    @property
    def small_cap_size(self) -> float:
        """Small cap size from document resources."""
        assert "SmallCapSize" in self.document_resources
        return float(self.document_resources["SmallCapSize"].value)

    @property
    def _paragraph_run(self) -> DictElement:
        """Paragraph run dictionary from engine data."""
        assert "ParagraphRun" in self.engine_dict
        return self.engine_dict["ParagraphRun"]

    @property
    def _style_run(self) -> DictElement:
        """Style run dictionary from engine data."""
        assert "StyleRun" in self.engine_dict
        return self.engine_dict["StyleRun"]

    def __iter__(self) -> Iterator[Paragraph]:
        """Iterate over paragraph and style runs."""
        paragraph_index = RunLengthIndex(self._paragraph_run["RunLengthArray"])
        style_index = RunLengthIndex(self._style_run["RunLengthArray"])
        stops = sorted(set(paragraph_index.boundaries) | set(style_index.boundaries))
        for index, group in groupby(
            zip([0] + stops, stops), key=lambda start_end: paragraph_index(start_end[0])
        ):
            paragraph_sheet = self.get_paragraph_sheet(
                ParagraphSheet.from_dict(self._paragraph_run["RunArray"][index])
            )
            spans = [
                Span(
                    start=start,
                    end=stop,
                    text=str(self.text[start:stop]),
                    style=self.get_style_sheet(
                        StyleSheet.from_dict(
                            self._style_run["RunArray"][style_index(start)]
                        )
                    ),
                )
                for start, stop in group
            ]
            yield Paragraph(style=paragraph_sheet, spans=spans)

    def get_postscript_name(self, font_index: int) -> str | None:
        """Get the PostScript name for the given font index.

        Args:
            font_index: Index into the font set.

        Returns:
            PostScript name string, or None if not found.
        """
        font_info = self.font_set[font_index]
        postscriptname = font_info.get("Name", None)
        if postscriptname is None:
            logger.warning(f"PostScript name not found for font index {font_index}.")
            return None
        return postscriptname.value

    def is_japanese_font(self, font_index: int) -> bool:
        """Whether the EngineData font record uses the Japanese script."""
        font_info = self.font_set[font_index]
        return int(font_info.get("Script", 0)) == _JAPANESE_FONT_SCRIPT

    def get_font_info(
        self,
        font_index: int,
        font_mapping: dict[str, dict[str, float | str]] | None = None,
    ) -> font_utils.FontInfo | None:
        """Get the font family name for the given font index.

        Args:
            font_index: Index into the font set.
            font_mapping: Optional custom font mapping dictionary.

        Returns:
            FontInfo object with font metadata, or None if font not found.
        """
        postscriptname = self.get_postscript_name(font_index)
        if postscriptname is None:
            return None
        return font_utils.FontInfo.lookup_static(postscriptname, font_mapping)

    def get_paragraph_sheet(self, sheet: ParagraphSheet) -> ParagraphSheet:
        """Get the merged paragraph sheet."""
        default_properties = dict(
            self.paragraph_sheets[sheet.default_style_sheet].properties
        )
        default_properties.update(sheet.properties)
        return ParagraphSheet(
            name=sheet.name,
            default_style_sheet=sheet.default_style_sheet,
            properties=default_properties,
        )

    def get_style_sheet(self, sheet: StyleSheet) -> StyleSheet:
        """Get the merged style sheet."""
        default_sheet_data = dict(
            self.style_sheets[
                int(self.resources["TheNormalStyleSheet"])
            ].style_sheet_data
        )
        default_sheet_data.update(sheet.style_sheet_data)
        return StyleSheet(
            name=sheet.name,
            style_sheet_data=default_sheet_data,
        )

    def has_warp(self) -> bool:
        """Check if the text has a warp effect applied."""
        return self.warp_style is not None and self.warp_style != "warpNone"

    def get_warp_path(self) -> str:
        """Generate SVG path data for the warp effect."""
        if self.warp_style != "warpArc":
            logger.debug("Warp style not supported for path generation.")
            return ""
        if self.warp_rotate != "Hrzn":
            logger.debug(
                "Warp rotate only supported for horizontal orientation, "
                "falling back to straight line."
            )
            return "M%s L%s" % (
                svg_utils.seq2str((self.bounding_box.left, self.bounding_box.bottom)),
                svg_utils.seq2str((self.bounding_box.right, self.bounding_box.bottom)),
            )

        # NOTE: warp_value 100 = 180 degrees arc
        # NOTE: warp_value -100 = -180 degrees arc
        # NOTE: warp_value 0 = straight line

        if self.warp_value == 0:
            # No warp, straight line.
            return "M%s L%s" % (
                svg_utils.seq2str((self.bounding_box.left, self.bounding_box.bottom)),
                svg_utils.seq2str((self.bounding_box.right, self.bounding_box.bottom)),
            )

        # We have a warp, compute the arc parameters.
        scale = math.sin(math.pi / 2 * abs(self.warp_value) / 100)
        radius = (self.bounding_box.width + self.bounding_box.height) / 2 / scale
        commands = []
        if self.warp_value > 0:
            # Positive warp, arc bulging upwards.
            x1 = self.bounding_box.left - self.bounding_box.height / 2
            y1 = self.bounding_box.bottom
            commands.append("M%s" % svg_utils.seq2str((x1, y1)))
            x2 = self.bounding_box.right + self.bounding_box.height / 2
            y2 = self.bounding_box.bottom
            commands.append(
                "A%s 0 0 1 %s"
                % (svg_utils.seq2str((radius, radius)), svg_utils.seq2str((x2, y2)))
            )
        else:
            # Negative warp, arc bulging downwards.
            # NOTE: Height adjustment should be the baseline height, not the
            # half box height.
            x1 = self.bounding_box.left - self.bounding_box.height / 2
            y1 = self.bounding_box.top + self.bounding_box.height / 2
            commands.append("M%s" % svg_utils.seq2str((x1, y1)))
            x2 = self.bounding_box.right + self.bounding_box.height / 2
            y2 = self.bounding_box.top + self.bounding_box.height / 2
            commands.append(
                "A%s 0 0 0 %s"
                % (svg_utils.seq2str((radius, radius)), svg_utils.seq2str((x2, y2)))
            )
        return " ".join(commands)


def _color_to_argb(
    color: DictElement, fallback: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """Convert an EngineData color record to an ARGB tuple with values in 0-1.

    Args:
        color: EngineData color record, carrying a ``Type`` and ``Values``.
        fallback: Color to use when the record cannot be interpreted.

    Returns:
        Tuple of (a, r, g, b) as floats in the range 0.0-1.0.

    Note:
        An unsupported color type degrades to the fallback so that a single
        bad span does not abort the conversion of the whole document.
    """
    color_type = color.get("Type", None)
    values = [float(value) for value in color.get("Values", [])]
    if color_type is not None:
        if int(color_type) == TextColorType.GRAY and len(values) == 2:
            # EngineData stores the single component as luminance, not ink
            # coverage, so 0.0 is black -- inverted from the "% black" value
            # Photoshop itself shows for the same color.
            a, gray = values
            return (a, gray, gray, gray)
        if int(color_type) == TextColorType.ARGB and len(values) == 4:
            a, r, g, b = values
            return (a, r, g, b)
        if int(color_type) == TextColorType.ACMYK and len(values) == 5:
            a, c, m, y, k = values
            r, g, b = color_utils.cmyk2rgb_float((c, m, y, k))
            return (a, r, g, b)
    logger.warning(
        "Unsupported text color, falling back to %s: %s", fallback, dict(color)
    )
    return fallback


def _get_hex_color_from_argb(argb: tuple[float, float, float, float]) -> str | None:
    """Convert ARGB color tuple to hex string."""
    a, r, g, b = argb
    if a == 0:
        return "none"
    elif ((r, g, b) == (0, 0, 0)) and (a == 1):
        return None  # Default black color in SVG.
    return color_utils.rgba2hex(
        (
            color_utils.float2uint8(r),
            color_utils.float2uint8(g),
            color_utils.float2uint8(b),
        ),
        alpha=a,
    )
