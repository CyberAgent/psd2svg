Rasterizers
===========

This guide covers converting SVG documents to raster images (PNG, JPEG, etc.).

Overview
--------

Rasterizers convert SVG documents produced by psd2svg into raster images. The package provides two rasterization backends:

* **ResvgRasterizer** (default) - Fast Rust-based renderer using resvg-py
* **PlaywrightRasterizer** (optional) - Browser-based renderer with full SVG 2.0 support

Quick Start
~~~~~~~~~~~

Using with SVGDocument:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   # Convert PSD to SVG
   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)

   # Rasterize to PNG (uses ResvgRasterizer by default)
   image = document.rasterize()
   image.save('output.png')

   # High DPI for print
   image = document.rasterize(dpi=300)
   image.save('output_print.png')

Choosing a Rasterizer
----------------------

Feature Comparison
~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Feature
     - ResvgRasterizer
     - PlaywrightRasterizer
   * - Performance
     - Fast (Rust-based)
     - Slower (browser-based)
   * - Installation Size
     - Small (~5MB)
     - Large (~200MB)
   * - SVG 1.1 Support
     - Excellent
     - Excellent
   * - SVG 2.0 Support
     - Partial
     - Full
   * - ``<foreignObject>``
     - Not supported
     - Supported
   * - Variable Fonts
     - Known issues
     - Works correctly
   * - Memory Usage
     - Low
     - Higher
   * - Serverless Friendly
     - Yes
     - No
   * - Production Ready
     - Yes
     - Yes

When to Use Which
~~~~~~~~~~~~~~~~~

**Use ResvgRasterizer (default) when:**

* Performance is critical
* Deploying to serverless environments
* Memory constraints exist
* Standard SVG features are sufficient
* Installation size matters

**Use PlaywrightRasterizer when:**

* SVG 2.0 features are required
* Text wrapping with ``<foreignObject>`` is needed
* Variable font rendering is important
* Browser-accurate rendering is required
* Testing/QA against browser rendering

ResvgRasterizer
---------------

Fast, production-ready SVG renderer using resvg (Rust implementation).

Installation
~~~~~~~~~~~~

Included automatically with psd2svg:

.. code-block:: bash

   pip install psd2svg

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from psd2svg.rasterizer import ResvgRasterizer

   # Create rasterizer
   rasterizer = ResvgRasterizer()

   # From file
   image = rasterizer.from_file('input.svg')
   image.save('output.png')

   # From string
   svg_string = '<svg>...</svg>'
   image = rasterizer.from_string(svg_string)
   image.save('output.png')

   # High DPI
   rasterizer = ResvgRasterizer(dpi=300)
   image = rasterizer.from_file('input.svg')
   image.save('output_print.png')

Examples
~~~~~~~~

Batch Processing
^^^^^^^^^^^^^^^^

.. code-block:: python

   from pathlib import Path
   from psd2svg.rasterizer import ResvgRasterizer

   rasterizer = ResvgRasterizer()
   svg_dir = Path("svg_files")
   png_dir = Path("png_output")
   png_dir.mkdir(exist_ok=True)

   for svg_file in svg_dir.glob("*.svg"):
       output_path = png_dir / f"{svg_file.stem}.png"
       image = rasterizer.from_file(str(svg_file))
       image.save(output_path)

Output Formats
^^^^^^^^^^^^^^

.. code-block:: python

   from psd2svg.rasterizer import ResvgRasterizer

   rasterizer = ResvgRasterizer()
   image = rasterizer.from_file('input.svg')

   # PNG - lossless
   image.save('output.png', format='PNG', optimize=True)

   # JPEG - lossy (convert to RGB first)
   image.convert('RGB').save('output.jpg', format='JPEG', quality=95)

   # WebP - modern format
   image.save('output.webp', format='WEBP', quality=90)

API Reference
~~~~~~~~~~~~~

.. code-block:: python

   class ResvgRasterizer(BaseRasterizer):
       def __init__(self, dpi: int = 0) -> None:
           """Initialize the resvg rasterizer.

           Args:
               dpi: Dots per inch for rendering. If 0 (default), uses 96 DPI.
                   Higher values produce larger, higher resolution images.
           """

       def from_file(self, filepath: str) -> Image.Image:
           """Rasterize an SVG file to a PIL Image.

           Args:
               filepath: Path to the SVG file to rasterize.

           Returns:
               PIL Image object in RGBA mode.

           Raises:
               FileNotFoundError: If the SVG file does not exist.
               ValueError: If the SVG content is invalid.
           """

       def from_string(self, svg_content: Union[str, bytes]) -> Image.Image:
           """Rasterize SVG content from a string to a PIL Image.

           Args:
               svg_content: SVG content as string or bytes.

           Returns:
               PIL Image object in RGBA mode.

           Raises:
               ValueError: If the SVG content is invalid.
           """

Limitations
~~~~~~~~~~~

**SVG Feature Support:**

* Does not support ``<foreignObject>`` elements (ignored during rendering)
* Partial SVG 2.0 support (e.g., ``text-orientation: upright`` not supported)
* Variable fonts may not render correctly

**Error Handling:**

As of resvg-py 0.2.5, the library properly raises Python exceptions for edge cases:

* **Malformed SVG**: Raises ``ValueError`` with descriptive error message
* **Missing files**: Raises ``ValueError`` with error details
* **Empty/invalid content**: Raises ``ValueError``

These exceptions can be caught with standard Python exception handling:

.. code-block:: python

   from psd2svg.rasterizer import ResvgRasterizer

   def safe_rasterize(svg_path):
       rasterizer = ResvgRasterizer()
       try:
           return rasterizer.from_file(svg_path)
       except ValueError as e:
           print(f"Failed to rasterize: {e}")
           return None

**Note:** Versions prior to resvg-py 0.2.5 would crash (SIGABRT) with malformed SVG.

PlaywrightRasterizer
--------------------

Browser-based SVG rasterizer with full SVG 2.0 support using Chromium.

Installation
~~~~~~~~~~~~

Requires the ``browser`` optional dependency:

.. code-block:: bash

   pip install psd2svg[browser]
   playwright install chromium

Basic Usage
~~~~~~~~~~~

**Important:** Always use as a context manager to ensure proper browser cleanup.

.. code-block:: python

   from psd2svg.rasterizer import PlaywrightRasterizer

   # Use as context manager
   with PlaywrightRasterizer(dpi=96) as rasterizer:
       image = rasterizer.from_file('input.svg')
       image.save('output.png')

With SVGDocument
~~~~~~~~~~~~~~~~

.. code-block:: python

   from psd2svg import SVGDocument
   from psd2svg.rasterizer import PlaywrightRasterizer
   from psd_tools import PSDImage

   psdimage = PSDImage.open('input.psd')
   document = SVGDocument.from_psd(psdimage)

   # Rasterize using Playwright
   with PlaywrightRasterizer(dpi=96) as rasterizer:
       image = document.rasterize(rasterizer=rasterizer)
       image.save('output.png')

Examples
~~~~~~~~

Batch Processing
^^^^^^^^^^^^^^^^

.. code-block:: python

   from pathlib import Path
   from psd2svg.rasterizer import PlaywrightRasterizer

   svg_dir = Path("svg_files")
   png_dir = Path("png_output")
   png_dir.mkdir(exist_ok=True)

   # Reuse browser instance for better performance
   with PlaywrightRasterizer() as rasterizer:
       for svg_file in svg_dir.glob("*.svg"):
           output_path = png_dir / f"{svg_file.stem}.png"
           image = rasterizer.from_file(str(svg_file))
           image.save(output_path)

SVG 2.0 Features
^^^^^^^^^^^^^^^^

.. code-block:: python

   from psd2svg import SVGDocument
   from psd2svg.rasterizer import PlaywrightRasterizer
   from psd_tools import PSDImage

   # Convert PSD with vertical text (SVG 2.0 feature)
   psdimage = PSDImage.open('vertical_text.psd')
   document = SVGDocument.from_psd(psdimage)

   # Render with Playwright (supports SVG 2.0)
   with PlaywrightRasterizer() as rasterizer:
       image = document.rasterize(rasterizer=rasterizer)
       image.save('output_vertical_text.png')

API Reference
~~~~~~~~~~~~~

.. code-block:: python

   class PlaywrightRasterizer(BaseRasterizer):
       def __init__(
           self,
           dpi: int = 96,
           browser_type: Literal["chromium", "firefox", "webkit"] = "chromium",
       ) -> None:
           """Initialize the Playwright rasterizer.

           Args:
               dpi: Dots per inch for rendering. Default is 96 DPI; 0 also
                   means 96 DPI. Higher values produce larger, higher
                   resolution images.
               browser_type: Browser engine to use. Default is "chromium".
           """

       def __enter__(self) -> PlaywrightRasterizer:
           """Enter context manager - starts browser."""

       def __exit__(self, *args) -> None:
           """Exit context manager - closes browser and cleans up resources."""

       def from_file(self, filepath: str) -> Image.Image:
           """Rasterize an SVG file to a PIL Image.

           Args:
               filepath: Path to the SVG file to rasterize.

           Returns:
               PIL Image object in RGBA mode.
           """

       def from_string(self, svg_content: Union[str, bytes]) -> Image.Image:
           """Rasterize SVG content from a string to a PIL Image.

           Args:
               svg_content: SVG content as string or bytes.

           Returns:
               PIL Image object in RGBA mode.
           """

Common Tasks
------------

Resizing Images
~~~~~~~~~~~~~~~

Rasterizers render at the intrinsic size defined in the SVG. To resize:

.. code-block:: python

   from psd2svg.rasterizer import ResvgRasterizer
   from PIL import Image

   rasterizer = ResvgRasterizer()
   image = rasterizer.from_file('input.svg')

   # Resize to specific dimensions
   resized = image.resize((800, 600), Image.Resampling.LANCZOS)
   resized.save('output_800x600.png')

Custom Background
~~~~~~~~~~~~~~~~~

Rasterized images have transparent backgrounds by default. To add a background:

.. code-block:: python

   from psd2svg.rasterizer import ResvgRasterizer
   from PIL import Image

   rasterizer = ResvgRasterizer()
   image = rasterizer.from_file('input.svg')

   # Create white background
   background = Image.new('RGB', image.size, (255, 255, 255))
   background.paste(image, (0, 0), image)
   background.save('output_white_bg.png')

Fallback Strategy
~~~~~~~~~~~~~~~~~

Try ResvgRasterizer first, fall back to Playwright if needed:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd2svg.rasterizer import ResvgRasterizer
   from psd_tools import PSDImage

   psdimage = PSDImage.open('input.psd')
   document = SVGDocument.from_psd(psdimage)

   # Try ResvgRasterizer first (faster)
   try:
       image = document.rasterize()
       image.save('output.png')
   except Exception:
       # Fall back to Playwright if needed
       from psd2svg.rasterizer import PlaywrightRasterizer
       with PlaywrightRasterizer() as rasterizer:
           image = document.rasterize(rasterizer=rasterizer)
           image.save('output.png')

Performance Tips
~~~~~~~~~~~~~~~~

**For ResvgRasterizer:**

* Reuse rasterizer instances when possible
* Use appropriate DPI (higher DPI = larger output)
* Validate SVG before rasterizing (see Limitations section)

**For PlaywrightRasterizer:**

* Reuse browser instance for batch operations (use context manager once)
* Close browser when done (use context manager)
* Minimize page loads (process multiple SVGs in one session)
* Consider headless mode overhead

Troubleshooting
---------------

ResvgRasterizer Issues
~~~~~~~~~~~~~~~~~~~~~~

**Installation fails:**

.. code-block:: bash

   # Ensure compatible Python version
   python --version  # Should be 3.10+

   # Upgrade pip
   pip install --upgrade pip

   # Install resvg-py
   pip install resvg-py

**Crashes (SIGABRT):**

If resvg-py crashes, validate SVG content before rasterizing (see Limitations section above) or use PlaywrightRasterizer.

PlaywrightRasterizer Issues
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Browser not installed:**

.. code-block:: bash

   playwright install chromium

**Import error:**

Ensure the ``browser`` extra is installed:

.. code-block:: bash

   pip install psd2svg[browser]

**Memory issues:**

For long-running processes, close and reopen browser periodically:

.. code-block:: python

   from pathlib import Path
   from psd2svg.rasterizer import PlaywrightRasterizer

   svg_files = list(Path("svg_files").glob("*.svg"))

   # Process in batches to manage memory
   batch_size = 50
   for i in range(0, len(svg_files), batch_size):
       batch = svg_files[i:i+batch_size]
       with PlaywrightRasterizer() as rasterizer:
           for svg_file in batch:
               image = rasterizer.from_file(str(svg_file))
               image.save(f"{svg_file.stem}.png")
