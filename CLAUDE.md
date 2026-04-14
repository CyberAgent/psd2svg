# CLAUDE.md

## Quick Reference

### Essential Commands

```bash
# Development
uv sync                          # Install dependencies
uv run pytest                    # Run tests
uv run mypy src/ tests/          # Type checking
uv run ruff check src/ tests/    # Linting
uv run ruff format src/ tests/   # Format code
uv run python                    # Run python interpreter

# Optional dependencies
uv sync --group docs             # Documentation tools
uv sync --extra browser          # Playwright rasterizer
uv run playwright install chromium  # Install Chromium browser for Playwright

# Documentation
uv run sphinx-build -b html docs docs/_build/html
```

### Pre-commit Checklist

Before pushing changes, always run:

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run mypy src/ tests/
uv run pytest
```

## Platform Support

All platforms (Linux, macOS, Windows) are fully supported for text conversion and font embedding.

For platform-specific implementation details, see:

- **Font resolution architecture**: [docs/technical-notes.rst](docs/technical-notes.rst) (deferred resolution, lookup methods)
- **Text limitations**: [docs/limitations.rst](docs/limitations.rst)
- **Font configuration**: [docs/fonts.rst](docs/fonts.rst)

## Architecture Overview

### Public API

- **`SVGDocument`**: Main class for SVG documents and resources
- **`convert()`**: Convenience function for simple conversions

### Project Structure

```text
src/psd2svg/
├── core/                      # Internal converter implementations
│   ├── adjustment.py          # Adjustment layer converter
│   ├── effects.py             # Effect converter
│   ├── layer.py               # Layer converter
│   ├── paint.py               # Paint converter
│   ├── shape.py               # Shape converter
│   ├── text.py                # Text converter
│   ├── font_mapping.py        # Font resolution (lookup_static, resolve, find)
│   ├── font_utils.py          # Font utility functions
│   ├── typesetting.py         # PSD text layer parsing
│   └── windows_fonts.py       # Windows font resolution
├── svg_document.py            # Public API (SVGDocument, convert)
├── font_subsetting.py         # Font subsetting and embedding
├── rasterizer/                # Rasterization backends
│   ├── resvg_rasterizer.py    # ResvgRasterizer (default)
│   └── playwright_rasterizer.py  # PlaywrightRasterizer (optional)
├── data/                      # Static font mapping data
│   ├── default_fonts.json     # Default font mappings (~539 fonts)
│   └── morisawa_fonts.json    # Morisawa font mappings (~4,042 fonts)
└── tools/                     # CLI tools
    └── generate_font_mapping.py  # Generate custom font mappings
```

For detailed architecture documentation, see [docs/development.rst](docs/development.rst).

## CI/CD

### GitHub Actions

- **Test Workflow** (`.github/workflows/test.yml`): Runs on every push and PR
- **Release Workflow** (`.github/workflows/release.yml`): Triggered by version tags on main branch

For release process details, see [docs/development.rst](docs/development.rst).

### Git Workflow

**IMPORTANT**: This project uses a pull request workflow for all changes to the main branch.

**Never commit directly to main.** All changes must:

1. Be developed on a feature branch
2. Be pushed to the remote repository
3. Go through a pull request targeting `main`
4. Pass CI checks before merging

**Workflow example:**

```bash
# Create feature branch
git checkout -b feature/my-change

# Make changes and commit
git add .
git commit -m "Description of changes"

# Push branch and create PR
git push -u origin feature/my-change
gh pr create --title "My Change" --body "Description"
```

## Code Quality Standards

- **Type hints**: Full type annotation coverage
- **Linting**: Ruff for fast linting/formatting
- **Python 3.10+**: Modern Python, no legacy code
- **Abstract base classes**: Proper ABC usage for interfaces
- **Import statements**: Prefer top-/module-level import over function-level import

## Development Notes

### When Making Changes

1. **Create a git branch** - Always work on a feature branch, never directly on main
2. **Avoid backwards-compatibility hacks** - Delete unused code completely

### Documentation Structure

- **README.md** - Quick start guide, basic usage
- **docs/** - Full Sphinx documentation (comprehensive details)

For detailed feature documentation, configuration options, and usage examples, refer to the [full documentation](https://psd2svg.readthedocs.io/).

### Debugging PSD files

Use `psd-tools` API to inspect PSD content. Don't forget to use `uv run python` to explore the package API in the uv-managed environment.

For inspecting low-level structure in PSD file, you can use the instance method provided by specific layer type, or access the `_record` attribute of each layer:

```python
from psd_tools import PSDImage
from psd_tools.api.adjustments import Posterize
from IPython.display import display

psdimage = PSDImage.open("tests/fixtures/adjustments/posterize-levels4.psd")
display(psdimage)   # Use IPython to pretty-print the PSD layer structure

for layer in psdimage.descendants():
    if isinstance(layer, Posterize) and layer.is_visible():
        print(layer)              # Layer object
        print(layer.posterize)    # Specific layer has specific attribute
        display(layer._record)    # Low-level record supports pretty printing via IPython
```

Text layers have a wrapper class `TypeSetting` in psd2svg. Use the following approach:

```python
from psd_tools import PSDImage
from psd_tools.api.layers import TypeLayer
from psd2svg.core.typesetting import TypeSetting

psdimage = PSDImage.open("tests/fixtures/texts/style-tsume.psd")
for layer in psd.descendants():
    if isinstance(layer, TypeLayer) and layer.is_visible():
        text_setting = TypeSetting(layer._data)
        for paragraph in text_setting:
            for style in paragraph:
                # Do whatever you want to debug with the style span.
                pass
```

## Important Links

- **User Documentation**: [https://psd2svg.readthedocs.io/](https://psd2svg.readthedocs.io/)
- **Technical Architecture**: [docs/technical-notes.rst](docs/technical-notes.rst) (font resolution, clipping, effects, shape operations)
- **Development Guide**: [docs/development.rst](docs/development.rst) (setup, architecture, contributing, release process)
- **Feature Limitations**: [docs/limitations.rst](docs/limitations.rst) (known issues and workarounds)
- **API Reference**: [docs/api-reference.rst](docs/api-reference.rst) (complete API documentation)
