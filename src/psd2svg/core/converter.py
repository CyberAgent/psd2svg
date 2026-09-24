import contextlib
import logging
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any, Iterator

from PIL import Image
from psd_tools import PSDImage

from psd2svg import svg_utils
from psd2svg.core.adjustment import AdjustmentConverter
from psd2svg.core.counter import AutoCounter
from psd2svg.core.effects import EffectConverter
from psd2svg.core.layer import LayerConverter
from psd2svg.core.paint import PaintConverter
from psd2svg.core.shape import ShapeConverter
from psd2svg.core.text import TextConverter

if TYPE_CHECKING:
    from psd2svg.resource_limits import ResourceLimits

logger = logging.getLogger(__name__)


class Converter(
    AdjustmentConverter,
    LayerConverter,
    PaintConverter,
    ShapeConverter,
    TextConverter,
    EffectConverter,
):
    """Converter main class.

    Example usage:

        from psd2svg.core.converter import Converter

        Converter.convert("example.psd", "output.svg")

    Example usage:

        from psd_tools import PSDImage
        from psd2svg.core.conveter import Converter

        psd = PSDImage.open("example.psd")
        converter = Converter(psd)
        document = converter.build()
        document.embed_images()  # or document.export_images("output/image_%02d")
        svg_string = document.export()

    Args:
        psdimage: Source PSDImage to convert.
        enable_live_shapes: Enable live shape conversion when possible.
        enable_text: Enable text layer conversion when possible.
        enable_title: Enable insertion of <title> elements with layer names. When True
            (default), each layer in the SVG will have a <title> element containing the
            Photoshop layer name for accessibility and debugging. Set to False to omit
            title elements and reduce file size.
        enable_class: Enable insertion of class attributes on SVG elements for debugging
            purposes. When False (default), elements will not have class attributes,
            producing cleaner SVG output. Set to True to add class attributes for layer
            types, effects, and semantic roles (e.g., "shape-layer",
            "drop-shadow-effect", "fill") for debugging or styling.
        text_letter_spacing_offset: Global offset (in pixels) to add to all
            letter-spacing values. This can be used to compensate for differences
            between Photoshop's text rendering and SVG's text rendering. Typical values
            range from -0.02 to 0.02. Default is 0.0 (no offset).
        text_wrapping_mode: Text wrapping mode for bounding box text.
            Use 0 for no wrapping (default, native SVG <text>), or 1 for <foreignObject>
            with XHTML wrapping. Import TextWrappingMode from psd2svg.core.text for enum
            values. Only affects bounding box text (ShapeType=1); point text always uses
            native SVG <text> elements.
        font_mapping: Optional custom font mapping dictionary. Takes priority over
            built-in static mapping.
            Format: {"PostScriptName": {"family": str, "style": str, "weight": float}}.
            When not provided, uses built-in mapping for ~4,950 fonts
            (539 default + 370 Hiragino + 4,042 Morisawa) with automatic fallback to
            system font resolution (fontconfig/Windows registry) if needed.
    """

    _id_counter: AutoCounter | None = None

    def __init__(
        self,
        psdimage: PSDImage,
        enable_live_shapes: bool = True,
        enable_text: bool = True,
        enable_title: bool = False,
        enable_class: bool = False,
        text_letter_spacing_offset: float = 0.0,
        text_wrapping_mode: int = 0,
        font_mapping: dict[str, dict[str, float | str]] | None = None,
        resource_limits: "ResourceLimits | None" = None,
    ) -> None:
        """Initialize the converter internal state."""
        # Source PSD image.
        if not isinstance(psdimage, PSDImage):
            raise TypeError("psdimage must be an instance of PSDImage")
        self.psd = psdimage
        self.enable_live_shapes = enable_live_shapes
        self.enable_text = enable_text
        self.enable_title = enable_title
        self.enable_class = enable_class
        self.text_letter_spacing_offset = text_letter_spacing_offset
        self.text_wrapping_mode = text_wrapping_mode
        self.font_mapping = font_mapping
        self.resource_limits = resource_limits

        # Initialize the SVG root element.
        self.svg = svg_utils.create_node(
            "svg",
            xmlns=svg_utils.NAMESPACE,
            width=psdimage.width,
            height=psdimage.height,
            viewBox=svg_utils.seq2str([0, 0, psdimage.width, psdimage.height], sep=" "),
        )
        self.images: dict[str, Image.Image] = {}  # Store PIL images keyed by image ID.
        # Note: Font tracking removed - PostScript names are stored directly
        # in SVG font-family attributes

        # Initialize the current node pointer.
        self.current = self.svg

    def build(self) -> None:
        """Build the SVG structure and internally save the result."""
        assert self.psd is not None, "PSD image is not set."

        if len(self.psd) == 0 and self.psd.has_preview():
            # Special case: No layers, just a flat image.
            # Check before compositing so an oversized canvas is never allocated.
            description = "Flattened composite"
            self.check_image_dimension(
                self.psd.width, self.psd.height, description=description
            )
            image_id = self.register_image(
                self.psd.composite(), description=description
            )
            self.create_node(
                "image",
                id=image_id,
                width=self.psd.width,
                height=self.psd.height,
            )
        else:
            self.add_children(self.psd)

    def auto_id(self, prefix: str = "") -> str:
        """Generate a unique ID for SVG elements."""
        if self._id_counter is None:
            self._id_counter = AutoCounter()
        return self._id_counter.get_id(prefix)

    def check_image_dimension(
        self, width: int, height: int, *, description: str
    ) -> None:
        """Check a bitmap size against the configured image dimension limit.

        Call this before decoding whenever the size is known from metadata, so an
        oversized bitmap is rejected instead of allocated.

        Args:
            width: Bitmap width in pixels.
            height: Bitmap height in pixels.
            description: What the bitmap is, used to open the error message.

        Raises:
            ValueError: If either dimension exceeds the limit.
        """
        if self.resource_limits is not None:
            self.resource_limits.check_image_dimension(width, height, description)

    def register_image(self, image: Image.Image, *, description: str) -> str:
        """Validate an image and store it, returning its generated element ID.

        Every bitmap that ends up in the SVG goes through here, so the dimension
        limit applies to all of them. This does not create the ``<image>`` node;
        the caller does that with the returned ID.

        Args:
            image: The bitmap to store.
            description: What the bitmap is, used to open the error message.

        Returns:
            The generated element ID to use for the ``<image>`` node.

        Raises:
            ValueError: If either dimension exceeds the limit.
        """
        self.check_image_dimension(image.width, image.height, description=description)
        image_id = self.auto_id("image")
        self.images[image_id] = image
        return image_id

    def create_node(
        self,
        tag: str,
        parent: ET.Element | None = None,
        class_: str = "",
        title: str = "",
        text: str = "",
        desc: str = "",
        **kwargs: Any,
    ) -> ET.Element:
        """Create an SVG node with the current element as default parent.

        This is a convenience wrapper around svg_utils.create_node that automatically
        uses self.current as the parent if no parent is specified.

        Args:
            tag: The XML tag name.
            parent: Optional parent element. Defaults to self.current.
            class_: Optional class attribute.
            title: Optional title element.
            text: Optional text content.
            desc: Optional description element.
            **kwargs: Additional attributes to pass to svg_utils.create_node.

        Returns:
            The created XML element.
        """
        if parent is None:
            parent = self.current

        # Conditionally suppress class based on enable_class flag
        if not self.enable_class:
            class_ = ""

        # Conditionally suppress title based on enable_title flag
        if not self.enable_title:
            title = ""

        return svg_utils.create_node(
            tag,
            parent=parent,
            class_=class_,
            title=title,
            text=text,
            desc=desc,
            **kwargs,
        )

    @contextlib.contextmanager
    def set_current(self, node: ET.Element) -> Iterator[None]:
        """Set the current node for the converter."""
        previous = self.current
        self.current = node
        try:
            yield
        finally:
            self.current = previous
