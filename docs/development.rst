Development Guide
=================

This guide covers setting up a development environment and contributing to psd2svg.

Development Setup
-----------------

Prerequisites
~~~~~~~~~~~~~

* Python 3.10-3.14
* `uv <https://github.com/astral-sh/uv>`_ package manager
* Git

Clone the Repository
~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/CyberAgent/psd2svg.git
   cd psd2svg

Install Dependencies
~~~~~~~~~~~~~~~~~~~~

The project uses ``uv`` for dependency management:

.. code-block:: bash

   # Install dependencies
   uv sync

   # Optional dependencies
   uv sync --group docs                   # Documentation tools
   uv sync --extra browser                # Playwright rasterizer
   uv run playwright install chromium     # Install Chromium browser for Playwright

Quick Reference
~~~~~~~~~~~~~~~

For a quick command reference, git workflow, and development philosophy,
see the ``CLAUDE.md`` file in the repository root. This file provides
essential guidance for AI-assisted development with Claude Code.

Development Commands
--------------------

Testing
~~~~~~~

Run the test suite with pytest:

.. code-block:: bash

   uv run pytest

   # Run with coverage
   uv run pytest --cov=psd2svg

   # Run specific test file
   uv run pytest tests/test_svg_document.py

Type Checking
~~~~~~~~~~~~~

The project uses mypy for static type checking:

.. code-block:: bash

   uv run mypy src/ tests/

   # Check specific module
   uv run mypy src/psd2svg/svg_document.py

Linting
~~~~~~~

Ruff is used for fast linting:

.. code-block:: bash

   uv run ruff check src/ tests/

   # Auto-fix issues
   uv run ruff check --fix src/ tests/

Code Formatting
~~~~~~~~~~~~~~~

Format code with ruff:

.. code-block:: bash

   uv run ruff format src/ tests/

   # Check formatting without changes
   uv run ruff format --check src/ tests/

Building
~~~~~~~~

Build distribution packages:

.. code-block:: bash

   uv build

This creates wheel and sdist packages in the ``dist/`` directory.

Documentation
~~~~~~~~~~~~~

Build the documentation:

.. code-block:: bash

   uv run sphinx-build -b html docs docs/_build/html

   # Watch for changes and rebuild
   uv run sphinx-autobuild docs docs/_build/html

View the built documentation by opening ``docs/_build/html/index.html`` in a browser.

Architecture
------------

The package follows a modular converter architecture with multiple inheritance.

Public API Layer
~~~~~~~~~~~~~~~~

**Location:** ``src/psd2svg/``

The public API consists of:

* ``SVGDocument`` - Main class for working with SVG documents
* ``convert()`` - Convenience function for simple conversions
* ``svg_utils`` - SVG manipulation utilities
* ``image_utils`` - Image encoding/decoding utilities
* ``eval.py`` - Quality evaluation utilities for testing

Core Converter Layer
~~~~~~~~~~~~~~~~~~~~

**Location:** ``src/psd2svg/core/``

The core converter uses multiple inheritance with specialized mixins:

.. code-block:: python

   class Converter(
       AdjustmentConverter,
       LayerConverter,
       PaintConverter,
       ShapeConverter,
       TextConverter,
       EffectConverter,
   ):
       """Main converter class combining all converter mixins."""

**Converter Mixins:**

* ``AdjustmentConverter`` (``adjustment.py``) - Handles adjustment layers
* ``EffectConverter`` (``effects.py``) - Processes layer effects
* ``LayerConverter`` (``layer.py``) - Core layer conversion logic
* ``ShapeConverter`` (``shape.py``) - Converts vector shapes
* ``PaintConverter`` (``paint.py``) - Handles fill and stroke patterns
* ``TextConverter`` (``text.py``) - Processes text layers

**Supporting Modules:**

* ``base.py`` - Base converter class
* ``color_utils.py`` - Color conversion utilities
* ``constants.py`` - Constants and enums
* ``converter.py`` - Main converter class
* ``counter.py`` - ID generation for SVG elements
* ``font_mapping.py`` - Font mapping functionality
* ``font_utils.py`` - Font utilities
* ``gradient.py`` - Gradient conversion logic
* ``typesetting.py`` - Text typesetting
* ``windows_fonts.py`` - Windows font resolution
* ``_font_mapping_data.py`` - Font mapping data

Rasterizer Layer
~~~~~~~~~~~~~~~~

**Location:** ``src/psd2svg/rasterizer/``

Provides SVG to raster image conversion:

* ``base_rasterizer.py`` - Abstract base class defining the interface
* ``resvg_rasterizer.py`` - Default, fast production rasterizer (resvg-py)
* ``playwright_rasterizer.py`` - Optional browser-based renderer (better SVG 2.0 support)

Code Quality Standards
----------------------

Type Hints
~~~~~~~~~~

The project requires full type annotation coverage:

.. code-block:: python

   from PIL import Image
   from typing import Optional

   def process_image(
       image: Image.Image,
       quality: int = 95,
       format: str = "png",
   ) -> bytes:
       """Process image and return bytes."""
       ...

All public APIs and internal functions must have type hints. Use ``mypy`` to verify:

.. code-block:: bash

   uv run mypy src/

Docstrings
~~~~~~~~~~

Use Google-style docstrings for all public functions and classes:

.. code-block:: python

   def convert(
       input_path: str,
       output_path: str,
       embed_images: bool = True,
   ) -> None:
       """Convert PSD file to SVG.

       Args:
           input_path: Path to input PSD file.
           output_path: Path to output SVG file.
           embed_images: Whether to embed images as data URIs.

       Returns:
           None

       Raises:
           FileNotFoundError: If input file doesn't exist.
           ValueError: If file format is invalid.
       """
       ...

Code Style
~~~~~~~~~~

* Follow PEP 8 guidelines
* Use ruff for linting and formatting
* Maximum line length: 88 characters (Black-compatible)
* Use meaningful variable names
* Keep functions focused and small

Testing
~~~~~~~

* Write tests for all new features
* Maintain or improve code coverage
* Test edge cases and error conditions
* Use pytest fixtures for common setup

.. code-block:: python

   import pytest
   from psd2svg import SVGDocument

   def test_svg_document_creation():
       """Test SVGDocument creation."""
       # Arrange
       svg_string = '<svg>...</svg>'

       # Act
       document = SVGDocument.load(svg_string, {})

       # Assert
       assert document is not None

Contributing
------------

Workflow
~~~~~~~~

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a feature branch**: ``git checkout -b feature/my-feature``
4. **Make your changes** with tests and documentation
5. **Run quality checks**:

   .. code-block:: bash

      uv run ruff format src/ tests/
      uv run ruff check src/ tests/
      uv run mypy src/ tests/
      uv run pytest

6. **Commit your changes**: ``git commit -m "Add my feature"``
7. **Push to your fork**: ``git push origin feature/my-feature``
8. **Open a Pull Request** on GitHub

Pull Request Guidelines
~~~~~~~~~~~~~~~~~~~~~~~~

* Provide a clear description of the changes
* Reference related issues
* Include tests for new functionality
* Update documentation as needed
* Ensure all CI checks pass
* Keep PRs focused on a single feature/fix

Commit Messages
~~~~~~~~~~~~~~~

Use clear, descriptive commit messages:

.. code-block:: text

   Add support for gradient patterns

   - Implement linear gradient conversion
   - Add radial gradient support
   - Add tests for gradient patterns
   - Update documentation

Code Review
~~~~~~~~~~~

All contributions go through code review:

* Address reviewer feedback promptly
* Be open to suggestions and improvements
* Discuss significant changes before implementation

Adding New Features
-------------------

Adding a Converter Feature
~~~~~~~~~~~~~~~~~~~~~~~~~~

To add support for a new Photoshop feature:

1. **Identify the appropriate converter mixin** (Layer, Shape, Effect, etc.)
2. **Add conversion logic** to the mixin
3. **Add helper methods** if needed
4. **Write tests** for the new feature
5. **Update documentation**

Example structure:

.. code-block:: python

   # In src/psd2svg/core/effects.py

   class EffectConverter(BaseConverter):
       def convert_new_effect(
           self,
           layer: Layer,
           effect_data: dict,
       ) -> str:
           """Convert new effect to SVG.

           Args:
               layer: The layer with the effect.
               effect_data: Effect parameters.

           Returns:
               SVG filter element string.
           """
           # Implementation here
           ...

Working with Rasterizers
~~~~~~~~~~~~~~~~~~~~~~~~~

The package provides two rasterization backends:

**ResvgRasterizer** (default):

.. code-block:: python

   from psd2svg.rasterizer import ResvgRasterizer

   # Create rasterizer instance
   rasterizer = ResvgRasterizer(dpi=96)

   # Rasterize from string
   svg_string = '<svg>...</svg>'
   image = rasterizer.from_string(svg_string)
   image.save('output.png')

   # Rasterize from file
   image = rasterizer.from_file('input.svg')
   image.save('output.png')

**PlaywrightRasterizer** (optional, requires ``browser`` optional dependency):

.. code-block:: python

   from psd2svg.rasterizer import PlaywrightRasterizer

   # Use as context manager (automatically cleans up browser)
   with PlaywrightRasterizer(dpi=96) as rasterizer:
       image = rasterizer.from_file('input.svg')
       image.save('output.png')

Debugging
---------

Common Issues
~~~~~~~~~~~~~

**Import errors:**

.. code-block:: bash

   # Ensure dependencies are installed
   uv sync

**Type checking errors:**

.. code-block:: bash

   # Run mypy with verbose output
   uv run mypy --verbose src/

**Test failures:**

.. code-block:: bash

   # Run specific test with output
   uv run pytest -vv tests/test_name.py::test_function

Development Tips
~~~~~~~~~~~~~~~~

1. **Use the Python REPL** for interactive testing:

   .. code-block:: bash

      uv run python

2. **Test with sample PSD files** in ``tests/`` directory
3. **Check SVG output** in a browser to verify rendering
4. **Use debugger** for complex issues:

   .. code-block:: python

      import pdb; pdb.set_trace()

Resources
---------

* `PSD Tools Documentation <https://psd-tools.readthedocs.io/>`_
* `SVG Specification <https://www.w3.org/TR/SVG11/>`_
* `Pillow Documentation <https://pillow.readthedocs.io/>`_
* `Python Type Hints <https://docs.python.org/3/library/typing.html>`_

Release Process
---------------

For maintainers, this project follows a pull request workflow for all changes to the main branch:

.. code-block:: bash

   # 1. Create release branch
   git checkout -b release/v0.10.0

   # 2. Update version and changelog
   # - Edit version in pyproject.toml
   # - Update CHANGELOG.md with release notes

   # 3. Sync dependencies to update lock file
   uv sync

   # 4. Commit and push
   git add pyproject.toml CHANGELOG.md uv.lock
   git commit -m "Prepare release v0.10.0"
   git push -u origin release/v0.10.0

   # 5. Create PR for release
   gh pr create --title "Release v0.10.0" --body "Release notes..."

   # 6. After PR is merged to main, create and push tag
   git checkout main
   git pull origin main
   git tag v0.10.0
   git push origin v0.10.0

**Note:** GitHub Actions automatically builds and publishes to PyPI via OIDC when a version tag is pushed (``.github/workflows/release.yml``).
Manual publishing is not necessary as the release workflow handles this automatically.

Getting Help
------------

* **Issues**: Report bugs and ask questions on `GitHub Issues <https://github.com/CyberAgent/psd2svg/issues>`_
* **Documentation**: Refer to `psd2svg.readthedocs.io <https://psd2svg.readthedocs.io/>`_
* **Security**: Report vulnerabilities privately following `SECURITY.md <https://github.com/CyberAgent/psd2svg/blob/main/SECURITY.md>`_
