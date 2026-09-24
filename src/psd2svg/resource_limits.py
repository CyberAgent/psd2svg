"""Resource limits for DoS prevention.

This module provides configurable resource limits to prevent denial-of-service
attacks from malicious or malformed input files.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default resource limits
DEFAULT_MAX_FILE_SIZE = 2147483648  # 2GB (typical for professional PSD files)
DEFAULT_TIMEOUT = 180  # 3 minutes
DEFAULT_MAX_LAYER_DEPTH = 100  # Maximum layer nesting depth
DEFAULT_MAX_IMAGE_DIMENSION = 16383  # WebP hard limit for image dimensions

# Deprecated: Use DEFAULT_MAX_IMAGE_DIMENSION instead
WEBP_MAX_DIMENSION = DEFAULT_MAX_IMAGE_DIMENSION


@dataclass
class ResourceLimits:
    """Resource limits for PSD conversion operations.

    These limits help prevent denial-of-service attacks by constraining:
    - File size (prevents memory exhaustion)
    - Conversion timeout (prevents CPU exhaustion)
    - Layer depth (prevents exponential processing time)
    - Image dimensions (prevents memory exhaustion from large images)

    Limits can be configured via environment variables or constructor parameters.
    Constructor parameters take precedence over environment variables.

    Environment variables:
        PSD2SVG_MAX_FILE_SIZE: Maximum file size in bytes (default: 2147483648 = 2GB)
        PSD2SVG_TIMEOUT: Conversion timeout in seconds (default: 180 = 3 minutes)
        PSD2SVG_MAX_LAYER_DEPTH: Maximum layer nesting depth (default: 100)
        PSD2SVG_MAX_IMAGE_DIMENSION: Maximum image dimension in pixels
            (default: 16383 = WebP limit)

    Example:
        >>> # Use default limits
        >>> limits = ResourceLimits.default()
        >>>
        >>> # Customize limits
        >>> limits = ResourceLimits(
        ...     max_file_size=50 * 1024 * 1024,  # 50MB
        ...     timeout=30,  # 30 seconds
        ...     max_layer_depth=50,
        ...     max_image_dimension=8192
        ... )
        >>>
        >>> # Disable specific limits (set to 0 or None)
        >>> limits = ResourceLimits(max_file_size=0)  # No file size limit
    """

    max_file_size: int = DEFAULT_MAX_FILE_SIZE
    timeout: int = DEFAULT_TIMEOUT
    max_layer_depth: int = DEFAULT_MAX_LAYER_DEPTH
    max_image_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION

    @classmethod
    def default(cls) -> "ResourceLimits":
        """Create ResourceLimits with default values from environment variables.

        Returns:
            ResourceLimits instance with values from environment variables,
            falling back to hardcoded defaults if not set.

        Raises:
            ValueError: If environment variable contains invalid integer value.

        Note:
            Negative values are treated as 0 (disabled limit) with a warning logged.
            Non-integer values raise ValueError. For intentionally disabling all
            limits, use ResourceLimits.unlimited() instead of negative values.
        """
        return cls(
            max_file_size=cls._parse_env_int(
                "PSD2SVG_MAX_FILE_SIZE", DEFAULT_MAX_FILE_SIZE
            ),
            timeout=cls._parse_env_int("PSD2SVG_TIMEOUT", DEFAULT_TIMEOUT),
            max_layer_depth=cls._parse_env_int(
                "PSD2SVG_MAX_LAYER_DEPTH", DEFAULT_MAX_LAYER_DEPTH
            ),
            max_image_dimension=cls._parse_env_int(
                "PSD2SVG_MAX_IMAGE_DIMENSION", DEFAULT_MAX_IMAGE_DIMENSION
            ),
        )

    @classmethod
    def from_cli_args(
        cls,
        max_file_size: int | None = None,
        timeout: int | None = None,
        max_layer_depth: int | None = None,
        max_image_dimension: int | None = None,
        unlimited: bool = False,
    ) -> "ResourceLimits":
        """Create ResourceLimits from CLI arguments with proper precedence.

        Precedence: CLI flags > Environment variables > Defaults

        Args:
            max_file_size: CLI flag value for max file size
                (None if not provided).
            timeout: CLI flag value for timeout (None if not provided).
            max_layer_depth: CLI flag value for max layer depth
                (None if not provided).
            max_image_dimension: CLI flag value for max image dimension
                (None if not provided).
            unlimited: Whether --unlimited-resources flag was set.

        Returns:
            ResourceLimits instance with validated values.

        Raises:
            ValueError: If unlimited=True and any other limit parameter is not None.

        Note:
            Negative values are treated as 0 (disabled limit) with a warning logged.
        """
        # Validate conflict between unlimited and other flags
        if unlimited:
            conflicting = []
            if max_file_size is not None:
                conflicting.append("--max-file-size")
            if timeout is not None:
                conflicting.append("--timeout")
            if max_layer_depth is not None:
                conflicting.append("--max-layer-depth")
            if max_image_dimension is not None:
                conflicting.append("--max-image-dimension")

            if conflicting:
                raise ValueError(
                    f"--unlimited-resources conflicts with: {', '.join(conflicting)}"
                )

            return cls.unlimited()

        # Start with environment variable defaults
        limits = cls.default()

        # Override with CLI flags if provided (None means not provided)
        if max_file_size is not None:
            limits.max_file_size = cls._validate_cli_limit(
                max_file_size, "max_file_size"
            )
        if timeout is not None:
            limits.timeout = cls._validate_cli_limit(timeout, "timeout")
        if max_layer_depth is not None:
            limits.max_layer_depth = cls._validate_cli_limit(
                max_layer_depth, "max_layer_depth"
            )
        if max_image_dimension is not None:
            limits.max_image_dimension = cls._validate_cli_limit(
                max_image_dimension, "max_image_dimension"
            )

        return limits

    @staticmethod
    def _parse_env_int(key: str, default: int) -> int:
        """Parse integer from environment variable with validation.

        Args:
            key: Environment variable name.
            default: Default value if not set.

        Returns:
            Parsed integer value, or 0 if negative.

        Raises:
            ValueError: If value is not a valid integer.
        """
        value_str = os.environ.get(key)
        if value_str is None:
            return default

        try:
            value = int(value_str)
        except ValueError as e:
            raise ValueError(
                f"Environment variable {key}={value_str!r} is not a valid integer"
            ) from e

        # Treat negative values as 0 (disabled limit)
        if value < 0:
            logger.warning(
                f"Environment variable {key}={value} is negative, "
                f"treating as 0 (disabled limit). "
                f"Consider using ResourceLimits.unlimited() instead."
            )
            return 0

        return value

    @staticmethod
    def _validate_cli_limit(value: int, name: str) -> int:
        """Validate and clamp CLI limit values.

        Args:
            value: The limit value to validate.
            name: The name of the limit (for logging).

        Returns:
            Validated value (clamped to 0 if negative).
        """
        if value < 0:
            logger.warning(
                f"CLI flag --{name.replace('_', '-')}={value} is negative, "
                f"treating as 0 (disabled limit)"
            )
            return 0
        return value

    @classmethod
    def unlimited(cls) -> "ResourceLimits":
        """Create ResourceLimits with all limits disabled.

        Returns:
            ResourceLimits instance with all limits set to 0 (disabled).

        Warning:
            Only use this for trusted input files in controlled environments.
        """
        return cls(
            max_file_size=0,
            timeout=0,
            max_layer_depth=0,
            max_image_dimension=0,
        )

    def is_file_size_limited(self) -> bool:
        """Check if file size limit is enabled."""
        return self.max_file_size > 0

    def is_timeout_enabled(self) -> bool:
        """Check if timeout is enabled."""
        return self.timeout > 0

    def is_layer_depth_limited(self) -> bool:
        """Check if layer depth limit is enabled."""
        return self.max_layer_depth > 0

    def is_image_dimension_limited(self) -> bool:
        """Check if image dimension limit is enabled."""
        return self.max_image_dimension > 0

    def check_image_dimension(self, width: int, height: int, description: str) -> None:
        """Raise ValueError if the given bitmap exceeds max_image_dimension.

        Args:
            width: Bitmap width in pixels.
            height: Bitmap height in pixels.
            description: What the bitmap is, used to open the error message.
                For example ``"Layer 'Background'"`` or ``"Pattern 'Grass'"``.

        Raises:
            ValueError: If either dimension exceeds the limit. The message names
                the limit and how to raise it.
        """
        if not self.is_image_dimension_limited():
            return
        max_dim = self.max_image_dimension
        if width <= max_dim and height <= max_dim:
            return

        suggested = max(width, height) + 1000
        prefix = (
            f"{description} dimensions {width}x{height} "
            f"exceed limit {max_dim}x{max_dim}. "
        )
        if max_dim == WEBP_MAX_DIMENSION:
            raise ValueError(
                prefix + f"WebP has a {WEBP_MAX_DIMENSION}px hard limit. "
                f"To process images larger than this, use image_format='png' and, "
                f"if necessary, increase PSD2SVG_MAX_IMAGE_DIMENSION "
                f"(for example, to {suggested})."
            )
        raise ValueError(
            prefix + f"To process: set PSD2SVG_MAX_IMAGE_DIMENSION={suggested} "
            f"environment variable, or use "
            f"ResourceLimits(max_image_dimension={suggested}) in Python API."
        )
