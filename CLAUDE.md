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

A plain `uv sync` environment silently skips the Playwright tests. Install the
`browser` extra on the development host so a green run means the whole suite:

```bash
uv sync --extra browser && uv run playwright install chromium
```

This matters most for `<foreignObject>` output (`text_wrapping_mode=1`): resvg
ignores `foreignObject` entirely, so Chromium is the only rasterizer that
renders it. Verify wrapped-text changes there, not with the default rasterizer.

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
git commit -s -m "Description of changes"

# Push branch and create PR
git push -u origin feature/my-change
gh pr create --title "My Change" --body "Description"
```

The `-s` flag is required: every commit needs a `Signed-off-by` line
([DCO](https://developercertificate.org/)). Sign-off uses your own
`git config user.email` and asserts *your* right to submit the code - it is not
something an agent asserts on your behalf. `Co-Authored-By:` lines are separate
and still apply. Fix a missing sign-off with `git commit --amend -s`, or a whole
branch with `git rebase --signoff main`.

## Code Quality Standards

- **Type hints**: Full type annotation coverage
- **Linting**: Ruff for fast linting/formatting
- **Python 3.10+**: Modern Python, no legacy code
- **Abstract base classes**: Proper ABC usage for interfaces
- **Import statements**: Prefer top-/module-level import over function-level import

## Development Notes

### When Making Changes

1. **Create a git branch** - Always work on a feature branch, never directly on main
2. **Sign off every commit** - `git commit -s`; every commit needs a
   `Signed-off-by` line matching the commit author
3. **Avoid backwards-compatibility hacks** - Delete unused code completely
4. **Update the changelog for user-facing changes** - In the same pull
   request, add an entry under `## [Unreleased]` in
   [CHANGELOG.md](CHANGELOG.md) when a change affects users (new feature,
   behavior change, bug fix, security fix). Skip it for refactors, test-only
   changes, CI config, and dependency bumps - the release process collapses
   dependency bumps into a single entry. Entries are grouped under
   `### Added` / `### Changed` / `### Fixed` / `### Security` /
   `### Dependencies` and reference the PR number:
   `- **Short description** (#PR)`. Keep entries concise - one bold summary
   line plus at most one short sub-bullet.
5. **Keep history out of the docs** - state the current rules and behavior; what
   changed and why belongs in the issue and the pull request. See
   [Documentation Structure](#documentation-structure).

### Documentation Structure

- **README.md** - Quick start guide, basic usage
- **docs/** - Full Sphinx documentation (comprehensive details)
- **CONTRIBUTING.md**, **SECURITY.md**, **CODE_OF_CONDUCT.md** - contribution
  rules, security policy, expected conduct
- **CLAUDE.md** - this file: commands, architecture, and session conventions

**Documentation states the current rules and behavior. GitHub issues and pull
requests hold the record of how it got that way.** Do not write what changed,
what was tried and rejected, or when something was decided. Not history:
explaining why the code behaves as it does, version and deprecation markers, and
a link to a currently open issue for a known gap.

Keep documentation and code comments concise - state the rule or the behavior,
not the argument for it.

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
- **Contribution Policy**: [CONTRIBUTING.md](CONTRIBUTING.md) (DCO sign-off, AI-assisted contributions, test fixtures, review priorities)
- **Security Policy**: [SECURITY.md](SECURITY.md) (supply-chain and contribution security, reporting vulnerabilities)
