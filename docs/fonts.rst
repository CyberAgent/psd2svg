Font Handling
=============

This guide covers font embedding, subsetting, and optimization for SVG output.

Overview
--------

psd2svg can embed fonts directly in SVG files using ``@font-face`` CSS rules. For web delivery, font subsetting dramatically reduces file sizes by including only the glyphs actually used.

**Note:** Font subsetting is enabled by default when embedding fonts. The required ``fonttools`` package is automatically installed with psd2svg.

**Platform Support:**

* **Linux/macOS**: Full font resolution and embedding via fontconfig
* **Windows**: Full font resolution and embedding via Windows registry + fontTools parsing

Font Embedding Basics
----------------------

Simple Embedding
~~~~~~~~~~~~~~~~

Embed fonts as base64-encoded data URIs in the SVG:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)
   document.save("output.svg", embed_fonts=True)

**Result:** Fonts are embedded as base64-encoded TTF/OTF files in ``@font-face`` rules.

**Pros:**

* Self-contained SVG files (no external font dependencies)
* Consistent rendering across platforms
* Works offline

**Cons:**

* Much larger file sizes (100KB+ per font)
* Base64 encoding adds ~33% overhead
* May include glyphs not used in the document

Font Resolution Process
-----------------------

psd2svg uses a two-phase process for handling fonts in text layers:

Two-Phase Font Handling
~~~~~~~~~~~~~~~~~~~~~~~~

**Phase 1: Conversion (from_psd)**

During PSD to SVG conversion, PostScript font names are preserved in the SVG tree:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")  # Text uses PostScript name "ArialMT"
   document = SVGDocument.from_psd(psdimage)
   # SVG tree now contains: <text font-family="ArialMT">...</text>

At this stage, font names remain as PostScript names (e.g., "ArialMT", "TimesNewRomanPSMT").

**Phase 2: Output (save/tostring)**

During SVG output, font names are resolved based on the embedding mode:

**Without font embedding** (``embed_fonts=False``, default):

.. code-block:: python

   # Uses static font mapping (~4,950 fonts)
   document.save("output.svg")
   # Result: <text font-family="Arial">...</text>

* PostScript names are mapped to CSS family names using static mapping
* No system font queries are performed
* Works on all platforms without external dependencies

**With font embedding** (``embed_fonts=True``):

.. code-block:: python

   # Uses platform-specific font resolution
   document.save("output.svg", embed_fonts=True)
   # Result: <text font-family="DejaVu Sans">...</text>
   #         @font-face { font-family: 'DejaVu Sans'; ... }

* PostScript names are resolved to system fonts via fontconfig (Linux/macOS) or Windows registry
* Automatically handles font substitution when requested font is unavailable
* Embeds the actual system font file found
* Logs font resolution at INFO level

**Example with substitution:**

If "ArialMT" is requested but Arial is not installed, the system may substitute DejaVu Sans:

.. code-block:: text

   INFO Resolved font 'ArialMT' → 'DejaVu Sans' (file: '/usr/share/fonts/...')

The generated SVG will use the substituted font:

.. code-block:: xml

   <!-- Text element uses substituted font -->
   <text font-family="DejaVu Sans">Hello World</text>

.. code-block:: css

   /* Font embedded in <style> or <defs> section */
   @font-face {
     font-family: 'DejaVu Sans';
     src: url(data:font/ttf;base64,...);
   }

Platform Behavior
~~~~~~~~~~~~~~~~~

**Static mapping** (all platforms, no embedding):

* Uses built-in font database (~4,950 fonts)
* Maps PostScript names to CSS family names
* No system font queries or file access
* Enables text conversion without font files

**Linux/macOS** (with font embedding):

* Queries fontconfig for system fonts
* Uses fontconfig CharSet API for Unicode codepoint-based font matching
* Automatically handles font substitution
* Embeds actual system font files

**Windows** (with font embedding):

* Queries Windows registry for system fonts
* Uses fontTools cmap parsing for Unicode codepoint-based font matching
* Automatically handles font substitution
* Supports both TrueType and OpenType fonts
* Embeds actual system font files

Custom Font Mapping
-------------------

For fonts not in the default mapping (~4,950 fonts), you can provide custom font mappings to enable text conversion.

Understanding Font Mapping
~~~~~~~~~~~~~~~~~~~~~~~~~~~

psd2svg uses PostScript font names (e.g., "ArialMT", "TimesNewRomanPSMT") to resolve fonts. The mapping provides:

* **Font family** name (e.g., "Arial")
* **Font style** (e.g., "Regular", "Bold")
* **Font weight** (numeric value, 0-250, where 80 = Regular, 200 = Bold)

This information is used to generate SVG ``<text>`` elements with correct font properties.

**Built-in Font Mapping:**

The default static mapping includes approximately 4,950 fonts:

* **539 default fonts**: Core fonts (Arial, Times New Roman, Noto fonts, Roboto, Adobe fonts, etc.)
* **370 Hiragino variants**: Japanese fonts with W0-W9 weight pattern (generated dynamically)
* **4,042 Morisawa fonts**: Professional Japanese typography fonts

Font mappings are stored as JSON resource files and lazy-loaded on first access for optimal performance.

**Font Resolution Priority:**

1. Custom mapping (if provided via ``font_mapping`` parameter)
2. Default static mapping (539 core fonts, lazy-loaded)
3. Hiragino generated mapping (370 variants, generated on first call)
4. Morisawa mapping (4,042 fonts, lazy-loaded)
5. Platform-specific font resolution for file path discovery:

   * **Linux/macOS**: fontconfig query
   * **Windows**: Windows registry + fontTools parsing

Custom mappings take highest priority, allowing you to override built-in font resolution.

Generating Custom Mappings
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use the CLI tool to extract fonts from your PSD files:

.. code-block:: bash

   # Extract all fonts from a PSD file
   python -m psd2svg.tools.generate_font_mapping input.psd -o fonts.json

   # Show only fonts NOT in default mapping
   python -m psd2svg.tools.generate_font_mapping input.psd --only-missing

   # Query fontconfig to auto-fill font details (Linux/macOS)
   python -m psd2svg.tools.generate_font_mapping input.psd --query-fontconfig -o fonts.json

   # Multiple PSD files
   python -m psd2svg.tools.generate_font_mapping *.psd -o fonts.json

   # Python format output (for embedding in code)
   python -m psd2svg.tools.generate_font_mapping input.psd -o fonts.py --format python

   # Verbose mode shows progress and font details
   python -m psd2svg.tools.generate_font_mapping input.psd -v

**Output Formats:**

* ``json`` (default): JSON file for use with Python API
* ``python``: Python dict literal for embedding in source code

**What the tool does:**

1. Opens PSD file(s) and scans all visible text layers
2. Extracts PostScript font names actually used
3. Checks against default mapping
4. Optionally queries fontconfig for font details
5. Generates mapping file in requested format

Using Custom Mappings
~~~~~~~~~~~~~~~~~~~~~~

Load and use custom font mappings in your conversion:

.. code-block:: python

   import json
   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   # Load custom font mapping from JSON
   with open("fonts.json") as f:
       custom_fonts = json.load(f)

   # Use custom mapping in conversion
   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage, font_mapping=custom_fonts)
   document.save("output.svg")

**Font Mapping Structure:**

.. code-block:: json

   {
       "MyCustomFont-Regular": {
           "family": "My Custom Font",
           "style": "Regular",
           "weight": 80.0,
           "_comment": "Optional comment for documentation"
       },
       "MyCustomFont-Bold": {
           "family": "My Custom Font",
           "style": "Bold",
           "weight": 200.0
       },
       "AnotherFont-Italic": {
           "family": "Another Font",
           "style": "Italic",
           "weight": 80.0
       }
   }

**Required fields:**

* ``family`` (string): Font family name
* ``style`` (string): Font style (e.g., "Regular", "Bold", "Italic")
* ``weight`` (float): Font weight (0-250, typical: 80 = Regular, 200 = Bold)

**Optional fields:**

* ``_comment`` (string): Human-readable comment (ignored during processing)

When to Use Custom Mappings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Custom font mappings are useful when:

* **Using custom or proprietary fonts** not in the default mapping
* **Working with uncommon fonts** in PSD files
* **Overriding default font resolution** for specific fonts
* **Working on Windows** to enable text conversion for specific fonts
* **Ensuring consistent font naming** across different systems

**Example Use Cases:**

1. **Corporate branding fonts**: Map proprietary brand fonts used in PSD files
2. **Web font services**: Map PostScript names to web font equivalents
3. **Font substitution**: Override mappings to use different fonts in output
4. **Multi-language projects**: Add fonts for specific writing systems

Font Embedding with Custom Mappings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Custom mappings enable text conversion but don't provide font file paths. For font embedding, the ``FontInfo.find_with_files()`` method automatically queries platform-specific font resolution:

**On Linux/macOS:**

Automatically queries fontconfig during conversion:

* Resolves fonts to actual system fonts
* Detects substitutions and generates fallback chains
* Enables font embedding with ``embed_fonts=True``

**On Windows:**

Automatically queries Windows registry + fontTools parsing during conversion:

* Resolves fonts to actual system fonts
* Detects substitutions and generates fallback chains
* Enables font embedding with ``embed_fonts=True``

.. code-block:: python

   # Font embedding works automatically on all platforms
   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(
       psdimage,
       font_mapping=custom_fonts,  # Provides font metadata
       embed_fonts=True             # Fonts resolved and embedded automatically
   )

Font Subsetting (Recommended)
------------------------------

What is Font Subsetting?
~~~~~~~~~~~~~~~~~~~~~~~~~

Font subsetting creates minimal font files containing only the glyphs actually used in your SVG. This typically reduces font file sizes by 90-95%.

**Example:** If your SVG only uses "Hello World", the subset font will only contain the glyphs for H, e, l, o, W, r, d (plus space and punctuation).

Using WOFF2 Format
~~~~~~~~~~~~~~~~~~

WOFF2 provides the best compression and automatically enables subsetting:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)

   # Save with WOFF2 subsetting and font embedding
   document.save("output.svg", embed_fonts=True, font_format="woff2")

**Result:** Fonts are:

1. Analyzed to extract used glyphs
2. Subset to include only those glyphs
3. Compressed with WOFF2 (best compression)
4. Embedded as base64 data URIs

**Typical Size Reduction:**

* Original TTF: 150 KB
* Subset WOFF2: 5-10 KB (90-95% reduction)

Supported Font Formats
~~~~~~~~~~~~~~~~~~~~~~

The ``font_format`` parameter accepts:

* ``woff2`` - Best compression, subset automatically (recommended)
* ``woff`` - Good compression, subset automatically
* ``ttf`` - No compression, subset if glyphs specified
* ``otf`` - No compression, subset if glyphs specified

.. code-block:: python

   # WOFF2 (recommended)
   document.save("output.svg", font_format="woff2")

   # WOFF (good compression)
   document.save("output.svg", font_format="woff")

   # TTF (no compression, larger files)
   document.save("output.svg", font_format="ttf")

Advanced Subsetting Options
----------------------------

Manual Glyph Selection
~~~~~~~~~~~~~~~~~~~~~~

For advanced use cases, you can manually specify glyphs to include:

.. code-block:: python

   from psd2svg.font_subsetting import extract_used_unicode, subset_font
   import xml.etree.ElementTree as ET

   # Parse SVG
   svg_tree = ET.parse("output.svg").getroot()

   # Extract Unicode characters per font
   font_usage = extract_used_unicode(svg_tree)
   # => {"Arial": {"H", "e", "l", "o"}, "Times": {"W", "r", "d"}}

   # Subset a font file
   font_bytes = subset_font(
       input_path="/usr/share/fonts/arial.ttf",
       output_format="woff2",
       unicode_chars={"H", "e", "l", "o"}
   )
   # => b'wOF2...' (WOFF2 font bytes)

**Note:** This is typically used internally by ``SVGDocument.save()`` and ``tostring()`` methods. Direct usage is only needed for custom workflows.

Subsetting with tostring()
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Font subsetting also works with the ``tostring()`` method:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)

   # Get SVG string with WOFF2 subsetting and font embedding
   svg_string = document.tostring(embed_fonts=True, font_format="woff2")

Browser Compatibility
---------------------

Font Format Support
~~~~~~~~~~~~~~~~~~~

Modern browsers have excellent font format support:

* **WOFF2**: Chrome 36+, Firefox 39+, Safari 10+, Edge 14+ (recommended)
* **WOFF**: Chrome 5+, Firefox 3.6+, Safari 5.1+, Edge 12+
* **TTF/OTF**: Universal support (but larger files)

For maximum compatibility with older browsers, use WOFF:

.. code-block:: python

   document.save("output.svg", font_format="woff")

Font Loading Behavior
~~~~~~~~~~~~~~~~~~~~~~

Embedded fonts in SVG are loaded immediately when the SVG is parsed. There is no FOUT (Flash of Unstyled Text) or layout shift.

Font Licensing
--------------

Important Considerations
~~~~~~~~~~~~~~~~~~~~~~~~

Font embedding and subsetting may be subject to licensing restrictions. Before distributing SVG files with embedded fonts:

1. **Check font licenses** - Verify the font license allows embedding
2. **Review restrictions** - Some licenses prohibit subsetting or modification
3. **Commercial fonts** - May require additional licensing for web use
4. **Open source fonts** - Generally more permissive (e.g., SIL OFL, Apache)

**Note:** Font subsetting creates a derivative work. Ensure your font license permits this.

Consult with legal counsel if uncertain about font license compliance.

Troubleshooting
---------------

Subsetting Not Working
~~~~~~~~~~~~~~~~~~~~~~

If font subsetting isn't working:

1. **Verify fontTools is installed:**

   .. code-block:: python

      import fontTools
      print(fontTools.__version__)

   If not installed, reinstall psd2svg:

   .. code-block:: bash

      pip install --force-reinstall psd2svg

2. **Check for errors** in the console output

Missing Glyphs
~~~~~~~~~~~~~~

If characters are missing after subsetting:

* The font may not contain glyphs for those characters
* Unicode normalization issues (e.g., composed vs decomposed characters)
* Try using ``font_format="ttf"`` without subsetting to verify

File Size Still Large
~~~~~~~~~~~~~~~~~~~~~

If file sizes are still large after subsetting:

* Multiple fonts may be embedded (each font adds size)
* Font may have extensive hinting data
* Try WOFF2 for best compression
* Consider using external font files instead of embedding

Performance Tips
----------------

Rasterization Performance
~~~~~~~~~~~~~~~~~~~~~~~~~

Playwright renders SVG content in an ``about:blank`` page, so local ``file://``
font URLs do not load there. During ``rasterize()`` with PlaywrightRasterizer,
psd2svg embeds the used glyphs as data URIs so Chromium can load the resolved font.
ResvgRasterizer continues to receive local font paths for its native loader.

.. code-block:: python

   from psd2svg import SVGDocument
   from psd2svg.rasterizer import PlaywrightRasterizer
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)

   # Resolved font glyphs are embedded as data URIs for Chromium.
   rasterizer = PlaywrightRasterizer(dpi=144)
   image = document.rasterize(rasterizer)
   image.save("output.png")

**Font handling:**

* ``save()``/``tostring()``: data URIs for portable SVG files
* Playwright rasterization: subset data URIs that load from the browser page
* Resvg rasterization: local ``file://`` URLs passed to the native font loader
* Font resolution and fallback chains are shared across both rasterizers

Best Practices
~~~~~~~~~~~~~~

1. **Use WOFF2 for web** - Best compression and broad browser support
2. **Subset by default** - No reason not to with WOFF2
3. **Cache font files** - If using external fonts, leverage HTTP caching
4. **Limit font families** - Each font adds to file size
5. **Consider system fonts** - For non-critical text, use web-safe fonts
6. **Choose a rasterizer for its rendering support** - Playwright supports browser SVG behavior; Resvg uses its native renderer

Comparison: Embedded vs External
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Embedded fonts (with subsetting):**

* **Pros:** Self-contained, no HTTP requests, works offline
* **Cons:** Larger initial file size (5-10KB per font)
* **Best for:** Single-page documents, offline use, email

**External fonts:**

* **Pros:** Smaller SVG files, fonts can be cached and reused
* **Cons:** Additional HTTP requests, requires server/CDN
* **Best for:** Multiple SVGs sharing fonts, web applications

Example: Optimized Web Delivery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)

   # Optimize for web: WOFF2 subsetting, external images, font embedding
   document.save(
       "output.svg",
       embed_fonts=True,
       font_format="woff2",
       image_prefix="images/img",
       image_format="webp",
       enable_title=False  # Remove layer names
   )

This produces the smallest possible file while maintaining visual fidelity.
