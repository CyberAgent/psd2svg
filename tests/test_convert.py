import logging
import os
from pathlib import Path

import pytest
from psd_tools import PSDImage
from psd_tools.api.adjustments import ColorBalance, Levels

from psd2svg import convert
from psd2svg.core.converter import Converter
from psd2svg.eval import compute_conversion_quality
from tests.conftest import get_fixture


@pytest.mark.parametrize(
    "psd_file",
    [
        "layer-types/black-and-white.psd",
        "layer-types/brightness-contrast.psd",
        "layer-types/channel-mixer.psd",
        "layer-types/color-balance.psd",
        "layer-types/curves-with-vectormask.psd",
        "layer-types/curves.psd",
        "layer-types/exposure.psd",
        "layer-types/gradient-map-v3-classic.psd",
        "layer-types/gradient-map-v3-linear.psd",
        "layer-types/gradient-map.psd",
        "layer-types/hue-saturation.psd",
        "layer-types/invert.psd",
        "layer-types/levels.psd",
        "layer-types/photo-filter.psd",
        "layer-types/selective-color.psd",
        "layer-types/threshold.psd",
        "layer-types/vibrance.psd",
        "layer-types/gradient-fill.psd",
        "layer-types/solid-color-fill.psd",
        "layer-types/pattern-fill.psd",
        "layer-types/artboard.psd",
        "layer-types/group.psd",
        "layer-types/pixel-layer.psd",
        "layer-types/shape-layer.psd",
        "layer-types/smartobject-layer.psd",
        "layer-types/type-layer.psd",
    ],
)
def test_convert(tmp_path: Path, psd_file: str) -> None:
    """Test conversion succeeds for various file types."""
    input_path = get_fixture(psd_file)
    output_path = str(tmp_path / "output.svg")
    images_path = str(tmp_path / "images")
    convert(input_path, output_path, images_path)
    assert os.path.exists(output_path)


def evaluate_quality(psd_file: str, quality: float) -> None:
    """Generic quality evaluation helper."""
    psdimage = PSDImage.open(get_fixture(psd_file))
    score = compute_conversion_quality(psdimage, "MSE")
    logging.info(f"MSE for {psd_file}: {score} vs. {quality}")
    assert score < quality, f"MSE is too high: {score} vs. {quality}"


@pytest.mark.parametrize(
    "psd_file, quality",
    [
        pytest.param("layer-types/artboard.psd", 0.01),
        pytest.param("layer-types/group.psd", 0.01),
        pytest.param("layer-types/pixel-layer.psd", 0.01),
        pytest.param(
            "layer-types/shape-layer.psd", 0.02
        ),  # Shape layers may require a bit more tolerance
        pytest.param("layer-types/smartobject-layer.psd", 0.01),
        pytest.param(
            "layer-types/type-layer.psd",
            0.01,
            marks=pytest.mark.xfail(
                reason="Text layer support is not fully implemented."
            ),
        ),
        pytest.param("layer-types/gradient-fill.psd", 0.01),
        pytest.param("layer-types/solid-color-fill.psd", 0.01),
        pytest.param("layer-types/pattern-fill.psd", 0.01),
    ],
)
def test_layer_types_quality(psd_file: str, quality: float) -> None:
    """Test conversion quality for various layer types."""
    evaluate_quality(psd_file, quality)


@pytest.mark.parametrize(
    "psd_file, quality",
    [
        pytest.param(
            "clipping/group-with-clip-stroke-effect.psd",
            0.02,
            marks=pytest.mark.xfail(reason="Stroke effect is inaccurate."),
        ),
        pytest.param("clipping/group-with-clip-stroke.psd", 0.02),
        pytest.param("clipping/pixel-with-clip-stroke-effect.psd", 0.02),
        pytest.param("clipping/shape-with-clip-stroke-effect.psd", 0.02),
        pytest.param("clipping/shape-with-clip-stroke.psd", 0.02),
        pytest.param("clipping/shape-with-clip2-stroke.psd", 0.02),
        pytest.param("clipping/shape-with-invisible-clip.psd", 0.01),
        pytest.param(
            "clipping/shape-with-blend.psd", 0.01
        ),  # Blend mode for clipping shape layer
        pytest.param(
            "clipping/pixel-with-blend.psd", 0.01
        ),  # Blend mode for clipping pixel layer
        # Tests for clipping with transforms.
        pytest.param("clipping/clipping-1-raster-with-transform.psd", 0.005),
        pytest.param("clipping/clipping-1-vector-with-transform.psd", 0.005),
        pytest.param("clipping/clipping-2-raster-with-transform.psd", 0.005),
        pytest.param("clipping/clipping-2-vector-with-transform.psd", 0.005),
        pytest.param("clipping/clipping-3-raster-with-transform.psd", 0.005),
        pytest.param("clipping/clipping-3-vector-with-transform.psd", 0.005),
        # Tests for clipping with masks and transforms.
        pytest.param(
            "clipping/clipping-4-pixel-mask-with-transform-w-mask.psd",
            0.001,
        ),
        pytest.param(
            "clipping/clipping-4-pixel-mask-with-transform-wo-mask.psd",
            0.001,
        ),
        pytest.param(
            "clipping/clipping-4-shape-mask-with-transform-w-mask.psd",
            0.001,
        ),
        pytest.param(
            "clipping/clipping-4-shape-mask-with-transform-wo-mask.psd",
            0.001,
        ),
        pytest.param(
            "clipping/clipping-4-shape-mask-clippath.psd",
            0.001,
        ),
        pytest.param(
            "clipping/clipping-5-mask-with-effect.psd",
            0.001,
        ),
    ],
)
def test_clipping(psd_file: str, quality: float) -> None:
    """Test converting PSD files with clipping masks to SVG."""
    evaluate_quality(psd_file, quality)


@pytest.mark.parametrize(
    "psd_file, quality",
    [
        pytest.param("blend-modes/effect-color-burn.psd", 0.01),
        pytest.param("blend-modes/effect-color-dodge.psd", 0.01),
        pytest.param("blend-modes/effect-color.psd", 0.01),
        pytest.param("blend-modes/effect-darken.psd", 0.01),
        pytest.param("blend-modes/effect-darker-color.psd", 0.01),
        pytest.param("blend-modes/effect-difference.psd", 0.01),
        pytest.param(
            "blend-modes/effect-dissolve.psd", 0.01
        ),  # Dissolve is not supported, but MSE is low.
        pytest.param(
            "blend-modes/effect-divide.psd",
            0.01,
            marks=pytest.mark.xfail(reason="Divide is not accurately supported."),
        ),
        pytest.param("blend-modes/effect-exclusion.psd", 0.01),
        pytest.param("blend-modes/effect-hard-light.psd", 0.01),
        pytest.param(
            "blend-modes/effect-hard-mix.psd",
            0.01,
            marks=pytest.mark.xfail(reason="Hard mix is not accurately supported."),
        ),
        pytest.param("blend-modes/effect-hue.psd", 0.01),
        pytest.param("blend-modes/effect-lighten.psd", 0.01),
        pytest.param("blend-modes/effect-lighter-color.psd", 0.01),
        pytest.param(
            "blend-modes/effect-linear-burn.psd",
            0.01,
            marks=pytest.mark.xfail(reason="Linear burn is not accurately supported."),
        ),
        pytest.param(
            "blend-modes/effect-linear-dodge.psd",
            0.01,
            marks=pytest.mark.xfail(reason="Linear dodge is not accurately supported."),
        ),
        pytest.param(
            "blend-modes/effect-linear-light.psd",
            0.01,
            marks=pytest.mark.xfail(reason="Linear light is not accurately supported."),
        ),
        pytest.param("blend-modes/effect-luminosity.psd", 0.01),
        pytest.param("blend-modes/effect-multiply.psd", 0.01),
        pytest.param("blend-modes/effect-normal.psd", 0.01),
        pytest.param("blend-modes/effect-overlay.psd", 0.01),
        pytest.param(
            "blend-modes/effect-pin-light.psd",
            0.01,
            marks=pytest.mark.xfail(reason="Pin light is not accurately supported."),
        ),
        pytest.param("blend-modes/effect-saturation.psd", 0.01),
        pytest.param("blend-modes/effect-screen.psd", 0.01),
        pytest.param("blend-modes/effect-soft-light.psd", 0.01),
        pytest.param(
            "blend-modes/effect-subtract.psd",
            0.01,
            marks=pytest.mark.xfail(reason="Subtract is not accurately supported."),
        ),
        pytest.param(
            "blend-modes/effect-vivid-light.psd",
            0.01,
            marks=pytest.mark.xfail(reason="Vivid light is not accurately supported."),
        ),
    ],
)
def test_blend_mode_quality(psd_file: str, quality: float) -> None:
    """Test conversion quality for various blend modes."""
    evaluate_quality(psd_file, quality)


@pytest.mark.parametrize(
    "psd_file",
    [
        "shapes/triangle-1.psd",
        "shapes/triangle-2.psd",
        "shapes/custom-1.psd",  # Complex custom shape with a subpath
        "shapes/custom-2.psd",  # Complex custom shape with a subpath and a mask
        "shapes/custom-3.psd",  # Complex custom shape with composite subpaths
        "shapes/ellipse-1.psd",
        "shapes/ellipse-2.psd",
        "shapes/ellipse-3.psd",
        "shapes/line-1.psd",
        "shapes/line-2.psd",
        "shapes/polygon-1.psd",
        "shapes/polygon-2.psd",
        "shapes/rectangle-1.psd",
        "shapes/rectangle-2.psd",
        "shapes/rectangle-3.psd",
        "shapes/rectangle-4.psd",
        "shapes/rectangle-5.psd",
        "shapes/rectangle-6-transform-mask.psd",  # Rectangle with transform and mask
        "shapes/star-1.psd",
        "shapes/star-2.psd",
        "shapes/multi-1.psd",  # Union + Subtract
        "shapes/multi-2.psd",  # Union + Subtract + Intersect
        "shapes/multi-3.psd",  # Union + Subtract + Union
        # Union + XOR with composite subpaths, requires 0.02 threshold
        "shapes/multi-4.psd",
        "shapes/multi-5-mask.psd",  # Multi-shape with mask
        "shapes/multi-5-mask-disabled.psd",  # Multi-shape with disabled mask
    ],
)
def test_shapes(psd_file: str) -> None:
    """Test conversion quality of shape layers."""
    evaluate_quality(psd_file, 0.02)


def test_enable_live_shapes_flag() -> None:
    """Test that disabling live shapes works."""
    psdimage = PSDImage.open(get_fixture("shapes/rectangle-1.psd"))

    converter = Converter(psdimage, enable_live_shapes=True)
    converter.build()
    assert converter.svg.find(".//rect") is not None, (
        "Expected <rect> element in SVG with live shapes enabled."
    )
    assert converter.svg.find(".//path") is None, (
        "Did not expect <path> element in SVG with live shapes enabled."
    )

    converter = Converter(psdimage, enable_live_shapes=False)
    converter.build()
    assert converter.svg.find(".//rect") is None, (
        "Did not expect <rect> element in SVG with live shapes disabled."
    )
    assert converter.svg.find(".//path") is not None, (
        "Expected <path> element in SVG with live shapes disabled."
    )


def test_enable_title_flag() -> None:
    """Test that enabling title elements works."""
    psdimage = PSDImage.open(get_fixture("layer-types/group.psd"))

    # Test with enable_title=True
    converter = Converter(psdimage, enable_title=True)
    converter.build()
    title_elements = converter.svg.findall(".//title")
    assert len(title_elements) > 0, (
        "Expected <title> elements in SVG with enable_title=True."
    )

    # Test with enable_title=False (default behavior)
    converter = Converter(psdimage, enable_title=False)
    converter.build()
    title_elements = converter.svg.findall(".//title")
    assert len(title_elements) == 0, (
        "Did not expect <title> elements in SVG with enable_title=False."
    )


@pytest.mark.parametrize(
    "psd_file",
    [
        "paint/transparent-1.psd",
        "paint/color-1.psd",
        "paint/color-2.psd",  # Fill opacity test for shape layer
        "paint/color-3.psd",  # Fill opacity test for raster layer
    ],
)
def test_paint_color(psd_file: str) -> None:
    """Test conversion quality for painting."""
    evaluate_quality(psd_file, 0.005)


@pytest.mark.parametrize(
    "psd_file",
    [
        "paint/linear-gradient-1.psd",
        "paint/linear-gradient-2.psd",  # Fill opacity test
        # Gradient interpolation methods: quality may vary.
        "paint/linear-gradient-3-interp-classic.psd",  # Classic interpolation
        "paint/linear-gradient-3-interp-linear.psd",  # Linear interpolation
        "paint/linear-gradient-3-interp-perceptual.psd",  # Perceptual interpolation
        "paint/linear-gradient-3-interp-smooth.psd",  # Smooth interpolation
        pytest.param(
            "paint/linear-gradient-3-interp-stripes.psd",
            marks=pytest.mark.xfail(reason="Stripes interpolation is not supported."),
        ),
        # Gradient alignment tests.
        "paint/linear-gradient-3-align.psd",
        "paint/linear-gradient-3-no-align.psd",
        # Gradient transformation tests.
        "paint/linear-gradient-4-00deg.psd",
        "paint/linear-gradient-4-45deg.psd",
        "paint/linear-gradient-4-90deg.psd",
        "paint/linear-gradient-5-00deg.psd",
        "paint/linear-gradient-5-45deg.psd",
        "paint/linear-gradient-5-90deg.psd",
        "paint/linear-gradient-6-00deg.psd",
        "paint/linear-gradient-6-45deg.psd",
        "paint/linear-gradient-6-90deg.psd",
        # Offset test.
        "paint/linear-gradient-7-offset.psd",
        # Interpolation test.
        "paint/linear-gradient-8-stops.psd",
        # Radial gradients.
        "paint/radial-gradient-1.psd",
    ],
)
def test_paint_gradient(psd_file: str) -> None:
    """Test conversion quality for gradient painting."""
    evaluate_quality(psd_file, 0.005)


@pytest.mark.parametrize(
    "psd_file",
    [
        "paint/pattern-1.psd",
        "paint/pattern-2.psd",  # Transformed pattern
    ],
)
def test_paint_pattern(psd_file: str) -> None:
    """Test conversion quality for pattern painting."""
    evaluate_quality(psd_file, 0.005)


@pytest.mark.parametrize(
    "psd_file",
    [
        "paint/stroke-1-color.psd",
        "paint/stroke-1-gradient.psd",
        "paint/stroke-1-pattern.psd",
    ],
)
def test_paint_stroke(psd_file: str) -> None:
    """Test conversion quality for stroke painting."""
    evaluate_quality(psd_file, 0.005)


@pytest.mark.parametrize(
    "psd_file",
    [
        "effects/color-overlay-1.psd",
        "effects/color-overlay-2.psd",
        pytest.param(
            "effects/color-overlay-3.psd",
            marks=pytest.mark.xfail(reason="Outset stroke is not supported."),
        ),
        "effects/color-overlay-4.psd",
        "effects/color-overlay-5.psd",  # transparent fill opacity test
        "effects/color-overlay-6.psd",  # raster fill opacity and mask test
        "effects/color-overlay-7.psd",  # vector fill opacity and mask test
        "effects/gradient-overlay-1.psd",
        "effects/gradient-overlay-2.psd",
        "effects/gradient-overlay-3.psd",
        "effects/gradient-overlay-4.psd",
        "effects/gradient-overlay-5.psd",
        "effects/gradient-overlay-6.psd",  # fill layer with overlay effect
        "effects/gradient-overlay-7.psd",  # fill layer with overlay effect and offset
        "effects/pattern-overlay-1.psd",  # raster pattern overlay
        "effects/pattern-overlay-2.psd",  # raster pattern overlay with transform
        "effects/pattern-overlay-3.psd",  # shape pattern overlay
        "effects/pattern-overlay-4.psd",  # shape pattern overlay with transform
        "effects/drop-shadow-1.psd",
        "effects/drop-shadow-2.psd",
        "effects/drop-shadow-3.psd",
        "effects/drop-shadow-4.psd",
        pytest.param(
            "effects/drop-shadow-5.psd",
            marks=pytest.mark.xfail(reason="Morphology filter is limited."),
        ),
        "effects/drop-shadow-6.psd",
        "effects/inner-shadow-1.psd",
        "effects/inner-shadow-2.psd",
        "effects/outer-glow-1.psd",
        "effects/outer-glow-2.psd",
        "effects/inner-glow-1.psd",
        "effects/inner-glow-2.psd",
        "effects/inner-glow-3.psd",
        # Multiple overlay effects. Priority is color > gradient > pattern.
        "effects/multiple-overlays-1-all.psd",  # All overlay effects together
        "effects/multiple-overlays-1-no-color.psd",  # Without color overlay
        "effects/multiple-overlays-1-duplicate-colors.psd",  # Duplicate color overlays
    ],
)
def test_effects(psd_file: str) -> None:
    """Test effects quality in the raster format."""
    evaluate_quality(psd_file, 0.01)


@pytest.mark.parametrize(
    "psd_file",
    [
        "effects/stroke-1-raster-color.psd",
        "effects/stroke-1-raster-gradient.psd",
        "effects/stroke-1-raster-pattern.psd",
        "effects/stroke-1-vector-color.psd",
        "effects/stroke-1-vector-gradient.psd",
        "effects/stroke-1-vector-pattern.psd",
        "effects/stroke-2-vector-color.psd",  # Stroke around stroke case.
    ],
)
def test_stroke_effects(psd_file: str) -> None:
    """Test stroke effect quality in the raster format."""
    evaluate_quality(psd_file, 0.01)


@pytest.mark.parametrize(
    "psd_file, quality",
    [
        pytest.param(
            "effects/color-overlay-8-text.psd",
            0.05,
            marks=pytest.mark.requires_arial,
        ),
        pytest.param(
            "effects/drop-shadow-7-text.psd",
            0.05,
            marks=pytest.mark.requires_arial,
        ),
        pytest.param(
            "effects/stroke-3-text.psd",
            0.05,
            marks=pytest.mark.requires_arial,
        ),
    ],
)
def test_text_effects_quality(psd_file: str, quality: float) -> None:
    """Test conversion quality for text layers with effects."""
    evaluate_quality(psd_file, quality)


@pytest.mark.parametrize(
    "psd_file",
    [
        "layer-types/gradient-fill.psd",
        "layer-types/pattern-fill.psd",
        "layer-types/solid-color-fill.psd",
    ],
)
def test_fill_layers(psd_file: str) -> None:
    """Test conversion quality of fill layers."""
    evaluate_quality(psd_file, 0.01)


@pytest.mark.parametrize(
    "psd_file",
    [
        "adjustments/invert-mask.psd",
        "adjustments/invert-clipping-mask.psd",
        pytest.param(
            "adjustments/invert-clippingbase.psd",
            marks=pytest.mark.xfail(
                reason="Adjustment layer for clipping base is not supported."
            ),
        ),
        pytest.param(
            "adjustments/invert-mask-transparent.psd",
            marks=pytest.mark.xfail(
                reason="Transparency is not supported for adjustment layers."
            ),
        ),
    ],
)
def test_adjustment_invert(psd_file: str) -> None:
    """Test conversion quality of invert adjustment layer."""
    evaluate_quality(psd_file, 0.01)


@pytest.mark.parametrize(
    "psd_file",
    [
        "adjustments/posterize-levels4.psd",
        "adjustments/posterize-levels16.psd",
    ],
)
def test_adjustment_posterize(psd_file: str) -> None:
    """Test conversion quality of posterize adjustment layer."""
    evaluate_quality(psd_file, 0.01)


@pytest.mark.parametrize(
    "psd_file",
    [
        "adjustments/huesaturation-h0-s0-l0.psd",
        "adjustments/huesaturation-h+180-s0-l0.psd",
        "adjustments/huesaturation-h-180-s0-l0.psd",
        "adjustments/huesaturation-h0-s+100-l0.psd",
        "adjustments/huesaturation-h0-s-100-l0.psd",
        "adjustments/huesaturation-h0-s0-l+100.psd",
        "adjustments/huesaturation-h0-s0-l-100.psd",
        "adjustments/huesaturation-colorize.psd",
    ],
)
def test_adjustment_huesaturation(psd_file: str) -> None:
    """Test conversion quality of hue/saturation adjustment layer."""
    # Use 0.02 threshold for lightness (RGB approximation of HSL)
    # and extreme hue rotations (±180 degrees have edge case rounding)
    # Use 0.01 for saturation (accurate with feColorMatrix)
    if (
        "l+" in psd_file
        or "l-" in psd_file
        or "h+180" in psd_file
        or "h-180" in psd_file
    ):
        threshold = 0.02
    else:
        threshold = 0.01
    evaluate_quality(psd_file, threshold)


@pytest.mark.parametrize(
    "psd_file",
    [
        "adjustments/exposure-e0.0-o0.0-g1.0.psd",
        "adjustments/exposure-e+4.0-o0.0-g1.0.psd",
        "adjustments/exposure-e-4.0-o0.0-g1.0.psd",
        "adjustments/exposure-e0.0-o+0.4-g1.0.psd",
        "adjustments/exposure-e0.0-o-0.4-g1.0.psd",
        "adjustments/exposure-e0.0-o0.0-g4.0.psd",
        "adjustments/exposure-e0.0-o0.0-g0.4.psd",
    ],
)
def test_adjustment_exposure(psd_file: str) -> None:
    """Test conversion quality of exposure adjustment layer."""
    # Use adaptive threshold based on parameter extremes
    # Extreme exposure or gamma values may have higher numerical error
    if (
        "e+4.0" in psd_file
        or "e-4.0" in psd_file
        or "g4.0" in psd_file
        or "g0.4" in psd_file
    ):
        threshold = 0.02
    else:
        threshold = 0.01
    evaluate_quality(psd_file, threshold)


@pytest.mark.parametrize(
    "psd_file",
    [
        "adjustments/brightnesscontrast-b0-c0.psd",
        "adjustments/brightnesscontrast-b+150-c0.psd",
        "adjustments/brightnesscontrast-b-150-c0.psd",
        "adjustments/brightnesscontrast-b0-c+100.psd",
        "adjustments/brightnesscontrast-b0-c-50.psd",
    ],
)
def test_adjustment_brightnesscontrast(psd_file: str) -> None:
    """Test conversion quality of brightness/contrast adjustment layer."""
    # Use adaptive threshold based on parameter extremes
    # Note: Extreme negative brightness has higher error due to differences between
    # Photoshop's complex curves-based algorithm and our linear approximation
    if "b-150" in psd_file:
        threshold = 0.09  # Higher tolerance for extreme negative brightness
    elif "b+150" in psd_file or "c+100" in psd_file or "c-50" in psd_file:
        threshold = 0.02
    else:
        threshold = 0.01
    evaluate_quality(psd_file, threshold)


@pytest.mark.parametrize(
    "psd_file",
    [
        "adjustments/threshold-1.psd",
        "adjustments/threshold-128.psd",
        "adjustments/threshold-255.psd",
    ],
)
def test_adjustment_threshold(psd_file: str) -> None:
    """Test conversion quality of threshold adjustment layer."""
    # Threshold is a binary operation with some tolerance for anti-aliasing
    # threshold-128 has slightly higher error due to more edge pixels
    if "threshold-128" in psd_file:
        threshold = 0.03
    else:
        threshold = 0.02
    evaluate_quality(psd_file, threshold)


@pytest.mark.parametrize(
    "psd_file,threshold",
    [
        ("adjustments/colorbalance-s0_0_0-m0_0_0-h0_0_0.psd", 0.01),
        ("adjustments/colorbalance-s+50_0_-50-m0_0_0-h0_0_0.psd", 0.03),
        ("adjustments/colorbalance-s0_0_0-m-50_0_+50-h0_0_0.psd", 0.02),
        ("adjustments/colorbalance-s0_0_0-m0_0_0-h0_-50_-50.psd", 0.03),
        # Note: This file demonstrates neutral color preservation limitation
        # White pixels become tinted (RGB(255,127,127)) vs Photoshop keeping them white
        ("adjustments/colorbalance-s0_0_0-m0_0_0-h0_-50_-50-nolum.psd", 0.04),
        (
            "adjustments/colorbalance-s+100_+100_+100-m+100_+100_+100-h+100_+100_+100.psd",
            0.08,
        ),
        # Extreme negative adjustments marked as xfail due to high error from
        # color clipping, neutral color preservation, and grayscale approximation
        pytest.param(
            "adjustments/colorbalance-s-100_-100_-100-m-100_-100_-100-h-100_-100_-100.psd",
            0.36,
            marks=pytest.mark.xfail(
                reason=(
                    "Extreme negative adjustment with preserve luminosity has "
                    "high error (MSE ~0.35) due to color clipping and neutral "
                    "color preservation limitation"
                ),
                strict=False,
            ),
        ),
        # Note: -nolum suffix files have luminosity=0 (preserve luminosity DISABLED)
        (
            "adjustments/colorbalance-s+100_+100_+100-m+100_+100_+100-h+100_+100_+100-nolum.psd",
            0.02,
        ),
        pytest.param(
            "adjustments/colorbalance-s-100_-100_-100-m-100_-100_-100-h-100_-100_-100-nolum.psd",
            0.30,
            marks=pytest.mark.xfail(
                reason="Extreme negative adjustment has high error (MSE ~0.30) "
                "due to color clipping and neutral color preservation limitation",
                strict=False,
            ),
        ),
    ],
)
def test_adjustment_colorbalance(psd_file: str, threshold: float) -> None:
    """Test conversion quality of color balance adjustment layer.

    Note: Extreme negative adjustments (-100) are marked as xfail due to
    high error from color clipping, neutral color preservation, and the
    grayscale approximation used for luminance.
    """
    evaluate_quality(psd_file, threshold)


def test_adjustment_colorbalance_noop() -> None:
    """Test that ColorBalance with zero adjustments returns None (no filter created)."""
    # Load the no-op test fixture
    psd = PSDImage.open(
        get_fixture("adjustments/colorbalance-s0_0_0-m0_0_0-h0_0_0.psd")
    )

    # Find the ColorBalance layer
    colorbalance_layer = None
    for layer in psd.descendants():
        if layer.kind == "colorbalance":
            colorbalance_layer = layer
            break

    assert colorbalance_layer is not None, "ColorBalance layer not found in fixture"
    assert isinstance(colorbalance_layer, ColorBalance)

    # Verify parameters are all zero
    assert colorbalance_layer.shadows == (0, 0, 0)
    assert colorbalance_layer.midtones == (0, 0, 0)
    assert colorbalance_layer.highlights == (0, 0, 0)

    # Create converter and test the method directly
    converter = Converter(psd)

    # Call add_color_balance_adjustment directly
    result = converter.add_color_balance_adjustment(colorbalance_layer)

    # Should return None for no-op case
    assert result is None, (
        "Expected None for no-op ColorBalance, but filter was created"
    )


@pytest.mark.parametrize(
    ("psd_file", "threshold"),
    [
        ("adjustments/curves-rgb.psd", 0.02),
        ("adjustments/curves-r.psd", 0.02),
        ("adjustments/curves-g.psd", 0.02),
        ("adjustments/curves-b.psd", 0.01),
        ("adjustments/curves-r-g-b.psd", 0.01),
        ("adjustments/curves-rgb-r.psd", 0.02),
        ("adjustments/curves-rgb-extreme.psd", 0.01),
    ],
)
def test_adjustment_curves(psd_file: str, threshold: float) -> None:
    """Test conversion quality of curves adjustment layer."""
    evaluate_quality(psd_file, threshold)


@pytest.mark.parametrize(
    ("psd_file", "threshold"),
    [
        ("adjustments/levels-identity.psd", 0.01),
        ("adjustments/levels-rgb-1.psd", 0.01),
        ("adjustments/levels-rgb-2.psd", 0.01),
        ("adjustments/levels-r-g-b.psd", 0.01),
        ("adjustments/levels-rgb-extreme-1.psd", 0.02),
        (
            "adjustments/levels-rgb-extreme-2.psd",
            0.04,
        ),  # Higher threshold for extreme darkening
        ("adjustments/levels-rgb-extreme-3.psd", 0.01),
        ("adjustments/levels-rgb-extreme-4.psd", 0.01),
        ("adjustments/levels-rgb-invert.psd", 0.01),
    ],
)
def test_adjustment_levels(psd_file: str, threshold: float) -> None:
    """Test conversion quality of levels adjustment layer."""
    evaluate_quality(psd_file, threshold)


def test_adjustment_levels_noop() -> None:
    """Test that Levels with identity adjustments returns None (no filter created)."""
    # Load the identity test fixture
    psd = PSDImage.open(get_fixture("adjustments/levels-identity.psd"))

    # Find the Levels layer
    levels_layer = None
    for layer in psd.descendants():
        if layer.kind == "levels":
            levels_layer = layer
            break

    assert levels_layer is not None, "Levels layer not found in fixture"
    assert isinstance(levels_layer, Levels)

    # Verify parameters are identity
    for i in range(4):
        record = levels_layer.data[i]
        assert record.input_floor == 0
        assert record.input_ceiling == 255
        assert record.output_floor == 0
        assert record.output_ceiling == 255
        assert record.gamma == 100

    # Create converter and test the method directly
    converter = Converter(psd)

    # Call add_levels_adjustment directly
    result = converter.add_levels_adjustment(levels_layer)

    # Should return None for identity case
    assert result is None, "Expected None for identity Levels, but filter was created"


@pytest.mark.parametrize(
    "psd_file",
    [
        "texts/paragraph-shapetype0-justification0.psd",
        "texts/paragraph-shapetype0-justification1.psd",
        "texts/paragraph-shapetype0-justification2.psd",
    ],
)
def test_text_paragraph_justification(psd_file: str) -> None:
    """Test text paragraph justification handling."""
    # We need a higher threshold depending on the available fonts.
    evaluate_quality(psd_file, 0.02)


def test_convert_with_options(tmp_path: Path) -> None:
    """Test convert() function with various options."""
    input_path = get_fixture("shapes/rectangle-1.psd")
    output_path = str(tmp_path / "output.svg")
    images_path = str(tmp_path / "images")

    # Test with enable_text=False
    convert(
        input_path,
        output_path,
        image_prefix=images_path,
        enable_text=False,
    )
    assert os.path.exists(output_path)

    # Test with enable_live_shapes=False
    output_path2 = str(tmp_path / "output2.svg")
    convert(
        input_path,
        output_path2,
        image_prefix=images_path,
        enable_live_shapes=False,
    )
    assert os.path.exists(output_path2)

    # Test with enable_title=False
    output_path3 = str(tmp_path / "output3.svg")
    convert(
        input_path,
        output_path3,
        image_prefix=images_path,
        enable_title=False,
    )
    assert os.path.exists(output_path3)

    # Test with different image_format
    output_path4 = str(tmp_path / "output4.svg")
    convert(
        input_path,
        output_path4,
        image_prefix=images_path,
        image_format="png",
    )
    assert os.path.exists(output_path4)

    # Test with text_letter_spacing_offset
    output_path5 = str(tmp_path / "output5.svg")
    convert(
        input_path,
        output_path5,
        image_prefix=images_path,
        text_letter_spacing_offset=-0.015,
    )
    assert os.path.exists(output_path5)


def test_image_prefix_dot(tmp_path: Path) -> None:
    """Test image_prefix='.' saves images in same directory as SVG."""
    input_path = get_fixture("layer-types/pixel-layer.psd")

    # Create a subdirectory for output
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    output_path = str(output_dir / "pixel-layer.svg")

    # Convert with image_prefix="."
    convert(input_path, output_path, image_prefix=".")

    # Check that SVG exists
    assert os.path.exists(output_path)

    # Check that image file exists in the same directory
    expected_image = output_dir / "01.webp"
    assert expected_image.exists(), f"Expected image file at {expected_image}"

    # Verify the href in the SVG is correct (relative path)
    with open(output_path, "r", encoding="utf-8") as f:
        svg_content = f.read()
        assert 'href="01.webp"' in svg_content, "Expected href='01.webp' in SVG"


def test_image_prefix_with_subdirectory(tmp_path: Path) -> None:
    """Test image_prefix with subdirectory path."""
    input_path = get_fixture("layer-types/pixel-layer.psd")
    output_path = str(tmp_path / "output.svg")

    # Convert with image_prefix="images/"
    convert(input_path, output_path, image_prefix="images/img")

    # Check that SVG exists
    assert os.path.exists(output_path)

    # Check that image file exists in subdirectory
    expected_image = tmp_path / "images" / "img01.webp"
    assert expected_image.exists(), f"Expected image file at {expected_image}"

    # Verify the href in the SVG is correct (relative path)
    with open(output_path, "r", encoding="utf-8") as f:
        svg_content = f.read()
        # On Windows, path separator might be different
        assert (
            'href="images/img01.webp"' in svg_content
            or 'href="images\\img01.webp"' in svg_content
        ), "Expected href='images/img01.webp' in SVG"


def test_image_prefix_nested_output_directory(tmp_path: Path) -> None:
    """Test image_prefix with nested output directory structure."""
    input_path = get_fixture("layer-types/pixel-layer.psd")

    # Create nested directory structure
    output_dir = tmp_path / "nested" / "deep" / "path"
    output_dir.mkdir(parents=True)
    output_path = str(output_dir / "output.svg")

    # Convert with image_prefix="."
    convert(input_path, output_path, image_prefix=".")

    # Check that SVG exists
    assert os.path.exists(output_path)

    # Check that image file exists in the same directory
    expected_image = output_dir / "01.webp"
    assert expected_image.exists(), f"Expected image file at {expected_image}"

    # Verify the href in the SVG is correct
    with open(output_path, "r", encoding="utf-8") as f:
        svg_content = f.read()
        assert 'href="01.webp"' in svg_content, "Expected href='01.webp' in SVG"
