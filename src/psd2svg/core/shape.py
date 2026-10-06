"""
Mixin module for geometric methods related to shape layers.

Handles conversion of Photoshop vector shapes to SVG path elements:

- Basic shapes (ellipse, rectangle, rounded rectangle, line, polygon)
- Custom paths with Bezier curves
- Multi-path shapes with boolean operations
- Path operations (combine, subtract, intersect, exclude)

The module processes vector mask data from shape layers and converts
Photoshop's knot points and control points to SVG path syntax.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Any, Iterator, Literal

import numpy as np
from psd_tools.api import layers
from psd_tools.api.shape import Ellipse, Rectangle, RoundedRectangle
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Descriptor
from psd_tools.psd.vector import Subpath

from psd2svg import svg_utils
from psd2svg.core.base import ConverterProtocol

logger = logging.getLogger(__name__)


class ShapeConverter(ConverterProtocol):
    """Mixin for shape layers."""

    def create_shape(self, layer: layers.ShapeLayer, **attrib: str) -> ET.Element:
        """Create a shape element from the layer's vector mask or origination data."""
        if not layer.has_vector_mask() or layer.vector_mask is None:
            raise ValueError(f"Layer has no vector mask: '{layer.name}' ({layer.kind})")

        if len(layer.vector_mask.paths) == 1:
            # TODO: Handle NOT OR for single path. This is a negated shape.
            path = layer.vector_mask.paths[0]
            return self.create_single_shape(layer, path, **attrib)
        else:
            return self.create_composite_shape(layer, **attrib)

    def create_composite_shape(
        self, layer: layers.ShapeLayer, **attrib: str
    ) -> ET.Element:
        """Create a composite shape element from multiple paths with operations.

        If the layer has a mask, it will be applied to the composite mask node,
        creating a mask chain: layer_mask -> composite_mask -> paths.
        """
        if layer.vector_mask is None:
            raise ValueError(f"Layer has no vector mask: '{layer.name}' ({layer.kind})")

        # Group subpaths by operations.
        subpaths: list[list[Subpath]] = []
        for path in layer.vector_mask.paths:
            if path.operation == -1:  # Even-odd fill rule
                if len(subpaths) == 0:
                    logger.warning("Even-odd fill rule without preceding path")
                    subpaths.append([path])
                else:
                    subpaths[-1].append(path)
            else:
                subpaths.append([path])

        rule: Literal["fill-rule", "clip-rule"] = (
            "clip-rule" if self.current.tag == "clipPath" else "fill-rule"
        )

        # NOTE: Use clipPath when possible.
        # It's possible when all operations are Union (OR) or Intersect (AND).

        # Composite shape with multiple paths.
        with self.set_current(self.create_node("defs")):
            current = self.create_node(
                "mask",
                id=self.auto_id("mask"),
                mask=attrib.pop("mask", None),  # Combine with existing mask if any.
            )
            for path_group in subpaths:
                path = path_group[0]
                previous = current
                if path.operation == 0:  # XOR
                    current = self.apply_xor_operation(
                        layer, path_group, current, previous, rule
                    )
                elif path.operation == 1:  # Union (OR)
                    current = self.apply_union_operation(
                        layer, path_group, current, rule
                    )
                elif path.operation == 2:  # Subtract (NOT OR)
                    current = self.apply_subtract_operation(
                        layer, path_group, current, rule
                    )
                elif path.operation == 3:  # Intersect (AND)
                    current = self.apply_intersect_operation(
                        layer, path_group, current, previous, rule
                    )
                else:
                    raise ValueError(f"Unsupported path operation: {path.operation}")

        return self.create_node(
            "rect",
            x=layer.left,
            y=layer.top,
            width=layer.width,
            height=layer.height,
            mask=svg_utils.get_funciri(current),
            **attrib,  # type: ignore[arg-type]
        )

    def apply_union_operation(
        self,
        layer: layers.ShapeLayer,
        path_group: list[Subpath],
        current: ET.Element,
        rule: Literal["fill-rule", "clip-rule"],
    ) -> ET.Element:
        """Apply Union (OR) operation to combine shapes."""
        with self.set_current(current):
            # Union operation: add the shape directly.
            if len(path_group) > 1:
                self.create_composite_path(path_group, rule, fill="#ffffff")
            else:
                self.create_single_shape(layer, path_group[0], fill="#ffffff")
        return current

    def apply_subtract_operation(
        self,
        layer: layers.ShapeLayer,
        path_group: list[Subpath],
        current: ET.Element,
        rule: Literal["fill-rule", "clip-rule"],
    ) -> ET.Element:
        """Apply Subtract (NOT OR) operation to create holes."""
        with self.set_current(current):
            if len(current) == 0:
                # First shape: fill white.
                self.create_node("rect", fill="#ffffff", width="100%", height="100%")
            # Subtract (Make a hole).
            if len(path_group) > 1:
                self.create_composite_path(path_group, rule, fill="#000000")
            else:
                self.create_single_shape(layer, path_group[0], fill="#000000")
        return current

    def apply_intersect_operation(
        self,
        layer: layers.ShapeLayer,
        path_group: list[Subpath],
        current: ET.Element,
        previous: ET.Element,
        rule: Literal["fill-rule", "clip-rule"],
    ) -> ET.Element:
        """Apply Intersect (AND) operation to find overlapping regions."""
        # Create a new mask for the AND operation.
        if len(previous) > 0:
            current = self.create_node(
                "mask",
                id=self.auto_id("mask"),
            )
        with self.set_current(current):
            # Create the intersection by masking the previous shape.
            if len(path_group) > 1:
                self.create_composite_path(path_group, rule, fill="#ffffff")
            else:
                self.create_single_shape(
                    layer,
                    path_group[0],
                    mask=svg_utils.get_funciri(previous) if len(previous) > 0 else None,
                    fill="#ffffff",
                )
        return current

    def apply_xor_operation(
        self,
        layer: layers.ShapeLayer,
        path_group: list[Subpath],
        current: ET.Element,
        previous: ET.Element,
        rule: Literal["fill-rule", "clip-rule"],
    ) -> ET.Element:
        """Apply XOR (exclusive-or) operation using (A OR B) AND NOT (A AND B)."""
        if len(previous) == 0:
            # First shape: just add it directly (XOR with nothing = identity)
            with self.set_current(current):
                if len(path_group) > 1:
                    self.create_composite_path(path_group, rule, fill="#ffffff")
                else:
                    self.create_single_shape(layer, path_group[0], fill="#ffffff")
            return current

        # Create the shape in <defs> to reuse it
        defs = self.create_node("defs")
        shape_id = self.auto_id("shape")
        with self.set_current(defs):
            if len(path_group) > 1:
                self.create_composite_path(path_group, rule, id=shape_id)
            else:
                self.create_single_shape(layer, path_group[0], id=shape_id)

        # Create a mask for the union (A OR B)
        union_mask = self.create_node(
            "mask",
            id=self.auto_id("mask"),
        )
        # Add previous shapes to union
        with self.set_current(union_mask):
            self.create_node(
                "rect",
                fill="#ffffff",
                width="100%",
                height="100%",
                mask=svg_utils.get_funciri(previous),
            )
        # Add current shape to union using <use>
        with self.set_current(union_mask):
            self.create_node(
                "use",
                href=f"#{shape_id}",
                fill="#ffffff",
            )

        # Create a mask for the intersection (A AND B)
        intersection_mask = self.create_node(
            "mask",
            id=self.auto_id("mask"),
        )
        with self.set_current(intersection_mask):
            self.create_node(
                "use",
                href=f"#{shape_id}",
                fill="#ffffff",
                mask=svg_utils.get_funciri(previous),
            )

        # Create the final XOR mask: union minus intersection
        current = self.create_node(
            "mask",
            id=self.auto_id("mask"),
        )
        with self.set_current(current):
            # Add the union
            self.create_node(
                "rect",
                fill="#ffffff",
                width="100%",
                height="100%",
                mask=svg_utils.get_funciri(union_mask),
            )
            # Subtract the intersection
            self.create_node(
                "rect",
                fill="#000000",
                width="100%",
                height="100%",
                mask=svg_utils.get_funciri(intersection_mask),
            )
        return current

    def create_single_shape(
        self, layer: layers.ShapeLayer, path: Subpath, **attrib: Any
    ) -> ET.Element:
        """Create a single shape element from the layer's vector mask
        or origination data."""
        if not layer.has_vector_mask() or layer.vector_mask is None:
            raise ValueError("Layer has no vector mask: %s", layer.name)

        if layer.vector_mask.initial_fill_rule:
            logger.warning("Initial fill rule (inverted mask) is not supported yet.")

        if self.enable_live_shapes and layer.has_origination():
            origination = layer.origination[path.index]
            if (
                layer.has_stroke()
                and layer.stroke is not None
                and layer.stroke.enabled
                and _has_scaling_transform(origination)
            ):
                # A transform on a live shape would scale the stroke width too.
                return self.create_path(path, **attrib)
            reference = layer.tagged_blocks.get_data(Tag.REFERENCE_POINT, (0.0, 0.0))
            if isinstance(origination, Rectangle):
                node = self.create_origination_rectangle(
                    origination, reference, **attrib
                )
                node = self.apply_origination_transform(layer, origination, node)
            elif (
                isinstance(origination, RoundedRectangle)
                and origination.radii is not None
            ):
                node = self.create_origination_rounded_rectangle(
                    origination, origination.radii, reference, **attrib
                )
                node = self.apply_origination_transform(layer, origination, node)
            elif isinstance(origination, Ellipse):
                node = self.create_origination_ellipse(origination, reference, **attrib)
                node = self.apply_origination_transform(layer, origination, node)
            else:
                # Fallback to path creation.
                # TODO: Support line shapes.
                logger.debug(f"Unsupported shape type: {origination}")
                node = self.create_path(path, **attrib)
        else:
            node = self.create_path(path, **attrib)

        return node

    def create_origination_rectangle(
        self,
        origination: Rectangle,
        reference: tuple[float, float],
        **attrib: Any,
    ) -> ET.Element:
        """Create a rectangle shape from origination data."""
        bbox = get_origin_bbox(origination, reference)
        return self.create_node(
            "rect",
            x=bbox[0],
            y=bbox[1],
            width=bbox[2] - bbox[0],
            height=bbox[3] - bbox[1],
            **attrib,
        )

    def create_origination_rounded_rectangle(
        self,
        origination: RoundedRectangle,
        radii: Descriptor,
        reference: tuple[float, float],
        **attrib: Any,
    ) -> ET.Element:
        """Create a rounded rectangle shape from origination data."""
        bbox = get_origin_bbox(origination, reference)
        scales = get_origin_scale(origination)
        scale = (scales[0] + scales[1]) / 2
        rx = (float(radii[b"topRight"]) + float(radii[b"bottomRight"])) / 2 / scale
        ry = (float(radii[b"topRight"]) + float(radii[b"topLeft"])) / 2 / scale
        return self.create_node(
            "rect",
            x=bbox[0],
            y=bbox[1],
            width=bbox[2] - bbox[0],
            height=bbox[3] - bbox[1],
            rx=rx,
            ry=ry,
            **attrib,
        )

    def create_origination_ellipse(
        self, origination: Ellipse, reference: tuple[float, float], **attrib: Any
    ) -> ET.Element:
        """Create an ellipse shape from origination data."""
        bbox = get_origin_bbox(origination, reference)
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        rx = (bbox[2] - bbox[0]) / 2
        ry = (bbox[3] - bbox[1]) / 2
        if rx == ry:
            return self.create_node(
                "circle",
                cx=int(cx),
                cy=int(cy),
                r=rx,
                **attrib,
            )
        else:
            return self.create_node(
                "ellipse",
                cx=int(cx),
                cy=int(cy),
                rx=rx,
                ry=ry,
                **attrib,
            )

    def apply_origination_transform(
        self,
        layer: layers.ShapeLayer,
        origination: Rectangle | RoundedRectangle | Ellipse,
        node: ET.Element,
    ) -> ET.Element:
        """Apply transform attribute from origination data."""
        # Check if transform is available.
        if b"Trnf" not in origination._data:
            return node

        # Apply the transformation matrix.
        transform = origination._data[b"Trnf"]
        assert transform.classID == b"Trnf"
        reference = tuple(layer.tagged_blocks.get_data(Tag.REFERENCE_POINT, (0, 0)))
        matrix = (
            float(transform[b"xx"]),
            float(transform[b"xy"]),
            float(transform[b"yx"]),
            float(transform[b"yy"]),
            float(transform[b"tx"]),
            float(transform[b"ty"]),
        )
        if (
            matrix[:4] == (1, 0, 0, 1)
            and matrix[4] - reference[0] == 0
            and matrix[5] - reference[1] == 0
        ):
            # Identity matrix, no transform needed.
            return node

        transform_applied = False
        if matrix != (1, 0, 0, 1, 0, 0):
            svg_utils.append_attribute(
                node, "transform", "matrix(%s)" % svg_utils.seq2str(matrix, digit=4)
            )
            transform_applied = True
        if reference != (0.0, 0.0):
            svg_utils.append_attribute(
                node,
                "transform",
                "translate(%s)"
                % svg_utils.seq2str((-reference[0], -reference[1]), digit=4),
            )
            transform_applied = True

        if transform_applied and ("clip-path" in node.attrib or "mask" in node.attrib):
            # We cannot set transform for node with clip-path or mask directly.
            # Instead, we wrap it in a <use> element.
            # NOTE: This interferes with mix-blend-mode isolation.
            clip_path = node.attrib.pop("clip-path", None)
            mask = node.attrib.pop("mask", None)
            if "id" not in node.attrib:
                svg_utils.set_attribute(node, "id", self.auto_id("shape"))
            if self.current.tag != "defs":
                defs = self.create_node("defs")
                svg_utils.wrap_element(node, self.current, defs)
            use = self.create_node(
                "use",
                href=svg_utils.get_uri(node),
                mask=mask,
                clip_path=clip_path,
                id=self.auto_id("use"),
            )
            if "style" in node.attrib and "mix-blend-mode" in node.attrib["style"]:
                logger.warning(
                    "Mix-blend-mode may not work correctly with transformed "
                    "shapes using clip-path or mask."
                )
            return use
        return node

    def create_path(self, path: Subpath, **attrib: Any) -> ET.Element:
        """Create a path element."""
        return self.create_node(
            "path",
            d=" ".join(generate_path(path, self.psd.width, self.psd.height)),
            **attrib,
        )

    def create_composite_path(
        self,
        paths: list[Subpath],
        rule: Literal["fill-rule", "clip-rule"] = "fill-rule",
        **attrib: Any,
    ) -> ET.Element:
        """Create a composite path element."""
        return self.create_node(
            "path",
            d=" ".join(
                " ".join(generate_path(path, self.psd.width, self.psd.height))
                for path in paths
            ),
            **{str(rule): "evenodd"},  # type: ignore[arg-type]
            **attrib,  # type: ignore[arg-type]
        )


def generate_path(
    path: Subpath, width: int, height: int, command: str = "C"
) -> Iterator[str]:
    """Sequence generator for SVG path constructor."""
    if len(path) == 0:
        return

    # Initial point.
    yield "M"
    yield ",".join(
        [
            svg_utils.num2str(path[0].anchor[1] * width),
            svg_utils.num2str(path[0].anchor[0] * height),
        ]
    )

    # Closed path or open path
    points = (
        zip(path, path[1:] + path[0:1]) if path.is_closed() else zip(path, path[1:])
    )

    # Rest of the points.
    yield command
    for p1, p2 in points:
        yield ",".join(
            [
                svg_utils.num2str(p1.leaving[1] * width),
                svg_utils.num2str(p1.leaving[0] * height),
            ]
        )
        yield ",".join(
            [
                svg_utils.num2str(p2.preceding[1] * width),
                svg_utils.num2str(p2.preceding[0] * height),
            ]
        )
        yield ",".join(
            [
                svg_utils.num2str(p2.anchor[1] * width),
                svg_utils.num2str(p2.anchor[0] * height),
            ]
        )

    if path.is_closed():
        yield "Z"


def get_origin_bbox(
    origination: Rectangle | RoundedRectangle | Ellipse,
    reference: tuple[float, float],
) -> tuple[float, float, float, float]:
    """Get the origin bounding box for origination data."""
    if b"keyOriginBoxCorners" in origination._data and b"Trnf" in origination._data:
        # Calculate rectangle from corner points when transform is available.
        # Corners are given in transformed space; i.e., after applying Trnf.
        corners = origination._data[b"keyOriginBoxCorners"]
        x1 = float(corners[b"rectangleCornerA"][b"Hrzn"])
        y1 = float(corners[b"rectangleCornerA"][b"Vrtc"])
        x2 = float(corners[b"rectangleCornerB"][b"Hrzn"])
        y2 = float(corners[b"rectangleCornerB"][b"Vrtc"])
        x3 = float(corners[b"rectangleCornerC"][b"Hrzn"])
        y3 = float(corners[b"rectangleCornerC"][b"Vrtc"])
        x4 = float(corners[b"rectangleCornerD"][b"Hrzn"])
        y4 = float(corners[b"rectangleCornerD"][b"Vrtc"])
        transform = origination._data[b"Trnf"]
        xx = float(transform[b"xx"])
        xy = float(transform[b"xy"])
        yx = float(transform[b"yx"])
        yy = float(transform[b"yy"])
        tx = float(transform[b"tx"])
        ty = float(transform[b"ty"])
        # Corners are in transformed space. Invert to get original coordinates.
        X = np.array([[x1, y1, 1], [x2, y2, 1], [x3, y3, 1], [x4, y4, 1]]).T
        M = np.array([[xx, yx, tx], [xy, yy, ty], [0, 0, 1]])
        # Apply inverse transform: Y = M^-1 @ X, then offset by reference point
        Y = np.linalg.solve(M, X) + np.array([[reference[0]], [reference[1]], [0]])
        bbox = (
            float(np.min(Y[0, :])),
            float(np.min(Y[1, :])),
            float(np.max(Y[0, :])),
            float(np.max(Y[1, :])),
        )
    else:
        bbox = origination.bbox
    return bbox


def _has_scaling_transform(origination: Any) -> bool:
    """Whether the origination transform scales, rotates, or skews the shape."""
    if b"Trnf" not in origination._data:
        return False
    transform = origination._data[b"Trnf"]
    matrix = tuple(float(transform[k]) for k in (b"xx", b"xy", b"yx", b"yy"))
    return matrix != (1.0, 0.0, 0.0, 1.0)


def get_origin_scale(
    origination: Rectangle | RoundedRectangle | Ellipse,
) -> tuple[float, float]:
    """Get the origin scale for origination data."""
    if b"Trnf" in origination._data:
        transform = origination._data[b"Trnf"]
        xx = float(transform[b"xx"])
        xy = float(transform[b"xy"])
        yx = float(transform[b"yx"])
        yy = float(transform[b"yy"])
        scale_x = (xx**2 + yx**2) ** 0.5
        scale_y = (xy**2 + yy**2) ** 0.5
        return (scale_x, scale_y)
    return (1.0, 1.0)
