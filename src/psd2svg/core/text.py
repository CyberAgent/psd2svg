"""SVG text conversion logic for PSD text layers.

This module contains the TextConverter mixin class that converts Photoshop text layers
(TypeLayer) to SVG text elements. It supports two rendering modes:

1. Native SVG <text> elements (default) - Uses SVG text/tspan for accurate
   text rendering
2. Foreign object mode - Uses <foreignObject> with XHTML for text wrapping support

The TextConverter works with TypeSetting and related data structures from the
typesetting module to extract PSD text data and generate corresponding SVG markup.

Key features:
- Point text and bounding box text
- Paragraph alignment and justification
- Text styling (font, color, size, decoration, etc.)
- Vertical and horizontal text direction
- Letter spacing, tracking, and kerning
- Font effects (superscript, subscript, small caps)

Note: This module re-exports TypeSetting and TextWrappingMode for backward
      compatibility. New code should import these directly from
      psd2svg.core.typesetting.
"""

import logging
import xml.etree.ElementTree as ET

from psd_tools.api import layers

from psd2svg import svg_utils
from psd2svg.core.base import ConverterProtocol
from psd2svg.core.typesetting import (
    FontBaseline,
    FontCaps,
    Justification,
    Paragraph,
    Rectangle,
    ShapeType,
    Span,
    TextWrappingMode,
    TypeSetting,
    WritingDirection,
)

logger = logging.getLogger(__name__)

# Threshold for negligible margin values (in pixels).
# Sub-pixel values below this threshold don't meaningfully affect rendering
# and are omitted to produce cleaner SVG output (avoiding "-0px" or "-0.005px").
NEGLIGIBLE_MARGIN_THRESHOLD = 0.01


def _needs_whitespace_preservation(text: str) -> bool:
    """Check if text needs whitespace preservation.

    Returns True if the text contains:
    - Leading or trailing spaces
    - Multiple consecutive spaces (2 or more)
    - Tabs or other whitespace characters

    When whitespace needs preservation, the xml:space="preserve" attribute is added
    to the SVG element. While MDN recommends the CSS white-space property as the
    modern approach (https://developer.mozilla.org/en-US/docs/Web/SVG/Attribute/xml:space),
    we use xml:space for better compatibility with SVG renderers including resvg-py.
    The attribute works equivalently to CSS "white-space: pre".

    Note: Carriage returns (\r) are ignored since they are stripped
    during text processing.

    Args:
        text: Text content to check.

    Returns:
        True if xml:space="preserve" is needed, False otherwise.
    """
    if not text:
        return False

    # Strip carriage returns as they're removed during text processing
    text = text.replace("\r", "")

    if not text:
        return False

    # Check for leading or trailing spaces
    if text != text.strip():
        return True

    # Check for multiple consecutive spaces
    if "  " in text:
        return True

    # Check for tabs or other special whitespace
    if "\t" in text or "\n" in text or "\f" in text:
        return True

    return False


class TextConverter(ConverterProtocol):
    """Mixin for text layers."""

    def create_text_node(self, layer: layers.TypeLayer) -> ET.Element:
        """Create SVG text node from a TypeLayer."""
        text_setting = TypeSetting(layer._data)

        # Determine if we should use foreignObject
        # Only use for bounding box text when explicitly enabled
        use_foreign_object = (
            self.text_wrapping_mode == TextWrappingMode.FOREIGN_OBJECT
            and text_setting.shape_type == ShapeType.BOUNDING_BOX
        )

        if use_foreign_object:
            return self._create_foreign_object_text(text_setting)
        else:
            return self._create_native_svg_text(text_setting)

    def _create_text_path_node(
        self, text_setting: TypeSetting, text_node: ET.Element
    ) -> ET.Element:
        """Create SVG textPath element from a TypeLayer."""
        defs = self.create_node("defs")
        warp_path = self.create_node(
            "path",
            parent=defs,
            d=text_setting.get_warp_path(),
            id=self.auto_id("warp-path"),
        )
        # NOTE: Due to browser inconsistencies with textLength on textPath,
        # we only set textLength for extreme warp values to better match Photoshop.
        text_length = (
            "100%"
            if text_setting.warp_style == "warpArc"
            and abs(text_setting.warp_value) > 50
            else None
        )
        text_path_node = self.create_node(
            "textPath",
            parent=text_node,
            startOffset="50%",
            href=svg_utils.get_uri(warp_path),
            lengthAdjust="spacingAndGlyphs",
            method="stretch",
            textLength=text_length,
        )
        return text_path_node

    def _create_native_svg_text(self, text_setting: TypeSetting) -> ET.Element:
        """Create native SVG <text> element (current implementation).

        Args:
            text_setting: TypeSetting object with text data.

        Returns:
            text element with nested tspan elements.
        """
        # Use native x, y attributes for translation-only transforms
        transform = text_setting.transform
        uses_native_positioning = (
            transform.is_translation_only() and not text_setting.has_warp()
        )

        paragraphs = list(text_setting)

        # Check if any span needs whitespace preservation
        needs_preserve = any(
            _needs_whitespace_preservation(span.text)
            for paragraph in paragraphs
            for span in paragraph
        )

        if uses_native_positioning:
            # Don't set x/y on parent - each tspan will have its own position
            text_node = self.create_node(
                "text", xml_space="preserve" if needs_preserve else None
            )
        else:
            # Use transform for non-translation transforms
            text_node = self.create_node(
                "text",
                transform=transform.to_svg_matrix(),
                xml_space="preserve" if needs_preserve else None,
            )

        if text_setting.writing_direction == WritingDirection.VERTICAL_RL:
            svg_utils.set_attribute(text_node, "writing-mode", "vertical-rl")

        container_node = text_node
        if text_setting.has_warp():
            container_node = self._create_text_path_node(text_setting, text_node)

        with self.set_current(container_node):
            for i, paragraph in enumerate(paragraphs):
                paragraph_node = self._add_paragraph(
                    text_setting,
                    paragraph,
                    first_paragraph=(i == 0),
                    uses_native_positioning=uses_native_positioning,
                )
                for span in paragraph:
                    self._add_text_span(text_setting, paragraph_node, span)

        if text_setting.has_warp():
            # When there is <textPath>, we can only optimize at the paragraph level.
            for child in container_node:
                svg_utils.merge_common_child_attributes(
                    child,
                    excludes={"x", "y", "dx", "dy", "transform"},
                )
                svg_utils.merge_consecutive_siblings(child)
                svg_utils.merge_offset_siblings(child)
                svg_utils.merge_singleton_children(child)
                svg_utils.merge_attribute_less_children(child)
        else:
            svg_utils.merge_common_child_attributes(
                text_node,
                excludes={"x", "y", "dx", "dy", "transform"},
            )
            svg_utils.merge_consecutive_siblings(text_node)
            svg_utils.merge_offset_siblings(text_node)
            svg_utils.merge_singleton_children(text_node)
            svg_utils.merge_attribute_less_children(text_node)
        return text_node

    def _create_foreign_object_text(self, text_setting: TypeSetting) -> ET.Element:
        """Create <foreignObject> with XHTML content for text wrapping.

        This method creates a foreignObject element containing XHTML div/p/span
        elements with CSS styling. This enables proper text wrapping for bounding
        box text, which is not natively supported by SVG.

        Args:
            text_setting: TypeSetting object with text data.

        Returns:
            foreignObject element containing XHTML content.

        Note:
            - Requires XHTML namespace for proper rendering
            - Supported by modern browsers (Chrome, Firefox, Safari, Edge)
            - Not supported by resvg/resvg-py or many other SVG renderers
              (PDF converters, design tools)
        """
        bounds = text_setting.box_bounds
        transform = text_setting.transform

        # Create foreignObject element with bounding box dimensions
        foreign_obj = self.create_node(
            "foreignObject",
            x=transform.tx + bounds.left,
            y=transform.ty + bounds.top,
            width=bounds.width,
            height=bounds.height,
        )

        # Apply non-translation transform if needed
        if not transform.is_translation_only():
            svg_utils.set_attribute(foreign_obj, "transform", transform.to_svg_matrix())

        # Check if any paragraph has auto hyphenation enabled
        # If so, add lang attribute for CSS hyphens to work
        paragraphs = list(text_setting)
        has_hyphenation = any(p.style.auto_hyphenate for p in paragraphs)

        # Create XHTML div container with proper namespace
        container_styles = self._get_foreign_object_container_styles(
            text_setting, bounds
        )
        div = svg_utils.create_xhtml_node(
            "div",
            parent=foreign_obj,
            style=svg_utils.styles_to_string(container_styles),
            lang="en" if has_hyphenation else None,
        )

        # Add paragraphs
        for paragraph in paragraphs:
            self._add_foreign_object_paragraph(div, paragraph, text_setting)

        return foreign_obj

    def _add_paragraph(
        self,
        text_setting: TypeSetting,
        paragraph: Paragraph,
        first_paragraph: bool = False,
        uses_native_positioning: bool = False,
    ) -> ET.Element:
        """Add a paragraph to the text node."""
        line_height = paragraph.compute_leading()
        text_anchor = paragraph.get_text_anchor()

        # Calculate positioning based on shape type and writing direction
        x, y, dominant_baseline = self._compute_paragraph_position(
            text_setting, text_anchor
        )

        # Create paragraph node
        paragraph_node = self._create_paragraph_node(
            text_setting,
            x,
            y,
            line_height,
            text_anchor,
            dominant_baseline,
            first_paragraph,
            uses_native_positioning,
        )

        # Apply justification settings
        self._apply_justification(paragraph, paragraph_node, text_setting)

        return paragraph_node

    def _compute_paragraph_position(
        self,
        text_setting: TypeSetting,
        text_anchor: str | None,
    ) -> tuple[float, float, str | None]:
        """Compute paragraph position based on justification, shape type,
        and writing direction.

        Args:
            text_setting: Type setting object containing bounds and writing direction.
            text_anchor: SVG text-anchor value ("start", "middle", "end", or None).

        Returns:
            Tuple of (x, y, dominant_baseline) for positioning the paragraph.
        """
        x = 0.0
        y = 0.0
        dominant_baseline = None

        if text_setting.shape_type == ShapeType.BOUNDING_BOX:
            # Use "hanging" baseline for bounding box text, which aligns text to
            # the hanging baseline (top of most glyphs). This provides the closest
            # match to Photoshop's bounding box text positioning, though subtle
            # differences may remain due to font rendering variations between
            # Photoshop and browsers.
            dominant_baseline = "hanging"
            if text_setting.writing_direction == WritingDirection.HORIZONTAL_TB:
                if text_anchor == "end":
                    x = text_setting.bounds.right
                elif text_anchor == "middle":
                    x = (text_setting.bounds.left + text_setting.bounds.right) / 2
            elif text_setting.writing_direction == WritingDirection.VERTICAL_RL:
                logger.debug(
                    "Dominant baseline may not be supported by SVG renderers "
                    "for vertical text."
                )
                x = text_setting.bounds.right
                if text_anchor == "end":
                    y = text_setting.bounds.bottom
                elif text_anchor == "middle":
                    y = (text_setting.bounds.top + text_setting.bounds.bottom) / 2

        return x, y, dominant_baseline

    def _create_paragraph_node(
        self,
        text_setting: TypeSetting,
        x: float,
        y: float,
        line_height: float,
        text_anchor: str | None,
        dominant_baseline: str | None,
        first_paragraph: bool,
        uses_native_positioning: bool,
    ) -> ET.Element:
        """Create paragraph node with positioning attributes.

        All paragraphs use consistent structure: each tspan has explicit
        x/y or dy positioning.

        Args:
            text_setting: Type setting object containing transform information.
            text_node: Parent text element.
            x: Base x position.
            y: Base y position.
            line_height: Line height for dy attribute.
            text_anchor: SVG text-anchor value.
            dominant_baseline: SVG dominant-baseline value.
            first_paragraph: Whether this is the first paragraph.
            uses_native_positioning: Whether native x/y positioning is used.

        Returns:
            New tspan element with appropriate position attributes.
        """
        # Add transform offset if using native positioning
        if uses_native_positioning:
            transform = text_setting.transform
            x += transform.tx
            y += transform.ty

        # Determine if we should set x, y on the tspan
        # All paragraphs get x for consistency (to reset horizontal position)
        # First paragraph gets both x and y
        # Subsequent paragraphs get x and dy (for line spacing)
        if uses_native_positioning:
            should_set_x = True  # Always set x for consistency
            should_set_y = first_paragraph  # Only first paragraph gets y
        else:
            # Using transform positioning
            should_set_x = x != 0.0 or not first_paragraph
            should_set_y = y != 0.0 and first_paragraph

        # Create paragraph node with positioning and baseline attributes.
        # The dominant-baseline="hanging" provides the closest match to Photoshop's
        # bounding box text positioning, though subtle differences may remain due to
        # font rendering variations between Photoshop and browsers.
        return self.create_node(
            "tspan",
            text_anchor=text_anchor,
            x=x if should_set_x else None,
            y=y if should_set_y else None,
            dy=line_height if not first_paragraph else None,
            dominant_baseline=dominant_baseline,
        )

    def _apply_justification(
        self,
        paragraph: Paragraph,
        paragraph_node: ET.Element,
        text_setting: TypeSetting,
    ) -> None:
        """Apply justification settings to paragraph node.

        Args:
            paragraph: Paragraph object containing justification settings.
            paragraph_node: SVG tspan element to apply justification to.
            text_setting: Type setting object containing bounds information.
        """
        if paragraph.justification == Justification.JUSTIFY_ALL:
            logger.info("Justify All is not fully supported in SVG.")
            svg_utils.set_attribute(
                paragraph_node,
                "textLength",
                text_setting.bounds.width,
            )
            svg_utils.set_attribute(paragraph_node, "lengthAdjust", "spacingAndGlyphs")

    def _add_text_span(
        self, text_setting: TypeSetting, paragraph_node: ET.Element, span: Span
    ) -> ET.Element:
        """Add a text span to the paragraph node."""
        style = span.style
        # Get PostScript name from font index - no font resolution needed
        postscript_name = text_setting.get_postscript_name(style.font)

        # Handle horizontal and vertical scaling
        scaled_font_size, transform_scale = self._calculate_text_scaling(
            style.font_size,
            style.horizontal_scale,
            style.vertical_scale,
        )

        # Determine font weight - only set for faux bold
        # (PostScript name encodes actual weight)
        font_weight: int | str | None = None
        if style.faux_bold:
            font_weight = "700"

        with self.set_current(paragraph_node):
            tspan = self.create_node(
                "tspan",
                text=span.text.strip("\r"),  # Remove carriage return characters
                font_size=scaled_font_size,
                font_family=postscript_name,  # Store PostScript name directly
                font_weight=font_weight,
                font_style="italic"
                if style.faux_italic
                else None,  # Only for faux italic
                fill=style.get_fill_color(),
                stroke=style.get_stroke_color(),
                baseline_shift=style.baseline_shift
                if style.baseline_shift != 0.0
                else None,
            )
        if style.font_caps == FontCaps.ALL_CAPS:
            svg_utils.add_style(tspan, "text-transform", "uppercase")
        elif style.font_caps == FontCaps.SMALL_CAPS:
            # NOTE: Using text_settings.small_caps_size with text-transform
            # may be more accurate.
            svg_utils.set_attribute(tspan, "font-variant", "small-caps")

        if style.underline:
            svg_utils.append_attribute(tspan, "text-decoration", "underline")
        if style.strikethrough:
            svg_utils.append_attribute(tspan, "text-decoration", "line-through")

        # Apply ligature settings using font-variant-ligatures
        # Photoshop defaults to ligatures=True (common ligatures enabled)
        # CSS default behavior is 'normal' which enables common ligatures
        # Only set font-variant-ligatures when it differs from the default
        if not style.ligatures and not style.discretionary_ligatures:
            # Both disabled -> none
            svg_utils.add_style(tspan, "font-variant-ligatures", "none")
        elif style.ligatures and not style.discretionary_ligatures:
            # Only common ligatures enabled (Photoshop default, CSS default)
            # Skip setting attribute - this is the default CSS behavior
            pass
        elif not style.ligatures and style.discretionary_ligatures:
            # Only discretionary ligatures enabled (uncommon case)
            svg_utils.add_style(
                tspan, "font-variant-ligatures", "discretionary-ligatures"
            )
        else:
            # Both enabled
            svg_utils.add_style(
                tspan,
                "font-variant-ligatures",
                "common-ligatures discretionary-ligatures",
            )

        # NOTE: Photoshop uses different values for subscript position/size.
        # Using baseline-shift with sub or super will result in inaccurate rendering.
        if style.font_baseline == FontBaseline.SUPERSCRIPT:
            svg_utils.set_attribute(
                tspan,
                "baseline-shift",
                scaled_font_size * text_setting.superscript_position,
            )
            svg_utils.set_attribute(
                tspan, "font-size", scaled_font_size * text_setting.superscript_size
            )
        elif style.font_baseline == FontBaseline.SUBSCRIPT:
            svg_utils.set_attribute(
                tspan,
                "baseline-shift",
                -scaled_font_size * text_setting.subscript_position,
            )
            svg_utils.set_attribute(
                tspan, "font-size", scaled_font_size * text_setting.subscript_size
            )

        # Apply letter spacing from tracking, tsume, and optional global offset
        # NOTE: Tracking is in 1/1000 em units.
        # NOTE: Tsume is a percentage (0-1) that reduces spacing
        # by that amount of font size.
        # NOTE: It seems Photoshop applies 1/10 of the tsume value
        # to letter spacing.
        # NOTE: There is a slight offset difference for the first charactor because
        # letter-spacing applies after the character.
        letter_spacing = style.tracking / 1000 * scaled_font_size
        letter_spacing -= style.tsume / 10 * scaled_font_size  # Tsume tightens spacing
        letter_spacing += self.text_letter_spacing_offset

        # Only set letter-spacing if non-zero (or if offset makes it non-zero)
        if letter_spacing != 0:
            svg_utils.set_attribute(
                tspan,
                "letter-spacing",
                letter_spacing,
            )

        # Apply kerning adjustment (manual kerning in 1/1000 em units)
        # Kerning adjusts the spacing BEFORE the current character
        # (between previous and current).
        # We use dx/dy to shift the character position, which effectively
        # adjusts the space before it.
        # NOTE: letter-spacing adds space AFTER characters,
        # so we can't use it for kerning.
        if style.kerning != 0:
            kerning_offset = style.kerning / 1000 * scaled_font_size
            # Use dx for horizontal text, dy for vertical text
            if text_setting.writing_direction == WritingDirection.HORIZONTAL_TB:
                svg_utils.set_attribute(tspan, "dx", kerning_offset)
            elif text_setting.writing_direction == WritingDirection.VERTICAL_RL:
                svg_utils.set_attribute(tspan, "dy", kerning_offset)

        # Apply non-uniform scale transform if needed
        # (Uniform scaling is already handled via scaled_font_size above)
        if transform_scale is not None:
            logger.warning(
                "Non-uniform text scaling (different horizontal and vertical scale) "
                "on spans is not supported by browsers. Scaled text will not render "
                "correctly. Consider using enable_text=False to rasterize text layers."
            )

            svg_utils.append_attribute(
                tspan,
                "transform",
                f"scale({svg_utils.num2str(transform_scale[0])},{svg_utils.num2str(transform_scale[1])})",
            )

            # Set transform-origin to the paragraph's position
            # to prevent scale from shifting the text
            # Get x and y from parent paragraph node
            parent_x = paragraph_node.attrib.get("x")
            parent_y = paragraph_node.attrib.get("y")
            if parent_x is not None and parent_y is not None:
                svg_utils.set_attribute(
                    tspan,
                    "transform-origin",
                    f"{parent_x} {parent_y}",
                )

        if (
            text_setting.writing_direction == WritingDirection.VERTICAL_RL
            and style.baseline_direction == 1
        ):
            # NOTE: Only Chromium-based browsers support
            # 'text-orientation: upright' for SVG.
            logger.debug(
                "Applying text-orientation: upright, but may not be supported "
                "in SVG renderers."
            )
            svg_utils.add_style(tspan, "text-orientation", "upright")
            # NOTE: glyph-orientation-vertical is deprecated but may help
            # with compatibility.
            # svg_utils.set_attribute(tspan, "glyph-orientation-vertical", "90")
        return tspan

    def _calculate_text_scaling(
        self,
        font_size: float,
        horizontal_scale: float,
        vertical_scale: float,
    ) -> tuple[float, tuple[float, float] | None]:
        """Calculate font-size scaling for text spans.

        Handles uniform and non-uniform text scaling with browser compatibility
        workarounds. For uniform scaling, scales font-size directly
        (browser-compatible). For non-uniform scaling, uses transform
        (still broken in browsers, but more consistent).

        Args:
            font_size: Base font size in pixels
            horizontal_scale: Horizontal scale factor (default 1.0)
            vertical_scale: Vertical scale factor (default 1.0)

        Returns:
            Tuple of (scaled_font_size, transform_scale):
            - scaled_font_size: Font size after applying scaling
            - transform_scale: (sx, sy) tuple for transform attribute,
              or None if not needed
        """
        SCALE_TOLERANCE = 1e-6  # Consistent with Transform.is_translation_only()
        has_scaling = vertical_scale != 1.0 or horizontal_scale != 1.0
        is_uniform_scale = abs(vertical_scale - horizontal_scale) < SCALE_TOLERANCE

        # Validate scale values and determine approach
        if has_scaling and (vertical_scale <= 0 or horizontal_scale <= 0):
            logger.warning(
                f"Invalid scale values: horizontal={horizontal_scale}, "
                f"vertical={vertical_scale}. Using original font-size."
            )
            scaled_font_size = font_size
            transform_scale = None
        elif has_scaling and is_uniform_scale:
            # Uniform scaling: scale font-size directly (browser-compatible)
            scale = horizontal_scale  # Could use vertical_scale, they're equal
            scaled_font_size = font_size * scale
            transform_scale = None  # No transform needed
        elif has_scaling:
            # Non-uniform scaling: scale by vertical, adjust horizontal with transform
            scaled_font_size = font_size * vertical_scale
            # Transform adjusts horizontal to match
            transform_scale = (horizontal_scale / vertical_scale, 1.0)
        else:
            # No scaling
            scaled_font_size = font_size
            transform_scale = None

        return scaled_font_size, transform_scale

    def _get_foreign_object_container_styles(
        self, text_setting: TypeSetting, bounds: Rectangle
    ) -> dict[str, str]:
        """Get CSS styles for foreignObject container div.

        Args:
            text_setting: TypeSetting object with writing direction.
            bounds: Bounding box dimensions.

        Returns:
            Dictionary of CSS property names to values.
        """
        styles = {
            "width": svg_utils.num2str_with_unit(bounds.width),
            "height": svg_utils.num2str_with_unit(bounds.height),
            "margin": "0",
            "padding": "0",
            "overflow": "hidden",  # Match Photoshop clipping behavior
            # Ensure padding (from paragraph indents) is included in width/height,
            # not added to it, matching Photoshop's bounding box behavior
            "box-sizing": "border-box",
        }

        if text_setting.writing_direction == WritingDirection.VERTICAL_RL:
            styles["writing-mode"] = "vertical-rl"

        return styles

    def _add_foreign_object_paragraph(
        self,
        container: ET.Element,
        paragraph: Paragraph,
        text_setting: TypeSetting,
    ) -> None:
        """Add a paragraph as XHTML <p> element.

        Args:
            container: Parent XHTML div element.
            paragraph: Paragraph object containing style and spans.
            text_setting: TypeSetting object for font info lookup.
        """
        # Get paragraph CSS styles
        p_styles = self._get_foreign_object_paragraph_styles(paragraph)

        # Check if any span in this paragraph needs whitespace preservation
        needs_preserve = any(
            _needs_whitespace_preservation(span.text) for span in paragraph
        )

        # Create <p> element
        p_elem = svg_utils.create_xhtml_node(
            "p",
            parent=container,
            xml_space="preserve" if needs_preserve else None,
            style=svg_utils.styles_to_string(p_styles),
        )

        # Add spans
        for span in paragraph:
            self._add_foreign_object_span(p_elem, span, text_setting, paragraph)

    def _get_foreign_object_paragraph_styles(
        self, paragraph: Paragraph
    ) -> dict[str, str]:
        """Convert paragraph settings to CSS styles.

        Supports paragraph formatting properties:
        - Text alignment (justification)
        - Line height (leading)
        - First line indent
        - Start/end indent (left/right padding)
        - Space before/after (top/bottom margins)
        - Hanging punctuation (limited browser support)

        Args:
            paragraph: Paragraph object containing style and formatting.

        Returns:
            Dictionary of CSS property names to values.
        """
        styles = {
            "margin": "0",
            "padding": "0",
        }

        # Text alignment mapping
        # Note: CSS text-align: justify works correctly with display: inline-block
        # spans because the text content inside spans can still wrap and justify.
        # However, CSS lacks direct support for Photoshop's justify variants:
        # - JUSTIFY_LAST_LEFT/RIGHT/CENTER: justify all lines except last
        # - JUSTIFY_ALL: justify all lines including last
        # CSS text-align-last could provide this, but browser support varies.
        # For now, all justify modes map to 'justify' (equivalent to JUSTIFY_LAST_LEFT).
        justification_map = {
            Justification.LEFT: "left",
            Justification.RIGHT: "right",
            Justification.CENTER: "center",
            Justification.JUSTIFY_LAST_LEFT: "justify",
            Justification.JUSTIFY_LAST_RIGHT: "justify",  # Approximation
            Justification.JUSTIFY_LAST_CENTER: "justify",  # Approximation
            Justification.JUSTIFY_ALL: "justify",  # Approximation
        }
        text_align = justification_map.get(paragraph.justification, "left")
        if text_align != "left":  # Skip default
            styles["text-align"] = text_align

        # Line height and margin-top compensation calculation
        leading = paragraph.compute_leading()
        margin_top_compensation = 0.0  # Track compensation for later use

        if leading > 0:
            styles["line-height"] = svg_utils.num2str_with_unit(leading)

            # Calculate half-leading compensation for all paragraphs
            # CSS line-height centers text within a line box, adding unwanted space
            # above each line. We calculate the negative margin as:
            # margin-top = -(leading - font_size) / 2
            # This removes the half-leading space above each paragraph.
            if paragraph.spans:
                # Get font size from the first span
                first_span = paragraph.spans[0]
                font_size = first_span.style.font_size
                if leading > font_size:
                    # Calculate half-leading compensation
                    margin_top_compensation = -(leading - font_size) / 2

        # First line indent
        if paragraph.style.first_line_indent != 0:
            styles["text-indent"] = svg_utils.num2str_with_unit(
                paragraph.style.first_line_indent
            )

        # Start indent (left padding) - overrides padding: 0
        if paragraph.style.start_indent != 0:
            styles["padding-left"] = svg_utils.num2str_with_unit(
                paragraph.style.start_indent
            )

        # End indent (right padding) - overrides padding: 0
        if paragraph.style.end_indent != 0:
            styles["padding-right"] = svg_utils.num2str_with_unit(
                paragraph.style.end_indent
            )

        # Space before paragraph - combine with line-height compensation
        # If we have both space_before and compensation, add them together
        total_margin_top = paragraph.style.space_before + margin_top_compensation
        # Only add margin-top if it exceeds the negligible threshold
        if abs(total_margin_top) > NEGLIGIBLE_MARGIN_THRESHOLD:
            styles["margin-top"] = svg_utils.num2str_with_unit(total_margin_top)

        # Space after paragraph - overrides margin: 0
        if paragraph.style.space_after != 0:
            styles["margin-bottom"] = svg_utils.num2str_with_unit(
                paragraph.style.space_after
            )

        # Hanging punctuation (limited browser support - Safari only as of 2025)
        # Note: Chrome, Firefox, and Edge do not support this CSS property.
        # We include it for future compatibility and Safari users.
        if paragraph.style.hanging:
            styles["hanging-punctuation"] = "first last"

        # Hyphenation
        # Map PSD AutoHyphenate property to CSS hyphens property.
        # CSS hyphens: auto requires the lang attribute to work properly.
        if paragraph.style.auto_hyphenate:
            styles["hyphens"] = "auto"

            # Map hyphenation parameters to CSS hyphenate-limit-chars
            # Format: hyphenate-limit-chars: <word-min> <char-before> <char-after>
            # Browser support: Firefox 43+, Safari 17+, not supported in Chrome
            word_min = paragraph.style.hyphenation_word_size
            char_before = paragraph.style.pre_hyphen
            char_after = paragraph.style.post_hyphen
            styles["hyphenate-limit-chars"] = (
                f"{svg_utils.num2str(word_min)} "
                f"{svg_utils.num2str(char_before)} "
                f"{svg_utils.num2str(char_after)}"
            )

        return styles

    def _add_foreign_object_span(
        self,
        p_elem: ET.Element,
        span: Span,
        text_setting: TypeSetting,
        paragraph: Paragraph,
    ) -> None:
        """Add a text span as XHTML <span> element.

        Args:
            p_elem: Parent XHTML <p> element.
            span: Span object containing text and style.
            text_setting: TypeSetting object for font info lookup.
            paragraph: Parent paragraph object for accessing line-height.
        """
        # Get span CSS styles
        span_styles = self._get_foreign_object_span_styles(
            span, text_setting, paragraph
        )

        # Create <span> element
        # If no styles needed, add text directly to paragraph
        if not span_styles:
            # Append text to parent
            if len(p_elem) > 0:
                # Has children, append to last child's tail
                if p_elem[-1].tail:
                    p_elem[-1].tail += span.text.strip("\r")
                else:
                    p_elem[-1].tail = span.text.strip("\r")
            else:
                # No children, append to parent text
                if p_elem.text:
                    p_elem.text += span.text.strip("\r")
                else:
                    p_elem.text = span.text.strip("\r")
        else:
            svg_utils.create_xhtml_node(
                "span",
                parent=p_elem,
                text=span.text.strip("\r"),
                style=svg_utils.styles_to_string(span_styles),
            )

    def _get_foreign_object_span_styles(
        self, span: Span, text_setting: TypeSetting, paragraph: Paragraph
    ) -> dict[str, str]:
        """Convert span style settings to CSS styles.

        Args:
            span: Span object containing text style information.
            text_setting: TypeSetting object for font info and calculations.
            paragraph: Parent paragraph object for accessing line-height.

        Returns:
            Dictionary of CSS property names to values.
        """
        style = span.style
        # Get PostScript name from font index - no font resolution needed
        postscript_name = text_setting.get_postscript_name(style.font)

        styles = {}

        # Set display: inline-block and line-height to prevent inline box from
        # expanding parent line height (CSS inline formatting issue).
        # This ensures the paragraph's line-height is respected even when
        # span font-size > line-height. See GitHub issue #273.
        styles["display"] = "inline-block"
        leading = paragraph.compute_leading()
        if leading > 0:
            styles["line-height"] = svg_utils.num2str_with_unit(leading)

        # Font family - use PostScript name directly
        if postscript_name:
            styles["font-family"] = f"'{postscript_name}'"

        # Font size
        if style.font_size:
            styles["font-size"] = svg_utils.num2str_with_unit(style.font_size)

        # Font weight - only set for faux bold (PostScript name encodes actual weight)
        if style.faux_bold:
            styles["font-weight"] = "700"

        # Font style - only set for faux italic (PostScript name encodes actual style)
        if style.faux_italic:
            styles["font-style"] = "italic"

        # Color
        fill_color = style.get_fill_color()
        if fill_color and fill_color != "none":
            styles["color"] = fill_color

        # Text decoration
        decorations = []
        if style.underline:
            decorations.append("underline")
        if style.strikethrough:
            decorations.append("line-through")
        if decorations:
            styles["text-decoration"] = " ".join(decorations)

        # Text transform
        if style.font_caps == FontCaps.ALL_CAPS:
            styles["text-transform"] = "uppercase"
        elif style.font_caps == FontCaps.SMALL_CAPS:
            styles["font-variant"] = "small-caps"

        # Letter spacing
        letter_spacing = style.tracking / 1000 * style.font_size
        letter_spacing += self.text_letter_spacing_offset
        if letter_spacing != 0:
            styles["letter-spacing"] = svg_utils.num2str_with_unit(letter_spacing)

        # Vertical alignment (superscript/subscript)
        if style.font_baseline == FontBaseline.SUPERSCRIPT:
            styles["vertical-align"] = "super"
            styles["font-size"] = svg_utils.num2str_with_unit(
                style.font_size * text_setting.superscript_size
            )
        elif style.font_baseline == FontBaseline.SUBSCRIPT:
            styles["vertical-align"] = "sub"
            styles["font-size"] = svg_utils.num2str_with_unit(
                style.font_size * text_setting.subscript_size
            )
        elif style.baseline_shift != 0.0:
            # Custom baseline shift
            styles["vertical-align"] = svg_utils.num2str_with_unit(style.baseline_shift)

        # Horizontal/vertical scale
        if style.vertical_scale != 1.0 or style.horizontal_scale != 1.0:
            styles["transform"] = (
                f"scale({svg_utils.num2str(style.horizontal_scale)}, "
                f"{svg_utils.num2str(style.vertical_scale)})"
            )
            # Note: display: inline-block already set above for all spans
            styles["transform-origin"] = "center"

        # Stroke (text outline) - CSS supports this with -webkit-text-stroke
        stroke_color = style.get_stroke_color()
        if stroke_color and stroke_color != "none":
            # Note: This is a webkit-specific property but widely supported
            styles["-webkit-text-stroke"] = f"1px {stroke_color}"

        return styles


# Backward compatibility re-exports
__all__ = [
    "TextConverter",
    "TextWrappingMode",  # Re-exported from typesetting
    "TypeSetting",  # Re-exported from typesetting
]
