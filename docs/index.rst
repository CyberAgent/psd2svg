PSD2SVG Documentation
=====================

PSD2SVG is a PSD to SVG converter based on `psd-tools <https://github.com/psd-tools/psd-tools>`_.

This tool converts Adobe Photoshop (PSD) files to Scalable Vector Graphics (SVG) format, preserving layers, effects, and vector shapes where possible.

.. image:: https://img.shields.io/pypi/v/psd2svg.svg
   :target: https://pypi.python.org/pypi/psd2svg
   :alt: PyPI Version

Features
--------

* Convert PSD files to clean, editable SVG
* Preserve layers and artboards with smart group optimization
* Convert text layers to native SVG text elements (experimental)

  * Arc warp support with SVG textPath
  * Smart font matching with Unicode codepoint-based selection

* Support for most Photoshop blending modes (with approximations for unsupported modes)
* Adjustment layers support (experimental)
* Optional font subsetting and embedding for web optimization (typically 90-95% size reduction)
* Built-in resource limits for security (file size, timeout, layer depth, dimensions)
* Command-line tool and Python API

Quick Start
-----------

Installation
~~~~~~~~~~~~

Install via pip:

.. code-block:: bash

   pip install psd2svg

**Requirements:** Python 3.11 or higher. Dependencies (``psd-tools``, ``pillow``, ``numpy``, ``resvg-py``) are installed automatically.

**Optional features:**

.. code-block:: bash

   # Browser-based rasterization (better SVG 2.0 support)
   pip install psd2svg[browser]
   playwright install chromium

Basic Usage
~~~~~~~~~~~

**Command line:**

.. code-block:: bash

   psd2svg input.psd output.svg

**Python API:**

.. code-block:: python

   from psd2svg import convert

   convert('input.psd', 'output.svg')

**With SVGDocument class:**

.. code-block:: python

   from psd_tools import PSDImage
   from psd2svg import SVGDocument

   psdimage = PSDImage.open("input.psd")
   document = SVGDocument.from_psd(psdimage)
   document.save("output.svg", embed_images=True)

Next Steps
~~~~~~~~~~

* Read the :doc:`user-guide` for an overview and API reference
* Learn :doc:`command-line` usage for batch processing
* Optimize with :doc:`images` and :doc:`fonts` guides
* Explore :doc:`rasterizers` for SVG to raster conversion
* Fine-tune with :doc:`configuration` options
* Check the :doc:`api-reference` for complete API documentation
* Review :doc:`limitations` to understand current constraints
* Read :doc:`security` for security best practices when processing untrusted files

Documentation Contents
----------------------

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   user-guide
   command-line
   images
   fonts
   rasterizers
   configuration
   security
   limitations

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api-reference

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide

   development
   technical-notes
   changelog

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
