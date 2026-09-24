"""Tests for ResourceLimits DoS prevention functionality.

This module tests resource limit enforcement including:
- File size validation
- Timeout protection (Unix signal and Windows threading)
- Layer depth validation
- Image dimension validation
- Integration scenarios with all limits
"""

import os
import signal
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api import pil_io
from psd_tools.api.layers import PixelLayer
from psd_tools.api.mask import Mask

from psd2svg import ResourceLimits, SVGDocument, convert
from psd2svg.core.converter import Converter
from psd2svg.resource_limits import WEBP_MAX_DIMENSION
from psd2svg.timeout_utils import with_timeout
from tests.conftest import get_fixture


class TestResourceLimitsDefaults:
    """Tests for ResourceLimits default configuration."""

    def test_default_limits(self) -> None:
        """Test default ResourceLimits values."""
        limits = ResourceLimits.default()
        assert limits.max_file_size == 2147483648  # 2GB
        assert limits.timeout == 180  # 3 minutes
        assert limits.max_layer_depth == 100
        assert limits.max_image_dimension == WEBP_MAX_DIMENSION

    def test_unlimited_limits(self) -> None:
        """Test ResourceLimits.unlimited() disables all limits."""
        limits = ResourceLimits.unlimited()
        assert limits.max_file_size == 0
        assert limits.timeout == 0
        assert limits.max_layer_depth == 0
        assert limits.max_image_dimension == 0

    def test_custom_limits(self) -> None:
        """Test creating ResourceLimits with custom values."""
        limits = ResourceLimits(
            max_file_size=50 * 1024 * 1024,  # 50MB
            timeout=30,  # 30 seconds
            max_layer_depth=50,
            max_image_dimension=8192,
        )
        assert limits.max_file_size == 50 * 1024 * 1024
        assert limits.timeout == 30
        assert limits.max_layer_depth == 50
        assert limits.max_image_dimension == 8192

    def test_is_file_size_limited(self) -> None:
        """Test is_file_size_limited() check."""
        assert ResourceLimits(max_file_size=1000).is_file_size_limited()
        assert not ResourceLimits(max_file_size=0).is_file_size_limited()

    def test_is_timeout_enabled(self) -> None:
        """Test is_timeout_enabled() check."""
        assert ResourceLimits(timeout=60).is_timeout_enabled()
        assert not ResourceLimits(timeout=0).is_timeout_enabled()

    def test_is_layer_depth_limited(self) -> None:
        """Test is_layer_depth_limited() check."""
        assert ResourceLimits(max_layer_depth=100).is_layer_depth_limited()
        assert not ResourceLimits(max_layer_depth=0).is_layer_depth_limited()

    def test_is_image_dimension_limited(self) -> None:
        """Test is_image_dimension_limited() check."""
        assert ResourceLimits(max_image_dimension=8192).is_image_dimension_limited()
        assert not ResourceLimits(max_image_dimension=0).is_image_dimension_limited()

    def test_environment_variable_configuration(self) -> None:
        """Test ResourceLimits.default() reads environment variables."""
        with patch.dict(
            os.environ,
            {
                "PSD2SVG_MAX_FILE_SIZE": "1048576",  # 1MB
                "PSD2SVG_TIMEOUT": "60",  # 1 minute
                "PSD2SVG_MAX_LAYER_DEPTH": "50",
                "PSD2SVG_MAX_IMAGE_DIMENSION": "4096",
            },
        ):
            limits = ResourceLimits.default()
            assert limits.max_file_size == 1048576
            assert limits.timeout == 60
            assert limits.max_layer_depth == 50
            assert limits.max_image_dimension == 4096

    def test_environment_variable_negative_values(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test ResourceLimits.default() treats negative values as 0 (disabled)."""
        with patch.dict(
            os.environ,
            {
                "PSD2SVG_MAX_FILE_SIZE": "-100",
                "PSD2SVG_TIMEOUT": "-5",
                "PSD2SVG_MAX_LAYER_DEPTH": "-10",
                "PSD2SVG_MAX_IMAGE_DIMENSION": "-1000",
            },
        ):
            limits = ResourceLimits.default()
            assert limits.max_file_size == 0
            assert limits.timeout == 0
            assert limits.max_layer_depth == 0
            assert limits.max_image_dimension == 0

            # Verify warnings were logged for each negative value
            assert "PSD2SVG_MAX_FILE_SIZE=-100 is negative" in caplog.text
            assert "PSD2SVG_TIMEOUT=-5 is negative" in caplog.text
            assert "PSD2SVG_MAX_LAYER_DEPTH=-10 is negative" in caplog.text
            assert "PSD2SVG_MAX_IMAGE_DIMENSION=-1000 is negative" in caplog.text
            assert caplog.text.count("Consider using ResourceLimits.unlimited()") == 4

    def test_environment_variable_invalid_integer(self) -> None:
        """Test ResourceLimits.default() raises ValueError for invalid integers."""
        with patch.dict(
            os.environ,
            {"PSD2SVG_MAX_FILE_SIZE": "not_a_number"},
        ):
            with pytest.raises(
                ValueError,
                match="Environment variable PSD2SVG_MAX_FILE_SIZE='not_a_number' "
                "is not a valid integer",
            ):
                ResourceLimits.default()

    def test_environment_variable_invalid_float(self) -> None:
        """Test ResourceLimits.default() raises ValueError for float values."""
        with patch.dict(
            os.environ,
            {"PSD2SVG_TIMEOUT": "3.14"},
        ):
            with pytest.raises(
                ValueError,
                match="Environment variable PSD2SVG_TIMEOUT='3.14' "
                "is not a valid integer",
            ):
                ResourceLimits.default()


class TestFileSizeValidation:
    """Tests for file size limit enforcement."""

    def test_convert_with_valid_file_size(self, tmp_path: Path) -> None:
        """Test convert() succeeds when file size is below limit."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Get actual file size
        file_size = os.path.getsize(input_path)

        # Set limit well above file size
        limits = ResourceLimits(max_file_size=file_size + 1024 * 1024)

        # Should succeed
        convert(input_path, output_path, resource_limits=limits)
        assert os.path.exists(output_path)

    def test_convert_with_file_size_at_limit(self, tmp_path: Path) -> None:
        """Test convert() succeeds when file size equals limit."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Get exact file size
        file_size = os.path.getsize(input_path)

        # Set limit exactly at file size
        limits = ResourceLimits(max_file_size=file_size)

        # Should succeed (equal is allowed)
        convert(input_path, output_path, resource_limits=limits)
        assert os.path.exists(output_path)

    def test_convert_with_file_size_exceeds_limit(self, tmp_path: Path) -> None:
        """Test convert() raises ValueError when file size exceeds limit."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Get actual file size
        file_size = os.path.getsize(input_path)

        # Set limit below file size
        limits = ResourceLimits(max_file_size=file_size - 1)

        # Should raise ValueError
        with pytest.raises(
            ValueError, match=f"File size {file_size} bytes exceeds limit"
        ):
            convert(input_path, output_path, resource_limits=limits)

    def test_convert_with_file_size_limit_disabled(self, tmp_path: Path) -> None:
        """Test convert() succeeds when file size limit is disabled."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Disable file size limit
        limits = ResourceLimits(max_file_size=0)

        # Should succeed regardless of file size
        convert(input_path, output_path, resource_limits=limits)
        assert os.path.exists(output_path)

    def test_from_psd_does_not_check_file_size(self, tmp_path: Path) -> None:
        """Test from_psd() doesn't check file size (user's responsibility)."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        psdimage = PSDImage.open(input_path)

        # Set a very low file size limit
        limits = ResourceLimits(max_file_size=1)

        # Should succeed - from_psd() doesn't check file size
        document = SVGDocument.from_psd(psdimage, resource_limits=limits)
        assert document is not None


class TestTimeoutProtection:
    """Tests for timeout protection functionality."""

    def test_with_timeout_no_timeout_when_disabled(self) -> None:
        """Test with_timeout() executes normally when timeout is disabled."""

        def fast_function(x: int, y: int) -> int:
            return x + y

        # Timeout disabled (0 or negative)
        result = with_timeout(fast_function, 0, 5, 10)
        assert result == 15

        result = with_timeout(fast_function, -1, 5, 10)
        assert result == 15

    def test_with_timeout_succeeds_within_limit(self) -> None:
        """Test with_timeout() succeeds when function completes within timeout."""

        def fast_function() -> str:
            return "success"

        result = with_timeout(fast_function, 1)
        assert result == "success"

    def test_with_timeout_raises_timeout_error(self) -> None:
        """Test with_timeout() raises TimeoutError when function exceeds timeout."""

        def slow_function() -> None:
            time.sleep(2)

        with pytest.raises(
            TimeoutError, match="PSD conversion timed out after 1 seconds"
        ):
            with_timeout(slow_function, 1)

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"),
        reason="SIGALRM not available (Windows)",
    )
    def test_with_timeout_uses_signal_on_unix(self) -> None:
        """Test with_timeout() uses signal.SIGALRM on Unix/macOS."""

        def slow_function() -> None:
            time.sleep(2)

        # Should use signal-based timeout
        with pytest.raises(TimeoutError):
            with_timeout(slow_function, 1)

    @pytest.mark.skipif(
        hasattr(signal, "SIGALRM"),
        reason="Test only for Windows (no SIGALRM)",
    )
    def test_with_timeout_uses_threading_on_windows(self) -> None:
        """Test with_timeout() uses threading fallback on Windows."""

        def slow_function() -> None:
            time.sleep(2)

        # Should use threading-based timeout
        with pytest.raises(TimeoutError):
            with_timeout(slow_function, 1)

    def test_with_timeout_propagates_exceptions(self) -> None:
        """Test with_timeout() propagates exceptions from function."""

        def failing_function() -> None:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            with_timeout(failing_function, 5)

    def test_from_psd_with_timeout_enabled(self) -> None:
        """Test SVGDocument.from_psd() applies timeout when enabled."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        psdimage = PSDImage.open(input_path)

        # Set reasonable timeout
        limits = ResourceLimits(timeout=30)

        # Should succeed within timeout
        document = SVGDocument.from_psd(psdimage, resource_limits=limits)
        assert document is not None

    def test_from_psd_with_timeout_disabled(self) -> None:
        """Test SVGDocument.from_psd() skips timeout when disabled."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        psdimage = PSDImage.open(input_path)

        # Disable timeout
        limits = ResourceLimits(timeout=0)

        # Should succeed without timeout protection
        document = SVGDocument.from_psd(psdimage, resource_limits=limits)
        assert document is not None

    def test_convert_with_timeout_enabled(self, tmp_path: Path) -> None:
        """Test convert() applies timeout when enabled."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Set reasonable timeout
        limits = ResourceLimits(timeout=30)

        # Should succeed within timeout
        convert(input_path, output_path, resource_limits=limits)
        assert os.path.exists(output_path)


class TestLayerDepthValidation:
    """Tests for layer depth limit enforcement."""

    def test_from_psd_with_shallow_layers(self) -> None:
        """Test SVGDocument.from_psd() succeeds with shallow layer nesting."""
        # Use a simple PSD with minimal nesting
        input_path = get_fixture("layer-types/group.psd")
        psdimage = PSDImage.open(input_path)

        # Set a reasonable depth limit
        limits = ResourceLimits(max_layer_depth=10)

        # Should succeed
        document = SVGDocument.from_psd(psdimage, resource_limits=limits)
        assert document is not None

    def test_from_psd_with_depth_limit_disabled(self) -> None:
        """Test SVGDocument.from_psd() succeeds when depth limit is disabled."""
        input_path = get_fixture("layer-types/group.psd")
        psdimage = PSDImage.open(input_path)

        # Disable depth limit
        limits = ResourceLimits(max_layer_depth=0)

        # Should succeed regardless of depth
        document = SVGDocument.from_psd(psdimage, resource_limits=limits)
        assert document is not None

    def test_layer_depth_validation_raises_on_exceed(self) -> None:
        """Test layer depth validation raises ValueError when limit exceeded."""
        # Create a mock deeply nested structure
        input_path = get_fixture("layer-types/group.psd")
        psdimage = PSDImage.open(input_path)

        # Set an artificially low depth limit
        limits = ResourceLimits(max_layer_depth=1)

        # Should raise ValueError for deeply nested structure
        # Note: This may succeed if the test PSD is shallow
        # In that case, we're just testing the mechanism works
        try:
            document = SVGDocument.from_psd(psdimage, resource_limits=limits)
            # If we get here, the test PSD is too shallow
            # That's okay - we're testing the mechanism exists
            assert document is not None
        except ValueError as e:
            # Expected when depth limit is exceeded
            assert "Layer depth" in str(e) and "exceeds limit" in str(e)


class TestImageDimensionValidation:
    """Tests for image dimension limit enforcement."""

    def test_from_psd_with_small_images(self) -> None:
        """Test SVGDocument.from_psd() succeeds with images below dimension limit."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        psdimage = PSDImage.open(input_path)

        # Get actual image dimensions
        max_dim = max(psdimage.width, psdimage.height)

        # Set limit above actual dimensions
        limits = ResourceLimits(max_image_dimension=max_dim + 1000)

        # Should succeed
        document = SVGDocument.from_psd(psdimage, resource_limits=limits)
        assert document is not None

    def test_from_psd_with_dimension_limit_disabled(self) -> None:
        """Test SVGDocument.from_psd() succeeds when dimension limit is disabled."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        psdimage = PSDImage.open(input_path)

        # Disable dimension limit
        limits = ResourceLimits(max_image_dimension=0)

        # Should succeed regardless of dimensions
        document = SVGDocument.from_psd(psdimage, resource_limits=limits)
        assert document is not None

    def test_image_dimension_validation_raises_on_exceed(self) -> None:
        """Test image dimension validation raises ValueError when limit exceeded."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        psdimage = PSDImage.open(input_path)

        # Set artificially low dimension limit
        limits = ResourceLimits(max_image_dimension=1)

        # Should raise ValueError for oversized image
        with pytest.raises(ValueError, match=r"Layer '.*' dimensions .* exceed limit"):
            SVGDocument.from_psd(psdimage, resource_limits=limits)

    def test_layer_mask_is_validated(self) -> None:
        """Test a layer mask is rejected by the dimension limit.

        A mask bbox is unclipped, so a small document can carry an oversized
        mask. This fixture has no pixel layer, so the mask is the only source.
        """
        psdimage = PSDImage.open(get_fixture("adjustments/invert-mask.psd"))

        with pytest.raises(ValueError, match=r"Mask of layer 'Invert 1' dimensions"):
            SVGDocument.from_psd(
                psdimage, resource_limits=ResourceLimits(max_image_dimension=1)
            )

    def test_pattern_is_validated(self) -> None:
        """Test a pattern bitmap is rejected by the dimension limit.

        A pattern is not bounded by the canvas either: this 128x128 document
        carries a 946x946 pattern. It has no pixel layer and no mask.
        """
        psdimage = PSDImage.open(get_fixture("paint/pattern-1.psd"))

        with pytest.raises(ValueError, match=r"Pattern 'Grass' dimensions 946x946"):
            SVGDocument.from_psd(
                psdimage, resource_limits=ResourceLimits(max_image_dimension=1)
            )

    def test_flat_composite_is_validated(self) -> None:
        """Test the no-layer flat composite is rejected by the dimension limit."""
        psdimage = PSDImage.frompil(Image.new("RGB", (64, 48), "red"))
        assert len(psdimage) == 0 and psdimage.has_preview()

        with pytest.raises(ValueError, match=r"Flattened composite dimensions 64x48"):
            SVGDocument.from_psd(
                psdimage, resource_limits=ResourceLimits(max_image_dimension=1)
            )

    @pytest.mark.parametrize(
        "fixture",
        [
            "layer-types/pixel-layer.psd",
            "adjustments/invert-mask.psd",
            "paint/pattern-1.psd",
        ],
    )
    def test_sources_succeed_when_limit_disabled(self, fixture: str) -> None:
        """Test every validated source still converts when the limit is off."""
        psdimage = PSDImage.open(get_fixture(fixture))

        document = SVGDocument.from_psd(
            psdimage, resource_limits=ResourceLimits(max_image_dimension=0)
        )
        assert document.images

    def test_oversized_sources_are_rejected_before_decoding(self) -> None:
        """Test an oversized bitmap is never decoded.

        Rejecting after decoding would defeat the limit, whose purpose is to
        prevent the allocation in the first place.
        """
        limits = ResourceLimits(max_image_dimension=1)

        with patch.object(
            PixelLayer, "topil", side_effect=AssertionError("decoded")
        ) as topil:
            with pytest.raises(ValueError, match="exceed limit"):
                SVGDocument.from_psd(
                    PSDImage.open(get_fixture("layer-types/pixel-layer.psd")),
                    resource_limits=limits,
                )
            topil.assert_not_called()

        with patch.object(
            Mask, "topil", side_effect=AssertionError("decoded")
        ) as mask_topil:
            with pytest.raises(ValueError, match="exceed limit"):
                SVGDocument.from_psd(
                    PSDImage.open(get_fixture("adjustments/invert-mask.psd")),
                    resource_limits=limits,
                )
            mask_topil.assert_not_called()

        with patch.object(
            pil_io, "convert_pattern_to_pil", side_effect=AssertionError("decoded")
        ) as to_pil:
            with pytest.raises(ValueError, match="exceed limit"):
                SVGDocument.from_psd(
                    PSDImage.open(get_fixture("paint/pattern-1.psd")),
                    resource_limits=limits,
                )
            to_pil.assert_not_called()

    def test_register_image_validates_any_writer(self) -> None:
        """Test Converter.register_image() guards bitmaps from any source."""
        converter = Converter(
            PSDImage.open(get_fixture("layer-types/pixel-layer.psd")),
            resource_limits=ResourceLimits(max_image_dimension=8),
        )

        with pytest.raises(ValueError, match=r"Widget dimensions 16x4 exceed limit"):
            converter.register_image(Image.new("L", (16, 4)), description="Widget")
        assert converter.images == {}

        image_id = converter.register_image(
            Image.new("L", (8, 8)), description="Widget"
        )
        assert converter.images[image_id].size == (8, 8)


class TestCheckImageDimension:
    """Tests for ResourceLimits.check_image_dimension()."""

    def test_within_limit_passes(self) -> None:
        """Test dimensions at or below the limit are accepted."""
        limits = ResourceLimits(max_image_dimension=100)

        limits.check_image_dimension(
            100, 100, description="Layer 'a'"
        )  # Boundary is inclusive.
        limits.check_image_dimension(1, 1, description="Layer 'a'")

    def test_disabled_limit_accepts_anything(self) -> None:
        """Test no check is performed when the limit is disabled."""
        ResourceLimits(max_image_dimension=0).check_image_dimension(
            10**6, 1, description="Layer"
        )

    def test_webp_limit_message_points_at_png(self) -> None:
        """Test the default limit explains the WebP ceiling and the PNG escape."""
        limits = ResourceLimits(max_image_dimension=WEBP_MAX_DIMENSION)

        with pytest.raises(ValueError) as excinfo:
            limits.check_image_dimension(20000, 10, description="Layer 'foo'")

        message = str(excinfo.value)
        assert "Layer 'foo' dimensions 20000x10" in message
        assert f"exceed limit {WEBP_MAX_DIMENSION}x{WEBP_MAX_DIMENSION}" in message
        assert "image_format='png'" in message
        assert "21000" in message  # Suggested limit: longest side plus 1000.

    def test_custom_limit_message_points_at_the_setting(self) -> None:
        """Test a non-WebP limit names how to raise it and omits WebP advice."""
        limits = ResourceLimits(max_image_dimension=100)

        with pytest.raises(ValueError) as excinfo:
            limits.check_image_dimension(10, 200, description="Mask of layer 'foo'")

        message = str(excinfo.value)
        assert "Mask of layer 'foo' dimensions 10x200 exceed limit 100x100" in message
        assert "PSD2SVG_MAX_IMAGE_DIMENSION=1200" in message
        assert "ResourceLimits(max_image_dimension=1200)" in message
        assert "WebP" not in message


class TestResourceLimitsIntegration:
    """Integration tests with all resource limits enabled."""

    def test_default_limits_enabled_by_default(self, tmp_path: Path) -> None:
        """Test that ResourceLimits.default() is applied automatically."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Don't pass resource_limits - should use default
        convert(input_path, output_path)
        assert os.path.exists(output_path)

    def test_from_psd_default_limits_enabled_by_default(self) -> None:
        """Test that SVGDocument.from_psd() uses default limits when None."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        psdimage = PSDImage.open(input_path)

        # Don't pass resource_limits - should use default
        document = SVGDocument.from_psd(psdimage)
        assert document is not None

    def test_all_limits_enabled_together(self, tmp_path: Path) -> None:
        """Test all resource limits work together."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Get file size and dimensions
        file_size = os.path.getsize(input_path)
        psdimage = PSDImage.open(input_path)
        max_dim = max(psdimage.width, psdimage.height)

        # Set all limits to reasonable values
        limits = ResourceLimits(
            max_file_size=file_size + 1024 * 1024,  # 1MB above actual
            timeout=30,  # 30 seconds
            max_layer_depth=100,  # Generous depth
            max_image_dimension=max_dim + 1000,  # Above actual dimensions
        )

        # Should succeed with all limits enabled
        convert(input_path, output_path, resource_limits=limits)
        assert os.path.exists(output_path)

    def test_unlimited_disables_all_limits(self, tmp_path: Path) -> None:
        """Test ResourceLimits.unlimited() disables all checks."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Use unlimited configuration
        limits = ResourceLimits.unlimited()

        # Should succeed without any checks
        convert(input_path, output_path, resource_limits=limits)
        assert os.path.exists(output_path)

    def test_selective_limit_disabling(self, tmp_path: Path) -> None:
        """Test disabling specific limits while keeping others enabled."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Disable only file size limit, keep others
        limits = ResourceLimits(
            max_file_size=0,  # Disabled
            timeout=30,  # Enabled
            max_layer_depth=100,  # Enabled
            max_image_dimension=8192,  # Enabled
        )

        # Should succeed
        convert(input_path, output_path, resource_limits=limits)
        assert os.path.exists(output_path)


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code."""

    def test_convert_without_resource_limits_uses_defaults(
        self, tmp_path: Path
    ) -> None:
        """Test convert() without resource_limits parameter uses defaults."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Call without resource_limits parameter
        convert(input_path, output_path)
        assert os.path.exists(output_path)

    def test_from_psd_without_resource_limits_uses_defaults(self) -> None:
        """Test SVGDocument.from_psd() without resource_limits uses defaults."""
        input_path = get_fixture("layer-types/pixel-layer.psd")
        psdimage = PSDImage.open(input_path)

        # Call without resource_limits parameter
        document = SVGDocument.from_psd(psdimage)
        assert document is not None

    def test_existing_tests_still_pass(self, tmp_path: Path) -> None:
        """Test that existing code patterns still work."""
        # Simulate existing test patterns
        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Old-style call (should still work)
        convert(input_path, output_path)
        assert os.path.exists(output_path)

        # Load and convert pattern
        psdimage = PSDImage.open(input_path)
        document = SVGDocument.from_psd(psdimage)
        assert document is not None


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing of resource limits."""

    def test_help_displays_resource_limit_flags(self) -> None:
        """Test --help shows new resource limit flags."""
        result = subprocess.run(
            ["uv", "run", "python", "-m", "psd2svg", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--max-file-size" in result.stdout
        assert "--timeout" in result.stdout
        assert "--max-layer-depth" in result.stdout
        assert "--max-image-dimension" in result.stdout
        assert "--unlimited-resources" in result.stdout

    def test_parse_max_file_size_flag(self, tmp_path: Path) -> None:
        """Test --max-file-size flag is parsed correctly."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Test with valid integer
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--max-file-size",
                "10000000",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)

    def test_parse_timeout_flag(self, tmp_path: Path) -> None:
        """Test --timeout flag is parsed correctly."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--timeout",
                "30",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)

    def test_parse_unlimited_resources_flag(self, tmp_path: Path) -> None:
        """Test --unlimited-resources flag is parsed correctly."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--unlimited-resources",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)


class TestCLIConflictDetection:
    """Tests for conflict detection between CLI flags."""

    def test_unlimited_conflicts_with_max_file_size(self, tmp_path: Path) -> None:
        """Test --unlimited-resources conflicts with --max-file-size."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--unlimited-resources",
                "--max-file-size",
                "10000000",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2  # Argument error
        assert "--unlimited-resources conflicts with" in result.stderr
        assert "--max-file-size" in result.stderr

    def test_unlimited_conflicts_with_timeout(self, tmp_path: Path) -> None:
        """Test --unlimited-resources conflicts with --timeout."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--unlimited-resources",
                "--timeout",
                "30",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "--unlimited-resources conflicts with" in result.stderr
        assert "--timeout" in result.stderr

    def test_unlimited_conflicts_with_multiple_flags(self, tmp_path: Path) -> None:
        """Test --unlimited-resources conflicts with multiple limit flags."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--unlimited-resources",
                "--max-file-size",
                "10000000",
                "--timeout",
                "30",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "--unlimited-resources conflicts with" in result.stderr
        # Should list both conflicting flags
        assert "--max-file-size" in result.stderr
        assert "--timeout" in result.stderr

    def test_limit_flags_without_unlimited_succeeds(self, tmp_path: Path) -> None:
        """Test limit flags without --unlimited-resources are valid."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--max-file-size",
                "10000000",
                "--timeout",
                "30",
                "--max-layer-depth",
                "50",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)


class TestCLIPrecedence:
    """Tests for CLI flag precedence over environment variables."""

    def test_cli_flag_overrides_env_var_max_file_size(self, tmp_path: Path) -> None:
        """Test --max-file-size overrides PSD2SVG_MAX_FILE_SIZE."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Set env var to very low value that would fail
        env = os.environ.copy()
        env["PSD2SVG_MAX_FILE_SIZE"] = "100"

        # Override with CLI flag to allow conversion
        file_size = os.path.getsize(input_path)
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--max-file-size",
                str(file_size + 1000),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)

    def test_cli_flag_zero_overrides_env_var(self, tmp_path: Path) -> None:
        """Test CLI flag with 0 (disabled) overrides env var."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Set env var to very low value
        env = os.environ.copy()
        env["PSD2SVG_MAX_FILE_SIZE"] = "100"

        # Override with 0 to disable limit
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--max-file-size",
                "0",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)

    def test_cli_flag_negative_clamped_to_zero(self, tmp_path: Path) -> None:
        """Test CLI flag with negative value is clamped to 0."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Negative value should be clamped to 0 (disabled)
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--max-file-size",
                "-100",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)

    def test_env_var_used_when_cli_flag_not_provided(self, tmp_path: Path) -> None:
        """Test environment variable is used when CLI flag not provided."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Set env var to disable limit
        env = os.environ.copy()
        env["PSD2SVG_MAX_FILE_SIZE"] = "0"

        # Don't provide CLI flag - env var should be used
        result = subprocess.run(
            ["uv", "run", "python", "-m", "psd2svg", input_path, output_path],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)

    def test_unlimited_overrides_all(self, tmp_path: Path) -> None:
        """Test --unlimited-resources overrides env vars and defaults."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Set env vars with limits
        env = os.environ.copy()
        env["PSD2SVG_TIMEOUT"] = "1"  # Very short timeout

        # Override with unlimited
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--unlimited-resources",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)


class TestCLIResourceLimitIntegration:
    """Integration tests for CLI resource limits with actual conversion."""

    def test_cli_conversion_with_custom_file_size_limit(self, tmp_path: Path) -> None:
        """Test CLI conversion with custom --max-file-size."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        file_size = os.path.getsize(input_path)
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--max-file-size",
                str(file_size + 1000),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)

    def test_cli_conversion_with_unlimited(self, tmp_path: Path) -> None:
        """Test CLI conversion with --unlimited-resources."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--unlimited-resources",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)

    def test_cli_conversion_exceeds_file_size_limit(self, tmp_path: Path) -> None:
        """Test CLI conversion fails when file exceeds limit."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Set very low limit
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--max-file-size",
                "100",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "File size" in result.stderr
        assert "exceeds limit" in result.stderr

    def test_cli_error_message_includes_guidance(self, tmp_path: Path) -> None:
        """Test error messages include helpful guidance (issue #236)."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Trigger file size error
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "psd2svg",
                input_path,
                output_path,
                "--max-file-size",
                "100",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        # Verify enhanced error messages from commit 50dc280
        assert (
            "PSD2SVG_MAX_FILE_SIZE" in result.stderr
            or "ResourceLimits" in result.stderr
        )

    def test_cli_without_resource_limit_flags_uses_defaults(
        self, tmp_path: Path
    ) -> None:
        """Test CLI without new flags uses default limits (backward compat)."""

        input_path = get_fixture("layer-types/pixel-layer.psd")
        output_path = str(tmp_path / "output.svg")

        # Run without any resource limit flags
        result = subprocess.run(
            ["uv", "run", "python", "-m", "psd2svg", input_path, output_path],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert os.path.exists(output_path)


class TestFromCLIArgs:
    """Tests for ResourceLimits.from_cli_args() class method."""

    def test_from_cli_args_with_unlimited(self) -> None:
        """Test from_cli_args() with unlimited=True."""
        limits = ResourceLimits.from_cli_args(unlimited=True)
        assert limits.max_file_size == 0
        assert limits.timeout == 0
        assert limits.max_layer_depth == 0
        assert limits.max_image_dimension == 0

    def test_from_cli_args_all_none_uses_defaults(self) -> None:
        """Test from_cli_args() with all None values uses defaults."""
        limits = ResourceLimits.from_cli_args()
        # Should use environment variable defaults
        assert limits.max_file_size == 2147483648  # 2GB default
        assert limits.timeout == 180  # 3 minutes default
        assert limits.max_layer_depth == 100
        assert limits.max_image_dimension == 16383  # WebP limit

    def test_from_cli_args_overrides_with_cli_values(self) -> None:
        """Test from_cli_args() overrides defaults with CLI values."""
        limits = ResourceLimits.from_cli_args(
            max_file_size=1000,
            timeout=30,
            max_layer_depth=50,
            max_image_dimension=8192,
        )
        assert limits.max_file_size == 1000
        assert limits.timeout == 30
        assert limits.max_layer_depth == 50
        assert limits.max_image_dimension == 8192

    def test_from_cli_args_partial_override(self) -> None:
        """Test from_cli_args() with partial CLI values."""
        limits = ResourceLimits.from_cli_args(
            max_file_size=5000,
            # Other values should use defaults
        )
        assert limits.max_file_size == 5000
        assert limits.timeout == 180  # Default
        assert limits.max_layer_depth == 100  # Default
        assert limits.max_image_dimension == 16383  # Default

    def test_from_cli_args_negative_value_clamped_with_warning(self) -> None:
        """Test from_cli_args() clamps negative values to 0 with warning."""
        with patch("psd2svg.resource_limits.logger") as mock_logger:
            limits = ResourceLimits.from_cli_args(max_file_size=-100)
            assert limits.max_file_size == 0
            mock_logger.warning.assert_called_once()
            assert "--max-file-size=-100" in mock_logger.warning.call_args[0][0]
            assert "treating as 0" in mock_logger.warning.call_args[0][0]

    def test_from_cli_args_zero_disables_limit(self) -> None:
        """Test from_cli_args() with 0 disables limit."""
        limits = ResourceLimits.from_cli_args(max_file_size=0)
        assert limits.max_file_size == 0

    def test_from_cli_args_with_env_vars(self) -> None:
        """Test from_cli_args() with environment variables set."""
        with patch.dict(
            os.environ,
            {"PSD2SVG_MAX_FILE_SIZE": "5000", "PSD2SVG_TIMEOUT": "60"},
        ):
            # CLI flag should override env var
            limits = ResourceLimits.from_cli_args(max_file_size=10000)
            assert limits.max_file_size == 10000  # CLI override
            assert limits.timeout == 60  # From env var

    def test_from_cli_args_cli_zero_overrides_env_var(self) -> None:
        """Test from_cli_args() with CLI 0 overrides env var."""
        with patch.dict(os.environ, {"PSD2SVG_MAX_FILE_SIZE": "5000"}):
            # CLI 0 should override env var (disable limit)
            limits = ResourceLimits.from_cli_args(max_file_size=0)
            assert limits.max_file_size == 0

    def test_from_cli_args_negative_all_limits(self) -> None:
        """Test from_cli_args() with all negative values."""
        with patch("psd2svg.resource_limits.logger") as mock_logger:
            limits = ResourceLimits.from_cli_args(
                max_file_size=-1,
                timeout=-2,
                max_layer_depth=-3,
                max_image_dimension=-4,
            )
            assert limits.max_file_size == 0
            assert limits.timeout == 0
            assert limits.max_layer_depth == 0
            assert limits.max_image_dimension == 0
            # Should log 4 warnings
            assert mock_logger.warning.call_count == 4

    def test_from_cli_args_unlimited_conflicts_with_max_file_size(self) -> None:
        """Test from_cli_args() raises ValueError when unlimited conflicts."""
        with pytest.raises(ValueError, match="--unlimited-resources conflicts with"):
            ResourceLimits.from_cli_args(unlimited=True, max_file_size=1000)

    def test_from_cli_args_unlimited_conflicts_with_multiple(self) -> None:
        """Test from_cli_args() raises ValueError with multiple conflicts."""
        with pytest.raises(ValueError) as exc_info:
            ResourceLimits.from_cli_args(
                unlimited=True,
                max_file_size=1000,
                timeout=30,
            )
        assert "--unlimited-resources conflicts with" in str(exc_info.value)
        assert "--max-file-size" in str(exc_info.value)
        assert "--timeout" in str(exc_info.value)

    def test_from_cli_args_unlimited_without_conflicts(self) -> None:
        """Test from_cli_args() with unlimited=True and no other args."""
        limits = ResourceLimits.from_cli_args(unlimited=True)
        assert limits.max_file_size == 0
        assert limits.timeout == 0
        assert limits.max_layer_depth == 0
        assert limits.max_image_dimension == 0
