Command Line Usage
==================

This guide covers the psd2svg command-line interface for converting PSD files to SVG.

Basic Usage
-----------

Simple Conversion
~~~~~~~~~~~~~~~~~

The simplest way to convert a PSD file to SVG:

.. code-block:: bash

   psd2svg input.psd output.svg

Automatic Output Naming
~~~~~~~~~~~~~~~~~~~~~~~~

When the output path is a directory or omitted, the tool infers the output name from the input:

.. code-block:: bash

   # Output to directory
   psd2svg input.psd output/
   # => output/input.svg

   # Output to current directory
   psd2svg input.psd
   # => input.svg

Command Line Options
--------------------

Image Handling
~~~~~~~~~~~~~~

**--image-prefix PATH**

Save extracted images to external files with the specified prefix, relative to the output SVG file's directory. By default, images are embedded as data URIs.

.. code-block:: bash

   # Export images to same directory as SVG (using "." prefix)
   psd2svg input.psd output.svg --image-prefix .
   # => output.svg, 01.webp, 02.webp, ...

   # Export images to subdirectory
   psd2svg input.psd output.svg --image-prefix images/img
   # => output.svg, images/img01.webp, images/img02.webp, ...

**--image-format FORMAT**

Specify the image format for rasterized layers. Supported formats:

* ``webp`` - Modern format with excellent compression (default)
* ``png`` - Lossless format with transparency support
* ``jpeg`` - Lossy format, best for photographs

.. code-block:: bash

   # Export images as PNG
   psd2svg input.psd output.svg --image-prefix . --image-format png
   # => output.svg, 01.png, 02.png, ...

   # Export images as JPEG
   psd2svg input.psd output.svg --image-prefix . --image-format jpeg
   # => output.svg, 01.jpeg, 02.jpeg, ...

Feature Flags
~~~~~~~~~~~~~

**--no-text**

Disable text layer conversion and rasterize text as images instead. This is useful when:

* Font rendering differences are unacceptable
* Fonts are not available on the system
* Maximum visual accuracy is required

.. code-block:: bash

   psd2svg input.psd output.svg --no-text

**--no-live-shapes**

Disable live shape conversion and use paths instead of shape primitives (``<rect>``, ``<circle>``). This produces more compact SVG but loses semantic information.

.. code-block:: bash

   psd2svg input.psd output.svg --no-live-shapes

**--no-title**

Disable insertion of ``<title>`` elements with layer names. This reduces file size but removes layer identification:

.. code-block:: bash

   psd2svg input.psd output.svg --no-title

   # Compact output: disable titles and use paths
   psd2svg input.psd output.svg --no-title --no-live-shapes

**--crop-layers-to-canvas**

Crop each layer's rasterized image to the canvas before embedding it. This
reduces memory use and output size for a layer (e.g. a Smart Object) whose
bounding box extends far beyond the canvas. See :doc:`configuration` for
when to keep this disabled.

.. code-block:: bash

   psd2svg input.psd output.svg --crop-layers-to-canvas

Text Adjustment
~~~~~~~~~~~~~~~

**--text-letter-spacing-offset OFFSET**

Apply a global offset (in pixels) to all letter-spacing values. This compensates for rendering differences between Photoshop and SVG renderers:

.. code-block:: bash

   # Increase letter spacing by 0.5 pixels
   psd2svg input.psd output.svg --text-letter-spacing-offset 0.5

   # Decrease letter spacing by 0.015 pixels
   psd2svg input.psd output.svg --text-letter-spacing-offset -0.015

Experiment with different values to achieve the best match for your fonts and target renderers.

**--text-wrapping-mode MODE**

Control text wrapping mode for bounding box text layers. Supported modes:

* ``none`` - Uses native SVG ``<text>`` elements (default)
* ``foreignobject`` - Uses ``<foreignObject>`` with XHTML ``<div>`` for text wrapping

.. code-block:: bash

   # Use default native SVG text
   psd2svg input.psd output.svg --text-wrapping-mode none

   # Use foreignObject for text wrapping
   psd2svg input.psd output.svg --text-wrapping-mode foreignobject

.. note::
   Only affects bounding box text. Point text always uses native SVG ``<text>`` elements.

.. warning::
   The ``foreignobject`` mode produces SVG that is not supported by ResvgRasterizer.
   Use browser-based rasterizers for output validation.

See :ref:`configuration-text-wrapping-mode` for detailed SVG output examples and configuration file options.

Generating Font Mappings
~~~~~~~~~~~~~~~~~~~~~~~~~

Extract font information from PSD files to create custom font mappings:

.. code-block:: bash

   python -m psd2svg.tools.generate_font_mapping [OPTIONS] PSD_FILES...

**Purpose:**

Analyzes PSD files to extract PostScript font names used in text layers and generates custom font mapping files. Useful for:

* Identifying fonts needed for conversion
* Creating custom mappings for fonts not in default mapping
* Documenting font usage across PSD files

**Options:**

``PSD_FILES``
  One or more PSD file paths to analyze

``-o, --output PATH``
  Output file path (default: stdout)

``--only-missing``
  Only output fonts NOT in default mapping (useful for identifying missing fonts)

``--query-fontconfig``
  Query fontconfig to auto-fill font details (Linux/macOS only)

``--format {json,python}``
  Output format (default: json)

  * ``json``: JSON file for use with Python API
  * ``python``: Python dict literal for embedding in code

``-v, --verbose``
  Show progress messages and font details during processing

**Examples:**

.. code-block:: bash

   # Analyze single PSD file (output to stdout)
   python -m psd2svg.tools.generate_font_mapping input.psd

   # Save to JSON file
   python -m psd2svg.tools.generate_font_mapping input.psd -o fonts.json

   # Analyze multiple files
   python -m psd2svg.tools.generate_font_mapping file1.psd file2.psd -o all_fonts.json

   # Show only fonts not in default mapping
   python -m psd2svg.tools.generate_font_mapping input.psd --only-missing

   # Query system fonts (Linux/macOS)
   python -m psd2svg.tools.generate_font_mapping input.psd --query-fontconfig -o fonts.json

   # Generate Python format
   python -m psd2svg.tools.generate_font_mapping input.psd -o fonts.py --format python

   # Verbose output shows progress
   python -m psd2svg.tools.generate_font_mapping input.psd -v

**Output:**

The tool generates a font mapping in the specified format:

.. code-block:: json

   {
       "ArialMT": {
           "family": "Arial",
           "style": "Regular",
           "weight": 80.0,
           "_comment": "Found in default mapping"
       },
       "CustomFont-Bold": {
           "family": "",
           "style": "",
           "weight": 0.0,
           "_comment": "Not in default mapping - please fill in values"
       }
   }

Fonts in the default mapping show their values. Fonts not in the mapping need to be filled in manually or queried with ``--query-fontconfig``.

**Usage in Conversion:**

.. code-block:: python

   import json
   from psd2svg import SVGDocument
   from psd_tools import PSDImage

   with open("fonts.json") as f:
       custom_fonts = json.load(f)

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage, font_mapping=custom_fonts)

Common Workflows
----------------

Web Optimization
~~~~~~~~~~~~~~~~

For web delivery, use external WebP images with no titles:

.. code-block:: bash

   psd2svg input.psd output.svg \
     --image-prefix images/img \
     --image-format webp \
     --no-title

Print Quality
~~~~~~~~~~~~~

For high-quality output with PNG images:

.. code-block:: bash

   psd2svg input.psd output.svg \
     --image-prefix . \
     --image-format png

Maximum Compatibility
~~~~~~~~~~~~~~~~~~~~~

For maximum compatibility across renderers, rasterize text and use simple paths:

.. code-block:: bash

   psd2svg input.psd output.svg \
     --no-text \
     --no-live-shapes \
     --image-format png

Batch Processing
~~~~~~~~~~~~~~~~

Process multiple PSD files:

.. code-block:: bash

   # Using shell loop
   for file in *.psd; do
     psd2svg "$file" "svg/${file%.psd}.svg"
   done

   # Using find and xargs
   find . -name "*.psd" -print0 | \
     xargs -0 -I {} psd2svg {} {}.svg

Exit Codes
----------

The command returns the following exit codes:

* ``0`` - Success
* ``1`` - General error (file not found, invalid PSD, etc.)
* ``2`` - Command-line argument error

You can use these in scripts:

.. code-block:: bash

   if psd2svg input.psd output.svg; then
     echo "Conversion successful"
   else
     echo "Conversion failed with exit code $?"
     exit 1
   fi

Environment Variables
---------------------

The command respects standard environment variables:

* ``NO_COLOR`` - Disable colored output
* ``FORCE_COLOR`` - Force colored output even in non-TTY environments

.. code-block:: bash

   # Disable colors
   NO_COLOR=1 psd2svg input.psd output.svg

Getting Help
------------

Display help information:

.. code-block:: bash

   psd2svg --help

   # Display version
   psd2svg --version

For more detailed documentation, visit the `online documentation <https://psd2svg.readthedocs.io/>`_.
