Technical Notes
===============

This section contains technical implementation notes about PSD to SVG conversion strategies.

Clipping Conversion
-------------------

Clipping involves non-trivial conversion. The basic approach is to use ``<clipPath>`` or ``<mask>`` SVG elements, but Photoshop can have arbitrarily complex rendering procedures due to the presence of vector drawings or filter effects.

Basic Idea
~~~~~~~~~~

Consider the following case::

    [1] ShapeLayer('Star 1' size=30x29)
    [2] +TypeLayer('B' size=22x23 clip)

This can be translated to the following SVG structure:

.. code-block:: xml

    <path id="path0" d="M15,14.5 ..." />
    <clipPath id="clip0">
      <use href="#path0" />
    </clipPath>
    <text clip-path="url(#clip0)">B</text>

If the clipping base is not a shape layer, we can instead use a mask::

    [1] PixelLayer('Star 1' size=30x29)
    [2] +TypeLayer('B' size=22x23 clip)

.. code-block:: xml

    <image id="image0" href="pixel.png">
    <mask id="mask0" mask-type="alpha">
      <use href="image0" />
    </mask>
    <text mask="url(#mask0)">B</text>

This structure is the most basic form of translation.

Styling SVG Use Element
~~~~~~~~~~~~~~~~~~~~~~~~

In SVG, the ``<use>`` element does not allow overriding the ``fill`` or ``stroke`` attributes of the referenced element. Therefore, in the following example, ``fill="transparent"`` is ignored.

.. code-block:: xml

    <path id="path0" d="M15,14.5 ..." fill="red" />
    <clipPath id="clip0">
      <use href="#path0" />
    </clipPath>
    <use href="#path0" fill="transparent" stroke="black" />

To correctly apply drawing attributes, we instead need to do the following: prepare a plain ``<path>`` element (like a ``<symbol>``), then reference this element in the ``<use>`` element with the desired attributes.

.. code-block:: xml

    <clipPath id="clip0">
      <path id="path0" d="M15,14.5 ..."/>
    </clipPath>
    <use href="#path0" fill="red" />
    <use href="#path0" fill="transparent" stroke="black" />

Stroke After Clipping Layers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In Photoshop, stroke (both as a shape attribute and as a filter effect) is applied after all clipping layers are rendered. Consider the following example, where the first shape layer has both fill and stroke attributes enabled::

    [1] ShapeLayer('Star 1' size=30x29)
    [2] +TypeLayer('B' size=22x23 clip)
    [3] +TypeLayer('C' size=22x23 clip)

This translates to the following:

.. code-block:: xml

    <clipPath id="clip0">
      <path id="path0" d="M15,14.5 ..."/>
    </clipPath>
    <use href="#path0" fill="red" />
    <text clip-path="url(#clip0)">B</text>
    <text clip-path="url(#clip0)">C</text>
    <use href="#path0" fill="transparent" stroke="black" />

Or, we can group clipping layers:

.. code-block:: xml

    <clipPath id="clip0">
      <path id="path0" d="M15,14.5 ..."/>
    </clipPath>
    <use href="#path0" fill="red" />
    <g clip-path="url(#clip0)">
      <text>B</text>
      <text>C</text>
    </g>
    <use href="#path0" fill="transparent" stroke="black" />

There are filter effects that happen before (e.g., filling) or after (e.g., stroking) the rendering of the clipped layers.

Stroke Effect on Raster Layers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Photoshop can apply stroke effects to any layer, whereas SVG allows stroke only on shape or text elements. We have to emulate the stroke effect using filter effects. The following example emulates a stroke effect on a pixel layer:

.. code-block:: xml

    <mask id="mask0" mask-type="alpha">
      <image id="image0" href="pixel.png">
    </mask>
    <use href="image0" />
    <text mask="url(#mask0)">B</text>
    <use href="image0" filter="url(#stroke0)">
    <filter id="stroke0">
      <feMorphology operator="dilate" radius="1" in="SourceAlpha" result="thicken" />
      <feComposite operator="out" in="thicken" in2="SourceGraphic" />
    </filter>

The SVG filter configuration depends on the stroke properties (alignment and stroke width).

Regular Masks and Clipping Masks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a clipped layer has a mask, we have to group the clipping layers and apply the mask to the group.

.. code-block:: xml

    <mask id="mask0" mask-type="alpha">
      <image id="image0" href="pixel.png">
    </mask>
    <use href="image0" />
    <g mask="url(#mask0)">
      <mask id="mask1" mask-type="alpha">
        <image />
      </mask>
      <text mask="url(#mask1)">B</text>
    </g>
    <use href="image0" filter="url(#stroke0)">
    <filter id="stroke0">
      <feMorphology operator="dilate" radius="1" in="SourceAlpha" result="thicken" />
      <feComposite operator="out" in="thicken" in2="SourceGraphic" />
    </filter>

Clipping Structure Summary
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Depending on the target layer kind, we have the following structure for clipping layers.

**Drawing target:**

.. code-block:: xml

    <!-- clip path -->
    <clipPath id="clipPath0">
      <path id="path0" />
    </clipPath>
    <!-- bottom effects like fill -->
    <use href="#path0" fill="red" />
    <!-- clipped layers -->
    <g clip-path="url(#clipPath0)"></g>
    <!-- top effects like stroke -->
    <use href="#path0" fill="transparent" stroke="black" />

**Raster target:**

.. code-block:: xml

    <!-- clip mask -->
    <mask id="mask0">
      <image id="image0" />
    </mask>
    <!-- bottom effects like fill -->
    <use href="#image0" />
    <!-- clipped layers -->
    <g mask="url(#mask0)"></g>
    <!-- top effects like stroke -->
    <use href="#image0" filter="url(#filter0)" />
    <filter id="filter0"></filter>

Conversion Logic
~~~~~~~~~~~~~~~~

The requirement to implement the above conversion is the following two logic:

1. Beginning of the clip section (mask or clipPath creation, fill, group)
2. End of the clip section (stroke)

Both halves belong to the same clipping base, so they are expressed as a
context manager that yields the attribute the clipped layers carry:

.. code-block:: python

    def add_children(self, group, depth=0):
        for layer in group:
            # Clip layers are converted through their base, not on their own.
            if layer.clipping or not layer.is_visible():
                continue

            if layer.has_clip_layers(visible=True):
                with self.add_clipping_target(layer, depth=depth) as attrib:
                    for clip_layer in layer.clip_layers:
                        self.add_layer(clip_layer, depth=depth + 1, **attrib)
            else:
                self.add_layer(layer, depth=depth)

``add_clipping_target()`` opens the clip section before it yields and closes it
afterwards, and the clip layers it yields to are counted one level deeper than
the base. A shape target without a mask goes to ``add_clip_path()``, which
builds the base with ``create_shape()`` and so has no nesting of its own to
account for. Everything else goes to ``add_clip_mask()``, which converts the
base at ``depth``, the same depth a plain sibling gets.

Overlay Filter Effects
-----------------------

Overlay effects can be thought of as adding another element on top of the original.

.. code-block:: xml

    <image id="image_0" />
    <use href="#image_0" filter="url(#filter_0)" class="color_overlay" />
    <use href="#image_0" filter="url(#filter_1)" class="color_overlay" />
    <filter id="filter_0">
      <feFlood flood-color="green" flood-alpha="0.5" result="flood" />
      <feComposite in="SourceAlpha" in2="flood" operator="in" />
    </filter>
    <filter id="filter_1">
      <feFlood flood-color="red" flood-alpha="0.5" result="flood" />
      <feComposite in="SourceAlpha" in2="flood" operator="in" />
    </filter>

For simple overlays, this is equivalent to using a mask with fill.

.. code-block:: xml

    <mask id="mask_0" mask-type="alpha">
      <image id="image_0">
    </mask>
    <use href="#image_0">
    <rect color="green" alpha="0.5" mask="url(#mask_0)">
    <rect color="red" alpha="0.5" mask="url(#mask_0)">

Blend Modes Without a CSS Equivalent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Divide, Subtract, Linear Burn and Linear Dodge have no usable ``mix-blend-mode``.
Photoshop's separable blend functions, however, relate each of them to an operation
SVG does support, applied to a rewritten blend layer::

    Divide(b, s)      = min(1, b / s)      = ColorDodge(b, 1 - s)
    Subtract(b, s)    = max(0, b - s)      = LinearBurn(b, 1 - s)
    LinearBurn(b, s)  = max(0, b + s - 1)
    LinearDodge(b, s) = min(1, b + s)

An overlay effect already synthesizes its blend layer inside the filter, so it can be
rewritten there. Divide inverts the fill and blends with ``color-dodge``:

.. code-block:: xml

    <filter id="gradientoverlay" color-interpolation-filters="sRGB">
      <feImage href="#gradientfill" />
      <feComponentTransfer>
        <feFuncR type="table" tableValues="1 0" />
        <feFuncG type="table" tableValues="1 0" />
        <feFuncB type="table" tableValues="1 0" />
      </feComponentTransfer>
      <feComposite in2="SourceAlpha" operator="in" />
    </filter>
    <use href="#image" filter="url(#gradientoverlay)" style="mix-blend-mode: color-dodge" />

The three sums instead evaluate ``b + s + k4`` with ``feComposite`` and drop
``mix-blend-mode`` altogether. Linear Burn and Linear Dodge use ``k4="-1"`` and
``k4="0"``; Subtract is Linear Burn with the fill inverted first:

.. code-block:: xml

    <filter id="gradientoverlay" color-interpolation-filters="sRGB">
      <feImage href="#gradientfill" result="fill" />
      <feComponentTransfer in="SourceGraphic" result="opaque">
        <feFuncA type="table" tableValues="1 1" />
      </feComponentTransfer>
      <feComposite in="fill" in2="opaque" operator="arithmetic" k1="0" k2="1" k3="1" k4="-1" />
      <feComposite in2="SourceAlpha" operator="in" />
    </filter>

The detour through ``opaque`` is what makes this correct for semi-transparent
layers. ``feComposite operator="arithmetic"`` works on premultiplied values, so a
layer of alpha ``a`` enters the sum as ``a·b`` and yields ``a·b + s + k4`` where the
right answer is ``a·(b + s + k4)`` — the constant cannot be scaled by ``a``. Forcing
the layer opaque with ``feFuncA`` (``feComponentTransfer`` operates on
*un*-premultiplied values) runs the sum at ``a = 1``, and the trailing
``feComposite in2="SourceAlpha" operator="in"`` puts the alpha back. Without it, a
layer at 50% opacity under a Linear Burn overlay renders 102 where Photoshop's
effect gives 115.

``color-interpolation-filters="sRGB"`` is required. The SVG default is ``linearRGB``,
and inverting or summing in linear space gives the wrong numbers.

This route only applies where the blend layer exists inside a filter. A layer-level
Divide or Subtract, and a shape layer's overlay effect (which paints a plain ``fill``
instead of a filter), still use the approximations in
:doc:`limitations`.

Stroke Overlays
~~~~~~~~~~~~~~~

Things get complicated when there is a stroke, because the overlay must be applied before the stroke.

.. code-block:: xml

    <rect id="rect_0" />
    <use href="#rect_0" fill="gray" />  <!-- fill -->
    <use href="#rect_0" filter="url(#filter_0)" class="color_overlay" />
    <filter id="filter_1">
      <feFlood flood-color="red" flood-alpha="0.5" result="flood" />
      <feComposite in="SourceAlpha" in2="flood" operator="in" />
    </filter>
    <use href="#rect_0" fill="transparent" stroke="black" />  <!-- stroke -->

The above is equivalent to applying fill operations on geometric elements (shapes and text).

.. code-block:: xml

    <defs>
      <rect id="rect_0" />
    </defs>
    <use href="#rect_0" fill="gray" />  <!-- fill -->
    <use href="#rect_0" fill="red" opacity="0.5" class="color_overlay" />
    <use href="#rect_0" fill="transparent" stroke="black" />  <!-- stroke -->

Interpreting overlay effects as clipped fill layers would likely be easier to implement.

.. code-block:: xml

    <clipPath id="clip_0">
      <rect id="rect_0" />
    </clipPath>
    <use href="#rect_0" fill="gray" />
    <g clip-path="url(#clip_0)">
        <use href="#rect_0" fill="red" opacity="0.5" class="color_overlay" />
    </g>
    <use href="#rect_0" fill="transparent" stroke="black" />

Generic Rendering Procedure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In any case, the generic rendering procedure for a single layer could be the following:

1. Shape definition; e.g., ``<clipPath>``, ``<mask>``, ``<defs>``
2. Fill
3. Clipping or filter effects for color
4. Stroke

Effects on Strokes
~~~~~~~~~~~~~~~~~~

When a shape layer does not have fill, effects do not render correctly if we naively split the shape definition, because stroke becomes the only shape. The following result will be incorrect for the filter, because the ``<rect>`` by default will have black fill.

.. code-block:: xml

    <defs>
      <rect id="shape" />
      <filter id="filter" />
    </defs>
    <use href="#shape" filter="url(#filter)">
    <use href="#shape" fill="transparent" />
    <use href="#shape" fill="transparent" stroke="red" >

This should be avoided by explicitly stating the fill is transparent in the definition.

.. code-block:: xml

    <defs>
      <rect id="shape" fill="transparent" stroke-width="1" />
      <filter id="filter" />
    </defs>
    <use href="#shape" filter="url(#filter)">
    <use href="#shape" fill="transparent" stroke="red" >

Shape Operations
----------------

Photoshop supports boolean operations for path objects. SVG does not natively support path operations, but it is possible to reproduce path operations using ``<mask>``.

The basics are:

- **AND** operation is a chain of ``<mask>``
- **OR** operation simply places multiple shape elements inside the same mask container
- **NOT** operation is a black fill

Unfortunately, strokes do not render correctly. Using ``<clipPath>`` might render strokes, but ``<clipPath>`` does not support NOT operator unless ``<path>`` element is used with ``evenodd`` rule.

Union (OR)
~~~~~~~~~~

A naive approach is to render multiple shapes in order.

.. code-block:: xml

    <g>
      <circle id="circle_A">
      <circle id="circle_B">
    </g>

If we separate the shape operations from painting, we can use ``<mask>``.

.. code-block:: xml

    <mask id="A_or_B">
      <circle id="circle_A" fill="#ffffff">
      <circle id="circle_B" fill="#ffffff">
    </mask>
    <rect mask="url(#A_or_B)">

Clip-path equivalent is the following:

.. code-block:: xml

    <clipPath id="A_or_B">
      <circle id="circle_A">
      <circle id="circle_B">
    </clipPath>
    <rect clip-path="url(#A_or_B)">

The general conversion process would be:

1. Create a ``<mask>`` container
2. Append shapes to the current ``<mask>`` container
3. Apply the mask to the final target (``<rect>``)

Subtraction (NOT OR)
~~~~~~~~~~~~~~~~~~~~

Subtraction operation is equivalent to specifying ``fill`` to black (``#000000``).

.. code-block:: xml

    <mask id="A_sub_B">
      <circle id="circle_A" fill="#ffffff" />
      <circle id="circle_B" fill="#000000" />
    </mask>
    <rect mask="url(#A_sub_B)">

It is not possible to directly use ``<clipPath>`` for subtraction.

Intersection (AND)
~~~~~~~~~~~~~~~~~~

Intersection is a chain of masks.

.. code-block:: xml

    <mask id="A">
      <circle id="circle_A" fill="#ffffff">
    </mask>
    <mask id="A_and_B">
      <circle id="circle_B" fill="#ffffff" mask="url(#A)">
    </mask>
    <rect mask="url(#A_and_B)">

The general conversion process would be:

1. Create a ``<mask>`` container
2. For each shape, create a new ``<mask>`` container with the content referencing the previous ``mask`` container

XOR
~~~

XOR is a combination: ``(A OR B) AND NOT (A AND B)``.

Alternative formulation of XOR is available: ``(A AND NOT B) OR (NOT A AND B)``.

Faux Bold
=========

Photoshop's faux bold (疑似ボールド) thickens the outline of the *specified*
face. CSS ``font-weight: 700`` instead asks the renderer for a different,
genuinely bolder design, and gets it whenever the family has a real bold
installed - so emitting the flag as a weight both overshoots and discards the
weight the PSD actually specified.

``core/text.py`` therefore emits it as a stroke on the glyph in its own fill
colour, with ``paint-order="stroke"`` so the thickening grows the silhouette
instead of eating into the fill, and leaves ``font-weight`` to the resolved
face. A centred stroke of width *w* grows every stem by exactly *w*;
``FAUX_BOLD_STROKE_RATIO`` is 3% of the em, the stem growth measured on the
``style-faux-bold*.psd`` fixtures — 2.9-3.2% depending on which scanlines are
sampled. The stroke uses ``stroke-linejoin="round"``: Photoshop offsets the
contour, which is round at a convex corner, where the default miter join would
spike instead.

Limitations:

- A span that also carries a PSD character stroke keeps the stroke and loses the
  thickening; ``stroke``/``stroke-width`` cannot express both, and psd2svg does
  not read Photoshop's character stroke width yet.
- A translucent fill is composited twice where the stroke underlies it, so the
  stem interior reads darker than its fringe. Photoshop keeps one uniform alpha.
- Faux *italic* is still emitted as ``font-style: italic``, which selects a real
  italic face where one exists rather than shearing the specified face.

Font Resolution Architecture
=============================

This section explains psd2svg's font resolution system and its deferred resolution strategy.

Background
----------

PSD files store font references as **PostScript names** (e.g., ``ArialMT``, ``HelveticaNeue-Bold``).
For SVG output, we need to convert these to **CSS font families** (e.g., ``Arial``, ``Helvetica Neue``).

When ``embed_fonts=False``: Only family names are needed for the SVG ``font-family`` attribute.

When ``embed_fonts=True``: Must locate actual system font files for embedding.

Deferred Resolution Strategy
-----------------------------

psd2svg uses a **two-phase approach** to optimize performance:

**Phase 1 - PSD Conversion** (``from_psd()``):

- PostScript names stored directly in SVG ``font-family`` attributes
- No font resolution performed (fast conversion)
- Original PSD intent preserved

**Phase 2 - Output** (``save()``, ``tostring()``, ``rasterize()``):

- Extract PostScript names from SVG tree
- Resolve to CSS family names based on context:

  - ``embed_fonts=False``: Use static mapping (fast, no system queries)
  - ``embed_fonts=True``: Use platform-specific resolution (locates font files)

- Update ``font-family`` attributes with resolved names
- Embed fonts if requested

Resolution Methods
------------------

psd2svg provides two distinct resolution methods optimized for different use cases.

FontInfo.lookup_static()
~~~~~~~~~~~~~~~~~~~~~~~~~

For font metadata lookup only:

- Resolution chain: Custom mapping → Static mapping (~4,950 fonts) → None
- Static mapping includes:

  - 539 default fonts (Arial, Times, Adobe fonts, etc.)
  - 370 Hiragino variants (W0-W9 pattern, generated dynamically)
  - 4,042 Morisawa fonts (Japanese typography)

- Returns family name, style, and weight (no file path)
- NO platform-specific queries (no fontconfig/Windows registry)
- Preserves original PostScript names in SVG when fonts not found
- Used when ``embed_fonts=False`` (prevents unwanted font substitution)
- Fast, cross-platform, no system dependencies
- JSON-based lazy loading (loaded on first access)

FontInfo.resolve()
~~~~~~~~~~~~~~~~~~

For font file access:

- Resolution chain: Custom mapping → Platform-specific resolution
- Returns complete font metadata including file path
- **Linux/macOS**: fontconfig with CharSet API (fontconfig-py >= 0.4.0)
- **Windows**: Windows registry + fontTools cmap parsing
- Used when ``embed_fonts=True`` or for rasterization
- May substitute fonts based on system availability

FontInfo.find()
~~~~~~~~~~~~~~~

Backward-compatible wrapper:

- Delegates to ``lookup_static()`` by default (safe behavior)
- Use ``disable_static_mapping=True`` to delegate to ``resolve()``
- Maintained for backward compatibility; prefer explicit methods in new code

Custom font mapping: Users can provide custom mappings via ``font_mapping`` parameter
(always checked first, regardless of method used).
See CLI tool: ``python -m psd2svg.tools.generate_font_mapping``

Weight Scale
------------

fontconfig stores weights on its own 0-215 scale; OpenType
(``OS/2.usWeightClass``) and CSS share the 1-1000 scale. ``core/font_weights.py``
converts between them with fontconfig's own piecewise-linear table, in both
directions:

.. code-block:: text

   OpenType/CSS  100  200  300  350  380  400  500  600  700  800  900  1000
   fontconfig      0   40   50   55   75   80  100  180  200  205  210   215

Bucketing into multiples of 100 instead would collapse neighbouring faces onto
one CSS weight. Hiragino W2 (fontconfig 45) and W3 (50) are the motivating case:
they are separately installed faces, and two faces sharing a CSS weight also
produce ``@font-face`` rules with identical ``(family, weight, style)``
descriptors, so the second shadows the first. Through the table they map back to
their own ``usWeightClass``, 250 and 300.

``_generate_css_rules_for_fonts()`` additionally detects any remaining
descriptor collision, emitting the first face and warning about the rest. It
cannot see two faces that share one font file, because ``resolved_fonts_map``
is keyed by file path and collapses them before the rules are generated.

Weights that are not points on the table interpolate, so a CSS weight need not
be a multiple of 100 - fontconfig 215 (extrablack, 200 of the bundled Morisawa
fonts) becomes ``font-weight: 1000``.

Charset-Based Font Matching
----------------------------

When resolving fonts, psd2svg analyzes actual text characters for better matching:

1. Extract Unicode characters from text layers
2. Convert to codepoints (e.g., 'あ' → 0x3042)
3. Query system for fonts with best glyph coverage
4. Fallback to name-only matching on errors

**Benefits**: Better selection for multilingual text (CJK, Arabic, etc.),
minimal overhead (~10-50ms)

Font Embedding Implementation
------------------------------

Font Subsetting
~~~~~~~~~~~~~~~

When ``embed_fonts=True``:

- Character extraction reused for both charset matching and subsetting
- Typically 90%+ size reduction with WOFF2 format

Embedding Modes
~~~~~~~~~~~~~~~

- ``tostring()``/``save()``: Data URIs (portable files)
- ``rasterize()`` with PlaywrightRasterizer: file:// URLs (60-80% faster)

Key API Methods
~~~~~~~~~~~~~~~

- ``TypeSetting.get_postscript_name()``: Extract PostScript name from PSD
- ``FontInfo.lookup_static()``: Lookup PostScript name to get font metadata (no platform queries)
- ``FontInfo.resolve()``: Resolve PostScript name to font file with platform resolution
- ``FontInfo.find()``: Backward-compatible wrapper (delegates to ``lookup_static()`` or ``resolve()``)
- SVG tree is single source of truth for fonts (no separate font list maintained)
