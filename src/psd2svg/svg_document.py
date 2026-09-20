import dataclasses
import logging
import os
import xml.etree.ElementTree as ET
from copy import deepcopy

from PIL import Image
from psd_tools import PSDImage

from psd2svg import image_utils, svg_utils
from psd2svg.core import font_utils
from psd2svg.core.converter import Converter
from psd2svg.core.font_utils import FontInfo
from psd2svg.rasterizer import BaseRasterizer, ResvgRasterizer
from psd2svg.resource_limits import ResourceLimits
from psd2svg.timeout_utils import with_timeout

logger = logging.getLogger(__name__)

DEFAULT_IMAGE_FORMAT = "webp"


@dataclasses.dataclass
class SVGDocument:
    """SVG document and resources.

    Example usage::

        from psd_tools import PSDImage
        from psd2svg import SVGDocument

        # Create from PSDImage.
        psdimage = PSDImage.open("input.psd")
        document = SVGDocument.from_psd(psdimage)

        # Save to file or get as string.
        document.save("output.svg")  # Images embedded by default
        svg_string = document.tostring()

        # Rasterize to PIL Image.
        rasterized = document.rasterize()

        # Export and load back.
        exported = document.export()
        document = SVGDocument.load(exported["svg"], exported["images"])
    """

    svg: ET.Element
    images: dict[str, Image.Image] = dataclasses.field(default_factory=dict)
    # Note: fonts property removed - PostScript names stored directly in SVG
    # font-family attributes
    _font_data_cache: dict[str, str] = dataclasses.field(
        default_factory=dict, init=False, repr=False
    )

    @staticmethod
    def from_psd(
        psdimage: PSDImage,
        enable_live_shapes: bool = True,
        enable_text: bool = True,
        enable_title: bool = False,
        enable_class: bool = False,
        text_letter_spacing_offset: float = 0.0,
        text_wrapping_mode: int = 0,
        font_mapping: dict[str, dict[str, float | str]] | None = None,
        resource_limits: ResourceLimits | None = None,
    ) -> "SVGDocument":
        """Create a new SVGDocument from a PSDImage.

        Args:
            psdimage: PSDImage object to convert.
            enable_live_shapes: Enable live shape conversion when possible.
                Disabling live shapes results in <path> elements instead of
                shape primitives like <rect> or <circle>. This may be more
                accurate, but less editable.
            enable_text: Enable text layer conversion. If False, text layers
                are rasterized as images.
            enable_title: Enable insertion of <title> elements with layer names.
                When False (default), title elements are omitted to reduce file size.
                Set to True to include <title> elements containing the Photoshop layer
                name for accessibility and debugging.
            enable_class: Enable insertion of class attributes on SVG elements for
                debugging purposes. When False (default), elements will not have class
                attributes, producing cleaner SVG output. Set to True to add class
                attributes for layer types, effects, and semantic roles (e.g.,
                "shape-layer", "drop-shadow-effect", "fill") for debugging or styling.
            text_letter_spacing_offset: Global offset (in pixels) to add to all
                letter-spacing values. This can be used to compensate for differences
                between Photoshop's text rendering and SVG's text rendering. Typical
                values range from -0.02 to 0.02. Default is 0.0 (no offset).
            text_wrapping_mode: Text wrapping mode for bounding box text. Use 0 for no
                wrapping (default, native SVG <text>), or 1 for <foreignObject> with
                XHTML wrapping. Import TextWrappingMode from psd2svg.core.text for
                enum values. Only affects bounding box text (ShapeType=1); point text
                always uses native SVG <text> elements.
            font_mapping: Optional custom font mapping dictionary for resolving
                PostScript font names to font families. Takes priority over built-in
                static mapping. Useful for providing custom fonts or overriding default
                mappings. Format: {"PostScriptName": {"family": str, "style": str,
                "weight": float}}. Example: {"ArialMT": {"family": "Arial",
                "style": "Regular", "weight": 80.0}}.
                When not provided, uses built-in mapping for ~4,950 fonts (539 default +
                370 Hiragino + 4,042 Morisawa), with automatic fallback to system font
                resolution (fontconfig/Windows registry) if needed.
            resource_limits: Optional resource limits for DoS prevention. If None,
                uses ResourceLimits.default() which enables limits (2GB file size,
                3 minute timeout, 100 layer depth, 16K image dimension). Use
                ResourceLimits.unlimited() to disable all limits for trusted input.

        Returns:
            SVGDocument object containing the converted SVG and images.

        Raises:
            ValueError: If layer depth or image dimensions exceed limits.
            TimeoutError: If conversion exceeds timeout limit.
        """
        # Default to ResourceLimits.default() if not specified
        if resource_limits is None:
            resource_limits = ResourceLimits.default()

        # Build SVG tree with original font names
        converter = Converter(
            psdimage,
            enable_live_shapes=enable_live_shapes,
            enable_text=enable_text,
            enable_title=enable_title,
            enable_class=enable_class,
            text_letter_spacing_offset=text_letter_spacing_offset,
            text_wrapping_mode=text_wrapping_mode,
            font_mapping=font_mapping,
            resource_limits=resource_limits,
        )

        # Build with timeout protection
        if resource_limits.is_timeout_enabled():
            with_timeout(converter.build, resource_limits.timeout)
        else:
            converter.build()

        document = SVGDocument(
            svg=converter.svg,
            images=converter.images,
        )

        return document

    def append_css(self, css: str) -> None:
        """Append custom CSS rules to the SVG <style> element.

        This method allows you to inject custom CSS rules into the SVG document.
        The CSS is appended to an existing <style> element if present, or a new
        <style> element is created as the first child of the root SVG element.

        Args:
            css: CSS rules to append. Can be any valid CSS including selectors,
                media queries, keyframes, etc.

        Example:
            >>> from psd_tools import PSDImage
            >>> from psd2svg import SVGDocument
            >>>
            >>> psdimage = PSDImage.open("input.psd")
            >>> svg_doc = SVGDocument.from_psd(psdimage)
            >>>
            >>> # Add custom CSS for Japanese text
            >>> svg_doc.append_css(
            ...     "text { font-variant-east-asian: proportional-width; }"
            ... )
            >>>
            >>> # Add more custom CSS
            >>> svg_doc.append_css("@media print { .no-print { display: none; } }")
            >>>
            >>> svg_doc.save("output.svg")

        Note:
            This method is idempotent - if the same CSS is appended multiple times,
            it will only appear once in the output (duplicate detection).
        """
        svg_utils.insert_or_update_style_element(self.svg, css)

    def _prepare_svg_for_output(
        self,
        embed_images: bool,
        embed_fonts: bool,
        subset_fonts: bool,
        font_format: str,
        image_prefix: str | None,
        image_format: str,
        optimize: bool,
        svg_filepath: str | None,
        use_data_uri_for_fonts: bool = True,
    ) -> ET.Element:
        """Prepare SVG element for output by handling images, fonts, and optimization.

        Args:
            embed_images: If True, embed images as base64 data URIs.
            embed_fonts: If True, embed fonts as @font-face rules in <style> element.
            subset_fonts: If True, subset fonts to only include glyphs used in the SVG.
            font_format: Font format for embedding: "woff2", "woff", "ttf", or "otf".
            image_prefix: If provided, save images to files with this prefix.
            image_format: Image format to use when embedding or saving images.
            optimize: If True, apply SVG optimizations (consolidate defs, etc.).
            svg_filepath: Path to the output SVG file (for save()), or None (for
                tostring()).
            use_data_uri_for_fonts: If True, embed fonts as data URIs. If False, use
                file:// URLs.
                Only applies when embed_fonts=True. Default is True.

        Returns:
            Prepared SVG element ready for serialization.
        """
        # Create a copy to avoid modifying the original SVG
        svg = deepcopy(self.svg)

        svg = self._handle_images(
            svg, embed_images, image_prefix, image_format, svg_filepath=svg_filepath
        )

        # Early split: different font resolution strategies for embed_fonts
        if embed_fonts:
            # Single-pass resolution: platform queries + charset extraction +
            # SVG updates
            resolved_fonts_map = self._resolve_and_collect_fonts(svg)
            self._insert_css_fontface(
                svg,
                subset_fonts=subset_fonts,
                font_format=font_format,
                use_data_uri=use_data_uri_for_fonts,
                resolved_fonts_map=resolved_fonts_map,
            )
        else:
            # Static mapping only: no platform queries, no charset extraction
            self._resolve_postscript_names_static(svg)

        if optimize:
            svg_utils.consolidate_defs(svg)
            svg_utils.deduplicate_definitions(svg)
            svg_utils.unwrap_groups(svg)

        return svg

    def tostring(
        self,
        embed_images: bool = True,
        embed_fonts: bool = False,
        subset_fonts: bool = True,
        font_format: str = "woff2",
        image_prefix: str | None = None,
        image_format: str = DEFAULT_IMAGE_FORMAT,
        indent: str = "  ",
        optimize: bool = True,
    ) -> str:
        """Convert SVG document to string.

        Args:
            embed_images: If True, embed images as base64 data URIs. Default is True
                since string output has no file system context for external images.
            embed_fonts: If True, embed fonts as @font-face rules in <style> element.
                WARNING: Font embedding may be subject to licensing restrictions.
                Ensure you have appropriate rights before distributing SVG files
                with embedded fonts.
            subset_fonts: If True, subset fonts to only include glyphs used in
                the SVG. Requires embed_fonts=True. This significantly reduces file
                size (typically 90%+ reduction). Default is True.
            font_format: Font format for embedding: "woff2" (default), "woff",
                "ttf", or "otf".
                WOFF2 provides best compression and is recommended for web use.
            image_prefix: If provided, save images to files with this prefix.
                When specified, embed_images is ignored.
            image_format: Image format to use when embedding or saving images.
            indent: Indentation string for pretty-printing the SVG.
            optimize: If True, apply SVG optimizations (consolidate defs, etc.).
                Default is True.
        """
        svg = self._prepare_svg_for_output(
            embed_images=embed_images,
            embed_fonts=embed_fonts,
            subset_fonts=subset_fonts,
            font_format=font_format,
            image_prefix=image_prefix,
            image_format=image_format,
            optimize=optimize,
            svg_filepath=None,
        )
        return svg_utils.tostring(svg, indent=indent)

    def save(
        self,
        filepath: str,
        embed_images: bool = True,
        embed_fonts: bool = False,
        subset_fonts: bool = True,
        font_format: str = "woff2",
        image_prefix: str | None = None,
        image_format: str = DEFAULT_IMAGE_FORMAT,
        indent: str = "  ",
        optimize: bool = True,
    ) -> None:
        """Save the SVG to a file.

        Args:
            filepath: Path to the output SVG file.
            embed_images: If True, embed images as base64 data URIs. Default is True.
                Set to False and provide image_prefix to save images as external files.
            embed_fonts: If True, embed fonts as @font-face rules in <style> element.
                WARNING: Font embedding may be subject to licensing restrictions.
                Ensure you have appropriate rights before distributing SVG files
                with embedded fonts.
            subset_fonts: If True, subset fonts to only include glyphs used in
                the SVG. Requires embed_fonts=True. This significantly reduces file
                size (typically 90%+ reduction). Default is True.
            font_format: Font format for embedding: "woff2" (default), "woff",
                "ttf", or "otf".
                WOFF2 provides best compression and is recommended for web use.
            image_prefix: If provided, save images to files with this prefix
                relative to the output SVG file's directory.
            image_format: Image format to use when embedding or saving images.
            indent: Indentation string for pretty-printing the SVG.
            optimize: If True, apply SVG optimizations (consolidate defs, etc.).
                Default is True.
        """
        svg = self._prepare_svg_for_output(
            embed_images=embed_images,
            embed_fonts=embed_fonts,
            subset_fonts=subset_fonts,
            font_format=font_format,
            image_prefix=image_prefix,
            image_format=image_format,
            optimize=optimize,
            svg_filepath=filepath,
        )
        with open(filepath, "w", encoding="utf-8") as f:
            svg_utils.write(svg, f, indent=indent)

    def rasterize(
        self, dpi: int = 0, rasterizer: BaseRasterizer | None = None
    ) -> Image.Image:
        """Rasterize the SVG document to PIL Image.

        Args:
            dpi: Dots per inch for rendering. If 0 (default), uses the
                rasterizer's default (96 DPI for ResvgRasterizer). Higher values
                produce larger, higher resolution images (e.g., 300 DPI for print
                quality). Only used if rasterizer is None.
            rasterizer: Optional custom rasterizer instance. If None, uses
                ResvgRasterizer with the specified dpi. Use this to specify
                alternative rasterizers like PlaywrightRasterizer for better
                SVG 2.0 feature support.

        Returns:
            PIL Image object in RGBA mode containing the rasterized SVG.

        Note:
            When using PlaywrightRasterizer, fonts are automatically embedded
            using local file:// URLs for optimal performance (60-80% faster
            than data URIs, 99% smaller SVG strings).

        Example:
            >>> # Default resvg rasterization
            >>> image = document.rasterize()

            >>> # High DPI rasterization
            >>> image = document.rasterize(dpi=300)

            >>> # Browser-based rasterization (fonts auto-embedded with file URLs)
            >>> from psd2svg.rasterizer import PlaywrightRasterizer
            >>> browser_rasterizer = PlaywrightRasterizer(dpi=96)
            >>> image = document.rasterize(rasterizer=browser_rasterizer)
        """
        if rasterizer is None:
            rasterizer = ResvgRasterizer(dpi=dpi)

        # Unified path: Prepare SVG with fonts embedded as file:// URLs
        # This allows both PlaywrightRasterizer and ResvgRasterizer to handle
        # fonts appropriately. ResvgRasterizer will extract font paths from
        # the @font-face CSS rules and pass them via its font_files API.
        svg = self._prepare_svg_for_output(
            embed_images=True,
            embed_fonts=True,
            subset_fonts=False,  # No subsetting for file URLs (faster)
            font_format="ttf",  # Not used for file URLs
            image_prefix=None,
            image_format=DEFAULT_IMAGE_FORMAT,
            optimize=False,  # No optimization needed for rasterization
            svg_filepath=None,
            use_data_uri_for_fonts=False,  # Use file:// URLs for better performance
        )
        svg_str = svg_utils.tostring(svg, indent="")
        return rasterizer.from_string(svg_str)

    def export(
        self,
        image_format: str = DEFAULT_IMAGE_FORMAT,
        indent: str = "  ",
    ) -> dict[str, str | dict[str, bytes]]:
        """Export the SVG document in a serializable format.

        Note: Font information is now embedded in SVG font-family attributes,
        so no separate fonts list is exported.
        """
        return {
            "svg": svg_utils.tostring(self.svg, indent=indent),
            "images": {
                image_id: image_utils.encode_image(image, image_format)
                for image_id, image in self.images.items()
            },
        }

    @classmethod
    def load(
        cls,
        svg: str,
        images: dict[str, bytes],
    ) -> "SVGDocument":
        """Load an SVGDocument from SVG content and image bytes.

        Args:
            svg: SVG content as a string.
            images: Dictionary mapping image IDs to image bytes.

        Note:
            Font information is stored in SVG font-family attributes, not
            as a separate parameter.
        """
        svg_node = ET.fromstring(svg)
        images_dict = {
            image_id: image_utils.decode_image(img_bytes)
            for image_id, img_bytes in images.items()
        }
        return SVGDocument(svg=svg_node, images=images_dict)

    def _handle_images(
        self,
        svg: ET.Element,
        embed_images: bool,
        image_prefix: str | None,
        image_format: str,
        svg_filepath: str | None = None,
    ) -> ET.Element:
        """Handle image embedding or saving.

        Modifies the provided SVG element in-place by updating <image> element
        href attributes to either data URIs or file paths.

        Args:
            svg: SVG element to modify in-place.
            embed_images: If True, embed images as base64 data URIs.
            image_prefix: Path prefix for saving images. If svg_filepath is provided,
                this is interpreted relative to the SVG file's directory.
            image_format: Image format to use when embedding or saving images.
            svg_filepath: Optional path to the SVG file. When provided, image_prefix
                is interpreted relative to this file's directory.

        Returns:
            The modified SVG element (same object as input).
        """
        nodes = svg.findall(".//image")

        # Validate that all image nodes have IDs and corresponding images exist
        for node in nodes:
            image_id = node.get("id")
            if image_id is None:
                raise RuntimeError(
                    f"<image> element missing required 'id' attribute: "
                    f"{ET.tostring(node, encoding='unicode')}"
                )
            if image_id not in self.images:
                raise RuntimeError(
                    f"No image found for <image> element with id='{image_id}'"
                )

        # Handle image resources (skip if no images).
        if len(nodes) == 0:
            return svg

        # image_prefix takes precedence over embed_images (as documented)
        if image_prefix is not None:
            self._save_images_to_files(nodes, image_prefix, image_format, svg_filepath)
        elif embed_images:
            self._embed_images_as_data_uris(nodes, image_format)
        else:
            raise ValueError(
                "Either embed_images must be True or image_prefix must be provided "
                "when the document contains images."
            )

        return svg

    def _embed_images_as_data_uris(
        self, nodes: list[ET.Element], image_format: str
    ) -> None:
        """Embed images as base64 data URIs in image nodes.

        Args:
            nodes: List of <image> elements to update.
            image_format: Image format to use for encoding.
        """
        for node in nodes:
            image_id = node.get("id")
            if image_id is None:
                raise RuntimeError("<image> element missing required 'id' attribute")
            if image_id not in self.images:
                raise RuntimeError(
                    f"No image found for <image> element with id='{image_id}'"
                )
            image = self.images[image_id]
            data_uri = image_utils.encode_data_uri(image, image_format)
            node.set("href", data_uri)

    def _save_images_to_files(
        self,
        nodes: list[ET.Element],
        image_prefix: str,
        image_format: str,
        svg_filepath: str | None,
    ) -> None:
        """Save images to files and update image nodes with file paths.

        Args:
            nodes: List of <image> elements to update.
            image_prefix: Path prefix for saving images.
            image_format: Image format to use for saving.
            svg_filepath: Optional path to the SVG file for relative path calculation.
        """
        # Determine base directory and filename prefix
        base_dir, prefix = self._resolve_image_output_paths(image_prefix, svg_filepath)

        # Create directory if needed
        if base_dir and not os.path.exists(base_dir):
            logger.debug("Creating directory: %s", base_dir)
            os.makedirs(base_dir)

        # Save each image and update node href
        for i, node in enumerate(nodes, start=1):
            image_id = node.get("id")
            if image_id is None:
                raise RuntimeError("<image> element missing required 'id' attribute")
            if image_id not in self.images:
                raise RuntimeError(
                    f"No image found for <image> element with id='{image_id}'"
                )

            image = self.images[image_id]
            filename = "{}{:02d}.{}".format(prefix, i, image_format.lower())
            filepath = os.path.join(base_dir, filename)

            # Save image (with JPEG conversion if needed)
            image_utils.save_image(image, filepath, image_format)

            # Set href: if svg_filepath provided, use relative path; otherwise
            # use filename
            if svg_filepath:
                svg_dir = os.path.dirname(os.path.abspath(svg_filepath))
                href = os.path.relpath(filepath, svg_dir)
            else:
                href = filename
            node.set("href", href)

    def _resolve_image_output_paths(
        self, image_prefix: str, svg_filepath: str | None
    ) -> tuple[str, str]:
        """Resolve base directory and filename prefix for image output.

        Args:
            image_prefix: Path prefix for saving images.
            svg_filepath: Optional path to the SVG file for relative path calculation.

        Returns:
            Tuple of (base_dir, filename_prefix).

        Raises:
            ValueError: If image_prefix contains path traversal sequences or
                is an absolute path when svg_filepath is not provided.

        Note:
            Special handling for "." prefix - treats it as "no prefix, just counter".
        """
        # Validate image_prefix to prevent path traversal attacks
        if ".." in image_prefix:
            raise ValueError(
                "image_prefix cannot contain '..' (path traversal not allowed)"
            )

        # Prevent absolute paths when svg_filepath is not provided (tostring case)
        if os.path.isabs(image_prefix) and svg_filepath is None:
            raise ValueError(
                "image_prefix must be relative when svg_filepath is not provided"
            )
        if svg_filepath:
            svg_dir = os.path.dirname(os.path.abspath(svg_filepath))
            # Special handling for "." - treat as "no prefix, just counter"
            if image_prefix == ".":
                return svg_dir, ""
            else:
                # image_prefix is relative to SVG file's directory
                base_dir = os.path.join(svg_dir, os.path.dirname(image_prefix))
                prefix = os.path.basename(image_prefix)
                return base_dir, prefix
        else:
            # No svg_filepath provided (tostring() case)
            # Special handling for "." - treat as "no prefix, just counter"
            if image_prefix == ".":
                return os.getcwd(), ""
            else:
                base_dir = os.path.dirname(image_prefix) or os.getcwd()
                prefix = os.path.basename(image_prefix)
                return base_dir, prefix

    def _extract_font_elements_and_charset(
        self, svg: ET.Element, font_name: str
    ) -> tuple[list[ET.Element], set[int]]:
        """Extract elements using a font and their charset codepoints.

        Args:
            svg: SVG element to search.
            font_name: Font family or PostScript name to search for.

        Returns:
            Tuple of (matching_elements, charset_codepoints).
            Returns ([], set()) if no elements found.
            Returns (elements, set()) if elements found but no characters extracted.
        """
        # Step 1: Find elements using this font
        matching_elements = svg_utils.find_elements_with_font_family(svg, font_name)
        if not matching_elements:
            return [], set()

        # Step 2: Extract characters from these elements
        chars_for_font: set[str] = set()
        for element in matching_elements:
            text_content = svg_utils.extract_text_characters(element)
            if text_content:
                chars_for_font.update(text_content)

        # Step 3: Convert to codepoints
        charset_codepoints = font_utils.create_charset_codepoints(chars_for_font)
        if charset_codepoints:
            logger.debug(
                f"Extracted {len(chars_for_font)} characters "
                f"({len(charset_codepoints)} codepoints) for font '{font_name}'"
            )

        return matching_elements, charset_codepoints

    @staticmethod
    def _update_element_font_attributes(
        element: ET.Element, resolved_font: FontInfo
    ) -> None:
        """Update font attributes on an SVG element based on resolved font info.

        Args:
            element: SVG element to update (text, tspan, etc.)
            resolved_font: Resolved font information with family, weight, and style.

        Note:
            Only sets font-weight if not 400 (Regular, CSS default).
            Only sets font-style if italic.
        """
        # The face's own weight always wins: faux bold is an outline thickening
        # emitted as a stroke in core/text.py, not a font-weight (issue #337).
        # A Regular face needs no attribute, but any weight already on the
        # element has to go, or it would outlive the face it contradicts.
        css_weight = resolved_font.css_weight
        if css_weight != 400:
            svg_utils.set_attribute(element, "font-weight", css_weight)
        else:
            element.attrib.pop("font-weight", None)

        # Set font-style if italic
        # Note: faux italic already set font-style="italic" in core/text.py,
        # so this only adds it for faces that are themselves italic.
        if resolved_font.italic:
            svg_utils.set_attribute(element, "font-style", "italic")

    def _resolve_postscript_names_static(self, svg: ET.Element) -> None:
        """Resolve PostScript names using static mapping only (no platform queries).

        Used when embed_fonts=False. This lightweight method only resolves PostScript
        names to CSS family names without accessing system fonts or extracting charset.
        Fonts not in the static mapping will preserve their PostScript names.

        Args:
            svg: SVG element to search for font usage and update with family names.

        Note:
            - Does NOT extract charset (performance optimization)
            - Does NOT query platform fonts (prevents unwanted substitution)
            - Updates font-family, font-weight, and font-style attributes
            - Returns nothing (no resolved_fonts_map needed)
        """
        # Get all unique PostScript names used in SVG. extract_font_families()
        # returns a set, so sort it to keep the traversal order stable.
        postscript_names = sorted(svg_utils.extract_font_families(svg))

        for ps_name in postscript_names:
            # Resolve using static mapping only (no platform queries)
            resolved_font = FontInfo.lookup_static(ps_name)

            if resolved_font is None:
                # Font not in static mapping - keep PostScript name
                logger.debug(
                    f"Font '{ps_name}' not in static mapping. "
                    "Preserving PostScript name in SVG."
                )
                continue

            # Get family name
            family_name = resolved_font.family

            # Find all elements with this PostScript name (direct declarations only)
            elements_with_font = svg_utils.find_elements_with_font_family(
                svg, ps_name, include_inherited=False
            )

            if not elements_with_font:
                # This shouldn't happen since extract_font_families() found it
                logger.warning(
                    f"Font '{ps_name}' was extracted from SVG tree but no elements "
                    "found with this font-family. This indicates an inconsistency."
                )
                continue

            # Log resolution
            if family_name != ps_name:
                logger.debug(f"Font resolution: '{ps_name}' → '{family_name}'")

            # Update all elements with this font
            for element in elements_with_font:
                # Replace PostScript name with CSS family name
                if family_name != ps_name:
                    svg_utils.replace_font_family(element, ps_name, family_name)

                # Set weight and style attributes
                self._update_element_font_attributes(element, resolved_font)

    def _resolve_and_collect_fonts(self, svg: ET.Element) -> dict[str, FontInfo]:
        """Resolve PostScript names to system fonts and collect for embedding.

        Performs single-pass resolution:
        1. Extract PostScript names from SVG
        2. Resolve each to system font with charset (single fontconfig/Windows call)
        3. Update SVG with CSS family names
        4. Return resolved fonts keyed by file path

        This unified method combines font resolution and SVG updates in one pass,
        eliminating the need for separate resolution and collection phases.

        Args:
            svg: SVG element to search for font usage and update with family names
                and weight/style attributes.

        Returns:
            Dictionary mapping font file paths to FontInfo instances with
            charset populated. This can be used for font embedding without
            re-resolving fonts. Multiple PostScript names may map to the same
            file (e.g., TTC collections).

        Note:
            - Always uses platform-specific resolution (fontconfig/Windows registry)
            - Extracts charset from text elements for optimal font matching
            - Only sets font-weight if not 400 (Regular, CSS default)
            - Only sets font-style if italic
        """
        # Get all unique PostScript names used in SVG. extract_font_families()
        # returns a set, so sort it: the order decides which face wins a
        # @font-face descriptor collision in _generate_css_rules_for_fonts().
        postscript_names = sorted(svg_utils.extract_font_families(svg))

        # Track resolved fonts for reuse in font embedding
        resolved_fonts_map: dict[str, FontInfo] = {}

        for ps_name in postscript_names:
            # Step 1: Extract elements and charset for this PostScript name
            matching_elements, charset_codepoints = (
                self._extract_font_elements_and_charset(svg, ps_name)
            )
            if not matching_elements:
                continue

            # Step 2: Resolve PostScript name → family name with platform resolution
            try:
                # Single resolution call per font (uses platform-specific resolution)
                # Empty sets are automatically treated as None (no charset matching)
                resolved_font = FontInfo.resolve(
                    ps_name,
                    charset_codepoints=charset_codepoints,
                )
            except Exception as e:
                logger.warning(
                    f"Font resolution failed for PostScript name '{ps_name}': {e}. "
                    "Keeping PostScript name in SVG."
                )
                resolved_font = None

            if resolved_font is None:
                # No resolution - keep PostScript name
                logger.warning(
                    f"Font '{ps_name}' not found via platform resolution. "
                    "Keeping PostScript name in SVG."
                )
                continue

            family_name = resolved_font.family

            # Log resolution with file path
            logger.info(
                f"Resolved font '{ps_name}' → '{family_name}' "
                f"(file: '{resolved_font.file}')"
            )

            # Step 3: Update font-family attributes and set weight/style
            for element in matching_elements:
                # Replace PostScript name with CSS family name (if different)
                if family_name != ps_name:
                    svg_utils.replace_font_family(element, ps_name, family_name)

                # Set weight and style attributes using helper method
                self._update_element_font_attributes(element, resolved_font)

            # Step 4: Store resolved font for embedding
            # Use file path as key to deduplicate fonts by file
            # (multiple PostScript names can map to the same file)
            # Note: resolved_font.file is guaranteed to be non-empty by
            # find_with_files()
            file_key = resolved_font.file
            if file_key not in resolved_fonts_map:
                # Store font with charset (may already be populated from find())
                if not resolved_font.charset and charset_codepoints:
                    resolved_font = dataclasses.replace(
                        resolved_font, charset=charset_codepoints
                    )
                resolved_fonts_map[file_key] = resolved_font
            else:
                # Merge codepoints if same file already tracked
                existing_font = resolved_fonts_map[file_key]
                if existing_font.charset and charset_codepoints:
                    existing_font.charset.update(charset_codepoints)

        logger.debug(f"Total fonts resolved: {len(resolved_fonts_map)}")
        return resolved_fonts_map

    def _generate_css_rules_for_fonts(
        self,
        resolved_fonts: list[FontInfo],
        subset_fonts: bool,
        font_format: str,
        use_data_uri: bool,
    ) -> list[str]:
        """Generate CSS @font-face rules from resolved fonts.

        Args:
            resolved_fonts: List of FontInfo instances with charset populated.
            subset_fonts: If True, subset fonts (only applicable for data URIs).
            font_format: Font format for encoding (only applicable for data URIs).
            use_data_uri: If True, use data URIs; if False, use file:// URLs.

        Returns:
            List of CSS @font-face rule strings.
        """
        # Generate CSS rules from resolved fonts
        css_rules: list[str] = []
        source_desc = "data URI" if use_data_uri else "file:// URL"

        # A @font-face rule is selected by (family, weight, style), so two faces
        # sharing those would shadow each other in the browser. Emit the first
        # and report the rest instead of writing dead rules (issue #337).
        emitted: dict[tuple[str, int, bool], str] = {}

        for resolved_font in resolved_fonts:
            descriptor = (
                resolved_font.family,
                resolved_font.css_weight,
                resolved_font.italic,
            )
            if descriptor in emitted:
                logger.warning(
                    f"Font '{resolved_font.file}' has the same @font-face "
                    f"descriptor as '{emitted[descriptor]}' "
                    f"(family='{resolved_font.family}', "
                    f"weight={resolved_font.css_weight}, "
                    f"style={'italic' if resolved_font.italic else 'normal'}). "
                    "Only the first is embedded."
                )
                continue

            # Step 4: Generate CSS source (data URI or file URL)
            try:
                # Generate CSS source based on mode
                if use_data_uri:
                    # Prepare subset codepoints from FontInfo.charset
                    subset_codepoints: set[int] | None = None
                    if subset_fonts and resolved_font.charset:
                        subset_codepoints = resolved_font.charset
                    css_source = font_utils.encode_font_with_options(
                        font_path=resolved_font.file,
                        cache=self._font_data_cache,
                        subset_codepoints=subset_codepoints,
                        font_format=font_format,
                    )
                else:
                    css_source = font_utils.create_file_url(resolved_font.file)

                # Generate @font-face CSS rule
                css_rule = resolved_font.to_font_face_css(css_source)
                css_rules.append(css_rule)
                emitted[descriptor] = resolved_font.file

                logger.debug(
                    f"Inserted CSS @font-face for '{resolved_font.family}' "
                    f"with {source_desc}: {css_source[:50]}..."
                )

            except (FileNotFoundError, IOError) as e:
                logger.warning(
                    f"Failed to create {source_desc} for font "
                    f"'{resolved_font.file}': {e}. "
                    "Font will not be embedded."
                )
                continue
            except Exception as e:
                logger.warning(
                    f"Failed to process font '{resolved_font.file}': {e}. "
                    "Font will not be embedded."
                )
                continue

        return css_rules

    def _insert_css_fontface(
        self,
        svg: ET.Element,
        subset_fonts: bool,
        font_format: str,
        use_data_uri: bool,
        resolved_fonts_map: dict[str, FontInfo],
    ) -> None:
        """Insert CSS @font-face rules in a <style> element.

        This is the unified implementation for both data URI and file URL approaches.

        NOTE: This method should be called AFTER _resolve_and_collect_fonts() has
        converted PostScript names to CSS font families and resolved fonts in the SVG.

        Args:
            svg: SVG element to modify in-place (must have PostScript names resolved).
            subset_fonts: If True, subset fonts (only applicable for data URIs).
            font_format: Font format for encoding (only applicable for data URIs).
            use_data_uri: If True, use data URIs; if False, use file:// URLs.
            resolved_fonts_map: Pre-resolved fonts from _resolve_and_collect_fonts().
        """
        if not resolved_fonts_map:
            logger.warning("No resolved fonts found; skipping font embedding")
            return

        # Use pre-resolved fonts directly - NO re-resolution needed
        resolved_fonts = list(resolved_fonts_map.values())

        # Generate CSS rules
        css_rules = self._generate_css_rules_for_fonts(
            resolved_fonts, subset_fonts, font_format, use_data_uri
        )
        if not css_rules:
            logger.warning("No css font rules inserted; skipping <style> update")
            return

        # Insert all CSS rules into <style> element
        css_content = "\n".join(css_rules)
        svg_utils.insert_or_update_style_element(svg, css_content)


def convert(
    input_path: str,
    output_path: str,
    image_prefix: str | None = None,
    enable_text: bool = True,
    enable_live_shapes: bool = True,
    enable_title: bool = False,
    enable_class: bool = False,
    image_format: str = DEFAULT_IMAGE_FORMAT,
    text_letter_spacing_offset: float = 0.0,
    text_wrapping_mode: int = 0,
    font_mapping: dict[str, dict[str, float | str]] | None = None,
    embed_fonts: bool = False,
    font_format: str = "woff2",
    resource_limits: ResourceLimits | None = None,
) -> None:
    """Convenience method to convert a PSD file to an SVG file.

    Args:
        input_path: Path to the input PSD file.
        output_path: Path to the output SVG file.
        image_prefix: Optional path prefix to save extracted images. If None,
            images will be embedded.
        enable_text: Enable text layer conversion. If False, text layers are
            rasterized as images. Default is True.
        enable_live_shapes: Enable live shape conversion when possible.
            Disabling live shapes results in <path> elements instead of shape
            primitives like <rect> or <circle>. This may be more accurate, but
            less editable. Default is True.
        enable_title: Enable insertion of <title> elements with layer names.
            When False (default), title elements are omitted to reduce file size.
            Set to True to include <title> elements containing the Photoshop layer
            name for accessibility and debugging.
        enable_class: Enable insertion of class attributes on SVG elements for
            debugging purposes. When False (default), elements will not have class
            attributes, producing cleaner SVG output. Set to True to add class
            attributes for layer types, effects, and semantic roles (e.g.,
            "shape-layer", "drop-shadow-effect", "fill") for debugging or styling.
        image_format: Image format to use when embedding or saving images.
            Supported formats: 'webp', 'png', 'jpeg'. Default is 'webp'.
        text_letter_spacing_offset: Global offset (in pixels) to add to all
            letter-spacing values. This can be used to compensate for differences
            between Photoshop's text rendering and SVG's text rendering. Typical
            values range from -0.02 to 0.02. Default is 0.0 (no offset).
        text_wrapping_mode: Text wrapping mode for bounding box text. Use 0 for no
            wrapping (default, native SVG <text>), or 1 for <foreignObject> with
            XHTML wrapping. Import TextWrappingMode from psd2svg.core.text for
            enum values. Only affects bounding box text (ShapeType=1); point text
            always uses native SVG <text> elements.
        font_mapping: Optional custom font mapping dictionary for resolving
            PostScript font names to font families without fontconfig. Useful on
            Windows or when fonts are not installed. Format: {"PostScriptName":
            {"family": str, "style": str, "weight": float}}. When not provided,
            uses built-in mapping for common fonts.
        embed_fonts: Enable font embedding in SVG. When True, fonts used in text
            layers are embedded as base64-encoded data URIs in @font-face rules.
            Default is False. Requires fontconfig on Linux/macOS for font file
            discovery.
        font_format: Font format for embedding. Supported formats: 'woff2' (best
            compression, default), 'woff', 'ttf', 'otf'. Only used when
            embed_fonts=True. WOFF2 provides
            90%+ size reduction through automatic font subsetting.
        resource_limits: Optional resource limits for DoS prevention. If None,
            uses ResourceLimits.default() which enables limits (2GB file size,
            3 minute timeout, 100 layer depth, 16K image dimension). Use
            ResourceLimits.unlimited() to disable all limits for trusted input.

    Raises:
        ValueError: If file size, layer depth, or image dimensions exceed limits.
        TimeoutError: If conversion exceeds timeout limit.
    """
    # Default to ResourceLimits.default() if not specified
    if resource_limits is None:
        resource_limits = ResourceLimits.default()

    # Validate file size before loading
    if resource_limits.is_file_size_limited():
        file_size = os.path.getsize(input_path)
        if file_size > resource_limits.max_file_size:
            raise ValueError(
                f"File size {file_size} bytes exceeds limit {resource_limits.max_file_size} bytes. "  # noqa: E501
                f"To process: set PSD2SVG_MAX_FILE_SIZE={file_size + 1024 * 1024 * 100} environment variable, "  # noqa: E501
                f"or use ResourceLimits(max_file_size={file_size + 1024 * 1024 * 100}) in Python API."  # noqa: E501
            )

    psdimage = PSDImage.open(input_path)
    document = SVGDocument.from_psd(
        psdimage,
        enable_text=enable_text,
        enable_live_shapes=enable_live_shapes,
        enable_title=enable_title,
        enable_class=enable_class,
        text_letter_spacing_offset=text_letter_spacing_offset,
        text_wrapping_mode=text_wrapping_mode,
        font_mapping=font_mapping,
        resource_limits=resource_limits,
    )
    document.save(
        output_path,
        embed_images=image_prefix is None,
        image_prefix=image_prefix,
        image_format=image_format,
        embed_fonts=embed_fonts,
        font_format=font_format,
    )
