Configuration Options
=====================

This guide covers advanced configuration options for customizing SVG output.

Title Elements
--------------

**Option:** ``enable_title=True`` (default: ``False``)

By default, title elements are omitted to reduce file size. When enabled, each layer includes a ``<title>`` element with the Photoshop layer name for tooltips, accessibility, and debugging.

**SVG output difference:**

.. code-block:: xml

   <!-- Default (enable_title=False) -->
   <g id="layer-1">
     <rect x="0" y="0" width="100" height="100" fill="#ff0000" />
   </g>

   <!-- With enable_title=True -->
   <g id="layer-1">
     <title>Background Layer</title>
     <rect x="0" y="0" width="100" height="100" fill="#ff0000" />
   </g>

**Usage:** ``SVGDocument.from_psd(psdimage, enable_title=True)`` or ``psd2svg input.psd output.svg --enable-title``

**Enable for:** Development, debugging, accessibility, SVG editing

**Keep disabled for:** Production builds, minified output, when layer names are sensitive

Text Letter Spacing
-------------------

**Option:** ``text_letter_spacing_offset=<float>`` (default: ``0.0``)

Compensates for differences between Photoshop and SVG text rendering by adding a global offset (in pixels) to all letter-spacing values.

**Effect:**

* Positive values increase spacing
* Negative values decrease spacing
* Typical range: -0.05 to 0.1

**Usage:** ``SVGDocument.from_psd(psdimage, text_letter_spacing_offset=-0.015)`` or ``psd2svg input.psd output.svg --text-letter-spacing-offset -0.015``

**Finding the right value:** Compare SVG output with Photoshop rendering and adjust incrementally (±0.01, ±0.05) until spacing matches.

Class Attributes
----------------

**Option:** ``enable_class=True`` (default: ``False``)

Adds CSS class attributes to SVG elements for debugging (e.g., ``class="layer"``, ``class="shape"``).

**SVG output difference:**

.. code-block:: xml

   <!-- Default -->
   <g id="layer-1">
     <rect x="0" y="0" width="100" height="100" fill="#ff0000" />
   </g>

   <!-- With enable_class=True -->
   <g class="layer" id="layer-1">
     <rect class="shape" x="0" y="0" width="100" height="100" fill="#ff0000" />
   </g>

**Usage:** ``SVGDocument.from_psd(psdimage, enable_class=True)``

**Purpose:** CSS targeting, debugging in browser dev tools, element type identification

**Warning:** Disabled by default - increases file size, not useful in production, may conflict with existing CSS

Text Wrapping Mode
------------------

**Option:** ``text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT`` (default: ``TextWrappingMode.NONE``)

Controls how bounding box text is rendered. Requires: ``from psd2svg.core.text import TextWrappingMode``

**Modes:**

* **NONE (default):** Native SVG ``<text>`` elements (no wrapping, best compatibility)
* **FOREIGN_OBJECT:** Uses ``<foreignObject>`` with HTML for wrapping (experimental, not supported by ResvgRasterizer)

**SVG output difference:**

.. code-block:: xml

   <!-- NONE (default) -->
   <text x="10" y="20" style="font-size: 16px;">
     Text may overflow bounding box
   </text>

   <!-- FOREIGN_OBJECT -->
   <foreignObject x="10" y="10" width="200" height="100">
     <div xmlns="http://www.w3.org/1999/xhtml" style="font-size: 16px; width: 200px;">
       Text wraps within bounding box
     </div>
   </foreignObject>

**Usage:** ``SVGDocument.from_psd(psdimage, text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT)``

**Limitation:** ``<foreignObject>`` is not supported by ResvgRasterizer, only works in browsers

**Recommendation:** Use default (NONE) unless you specifically need wrapping and target browsers only

**Paragraph Formatting Support:**

When ``text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT``, paragraph formatting properties are converted to CSS:

* **First line indent** → ``text-indent``
* **Start indent** → ``padding-left``
* **End indent** → ``padding-right``
* **Space before/after** → ``margin-block-start`` (the gap across a paragraph
  break is the sum of the two, emitted on one side only)
* **Hanging punctuation** → ``hanging-punctuation`` (Safari only)
* **Auto hyphenation** → ``hyphens: auto`` + ``hyphenate-limit-chars`` (requires lang attribute)

Example output:

.. code-block:: xml

   <p style="margin: 0; padding: 0; text-indent: 26.67px; padding-left: 13.33px; margin-block-start: 20px;">
     Paragraph with first-line indent, left padding, and the gap before it.
   </p>

**Browser Support Notes:**

* ``hyphens: auto`` requires the ``lang`` attribute (automatically set to ``en`` when hyphenation is enabled) and works in all modern browsers
* ``hyphenate-limit-chars`` is supported in Firefox 43+, Safari 17+, but **not** in Chrome/Edge
* ``hanging-punctuation`` is only supported in Safari 10+
* PSD's ``ConsecutiveHyphens`` and ``Zone`` properties have no CSS equivalents

Optimization
------------

**Option:** ``optimize=True`` (default: ``True``)

Consolidates all ``<defs>`` elements into a single global ``<defs>`` section at the top of the SVG.

**SVG output difference:**

.. code-block:: xml

   <!-- optimize=False (scattered defs) -->
   <svg>
     <g id="layer-1">
       <defs><linearGradient id="gradient-1">...</linearGradient></defs>
       <rect fill="url(#gradient-1)" />
     </g>
     <g id="layer-2">
       <defs><filter id="shadow-1">...</filter></defs>
       <circle filter="url(#shadow-1)" />
     </g>
   </svg>

   <!-- optimize=True (consolidated defs) -->
   <svg>
     <defs>
       <linearGradient id="gradient-1">...</linearGradient>
       <filter id="shadow-1">...</filter>
     </defs>
     <g id="layer-1">
       <rect fill="url(#gradient-1)" />
     </g>
     <g id="layer-2">
       <circle filter="url(#shadow-1)" />
     </g>
   </svg>

**Usage:** ``document.save("output.svg", optimize=True)``

**Benefits:** Reduces file size, cleaner structure, better compression

**Disable when:** Debugging SVG structure, need exact element hierarchy

Live Shapes
-----------

**Option:** ``enable_live_shapes=True`` (default: ``True``)

Converts Photoshop live shapes to native SVG primitives (``<rect>``, ``<circle>``, ``<ellipse>``) instead of ``<path>`` elements.

**SVG output difference:**

.. code-block:: xml

   <!-- enable_live_shapes=True (default) -->
   <rect x="10" y="10" width="100" height="50" fill="#ff0000" />
   <circle cx="60" cy="35" r="20" fill="#0000ff" />

   <!-- enable_live_shapes=False -->
   <path d="M10,10 L110,10 L110,60 L10,60 Z" fill="#ff0000" />
   <path d="M60,15 A20,20 0 1,1 60,55 A20,20 0 1,1 60,15 Z" fill="#0000ff" />

**Usage:** ``SVGDocument.from_psd(psdimage, enable_live_shapes=False)`` or ``psd2svg input.psd output.svg --no-live-shapes``

**Benefits of enabled (default):** Semantic elements, easier editing, better for animation

**Benefits of disabled:** Uniform structure, better for complex transformations

Performance Tips
----------------

**Faster conversion:**

* ``enable_text=False`` - Rasterize text instead of converting
* ``enable_title=False`` - Skip title elements (default)
* ``image_prefix="images/img"`` - External images faster than base64
* Simplify PSD: merge layers, flatten effects

**Smaller file size:**

* ``enable_title=False`` - Skip titles (default)
* ``image_prefix="images/img"`` - External images smaller than embedded
* ``image_format="webp"`` - Best compression (default)
* ``optimize=True`` - Consolidate defs (default)
* ``embed_fonts=True, font_format="woff2"`` - Font subsetting with WOFF2 (90%+ reduction)

**Optimal configuration:**

.. code-block:: python

   document = SVGDocument.from_psd(psdimage, enable_title=False)
   document.save(
       "output.svg",
       image_prefix="images/img",
       image_format="webp",
       optimize=True
   )

Thread Safety
-------------

**psd2svg APIs are NOT thread-safe.** Do not share ``SVGDocument`` instances across threads.

**Safe approach for parallel conversions:**

.. code-block:: python

   from concurrent.futures import ThreadPoolExecutor
   from psd2svg import convert

   def convert_file(input_path, output_path):
       convert(input_path, output_path)  # Each thread gets own instance

   with ThreadPoolExecutor() as executor:
       executor.submit(convert_file, "input1.psd", "output1.svg")
       executor.submit(convert_file, "input2.psd", "output2.svg")

**Recommendation:** Use multiprocessing instead of threading for better parallel performance.

Error Handling
--------------

**Best practices:** Wrap conversions in try-except blocks

.. code-block:: python

   try:
       psdimage = PSDImage.open("input.psd")
       document = SVGDocument.from_psd(psdimage)
       document.save("output.svg")
   except FileNotFoundError:
       print("PSD file not found")
   except ValueError as e:
       print(f"Invalid PSD: {e}")

**Common exceptions:** ``FileNotFoundError``, ``ValueError`` (invalid PSD), ``PermissionError``, ``OSError``

**Debug logging:**

.. code-block:: python

   import logging
   logging.basicConfig(level=logging.DEBUG)

Prints detailed info: layer processing, font resolution, rasterization decisions

Environment Variables
----------------------

Resource Limits Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Resource limits can be configured via environment variables to set custom defaults:

.. code-block:: bash

   # Set custom default limits via environment variables
   export PSD2SVG_MAX_FILE_SIZE=1073741824  # 1GB (default: 2GB)
   export PSD2SVG_TIMEOUT=120               # 2 minutes (default: 3 minutes)
   export PSD2SVG_MAX_LAYER_DEPTH=75        # 75 levels (default: 100)
   export PSD2SVG_MAX_IMAGE_DIMENSION=12000 # 12K pixels (default: 16K)

.. code-block:: python

   from psd2svg import ResourceLimits, convert

   # Uses environment variables if set, otherwise hardcoded defaults
   limits = ResourceLimits.default()

   # Or use with convert()
   convert("input.psd", "output.svg")  # Automatically uses ResourceLimits.default()

**When to use environment variables:**

* **Shared hosting**: Set lower limits to prevent resource exhaustion
* **High-performance systems**: Increase limits for large files
* **CI/CD pipelines**: Configure limits per environment
* **Docker containers**: Set via Dockerfile ENV or docker-compose

**Validation:**

Environment variables are validated:

* Negative values trigger warnings and use hardcoded defaults
* Invalid values (non-numeric) are ignored with warnings
* Zero or missing values use hardcoded defaults

See :doc:`security` for more information about resource limits and DoS prevention.
