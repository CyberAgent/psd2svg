# PSD2SVG

PSD to SVG converter based on [psd-tools](https://github.com/psd-tools/psd-tools).

[![PyPI Version](https://img.shields.io/pypi/v/psd2svg.svg)](https://pypi.python.org/pypi/psd2svg)
[![Documentation Status](https://readthedocs.org/projects/psd2svg/badge/?version=latest)](https://psd2svg.readthedocs.io/en/latest/?badge=latest)

## Features

- Convert PSD files to clean, editable SVG
- Preserve layers and artboards with smart group optimization
- Convert text layers to native SVG text elements (experimental)
  - Arc warp support with SVG textPath
  - Smart font matching with Unicode codepoint-based selection
- Support for most Photoshop blending modes (with approximations for unsupported modes)
- Adjustment layers support (experimental)
- Optional font subsetting and embedding for web optimization (typically 90-95% size reduction)
- Built-in resource limits for security (file size, timeout, layer depth, dimensions)
- Command-line tool and Python API

## Installation

```bash
pip install psd2svg
```

### Optional Features

```bash
# Browser-based rasterization (better SVG 2.0 support)
pip install psd2svg[browser]
playwright install chromium
```

## Quick Start

### Command Line

```bash
# Basic conversion
psd2svg input.psd output.svg

# With external images
psd2svg input.psd output.svg --image-prefix images/img
```

### Python API

```python
from psd2svg import convert

# Simple conversion with embedded images
convert('input.psd', 'output.svg')

# With external images
convert('input.psd', 'output.svg', image_prefix='images/img')
```

### Advanced Usage

```python
from psd_tools import PSDImage
from psd2svg import SVGDocument

# Load PSD and create SVG document
psdimage = PSDImage.open("input.psd")
document = SVGDocument.from_psd(psdimage)

# Save with options
document.save("output.svg", embed_images=True)

# Embed and subset fonts for web
document.save("output.svg", embed_fonts=True, font_format="woff2")

# Rasterize to PNG
image = document.rasterize()
image.save('output.png')
```

## Known Limitations

- **Text rendering**: Requires matching system fonts; rendering may differ from Photoshop if fonts are unavailable or substituted
- **Text wrapping**: Basic support via `--text-wrapping-mode foreignobject` CLI option or `text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT` in Python API (uses `<foreignObject>`). Note: not supported by ResvgRasterizer, only works in browsers
- **Blending modes**: Some advanced modes approximated due to CSS spec limitations (Dissolve, Linear Burn/Dodge, Darker/Lighter Color, Vivid/Linear/Pin Light, Hard Mix, Subtract, Divide)
- **Gradients**: Advanced types not supported (Angle, Reflected, Diamond)
- **Filter effects**: Bevels, embossing, and satin effects not supported; other effects are approximations
- **Adjustment layers**: Gradient Map, Channel Mixer, and Photo Filter are not yet implemented; Black & White, Selective Color, Vibrance, and Color Lookup cannot be represented in SVG filters and are omitted from the output
- **Smart objects**: Smart object filters not implemented
- **Thread safety**: APIs are not thread-safe

See the [full documentation](https://psd2svg.readthedocs.io/en/latest/limitations.html) for complete details and workarounds.

## Documentation

Full documentation is available at **[psd2svg.readthedocs.io](https://psd2svg.readthedocs.io/)**

## Platform Support

All platforms (Linux, macOS, Windows) are fully supported for text conversion and font embedding. Text layer conversion uses a hybrid approach with built-in font mappings (~4,950 fonts) plus platform-specific font resolution.

For detailed font resolution architecture, platform-specific implementation details, and custom font mapping, see the [Font Handling documentation](https://psd2svg.readthedocs.io/en/latest/fonts.html) and [Technical Notes](https://psd2svg.readthedocs.io/en/latest/technical-notes.html#font-resolution-architecture).

## Security

psd2svg includes built-in security features for processing untrusted PSD files:

- Resource limits (file size, timeout, layer depth, dimensions)
- Path traversal protection
- Font file validation

For comprehensive security guidance, sandboxing strategies, and production deployment best practices, see the [Security Documentation](https://psd2svg.readthedocs.io/en/latest/security.html). To report vulnerabilities, see [SECURITY.md](SECURITY.md).

## Development

```bash
# Install dependencies
uv sync

# Optional: Install browser support for PlaywrightRasterizer
uv sync --extra browser
uv run playwright install chromium

# Run tests
uv run pytest

# Run type checking and linting
uv run mypy src/ tests/
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

See [CLAUDE.md](CLAUDE.md) for detailed development instructions.

## License

MIT License - see LICENSE file for details.
