User Guide
==========

This guide provides an overview of using psd2svg for converting PSD files to SVG format.

For detailed information on specific topics, see the feature-specific guides linked below.

Quick Start
-----------

Command Line
~~~~~~~~~~~~

Convert a PSD file to SVG with a single command:

.. code-block:: bash

   psd2svg input.psd output.svg

For comprehensive command-line documentation, see :doc:`command-line`.

Python API
~~~~~~~~~~

Use the ``convert()`` convenience function for simple conversions:

.. code-block:: python

   from psd2svg import convert

   convert('input.psd', 'output.svg')

For advanced usage with the ``SVGDocument`` class, see the sections below.

Python API Reference
--------------------

The convert() Function
~~~~~~~~~~~~~~~~~~~~~~

For simple one-step conversions, use the ``convert()`` convenience function:

.. code-block:: python

   from psd2svg import convert

   # Basic conversion with embedded images
   convert('input.psd', 'output.svg')

   # With external images in same directory
   convert('input.psd', 'output.svg', image_prefix='.')

   # With external images in subdirectory
   convert('input.psd', 'output.svg', image_prefix='images/img')

   # With custom image format
   convert('input.psd', 'output.svg',
           image_prefix='images/img',
           image_format='webp')

   # With custom options
   convert('input.psd', 'output.svg',
           enable_title=False,
           include_hidden_layers=True,
           text_letter_spacing_offset=-0.015)

**Parameters:**

* ``input_path`` (str): Path to input PSD file
* ``output_path`` (str): Path to output SVG file
* ``embed_images`` (bool): Whether to embed images as data URIs (default: True if no image_prefix)
* ``image_prefix`` (str, optional): Prefix for external image files, relative to the output SVG file's directory
* ``image_format`` (str): Image format - 'png', 'jpeg', or 'webp' (default: 'webp')
* ``enable_title`` (bool): Enable insertion of <title> elements with layer names (default: False)
* ``include_hidden_layers`` (bool): Include layers hidden in Photoshop (default: False)
* ``text_letter_spacing_offset`` (float): Global offset (in pixels) to add to all letter-spacing values (default: 0.0)

SVGDocument Class
-----------------

The ``SVGDocument`` class is the main interface for working with SVG documents and their resources.

Creating SVGDocument
~~~~~~~~~~~~~~~~~~~~

From PSD File
^^^^^^^^^^^^^

Create an SVGDocument from a PSD file:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   # Load PSD file
   psdimage = PSDImage.open("input.psd")

   # Convert to SVGDocument
   document = SVGDocument.from_psd(psdimage)

   # Save to file
   document.save("output.svg")

**Common Options:**

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")

   # Disable text conversion (rasterize text)
   document = SVGDocument.from_psd(psdimage, enable_text=False)

   # Disable title elements
   document = SVGDocument.from_psd(psdimage, enable_title=False)

Saving SVG Documents
~~~~~~~~~~~~~~~~~~~~

With Embedded Images
^^^^^^^^^^^^^^^^^^^^

Embed all images as base64-encoded data URIs within the SVG file:

.. code-block:: python

   document.save("output.svg")  # Default behavior

With External Images
^^^^^^^^^^^^^^^^^^^^

Export images to external files. The ``image_prefix`` is interpreted relative to the output SVG file's directory:

.. code-block:: python

   # Images in same directory as SVG
   document.save("output.svg", image_prefix=".")
   # => output.svg, 01.webp, 02.webp, ...

   # Images in subdirectory
   document.save("output.svg", image_prefix="images/img")
   # => output.svg, images/img01.webp, images/img02.webp, ...

**For more details on image handling, see** :doc:`images`.

With Embedded Fonts
^^^^^^^^^^^^^^^^^^^

Embed fonts directly in the SVG file for self-contained documents:

.. code-block:: python

   # Embed fonts as base64-encoded data URIs
   document.save("output.svg", embed_fonts=True)

   # Embed fonts with WOFF2 compression and subsetting
   document.save("output.svg", embed_fonts=True, font_format="woff2")

**For more details on font handling and subsetting, see** :doc:`fonts`.

Getting SVG as String
~~~~~~~~~~~~~~~~~~~~~~

Get the SVG content as a string instead of saving to a file:

.. code-block:: python

   svg_string = document.tostring()
   print(svg_string)  # => "<svg>...</svg>"

   # With external images (relative paths)
   svg_string = document.tostring(image_prefix="images/img")

Export and Load
~~~~~~~~~~~~~~~

Export the document to a dictionary format:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)

   # Export document and resources
   data = document.export()
   # => {"svg": "<svg>...</svg>", "resources": {"001": <PIL.Image>, ...}}

   # Load from exported data
   restored = SVGDocument.load(data["svg"], data["resources"])

This is useful for serialization or transferring documents between processes.

Rasterization
~~~~~~~~~~~~~

Convert SVG documents to raster images using the built-in rasterizer support.

Using Built-in Method
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)

   # Rasterize to PIL Image
   image = document.rasterize()
   image.save('output.png')

   # Rasterize with custom DPI
   image = document.rasterize(dpi=300)
   image.save('output_high_res.png')

Using Rasterizer Directly
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from psd2svg.rasterizer import ResvgRasterizer

   rasterizer = ResvgRasterizer(dpi=96)

   # Rasterize from file
   image = rasterizer.from_file('output.svg')
   image.save('rasterized.png')

**For comprehensive rasterization documentation, see** :doc:`rasterizers`.

Feature Guides
--------------

For detailed information on specific features, see these dedicated guides:

* **:doc:`command-line`** - Complete command-line interface reference
* **:doc:`images`** - Image embedding, formats, and optimization
* **:doc:`fonts`** - Font embedding and subsetting
* **:doc:`rasterizers`** - SVG to raster image conversion
* **:doc:`configuration`** - Advanced configuration options

Best Practices
--------------

For Web Delivery
~~~~~~~~~~~~~~~~

Optimize for web applications:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)

   document.save(
       "output.svg",
       embed_fonts=True,           # Embed fonts
       image_prefix="images/img",  # External images
       image_format="webp",        # Best compression
       font_format="woff2",        # Font subsetting
       enable_title=False          # Remove layer names
   )

**Topics covered:**

* :doc:`images` - Image format selection and optimization
* :doc:`fonts` - Font subsetting with WOFF2
* :doc:`configuration` - Title elements and other options

For Print Quality
~~~~~~~~~~~~~~~~~

Optimize for print or archival:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)

   document.save(
       "output.svg",
       image_prefix="images/img",  # External images
       image_format="png"           # Lossless format
   )

   # Rasterize at high DPI for print
   image = document.rasterize(dpi=300)
   image.save("output_print.png")

**Topics covered:**

* :doc:`images` - PNG format for lossless quality
* :doc:`rasterizers` - High DPI rasterization

For Maximum Compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~

Optimize for maximum compatibility across viewers:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   psdimage = PSDImage.open("input.psd")

   # Rasterize text, use simple paths
   document = SVGDocument.from_psd(
       psdimage,
       enable_text=False,        # Rasterize text
       enable_live_shapes=False  # Use paths instead of primitives
   )

   document.save(
       "output.svg",
       image_format="png"  # Universal format
   )

**Topics covered:**

* :doc:`configuration` - Text conversion and live shapes

Error Handling
--------------

Always wrap conversion operations in try-except blocks:

.. code-block:: python

   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   try:
       psdimage = PSDImage.open("input.psd")
       document = SVGDocument.from_psd(psdimage)
       document.save("output.svg")
   except FileNotFoundError:
       print("PSD file not found")
   except Exception as e:
       print(f"Conversion failed: {e}")

**For more error handling information, see** :doc:`configuration`.

Next Steps
----------

* Learn about :doc:`command-line` options for batch processing
* Optimize file sizes with :doc:`fonts` subsetting
* Handle images efficiently with :doc:`images`
* Choose the right :doc:`rasterizers` for your needs
* Fine-tune output with :doc:`configuration` options
