import argparse
import logging

from psd2svg import convert
from psd2svg.core.typesetting import TextWrappingMode
from psd2svg.resource_limits import ResourceLimits


def parse_args() -> tuple[argparse.Namespace, argparse.ArgumentParser]:
    """Parse command line arguments.

    Returns:
        Tuple of (parsed arguments, parser instance) for error handling.
    """
    parser = argparse.ArgumentParser(description="Convert PSD file to SVG")
    parser.add_argument(
        "input", metavar="INPUT", type=str, help="Input PSD file path or URL"
    )
    parser.add_argument(
        "output",
        metavar="PATH",
        type=str,
        nargs="?",
        default=".",
        help="Output file.",
    )
    parser.add_argument(
        "--image-prefix",
        metavar="PATH",
        type=str,
        default=None,
        help="Path prefix for saving extracted images relative to output.",
    )
    parser.add_argument(
        "--no-text",
        dest="enable_text",
        action="store_false",
        help="Disable text layer conversion (rasterize text instead).",
    )
    parser.add_argument(
        "--no-live-shapes",
        dest="enable_live_shapes",
        action="store_false",
        help="Disable live shape conversion (use paths instead of shape primitives).",
    )
    parser.add_argument(
        "--enable-title",
        dest="enable_title",
        action="store_true",
        help="Enable insertion of <title> elements with layer names.",
    )
    parser.add_argument(
        "--enable-class",
        dest="enable_class",
        action="store_true",
        help="Enable insertion of class attributes on SVG elements for debugging.",
    )
    parser.add_argument(
        "--include-hidden-layers",
        action="store_true",
        help="Include layers hidden in Photoshop in the SVG output.",
    )
    parser.add_argument(
        "--image-format",
        metavar="FORMAT",
        type=str,
        choices=["webp", "png", "jpeg"],
        default="webp",
        help="Image format for rasterized layers (webp, png, jpeg). Default: webp",
    )
    parser.add_argument(
        "--text-letter-spacing-offset",
        metavar="OFFSET",
        type=float,
        default=0.0,
        help="Global offset (in pixels) to add to letter-spacing values. Default: 0.0",
    )
    parser.add_argument(
        "--embed-fonts",
        dest="embed_fonts",
        action="store_true",
        help=(
            "Embed fonts in SVG using @font-face rules. "
            "Requires fontconfig on Linux/macOS."
        ),
    )
    parser.add_argument(
        "--font-format",
        metavar="FORMAT",
        type=str,
        choices=["woff2", "woff", "ttf", "otf"],
        default="woff2",
        help="Font format for embedding (woff2, woff, ttf, otf). Default: woff2",
    )
    parser.add_argument(
        "--text-wrapping-mode",
        metavar="MODE",
        type=str,
        choices=["none", "foreignobject"],
        default="none",
        help=(
            "Text wrapping mode for bounding box text: 'none' (native SVG "
            "text, default) or 'foreignobject' (XHTML wrapping). Only affects "
            "bounding box text; point text always uses native SVG <text> elements."
        ),
    )
    parser.add_argument(
        "--loglevel",
        metavar="LEVEL",
        default="WARNING",
        help="Logging level, default WARNING",
    )
    # Resource limit arguments
    parser.add_argument(
        "--max-file-size",
        metavar="BYTES",
        type=int,
        default=None,
        help=(
            "Maximum file size in bytes. Default: 2147483648 (2GB). "
            "Set to 0 to disable. Overrides PSD2SVG_MAX_FILE_SIZE environment variable."
        ),
    )
    parser.add_argument(
        "--timeout",
        metavar="SECONDS",
        type=int,
        default=None,
        help=(
            "Conversion timeout in seconds. Default: 180 (3 minutes). "
            "Set to 0 to disable. Overrides PSD2SVG_TIMEOUT environment variable."
        ),
    )
    parser.add_argument(
        "--max-layer-depth",
        metavar="DEPTH",
        type=int,
        default=None,
        help=(
            "Maximum layer nesting depth. Default: 100. "
            "Set to 0 to disable. "
            "Overrides PSD2SVG_MAX_LAYER_DEPTH environment variable."
        ),
    )
    parser.add_argument(
        "--max-image-dimension",
        metavar="PIXELS",
        type=int,
        default=None,
        help=(
            "Maximum image dimension in pixels. Default: 16383 (WebP limit). "
            "Set to 0 to disable. "
            "Overrides PSD2SVG_MAX_IMAGE_DIMENSION environment variable."
        ),
    )
    parser.add_argument(
        "--unlimited-resources",
        dest="unlimited_resources",
        action="store_true",
        help=(
            "Disable all resource limits. Use only for trusted input files. "
            "Conflicts with other limit flags."
        ),
    )
    return parser.parse_args(), parser


def main() -> None:
    """Main function to convert PSD to SVG or raster image."""
    args, parser = parse_args()
    logging.basicConfig(level=getattr(logging, args.loglevel.upper(), "WARNING"))

    # Create ResourceLimits from CLI args with proper precedence
    try:
        resource_limits = ResourceLimits.from_cli_args(
            max_file_size=args.max_file_size,
            timeout=args.timeout,
            max_layer_depth=args.max_layer_depth,
            max_image_dimension=args.max_image_dimension,
            unlimited=args.unlimited_resources,
        )
    except ValueError as e:
        # Convert ValueError to CLI error with proper exit code
        parser.error(str(e))

    # Map text wrapping mode to enum value
    text_wrapping_mode_map = {
        "none": TextWrappingMode.NONE,
        "foreignobject": TextWrappingMode.FOREIGN_OBJECT,
    }
    text_wrapping_mode = text_wrapping_mode_map[args.text_wrapping_mode]

    convert(
        args.input,
        args.output,
        image_prefix=args.image_prefix,
        enable_text=args.enable_text,
        enable_live_shapes=args.enable_live_shapes,
        enable_title=args.enable_title,
        enable_class=args.enable_class,
        include_hidden_layers=args.include_hidden_layers,
        image_format=args.image_format,
        text_letter_spacing_offset=args.text_letter_spacing_offset,
        embed_fonts=args.embed_fonts,
        font_format=args.font_format,
        text_wrapping_mode=text_wrapping_mode,
        resource_limits=resource_limits,
    )


if __name__ == "__main__":
    main()
