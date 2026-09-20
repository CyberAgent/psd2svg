"""Mixin for adjustment layers conversion.

Due to the limited support of BackgroundImage in SVG filters, our approach wraps
the backdrop elements into a symbol, and use two <use> elements to apply the filter.

When we have a layer structure like this::

    <layer 1 />
    <layer 2 />
    <adjustment />

We convert it into the following SVG structure::

    <symbol id="backdrop">
        <image id="layer1" ... />
        <image id="layer2" ... />
    </symbol>
    <filter id="adjustment"></filter>
    <use href="#backdrop" />
    <use href="#backdrop" filter="url(#adjustment)" />


This approach may have limitations when the backdrop has transparency, as the
stacked use elements may not produce the intended visual result.
"""

import logging
import xml.etree.ElementTree as ET
from collections import OrderedDict

import numpy as np
from psd_tools.api import adjustments, layers
from psd_tools.psd.adjustments import LevelRecord

from psd2svg import svg_utils
from psd2svg.core.base import ConverterProtocol

logger = logging.getLogger(__name__)


class AdjustmentConverter(ConverterProtocol):
    """Mixin for adjustment layers."""

    def add_invert_adjustment(
        self, layer: adjustments.Invert, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add an invert adjustment layer to the svg document."""
        filter, use = self._create_filter(layer, name="invert", **attrib)
        with self.set_current(filter):
            fe_component = self.create_node(
                "feComponentTransfer", color_interpolation_filters="sRGB"
            )
            with self.set_current(fe_component):
                self.create_node("feFuncR", type="table", tableValues="1 0")
                self.create_node("feFuncG", type="table", tableValues="1 0")
                self.create_node("feFuncB", type="table", tableValues="1 0")
        return use

    def add_posterize_adjustment(
        self, layer: adjustments.Posterize, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a posterize adjustment layer to the svg document."""
        # Validate and clamp levels to valid range
        levels = layer.posterize
        if levels < 2:
            logger.warning(
                f"Posterize levels {levels} is below minimum (2), clamping to 2"
            )
            levels = 2
        elif levels > 256:
            logger.warning(
                f"Posterize levels {levels} exceeds maximum (256), clamping to 256"
            )
            levels = 256

        # Generate discrete table values: [0/(n-1), 1/(n-1), ..., (n-1)/(n-1)]
        table_values = [i / (levels - 1) for i in range(levels)]
        table_values_str = svg_utils.seq2str(table_values, sep=" ")

        filter, use = self._create_filter(layer, name="posterize", **attrib)
        with self.set_current(filter):
            fe_component = self.create_node(
                "feComponentTransfer", color_interpolation_filters="sRGB"
            )
            with self.set_current(fe_component):
                # Apply discrete posterization to RGB channels
                self.create_node(
                    "feFuncR", type="discrete", tableValues=table_values_str
                )
                self.create_node(
                    "feFuncG", type="discrete", tableValues=table_values_str
                )
                self.create_node(
                    "feFuncB", type="discrete", tableValues=table_values_str
                )
        return use

    def add_threshold_adjustment(
        self, layer: adjustments.Threshold, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a threshold adjustment layer to the svg document.

        Threshold converts the image to high-contrast black and white by comparing
        each pixel's luminance against a threshold value. Pixels below the threshold
        become black (0), and pixels at or above become white (255).

        Args:
            layer: The Threshold adjustment layer to convert.
            depth: Current nesting depth (for resource limit checking).
            attrib: Additional attributes for the SVG element.

        Returns:
            The SVG use element with the filter applied, or None if invalid.
        """
        # Extract threshold value (0-255)
        threshold = layer.threshold

        # Log for debugging
        logger.debug(f"Threshold adjustment '{layer.name}': threshold={threshold}")

        # Validate threshold value (warn but don't clamp except for > 255)
        if threshold < 1:
            logger.warning(
                f"Threshold value {threshold} is below minimum (1), "
                f"resulting in all-white output"
            )
        elif threshold > 255:
            logger.warning(
                f"Threshold value {threshold} exceeds maximum (255), clamping to 255"
            )
            threshold = 255

        # Generate lookup table: 256 values where LUT[i] = 0 if i < threshold else 1
        table_values = [0.0 if i < threshold else 1.0 for i in range(256)]
        table_values_str = svg_utils.seq2str(table_values, sep=" ")

        # Create filter structure
        filter, use = self._create_filter(layer, name="threshold", **attrib)
        with self.set_current(filter):
            # Step 1: Convert to grayscale using luminance formula
            # ITU-R BT.601: L = 0.299*R + 0.587*G + 0.114*B
            # This desaturates the image to grayscale
            self.create_node(
                "feColorMatrix",
                type="saturate",
                values=0,
                color_interpolation_filters="sRGB",
            )

            # Step 2: Apply threshold to the grayscale result
            fe_component = self.create_node(
                "feComponentTransfer", color_interpolation_filters="sRGB"
            )
            with self.set_current(fe_component):
                # Apply threshold to all RGB channels
                # (they're identical after desaturation)
                self.create_node("feFuncR", type="table", tableValues=table_values_str)
                self.create_node("feFuncG", type="table", tableValues=table_values_str)
                self.create_node("feFuncB", type="table", tableValues=table_values_str)

        return use

    def add_hue_saturation_adjustment(
        self, layer: adjustments.HueSaturation, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a hue/saturation adjustment layer to the svg document.

        Supports two modes:
        - Normal mode: Adjusts hue, saturation, and lightness using master values
        - Colorize mode: Desaturates then applies colorization tint

        Note: Per-range color adjustments (layer.data) are not yet supported.
        """
        # Extract adjustment parameters
        hue, saturation, lightness = layer.master
        enable_colorization = layer.enable_colorization

        # Check if this is a no-op adjustment
        if enable_colorization == 0 and hue == 0 and saturation == 0 and lightness == 0:
            logger.info(
                f"HueSaturation adjustment '{layer.name}' has no effect, skipping"
            )
            return None

        # Create filter structure
        filter, use = self._create_filter(layer, name="huesaturation", **attrib)

        with self.set_current(filter):
            if enable_colorization == 1:
                # Colorize mode: desaturate, then apply colorization
                self._apply_colorize_mode(layer)
            else:
                # Normal mode: apply master adjustments
                self._apply_normal_huesaturation(hue, saturation, lightness)

        return use

    def add_exposure_adjustment(
        self, layer: adjustments.Exposure, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add an exposure adjustment layer to the svg document.

        Applies exposure, offset, and gamma correction to simulate Photoshop's
        Exposure adjustment layer. Operations are applied in linear RGB space
        to match Photoshop's behavior.

        The three parameters are applied in sequence:
        1. Exposure: output = input × 2^exposure
        2. Offset: output = input + offset
        3. Gamma: output = input^(1/gamma)

        Args:
            layer: The Exposure adjustment layer to convert.
            depth: Current nesting depth (for resource limit checking).
            attrib: Additional attributes for the SVG element.

        Returns:
            The SVG use element with the filter applied, or None if no-op.
        """
        # Extract parameters
        exposure = layer.exposure
        offset = layer.exposure_offset
        gamma = layer.gamma

        # Log parameters for debugging
        logger.debug(
            f"Exposure adjustment '{layer.name}': "
            f"exposure={exposure}, offset={offset}, gamma={gamma}"
        )

        # Check if this is a no-op adjustment (within floating-point tolerance)
        if abs(exposure) < 1e-6 and abs(offset) < 1e-6 and abs(gamma - 1.0) < 1e-6:
            logger.info(f"Exposure adjustment '{layer.name}' has no effect, skipping")
            return None

        # Validate parameters (warn but don't clamp)
        if not (-20.0 <= exposure <= 20.0):
            logger.warning(
                f"Exposure value {exposure} is outside expected range [-20, +20]"
            )
        if not (-0.5 <= offset <= 0.5):
            logger.warning(
                f"Offset value {offset} is outside expected range [-0.5, +0.5]"
            )
        if not (0.01 <= gamma <= 9.99):
            logger.warning(
                f"Gamma value {gamma} is outside expected range [0.01, 9.99]"
            )

        # Create filter structure
        filter, use = self._create_filter(layer, name="exposure", **attrib)

        with self.set_current(filter):
            # Stage 1: Apply exposure (multiply by 2^exposure)
            if abs(exposure) >= 1e-6:  # Only apply if non-zero
                exposure_scale = 2**exposure
                fe_exposure = self.create_node(
                    "feComponentTransfer", color_interpolation_filters="linearRGB"
                )
                with self.set_current(fe_exposure):
                    for func in ["feFuncR", "feFuncG", "feFuncB"]:
                        self.create_node(
                            func, type="linear", slope=exposure_scale, intercept=0
                        )

            # Stage 2: Apply offset (add offset value)
            if abs(offset) >= 1e-6:  # Only apply if non-zero
                fe_offset = self.create_node(
                    "feComponentTransfer", color_interpolation_filters="linearRGB"
                )
                with self.set_current(fe_offset):
                    for func in ["feFuncR", "feFuncG", "feFuncB"]:
                        self.create_node(func, type="linear", slope=1, intercept=offset)

            # Stage 3: Apply gamma (power function with exponent 1/gamma)
            if abs(gamma - 1.0) >= 1e-6:  # Only apply if not 1.0
                gamma_exponent = 1.0 / gamma
                fe_gamma = self.create_node(
                    "feComponentTransfer", color_interpolation_filters="linearRGB"
                )
                with self.set_current(fe_gamma):
                    for func in ["feFuncR", "feFuncG", "feFuncB"]:
                        self.create_node(func, type="gamma", exponent=gamma_exponent)

        return use

    def add_brightness_contrast_adjustment(
        self, layer: adjustments.BrightnessContrast, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a brightness/contrast adjustment layer to the svg document.

        Applies brightness and contrast adjustments using SVG feComponentTransfer
        filters with linear transfer functions. Operations are applied sequentially:
        brightness first, then contrast.

        Brightness adds a constant value to all RGB channels:
            output = input + (brightness / 255)

        Contrast scales values around the midpoint (0.5):
            output = (input - 0.5) * factor + 0.5
            where factor = (259 * (contrast + 255)) / (255 * (259 - contrast))

        Note: Photoshop's modern (non-legacy) brightness/contrast uses a complex
        curves-based algorithm. Our linear approximation works well for most cases
        but may have higher error for extreme negative brightness values.

        Args:
            layer: The BrightnessContrast adjustment layer to convert.
            depth: Current nesting depth (for resource limit checking).
            attrib: Additional attributes for the SVG element.

        Returns:
            The SVG use element with the filter applied, or None if no-op.
        """
        # Extract parameters
        brightness = layer.brightness
        contrast = layer.contrast

        # Log parameters for debugging
        logger.debug(
            f"BrightnessContrast adjustment '{layer.name}': "
            f"brightness={brightness}, contrast={contrast}"
        )

        # Early return for no-op
        if brightness == 0 and contrast == 0:
            logger.info(
                f"BrightnessContrast adjustment '{layer.name}' has no effect, skipping"
            )
            return None

        # Parameter validation (warn but don't clamp)
        if not (-150 <= brightness <= 150):
            logger.warning(
                f"Brightness value {brightness} is outside expected range [-150, +150]"
            )
        if not (-50 <= contrast <= 100):
            logger.warning(
                f"Contrast value {contrast} is outside expected range [-50, +100]"
            )

        # Create filter structure
        filter, use = self._create_filter(layer, name="brightnesscontrast", **attrib)

        with self.set_current(filter):
            # Stage 1: Apply brightness (if non-zero)
            if brightness != 0:
                brightness_offset = brightness / 255.0
                fe_brightness = self.create_node(
                    "feComponentTransfer", color_interpolation_filters="sRGB"
                )
                with self.set_current(fe_brightness):
                    for func in ["feFuncR", "feFuncG", "feFuncB"]:
                        self.create_node(
                            func, type="linear", slope=1.0, intercept=brightness_offset
                        )

            # Stage 2: Apply contrast (if non-zero)
            if contrast != 0:
                # Calculate contrast factor using legacy-style formula
                # This formula: (259 * (contrast + 255)) / (255 * (259 - contrast))
                # Matches Photoshop's behavior better than the simple modern formula
                numerator = 259.0 * (contrast + 255.0)
                denominator = 255.0 * (259.0 - contrast)
                contrast_factor = numerator / denominator

                # Calculate intercept: 0.5 * (1 - factor)
                contrast_intercept = 0.5 * (1.0 - contrast_factor)

                fe_contrast = self.create_node(
                    "feComponentTransfer", color_interpolation_filters="sRGB"
                )
                with self.set_current(fe_contrast):
                    for func in ["feFuncR", "feFuncG", "feFuncB"]:
                        self.create_node(
                            func,
                            type="linear",
                            slope=contrast_factor,
                            intercept=contrast_intercept,
                        )

        return use

    def add_color_balance_adjustment(
        self, layer: adjustments.ColorBalance, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a color balance adjustment layer to the svg document.

        Applies color balance adjustments to shadows, midtones, and highlights
        using SVG feComponentTransfer filters with lookup tables.

        Note: Uses grayscale approximation for luminance due to SVG's
        independent channel processing. Accuracy ~95% for typical adjustments.

        Args:
            layer: The ColorBalance adjustment layer to convert.
            depth: Current nesting depth (for resource limit checking).
            attrib: Additional attributes for the SVG element.

        Returns:
            The SVG use element with the filter applied, or None if no-op.
        """
        # Extract parameters
        shadows = layer.shadows
        midtones = layer.midtones
        highlights = layer.highlights
        preserve_luminosity = layer.luminosity == 1  # 1=enabled, 0=disabled

        # Log parameters
        logger.debug(
            f"ColorBalance adjustment '{layer.name}': "
            f"shadows={shadows}, midtones={midtones}, highlights={highlights}, "
            f"preserve_luminosity={preserve_luminosity}"
        )

        # Check for no-op
        if shadows == (0, 0, 0) and midtones == (0, 0, 0) and highlights == (0, 0, 0):
            logger.info(
                f"ColorBalance adjustment '{layer.name}' has no effect, skipping"
            )
            return None

        # Warn about preserve luminosity limitation
        if preserve_luminosity:
            logger.warning(
                f"ColorBalance adjustment '{layer.name}': "
                "Preserve Luminosity is not fully supported in SVG. "
                "Results may differ from Photoshop."
            )

        # Warn about extreme adjustments with reduced accuracy
        max_abs_value = max(
            max(abs(v) for v in shadows),
            max(abs(v) for v in midtones),
            max(abs(v) for v in highlights),
        )
        if max_abs_value >= 80:
            logger.info(
                f"ColorBalance adjustment '{layer.name}': "
                f"Extreme adjustment values (max |{max_abs_value}|) detected. "
                "Accuracy may be reduced (65-85%) due to SVG's per-channel "
                "luminance approximation. For critical color accuracy, flatten "
                "this adjustment in Photoshop before conversion."
            )

        # Create filter structure
        filter, use = self._create_filter(layer, name="colorbalance", **attrib)

        # Generate lookup tables
        lut_r = self._generate_colorbalance_lut(shadows, midtones, highlights, 0)
        lut_g = self._generate_colorbalance_lut(shadows, midtones, highlights, 1)
        lut_b = self._generate_colorbalance_lut(shadows, midtones, highlights, 2)

        # Convert to SVG format
        lut_r_str = svg_utils.seq2str(lut_r, sep=" ")
        lut_g_str = svg_utils.seq2str(lut_g, sep=" ")
        lut_b_str = svg_utils.seq2str(lut_b, sep=" ")

        # Create filter
        with self.set_current(filter):
            fe_component = self.create_node(
                "feComponentTransfer", color_interpolation_filters="sRGB"
            )
            with self.set_current(fe_component):
                self.create_node("feFuncR", type="table", tableValues=lut_r_str)
                self.create_node("feFuncG", type="table", tableValues=lut_g_str)
                self.create_node("feFuncB", type="table", tableValues=lut_b_str)

        return use

    def add_black_and_white_adjustment(
        self, layer: adjustments.BlackAndWhite, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a black and white adjustment layer to the svg document.

        Note: Not supported. Photoshop's per-hue-range weighting has no SVG
        filter equivalent, so the layer is omitted from the output.
        """
        logger.warning(
            f"Black and White adjustment layer is not supported and is omitted "
            f"from the output: '{layer.name}' ({layer.kind}). Photoshop weights "
            f"each pixel by which of six color ranges its hue falls into, which "
            f"SVG filter primitives cannot classify. Flatten the adjustment in "
            f"Photoshop before conversion."
        )
        return None

    def add_channel_mixer_adjustment(
        self, layer: adjustments.ChannelMixer, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a channel mixer adjustment layer to the svg document.

        Note: Not yet implemented, tracked by issue #369. The layer is omitted
        from the output.
        """
        logger.warning(
            f"Channel Mixer adjustment layer is not yet implemented and is "
            f"omitted from the output: '{layer.name}' ({layer.kind}). "
            f"See https://github.com/CyberAgent/psd2svg/issues/369."
        )
        return None

    def add_color_lookup_adjustment(
        self, layer: adjustments.ColorLookup, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a color lookup adjustment layer to the svg document.

        Note: Not supported. A 3D LUT has no SVG filter primitive and psd-tools
        does not expose the data, so the layer is omitted from the output.
        """
        logger.warning(
            f"Color Lookup adjustment layer is not supported and is omitted "
            f"from the output: '{layer.name}' ({layer.kind}). A 3D LUT has no "
            f"SVG filter primitive, and psd-tools does not expose the lookup "
            f"data. Flatten the adjustment in Photoshop before conversion."
        )
        return None

    def add_curves_adjustment(
        self, layer: adjustments.Curves, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a curves adjustment layer to the svg document.

        Applies tonal curve adjustments using SVG feComponentTransfer filters
        with lookup tables generated from control points. Supports both composite
        (RGB) curves and per-channel (R/G/B) curves, matching Photoshop's curve
        application order.

        Args:
            layer: The Curves adjustment layer to convert.
            depth: Current nesting depth (for resource limit checking).
            attrib: Additional attributes for the SVG element.

        Returns:
            The SVG use element with the filter applied, or None if identity.
        """
        # Validate curve data
        if not hasattr(layer.data, "extra") or not layer.data.extra:
            logger.warning(
                f"Curves adjustment '{layer.name}' has no curve data, skipping"
            )
            return None

        # Check for identity curves (optimization)
        is_identity = True
        for item in layer.data.extra:  # type: ignore[attr-defined]
            if len(item.points) != 2 or item.points != [(0, 0), (255, 255)]:
                is_identity = False
                break

        if is_identity:
            logger.info(f"Curves adjustment '{layer.name}' is identity curve, skipping")
            return None

        # Log curve info for debugging
        logger.debug(
            f"Curves adjustment '{layer.name}': "
            f"Processing {len(layer.data.extra)} curve(s)"  # type: ignore[arg-type]
        )

        # Generate lookup tables
        lut_r, lut_g, lut_b = self._generate_curves_luts(layer)

        # Convert to SVG format
        lut_r_str = svg_utils.seq2str(lut_r, sep=" ")
        lut_g_str = svg_utils.seq2str(lut_g, sep=" ")
        lut_b_str = svg_utils.seq2str(lut_b, sep=" ")

        # Create filter structure
        filter, use = self._create_filter(layer, name="curves", **attrib)

        # Build SVG filter primitives
        with self.set_current(filter):
            fe_component = self.create_node(
                "feComponentTransfer", color_interpolation_filters="sRGB"
            )
            with self.set_current(fe_component):
                self.create_node("feFuncR", type="table", tableValues=lut_r_str)
                self.create_node("feFuncG", type="table", tableValues=lut_g_str)
                self.create_node("feFuncB", type="table", tableValues=lut_b_str)

        return use

    def add_gradient_map_adjustment(
        self, layer: adjustments.GradientMap, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a gradient map adjustment layer to the svg document.

        Note: Not yet implemented, tracked by issue #368. The layer is omitted
        from the output.
        """
        logger.warning(
            f"Gradient Map adjustment layer is not yet implemented and is "
            f"omitted from the output: '{layer.name}' ({layer.kind}). "
            f"See https://github.com/CyberAgent/psd2svg/issues/368."
        )
        return None

    def add_levels_adjustment(
        self, layer: adjustments.Levels, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a levels adjustment layer to the svg document.

        Applies tonal adjustments using input/output ranges and gamma correction.
        Supports both composite (RGB) and per-channel (R/G/B) adjustments,
        matching Photoshop's application order.

        Args:
            layer: The Levels adjustment layer to convert.
            depth: Current nesting depth (for resource limit checking).
            attrib: Additional attributes for the SVG element.

        Returns:
            The SVG use element with the filter applied, or None if identity.
        """
        # Validate data structure
        if not hasattr(layer, "data") or len(layer.data) < 4:
            logger.warning(
                f"Levels adjustment '{layer.name}' has insufficient data, skipping"
            )
            return None

        # Check for identity (optimization)
        is_identity = True
        for i in range(4):
            record = layer.data[i]
            if not (
                record.input_floor == 0
                and record.input_ceiling == 255
                and record.output_floor == 0
                and record.output_ceiling == 255
                and record.gamma == 100
            ):
                is_identity = False
                break

        if is_identity:
            logger.info(f"Levels adjustment '{layer.name}' is identity, skipping")
            return None

        # Log for debugging
        logger.debug(
            f"Levels adjustment '{layer.name}': "
            f"Processing composite RGB and per-channel adjustments"
        )

        # Generate lookup tables
        lut_r, lut_g, lut_b = self._generate_levels_luts(layer)

        # Convert to SVG format
        lut_r_str = svg_utils.seq2str(lut_r, sep=" ")
        lut_g_str = svg_utils.seq2str(lut_g, sep=" ")
        lut_b_str = svg_utils.seq2str(lut_b, sep=" ")

        # Create filter structure
        filter, use = self._create_filter(layer, name="levels", **attrib)

        # Build SVG filter primitives
        with self.set_current(filter):
            fe_component = self.create_node(
                "feComponentTransfer", color_interpolation_filters="sRGB"
            )
            with self.set_current(fe_component):
                self.create_node("feFuncR", type="table", tableValues=lut_r_str)
                self.create_node("feFuncG", type="table", tableValues=lut_g_str)
                self.create_node("feFuncB", type="table", tableValues=lut_b_str)

        return use

    def add_photo_filter_adjustment(
        self, layer: adjustments.PhotoFilter, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a photo filter adjustment layer to the svg document.

        Note: Not yet implemented, tracked by issue #370. The layer is omitted
        from the output.
        """
        logger.warning(
            f"Photo Filter adjustment layer is not yet implemented and is "
            f"omitted from the output: '{layer.name}' ({layer.kind}). "
            f"See https://github.com/CyberAgent/psd2svg/issues/370."
        )
        return None

    def add_selective_color_adjustment(
        self, layer: adjustments.SelectiveColor, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a selective color adjustment layer to the svg document.

        Note: Not supported. Photoshop's per-hue-range adjustment has no SVG
        filter equivalent, so the layer is omitted from the output.
        """
        logger.warning(
            f"Selective Color adjustment layer is not supported and is omitted "
            f"from the output: '{layer.name}' ({layer.kind}). Photoshop adjusts "
            f"each pixel by which color range its hue falls into, which SVG "
            f"filter primitives cannot classify. Flatten the adjustment in "
            f"Photoshop before conversion."
        )
        return None

    def add_vibrance_adjustment(
        self, layer: adjustments.Vibrance, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a vibrance adjustment layer to the svg document.

        Note: Not supported. The adjustment is nonlinear in each pixel's
        existing saturation, so the layer is omitted from the output.
        """
        logger.warning(
            f"Vibrance adjustment layer is not supported and is omitted from "
            f"the output: '{layer.name}' ({layer.kind}). The adjustment is "
            f"nonlinear in each pixel's existing saturation, which is not a "
            f"per-channel quantity SVG filters can compute. Flatten the "
            f"adjustment in Photoshop before conversion."
        )
        return None

    def _generate_colorbalance_lut(
        self,
        shadows: tuple[int, int, int],
        midtones: tuple[int, int, int],
        highlights: tuple[int, int, int],
        channel_idx: int,
    ) -> list[float]:
        """Generate 256-value lookup table for color balance adjustment.

        Uses grayscale approximation: assumes R≈G≈B for luminance.

        Args:
            shadows: (cyan-red, magenta-green, yellow-blue) for shadows
            midtones: Same for midtones
            highlights: Same for highlights
            channel_idx: 0 for R, 1 for G, 2 for B

        Returns:
            List of 256 float values in [0, 1] range.
        """
        lut = []

        for i in range(256):
            # Normalize input to [0, 1]
            input_val = i / 255.0

            # Grayscale approximation: luminance ≈ input_val
            luminance = input_val

            # Calculate tonal weights
            if luminance < 0.33:
                weight_shadows = (0.33 - luminance) / 0.33
            else:
                weight_shadows = 0.0

            # Midtones: centered at 0.495 with falloff range of 0.165
            # (triangular weighting)
            mid_distance = abs(luminance - 0.495)
            weight_midtones = max(0.0, 1.0 - mid_distance / 0.165)

            if luminance >= 0.66:
                weight_highlights = (luminance - 0.66) / 0.34
            else:
                weight_highlights = 0.0

            # Calculate weighted adjustment
            adjustment = (
                shadows[channel_idx] * weight_shadows
                + midtones[channel_idx] * weight_midtones
                + highlights[channel_idx] * weight_highlights
            ) / 100.0

            # Apply adjustment and clamp
            output_val = max(0.0, min(1.0, input_val + adjustment))

            lut.append(output_val)

        return lut

    def _interpolate_curve(self, points: list[tuple[int, int]]) -> list[float]:
        """Interpolate curve control points to 256-value LUT using Catmull-Rom spline.

        Uses Catmull-Rom spline interpolation for smooth C1 continuous curves
        with local control. For curves with only 2 points, uses linear interpolation.

        Args:
            points: List of (input, output) tuples in 0-255 range.
                    Always includes endpoints (0, 0) and (255, 255).

        Returns:
            List of 256 float values in [0, 1] range for SVG.
        """
        if len(points) < 2:
            # Edge case: invalid curve, return identity
            logger.warning("Curve has fewer than 2 points, using identity")
            return list(np.linspace(0, 1, 256))

        # IMPORTANT: Photoshop curve points are (output, input), not (input, output)!
        # We need to swap them to get (input, output) for interpolation
        # Example: [(0, 0), (160, 95), (255, 255)] means:
        #   input 0 → output 0
        #   input 95 → output 160 (brightening)
        #   input 255 → output 255
        swapped_points = [(p[1], p[0]) for p in points]

        # Deduplicate points: keep last point for each x value
        # This handles cases like [(0, 0), (255, 4), (255, 255)] which after
        # swapping becomes [(0, 0), (4, 255), (255, 255)]
        deduplicated_points = list(
            OrderedDict((p[0], p) for p in swapped_points).values()
        )

        if len(deduplicated_points) != len(swapped_points):
            logger.debug(
                f"Deduplicated curve points from {len(swapped_points)} to "
                f"{len(deduplicated_points)} (removed duplicate x values)"
            )
            points = deduplicated_points
        else:
            points = swapped_points

        # Validate we still have enough points after deduplication
        if len(points) < 2:
            logger.warning(
                "Curve has fewer than 2 points after deduplication, using identity"
            )
            return list(np.linspace(0, 1, 256))

        # Extract x and y coordinates (now in input, output order)
        x_points = np.array([p[0] for p in points], dtype=float)
        y_points = np.array([p[1] for p in points], dtype=float)

        # Handle 2-point case (identity or linear)
        if len(points) == 2:
            # Simple linear interpolation
            lut = np.interp(np.arange(256), x_points, y_points)
            # Clamp and normalize
            lut = np.clip(lut, 0, 255) / 255.0
            return lut.tolist()

        # Catmull-Rom spline for 3+ points
        # Duplicate first and last points for boundary tangent calculation
        x_extended = np.concatenate([[x_points[0]], x_points, [x_points[-1]]])
        y_extended = np.concatenate([[y_points[0]], y_points, [y_points[-1]]])

        # Catmull-Rom basis matrix
        cr_matrix = np.array(
            [
                [-0.5, 1.5, -1.5, 0.5],
                [1.0, -2.5, 2.0, -0.5],
                [-0.5, 0.0, 0.5, 0.0],
                [0.0, 1.0, 0.0, 0.0],
            ]
        )

        # Generate interpolated curve
        lut = np.zeros(256)

        for i in range(len(points) - 1):
            # Get four control points for this segment (p0, p1, p2, p3)
            # We interpolate between p1 and p2
            p0_y = y_extended[i]
            p1_x, p1_y = x_extended[i + 1], y_extended[i + 1]
            p2_x, p2_y = x_extended[i + 2], y_extended[i + 2]
            p3_y = y_extended[i + 3]

            # Determine which output indices correspond to this segment
            x_start = int(p1_x)
            x_end = int(p2_x)

            if x_start > x_end:
                # Skip segments going backwards (shouldn't happen after deduplication)
                continue

            if x_start == x_end:
                # Single point segment: set the value directly
                if x_start < 256:
                    lut[x_start] = p2_y
                continue

            # Generate samples for this segment
            for x in range(x_start, min(x_end + 1, 256)):
                # Parametric position t in [0, 1] within this segment
                t = (x - p1_x) / (p2_x - p1_x) if p2_x > p1_x else 0
                t = np.clip(t, 0, 1)

                # Catmull-Rom interpolation
                t_vec = np.array([t**3, t**2, t, 1])
                p_vec = np.array([p0_y, p1_y, p2_y, p3_y])
                y = t_vec @ cr_matrix @ p_vec

                lut[x] = y

        # Clamp and normalize to [0, 1]
        lut = np.clip(lut, 0, 255) / 255.0
        return lut.tolist()

    def _generate_curves_luts(
        self, layer: adjustments.Curves
    ) -> tuple[list[float], list[float], list[float]]:
        """Generate RGB lookup tables from Curves layer.

        Handles both composite (RGB) curves and per-channel curves with
        correct composition order matching Photoshop behavior: composite
        curve is applied first to all channels, then individual channel
        curves are applied on top.

        Args:
            layer: The Curves adjustment layer.

        Returns:
            Tuple of (lut_r, lut_g, lut_b) with 256 float values each in [0, 1].
        """
        # Parse curves by channel ID
        curves_by_channel: dict[int, list[tuple[int, int]]] = {}
        for item in layer.data.extra:  # type: ignore[attr-defined]
            if 0 <= item.channel_id <= 3:
                curves_by_channel[item.channel_id] = item.points
            else:
                logger.warning(
                    f"Curves adjustment '{layer.name}': "
                    f"Unknown channel ID {item.channel_id}, skipping"
                )

        # Start with identity LUTs (0-255 in pixel space)
        identity = np.arange(256, dtype=float)
        r_vals = identity.copy()
        g_vals = identity.copy()
        b_vals = identity.copy()

        # Apply composite curve (channel_id=0) to all channels first
        if 0 in curves_by_channel:
            logger.debug(
                f"Curves adjustment '{layer.name}': "
                f"Applying composite curve with {len(curves_by_channel[0])} points"
            )
            composite_lut_normalized = self._interpolate_curve(curves_by_channel[0])
            # Convert back to 0-255 space for composition
            composite_lut = np.array(composite_lut_normalized) * 255.0

            # Apply composite to all channels
            r_vals = np.interp(r_vals, identity, composite_lut)
            g_vals = np.interp(g_vals, identity, composite_lut)
            b_vals = np.interp(b_vals, identity, composite_lut)

        # Apply per-channel curves on top of composite
        for channel_id, channel_name in [(1, "Red"), (2, "Green"), (3, "Blue")]:
            if channel_id in curves_by_channel:
                logger.debug(
                    f"Curves adjustment '{layer.name}': "
                    f"Applying {channel_name} curve with "
                    f"{len(curves_by_channel[channel_id])} points"
                )
                channel_lut_normalized = self._interpolate_curve(
                    curves_by_channel[channel_id]
                )
                # Convert back to 0-255 space
                channel_lut = np.array(channel_lut_normalized) * 255.0

                # Apply to the corresponding channel
                if channel_id == 1:
                    r_vals = np.interp(r_vals, identity, channel_lut)
                elif channel_id == 2:
                    g_vals = np.interp(g_vals, identity, channel_lut)
                elif channel_id == 3:
                    b_vals = np.interp(b_vals, identity, channel_lut)

        # Clamp and normalize to [0, 1] for SVG
        r_lut = np.clip(r_vals, 0, 255) / 255.0
        g_lut = np.clip(g_vals, 0, 255) / 255.0
        b_lut = np.clip(b_vals, 0, 255) / 255.0

        return r_lut.tolist(), g_lut.tolist(), b_lut.tolist()

    def _generate_levels_luts(
        self, layer: adjustments.Levels
    ) -> tuple[list[float], list[float], list[float]]:
        """Generate RGB lookup tables from Levels layer.

        Handles both composite (RGB) and per-channel adjustments with
        correct composition order matching Photoshop behavior: composite
        adjustment is applied first to all channels, then individual channel
        adjustments are applied on top.

        Args:
            layer: The Levels adjustment layer.

        Returns:
            Tuple of (lut_r, lut_g, lut_b) with 256 float values each in [0, 1].
        """
        # Start with identity LUTs (0-255 in pixel space)
        identity = np.arange(256, dtype=float)
        r_vals = identity.copy()
        g_vals = identity.copy()
        b_vals = identity.copy()

        # Apply composite RGB adjustment (record 0) to all channels first
        composite_record = layer.data[0]
        composite_lut = self._apply_levels_to_lut(
            identity, composite_record, channel_name="RGB"
        )

        # Apply composite to all channels
        r_vals = composite_lut.copy()
        g_vals = composite_lut.copy()
        b_vals = composite_lut.copy()

        # Apply per-channel adjustments on top
        for channel_id, channel_name in [(1, "Red"), (2, "Green"), (3, "Blue")]:
            record = layer.data[channel_id]

            # Check if this channel has non-identity adjustment
            if (
                record.input_floor != 0
                or record.input_ceiling != 255
                or record.output_floor != 0
                or record.output_ceiling != 255
                or record.gamma != 100
            ):
                logger.debug(
                    f"Levels adjustment '{layer.name}': "
                    f"Applying {channel_name} channel adjustment"
                )

                # Apply levels adjustment to this channel
                if channel_id == 1:
                    r_vals = self._apply_levels_to_lut(r_vals, record, channel_name)
                elif channel_id == 2:
                    g_vals = self._apply_levels_to_lut(g_vals, record, channel_name)
                elif channel_id == 3:
                    b_vals = self._apply_levels_to_lut(b_vals, record, channel_name)

        # Clamp and normalize to [0, 1] for SVG
        r_lut = np.clip(r_vals, 0, 255) / 255.0
        g_lut = np.clip(g_vals, 0, 255) / 255.0
        b_lut = np.clip(b_vals, 0, 255) / 255.0

        return r_lut.tolist(), g_lut.tolist(), b_lut.tolist()

    def _apply_levels_to_lut(
        self, input_lut: np.ndarray, record: LevelRecord, channel_name: str = "RGB"
    ) -> np.ndarray:
        """Apply levels transformation to a lookup table.

        Applies the Photoshop Levels algorithm:
        1. Normalize input: (value - input_floor) / (input_ceiling - input_floor)
        2. Apply gamma: normalized ^ (100/gamma)
        3. Scale to output: result * (output_ceiling - output_floor) + output_floor
        4. Clamp to [0, 255]

        Args:
            input_lut: Input LUT values in 0-255 range (256 float values).
            record: LevelRecord with adjustment parameters.
            channel_name: Channel name for logging (e.g., "RGB", "Red").

        Returns:
            Output LUT values in 0-255 range (256 float values).
        """
        # Extract parameters
        input_floor = float(record.input_floor)
        input_ceiling = float(record.input_ceiling)
        output_floor = float(record.output_floor)
        output_ceiling = float(record.output_ceiling)
        gamma = float(record.gamma)

        # Handle edge case: input_ceiling == input_floor (division by zero)
        if abs(input_ceiling - input_floor) < 1e-6:
            logger.warning(
                f"Levels adjustment: {channel_name} channel has "
                f"input_ceiling == input_floor ({input_ceiling}), "
                f"using extreme mapping"
            )
            # All values below input_floor -> output_floor
            # All values at or above input_floor -> output_ceiling
            output_lut = np.where(input_lut < input_floor, output_floor, output_ceiling)
            return output_lut

        # Handle edge case: gamma <= 0 (invalid)
        if gamma <= 0:
            logger.warning(
                f"Levels adjustment: {channel_name} channel has "
                f"invalid gamma ({gamma}), using gamma=100"
            )
            gamma = 100.0

        # Step 1: Normalize input to [0, 1] range
        normalized = (input_lut - input_floor) / (input_ceiling - input_floor)

        # Clamp normalized values to [0, 1] before gamma
        normalized = np.clip(normalized, 0.0, 1.0)

        # Step 2: Apply gamma correction
        gamma_exponent = 100.0 / gamma
        gamma_corrected = np.power(normalized, gamma_exponent)

        # Step 3: Scale to output range
        output_lut = gamma_corrected * (output_ceiling - output_floor) + output_floor

        # Step 4: Clamp to valid range [0, 255]
        output_lut = np.clip(output_lut, 0.0, 255.0)

        return output_lut

    def _apply_normal_huesaturation(
        self, hue: int, saturation: int, lightness: int
    ) -> None:
        """Apply normal mode hue/saturation adjustments."""
        # Apply lightness decrease first (darkening)
        if lightness < 0:
            self._apply_lightness_adjustment(lightness)

        # Apply hue rotation
        if hue != 0:
            self.create_node(
                "feColorMatrix",
                type="hueRotate",
                values=hue,
                color_interpolation_filters="sRGB",
            )

        # Apply saturation adjustment
        if saturation != 0:
            saturate_factor = 1 + (saturation / 100)
            self.create_node(
                "feColorMatrix",
                type="saturate",
                values=saturate_factor,
                color_interpolation_filters="sRGB",
            )

        # Apply lightness increase (brightening)
        if lightness > 0:
            self._apply_lightness_adjustment(lightness)

    def _apply_colorize_mode(self, layer: adjustments.HueSaturation) -> None:
        """Apply colorize mode adjustments."""
        hue, saturation, lightness = layer.colorization

        # Step 1: Desaturate completely
        self.create_node(
            "feColorMatrix",
            type="saturate",
            values=0,
            color_interpolation_filters="sRGB",
        )

        # Step 2: Apply colorization hue rotation
        if hue != 0:
            self.create_node(
                "feColorMatrix",
                type="hueRotate",
                values=hue,
                color_interpolation_filters="sRGB",
            )

        # Step 3: Apply colorization saturation (absolute, not delta)
        # Note: Photoshop's colorization saturation is 0-100, not -100 to +100
        saturate_factor = 1 + (saturation / 100)
        self.create_node(
            "feColorMatrix",
            type="saturate",
            values=saturate_factor,
            color_interpolation_filters="sRGB",
        )

        # Step 4: Apply lightness adjustment
        if lightness != 0:
            self._apply_lightness_adjustment(lightness)

    def _apply_lightness_adjustment(self, lightness: int) -> None:
        """Apply lightness adjustment using feComponentTransfer.

        Args:
            lightness: Lightness value from -100 (darkest) to +100 (brightest).
        """
        if lightness < 0:
            # Darken: compress whites toward black
            slope: float = 1 + (lightness / 100)
            intercept: float = 0
        else:
            # Brighten: compress blacks toward white
            slope = 1 - (lightness / 100)
            intercept = lightness / 100

        fe_component = self.create_node(
            "feComponentTransfer", color_interpolation_filters="sRGB"
        )
        with self.set_current(fe_component):
            for func in ["feFuncR", "feFuncG", "feFuncB"]:
                self.create_node(func, type="linear", slope=slope, intercept=intercept)

    def _create_filter(
        self, layer: layers.AdjustmentLayer, name: str, **attrib: str
    ) -> tuple[ET.Element, ET.Element]:
        """Create SVG filter structure for the adjustment layer."""
        wrapper = self._wrap_backdrop("symbol", id=self.auto_id("backdrop"))
        filter = self.create_node("filter", id=self.auto_id(name))
        # Backdrop use.
        self.create_node(
            "use",
            href=svg_utils.get_uri(wrapper),
        )
        # Apply filter to the use.
        use = self.create_node(
            "use",
            href=svg_utils.get_uri(wrapper),
            filter=svg_utils.get_funciri(filter),
            class_=name,
            **attrib,  # type: ignore[arg-type]  # Clipping context etc.
        )
        self.set_layer_attributes(layer, use)
        use = self.apply_mask(layer, use)
        return filter, use

    def _wrap_backdrop(self, tag: str = "symbol", **attrib: str) -> ET.Element:
        """Wrap previous nodes into a container node for adjustment application."""
        # NOTE: Find the appropriate container in the clipping context,
        # as the parent is mask or clipPath.
        if self.current.tag == "clipPath" or self.current.tag == "mask":
            logger.warning(
                "Wrapping backdrop inside clipping/mask context is not supported yet."
            )
        siblings = list(self.current)
        if not siblings:
            logger.warning("No backdrop elements found to wrap for adjustment.")
        wrapper = self.create_node(tag, **attrib)  # type: ignore[arg-type]
        for node in siblings:
            self.current.remove(node)
            wrapper.append(node)
        return wrapper
