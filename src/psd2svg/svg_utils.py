import copy
import html
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from re import Pattern
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)

NAMESPACE = "http://www.w3.org/2000/svg"
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"

ILLEGAL_XML_RE: Pattern[str] = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff\ufdd0-\ufddf\ufffe-\uffff]"
)

DEFAULT_NUMBER_DIGITS = 2


def safe_utf8(text: str) -> str:
    """Remove illegal and problematic XML characters from text.

    This function filters out characters that are illegal or problematic in XML
    documents by replacing them with spaces. The filtering is intentionally
    conservative, removing more characters than strictly required by the XML 1.0
    specification.

    Characters filtered (replaced with space):
        - C0 controls (0x00-0x08, 0x0B-0x1F): NULL, control characters
          Exception: TAB (0x09), LF (0x0A) are preserved
        - C1 controls (0x7F-0x9F): DEL and C1 control block including NEL (0x85)
        - UTF-16 surrogates (0xD800-0xDFFF): Illegal in UTF-8/XML
        - Non-characters (0xFDD0-0xFDDF, 0xFFFE-0xFFFF): Illegal in XML

    Characters preserved:
        - TAB (0x09): Horizontal spacing
        - LF (0x0A): Line breaks
        - Normal printable characters (0x20 and above, excluding filtered ranges)

    Note on CR (0x0D):
        CR (Carriage Return) is filtered despite being technically legal in XML 1.0.
        This is an intentional conservative design choice because:
        1. XML processors normalize CR to LF per XML 1.0 spec (section 2.11)
        2. Filtering CR prevents line-ending confusion attacks
        3. TAB and LF are sufficient for all whitespace needs in SVG
        4. Historical issues with CR in PSD text conversion (see commit d81e4b5)

    Args:
        text: Input string that may contain illegal XML characters.

    Returns:
        Sanitized string with illegal characters replaced by spaces.

    Example:
        >>> safe_utf8("Hello\\x00World\\x85Test")
        'Hello World Test'
        >>> safe_utf8("Tab\\there\\nNewline")
        'Tab\there\nNewline'
    """
    return ILLEGAL_XML_RE.sub(" ", text)


def num2str(num: int | float | bool, digit: int = DEFAULT_NUMBER_DIGITS) -> str:
    """Convert a number to a string, using the specified format for floats."""
    if isinstance(num, bool):
        return "true" if num else "false"
    if isinstance(num, int):
        return str(num)
    if isinstance(num, float):
        if num.is_integer():
            return str(int(num))
        # Format float with specified number of digits, and trim trailing zeros
        number = f"{num:.{digit}f}"
        return f"{number[0]}{number[1:].rstrip('0').rstrip('.')}"
    raise ValueError(f"Unsupported type: {type(num)}")


def num2str_with_unit(
    num: int | float, unit: str = "px", digit: int = DEFAULT_NUMBER_DIGITS
) -> str:
    """Convert a number to a string with a CSS unit appended.

    Args:
        num: The numeric value to format
        unit: The CSS unit to append (default: "px")
        digit: Number of decimal digits for floats (default: 2)

    Returns:
        Formatted string with unit (e.g., "10px", "1.5em", "100%")

    Examples:
        >>> num2str_with_unit(10.0, "px")
        '10px'
        >>> num2str_with_unit(1.5, "em")
        '1.5em'
        >>> num2str_with_unit(100, "%")
        '100%'
    """
    return f"{num2str(num, digit)}{unit}"


def seq2str(
    seq: Sequence[int | float | bool],
    sep: str = ",",
    digit: int = DEFAULT_NUMBER_DIGITS,
) -> str:
    """Convert a sequence of numbers to a string.

    Uses the specified format for floats.
    """
    return sep.join(num2str(n, digit) for n in seq)


def create_node(
    tag: str,
    parent: Optional[ET.Element] = None,
    class_: str = "",
    title: str = "",
    text: str = "",
    desc: str = "",
    xml_space: Optional[str] = None,
    **kwargs: Any,
) -> ET.Element:
    """Create an XML node with attributes.

    Args:
        xml_space: Set xml:space attribute with proper XML namespace.
                  Use "preserve" to preserve whitespace, "default" for normal behavior.
    """
    node = ET.Element(tag)
    if class_:
        node.set("class", class_)

    # Handle xml:space with proper XML namespace
    if xml_space is not None:
        node.set("{http://www.w3.org/XML/1998/namespace}space", xml_space)

    for key, value in kwargs.items():
        if value is None:
            continue
        key = key.rstrip("_")  # allow trailing underscore for keywords
        key = key.replace("_", "-")  # convert underscores to hyphens
        set_attribute(node, key, value)
    if text:
        node.text = safe_utf8(text)
    if title:
        create_node("title", parent=node, text=safe_utf8(title))
    if desc:
        create_node("desc", parent=node, text=safe_utf8(desc))
    if parent is not None:
        parent.append(node)
    return node


def create_xhtml_node(
    tag: str,
    parent: Optional[ET.Element] = None,
    text: str = "",
    xml_space: Optional[str] = None,
    **kwargs: Any,
) -> ET.Element:
    """Create an XHTML node with proper namespace.

    This helper creates elements in the XHTML namespace for use within
    SVG <foreignObject> elements. The namespace is required for proper
    rendering in modern browsers (Chrome, Firefox, Safari, Edge).
    Note: resvg/resvg-py does not support foreignObject rendering.

    Args:
        tag: HTML tag name (e.g., 'div', 'p', 'span').
        parent: Optional parent element to append this node to.
        text: Optional text content.
        xml_space: Set xml:space attribute with proper XML namespace.
                  Use "preserve" to preserve whitespace.
        **kwargs: Additional attributes. Underscores in keys are converted
                 to hyphens (e.g., 'font_size' becomes 'font-size').

    Returns:
        XHTML element with namespace prefix.

    Example:
        >>> foreign_obj = create_node("foreignObject", x=0, y=0, width=100, height=50)
        >>> div = create_xhtml_node("div", parent=foreign_obj)
        >>> p = create_xhtml_node("p", parent=div, text="Hello")
        >>> span = create_xhtml_node("span", parent=p, text="World", style="color: red")
    """
    # Create element with XHTML namespace
    node = ET.Element(f"{{{XHTML_NAMESPACE}}}{tag}")

    # Handle xml:space with proper XML namespace
    if xml_space is not None:
        node.set("{http://www.w3.org/XML/1998/namespace}space", xml_space)

    # Set attributes
    for key, value in kwargs.items():
        if value is None:
            continue
        key = key.rstrip("_")  # allow trailing underscore for keywords
        key = key.replace("_", "-")  # convert underscores to hyphens
        set_attribute(node, key, value)

    # Set text content
    if text:
        node.text = safe_utf8(text)

    # Append to parent if provided
    if parent is not None:
        parent.append(node)

    return node


def styles_to_string(styles: dict[str, str]) -> str:
    """Convert a dictionary of CSS styles to a CSS string.

    Args:
        styles: Dictionary of CSS property names to values.

    Returns:
        CSS string suitable for use in a 'style' attribute.

    Example:
        >>> styles = {"color": "red", "font-size": "12px"}
        >>> styles_to_string(styles)
        'color: red; font-size: 12px'
    """
    if not styles:
        return ""
    return "; ".join(f"{key}: {value}" for key, value in styles.items())


def _strip_text_element_whitespace(node: ET.Element) -> None:
    """Strip whitespace-only text and tail from SVG text elements.

    SVG preserves whitespace in text elements by default. When pretty-printing
    adds indentation, this whitespace becomes significant and can cause
    alignment issues (especially with text-anchor="end"). This function ensures
    that any whitespace-only text/tail content is removed from text container
    elements, leaving only the actual text content in tspan children.
    """
    # Check if this is a text or tspan element
    tag = node.tag
    if isinstance(tag, str):
        # Handle namespaced tags
        local_name = tag.split("}")[-1] if "}" in tag else tag
        is_text_element = local_name in ("text", "tspan", "textPath")
    else:
        is_text_element = False

    if is_text_element:
        # If element has children, clear any whitespace-only text
        if len(node) > 0:
            if node.text and node.text.strip() == "":
                node.text = None

        # Clear whitespace-only tail for all child elements
        for child in node:
            if child.tail and child.tail.strip() == "":
                child.tail = None

    # Recursively clean all child elements
    for child in node:
        _strip_text_element_whitespace(child)


def fromstring(data: str) -> ET.Element:
    """Parse an XML string to an Element."""
    return ET.fromstring(data)


def _fix_xhtml_namespace_prefixes(svg_string: str) -> str:
    """Remove namespace prefixes from XHTML elements in foreignObject.

    ElementTree serializes XHTML namespaced elements with prefixes like
    'html:div', 'html:p', 'html:span'. Browsers require unprefixed elements
    with xmlns declaration for proper CSS styling.

    Transforms:
        <foreignObject xmlns:html="..."><html:div>...</html:div></foreignObject>

    Into:
        <foreignObject><div xmlns="http://www.w3.org/1999/xhtml">...</div></foreignObject>

    Args:
        svg_string: Serialized SVG string from ElementTree.

    Returns:
        SVG string with XHTML namespace prefixes removed.

    Note:
        - Handles multiple foreignObject elements
        - Works with any namespace prefix (html, ns0, ns1, etc.)
        - Only modifies XHTML elements (div, p, span)
        - Adds xmlns declaration to first XHTML element in each foreignObject
    """
    # XHTML namespace URL - escaped for use in regex patterns
    xhtml_ns_escaped = re.escape(XHTML_NAMESPACE)

    # Pattern to match XHTML namespace declarations with any prefix
    ns_decl_pattern = f' xmlns:([a-zA-Z0-9]+)="{xhtml_ns_escaped}"'

    # Find all prefixes used for XHTML namespace
    matches = re.findall(ns_decl_pattern, svg_string)
    if not matches:
        # No XHTML namespace found, return unchanged
        return svg_string

    result = svg_string

    # Process each prefix (usually just one, but handle multiple)
    for prefix in set(matches):  # Use set to avoid duplicates
        # Remove the namespace declaration
        result = re.sub(
            f' xmlns:{re.escape(prefix)}="{xhtml_ns_escaped}"',
            "",
            result,
        )

        # Replace prefixed tags with unprefixed versions
        # Opening tags: <prefix:tag> or <prefix:tag attr="...">
        result = re.sub(
            f"<{re.escape(prefix)}:(div|p|span)",
            r"<\1",
            result,
        )
        # Closing tags: </prefix:tag>
        result = re.sub(
            f"</{re.escape(prefix)}:(div|p|span)>",
            r"</\1>",
            result,
        )

    # Add xmlns attribute to first XHTML element after each foreignObject
    # Use negative lookahead to ensure we stay within foreignObject boundaries
    def add_xmlns_to_first_element(match: re.Match[str]) -> str:
        """Add xmlns declaration to first XHTML element."""
        # Everything up to and including <foreignObject...> and content before tag
        foreign_obj_part = match.group(1)
        tag_name = match.group(2)  # div, p, or span
        # All attributes and spaces before the closing >
        existing_attrs = match.group(3)
        end_bracket = match.group(4)  # The closing >

        # Check if xmlns already exists anywhere in the tag (idempotency)
        if f'xmlns="{XHTML_NAMESPACE}"' in existing_attrs:
            return match.group(0)

        xmlns_attr = f'xmlns="{XHTML_NAMESPACE}"'

        # Add xmlns as the first attribute, preserving existing attributes
        if existing_attrs.strip() == "":
            # No attributes: <tag>
            new_attrs = f" {xmlns_attr}"
        else:
            # Has attributes: <tag attr="...">
            new_attrs = f" {xmlns_attr}{existing_attrs}"

        return f"{foreign_obj_part}<{tag_name}{new_attrs}{end_bracket}"

    # Apply xmlns addition to first XHTML element in each foreignObject
    # Use negative lookahead (?!</foreignObject) to stay within boundaries
    result = re.sub(
        r"(<foreignObject[^>]*>(?:(?!</foreignObject).)*?)<(div|p|span)([^>]*)(>)",
        add_xmlns_to_first_element,
        result,
        flags=re.DOTALL,
    )

    return result


def tostring(node: ET.Element, indent: str = "  ") -> str:
    """Convert an XML node to a string."""
    ET.indent(node, space=indent)
    _strip_text_element_whitespace(node)
    svg_string = ET.tostring(node, encoding="unicode", xml_declaration=False)

    # Fix XHTML namespace prefixes in foreignObject elements
    # ElementTree adds prefixes (html:div), but browsers need unprefixed elements
    # with xmlns declaration for proper CSS styling
    svg_string = _fix_xhtml_namespace_prefixes(svg_string)

    return svg_string


def parse(file: Any) -> ET.Element:
    """Parse an XML file to an Element."""
    tree = ET.parse(file)
    if tree is None or tree.getroot() is None:
        raise ValueError("Failed to parse XML file.")
    return tree.getroot()


def write(node: ET.Element, file: Any, indent: str = "  ") -> None:
    """Write an XML node to a file."""
    tree = ET.ElementTree(node)
    ET.indent(tree, space=indent)
    _strip_text_element_whitespace(node)
    tree.write(file, encoding="unicode", xml_declaration=False)


def add_style(node: ET.Element, key: str, value: Any) -> None:
    """Add a CSS property to an XML node."""
    if "style" in node.attrib:
        node.set("style", f"{node.get('style')}; {key}: {value}")
    else:
        node.set("style", f"{key}: {value}")


def add_class(node: ET.Element, class_name: str) -> None:
    """Add a class to an XML node."""
    if "class" in node.attrib:
        classes = node.get("class", "").split()
        if class_name not in classes:
            classes.append(class_name)
            node.set("class", " ".join(classes))
    else:
        node.set("class", class_name)


def set_attribute(node: ET.Element, key: str, value: Any) -> None:
    """Add an attribute to an XML node."""
    if isinstance(value, (int, float, bool)):
        node.set(key, num2str(value))
    elif isinstance(value, list) and all(
        isinstance(v, (int, float, bool)) for v in value
    ):
        node.set(key, seq2str(value))
    else:
        node.set(key, str(value))


def append_attribute(
    node: ET.Element, key: str, value: Any, separator: str = " "
) -> None:
    """Append a value to an existing attribute of an XML node."""
    if key in node.attrib:
        existing_value = node.get(key, "")
        new_value = f"{existing_value}{separator}{value}"
        node.set(key, new_value)
    else:
        set_attribute(node, key, value)


def set_transform_with_origin(
    element: ET.Element,
    transform_attr: str,
    transforms: list[str],
    origin: tuple[float, float] | None = None,
) -> None:
    """Set transform attribute with optional transform-origin.

    This function sets transform operations on gradient, pattern, or other SVG elements
    using the modern SVG 2.0 transform-origin attribute instead of translate wrappers.

    Args:
        element: SVG element to modify (e.g., linearGradient, pattern)
        transform_attr: Name of the transform attribute (e.g., "gradientTransform",
            "patternTransform")
        transforms: List of transform functions (e.g., ['rotate(45)', 'scale(2)'])
        origin: Transform origin point (x, y). If provided, sets transform-origin
            attribute. Default SVG transform-origin is (0, 0).

    Example:
        Instead of: gradientTransform="translate(50,50) rotate(45)
                    translate(-50,-50)"
        Produces:   gradientTransform="rotate(45)" transform-origin="50 50"

    Note:
        SVG 2.0 feature. Supported by modern browsers and resvg-py. When origin
        is provided but no transforms, uses translate() instead. When the
        attribute already exists (from append_attribute), appends to it instead.
    """
    if transforms:
        # Check if there's already a transform attribute (e.g., from offset)
        has_existing = transform_attr in element.attrib

        if has_existing and origin is not None and origin != (0.0, 0.0):
            # If there's an existing transform (e.g., offset), we can't use
            # transform-origin because it would apply to all transforms. Use
            # the old translate pattern instead.
            append_attribute(
                element,
                transform_attr,
                f"translate({seq2str(origin, sep=',', digit=4)})",
            )
            append_attribute(element, transform_attr, " ".join(transforms))
            append_attribute(
                element,
                transform_attr,
                f"translate({seq2str((-origin[0], -origin[1]), sep=',', digit=4)})",
            )
        elif origin is not None and origin != (0.0, 0.0):
            # No existing transform, use transform-origin
            set_attribute(element, transform_attr, " ".join(transforms))
            set_attribute(element, "transform-origin", seq2str(origin, sep=" "))
        else:
            # No origin or origin is (0, 0)
            if has_existing:
                append_attribute(element, transform_attr, " ".join(transforms))
            else:
                set_attribute(element, transform_attr, " ".join(transforms))
    elif origin is not None and origin != (0.0, 0.0):
        # If we have origin but no transforms, use translate instead
        set_attribute(element, transform_attr, f"translate({seq2str(origin)})")


def get_uri(node: ET.Element) -> str:
    """Get an uri string for the given node."""
    id_ = node.get("id")
    if not id_:
        raise ValueError(f"Node must have an 'id' attribute to get uri: {node}")
    return f"#{id_}"


def get_funciri(node: ET.Element) -> str:
    """Get a funciri string for the given node."""
    return f"url({get_uri(node)})"


def wrap_element(
    node: ET.Element, parent: ET.Element, wrapper: ET.Element
) -> ET.Element:
    """Wrap the given existing node in the wrapper element.

    Usage::
        wrapper = svg_utils.create_node("g")
        wrapped_node = svg_utils.wrap_element(node, parent, wrapper)

    Args:
        node: The XML node to be wrapped.
        parent: The parent XML node containing the node to be wrapped.
        wrapper: The wrapper XML node.
    """
    # NOTE: There is no direct way to find a parent from the node.
    if node not in parent:
        raise ValueError(f"Node is not a child of the given parent: {node} in {parent}")
    parent.remove(node)
    wrapper.append(node)
    return wrapper


def _unwrap_wrapper_element(
    parent: ET.Element,
    wrapper: ET.Element,
    insert_position: int | None = None,
) -> None:
    """Unwrap a wrapper element by moving its children to parent level.

    This helper function is shared by merge_singleton_children and
    merge_attribute_less_children to eliminate code duplication.

    Args:
        parent: Parent element containing the wrapper.
        wrapper: Wrapper element to unwrap (will be removed from parent).
        insert_position: If None, append grandchildren to end of parent;
                        else insert at this position.

    The function:
    - Removes the wrapper from parent
    - Moves wrapper's children (grandchildren) to parent level
    - Transfers wrapper's tail to the last grandchild (or parent's text)
    - Preserves document order
    """
    grandchildren = list(wrapper)

    # Remove wrapper from parent
    parent.remove(wrapper)

    # Insert grandchildren at appropriate position
    if insert_position is None:
        # Append to end (used by merge_singleton_children)
        for grandchild in grandchildren:
            parent.append(grandchild)
    else:
        # Insert at specific position (used by merge_attribute_less_children)
        for j, grandchild in enumerate(grandchildren):
            parent.insert(insert_position + j, grandchild)

    # Transfer wrapper's tail to last grandchild
    if wrapper.tail:
        if len(grandchildren) > 0:
            # Add to last grandchild's tail
            if insert_position is None:
                last_grandchild = parent[-1]
            else:
                last_grandchild = parent[insert_position + len(grandchildren) - 1]
            last_grandchild.tail = (last_grandchild.tail or "") + wrapper.tail
        else:
            # No grandchildren - handle tail appropriately
            if insert_position is not None and insert_position > 0:
                # Append to previous sibling's tail
                prev = parent[insert_position - 1]
                prev.tail = (prev.tail or "") + wrapper.tail
            else:
                # No previous sibling, append to parent's text
                parent.text = (parent.text or "") + wrapper.tail


def merge_attribute_less_children(element: ET.Element) -> None:
    """Recursively merge children without attributes into their parent nodes.

    This utility removes redundant wrapper elements that have no attributes,
    moving their text content directly into the parent element. This helps
    produce cleaner, more compact SVG output.

    The function preserves document order by properly handling both element.text
    and child.tail to ensure text appears in the correct sequence.

    Args:
        element: The XML element to process recursively.

    Example:
        Before: <text><tspan x="10"><tspan>Hello</tspan></tspan></text>
        After:  <text><tspan x="10">Hello</tspan></text>

        Before: <text><tspan font-weight="700">Bold</tspan><tspan> text</tspan></text>
        After:  <text><tspan font-weight="700">Bold</tspan> text</text>
    """
    # First, recursively process all children
    for child in list(element):
        merge_attribute_less_children(child)

    # Then merge attribute-less children into parent
    # We need to find the previous element that still exists (wasn't removed)
    children = list(element)
    for i, child in enumerate(children):
        if not child.attrib:
            # If the child has its own children, unwrap it: move grandchildren up
            if len(child) > 0:
                # Only unwrap if there's no text content to preserve
                has_text = child.text is not None and child.text.strip() != ""

                if not has_text:
                    # Find where to insert grandchildren (at the child's position)
                    child_index = list(element).index(child)
                    # Unwrap the wrapper, inserting grandchildren at child's position
                    _unwrap_wrapper_element(element, child, insert_position=child_index)

                continue

            # Move child's text content
            if child.text:
                # Find previous sibling that still exists in the tree
                prev_existing = None
                for j in range(i - 1, -1, -1):
                    if children[j] in element:
                        prev_existing = children[j]
                        break

                if prev_existing is not None:
                    # Append to previous existing sibling's tail
                    prev_existing.tail = (prev_existing.tail or "") + child.text
                else:
                    # No previous sibling, append to parent's text
                    element.text = (element.text or "") + child.text

            # Move child's tail
            if child.tail:
                # Find next sibling that still exists in the tree
                next_existing = None
                for j in range(i + 1, len(children)):
                    if children[j] in element:
                        next_existing = children[j]
                        break

                if next_existing is not None:
                    # Prepend to next existing sibling's text
                    next_existing.text = child.tail + (next_existing.text or "")
                else:
                    # No next sibling, find previous sibling or append to parent
                    prev_existing = None
                    for j in range(i - 1, -1, -1):
                        if children[j] in element:
                            prev_existing = children[j]
                            break

                    if prev_existing is not None:
                        prev_existing.tail = (prev_existing.tail or "") + child.tail
                    else:
                        element.text = (element.text or "") + child.tail

            # Remove the now-empty child
            element.remove(child)


def merge_common_child_attributes(
    element: ET.Element, excludes: set[str] | None = None
) -> None:
    """Recursively merge common child attributes to their parent node.

    This utility hoists attributes that are common to ALL children (with the same value)
    to the parent element. This helps produce cleaner, more compact SVG output by
    reducing redundant attribute declarations.

    Args:
        element: The XML element to process recursively.
        excludes: Set of attribute names that should not be hoisted to parent.
                 Common excludes for text elements: {"x", "y", "dx", "dy", "transform"}

    Example:
        Before: <text><tspan fill="red">A</tspan><tspan fill="red">B</tspan>
                </text>

        After:  <text fill="red"><tspan>A</tspan><tspan>B</tspan></text>

        Before (with excludes={"x"}):
                <text><tspan x="10" fill="red">A</tspan><tspan x="20"
                      fill="red">B</tspan></text>

        After:  <text fill="red"><tspan x="10">A</tspan><tspan x="20">B
                </tspan></text>
    """
    if excludes is None:
        excludes = set()

    # First, recursively process all children
    for child in list(element):
        merge_common_child_attributes(child, excludes)

    # Find attributes that all children have in common with the same value
    children = list(element)
    if not children:
        return

    # Start with the first child's attributes as candidates
    common_attribs: dict[str, str] = {
        key: value for key, value in children[0].attrib.items() if key not in excludes
    }

    # Check if remaining children all have the same values
    for child in children[1:]:
        keys_to_remove = []
        for key, value in common_attribs.items():
            if key not in child.attrib or child.attrib[key] != value:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del common_attribs[key]

    # Migrate the common attributes to the parent element
    for key, value in common_attribs.items():
        element.attrib[key] = value
        for child in element:
            del child.attrib[key]


def merge_consecutive_siblings(element: ET.Element) -> None:
    """Recursively merge consecutive sibling elements with identical attributes.

    This utility consolidates sequences of consecutive child elements that have
    the same tag and identical attributes by merging their text content. This is
    particularly useful for optimizing SVG <tspan> elements.

    Args:
        element: The XML element to process recursively.

    Example:
        Before: <text>
                    <tspan font-size="18" letter-spacing="0.72">す</tspan>
                    <tspan font-size="18" letter-spacing="0.72">だ</tspan>
                    <tspan font-size="18" letter-spacing="0.72">け</tspan>
                </text>

        After:  <text>
                    <tspan font-size="18" letter-spacing="0.72">すだけ
                    </tspan>
                </text>

        Before: <text>
                    <tspan font-size="18" baseline-shift="-0.36"
                           letter-spacing="0.72">さ</tspan>
                    <tspan font-size="18" letter-spacing="0.72">す</tspan>
                    <tspan font-size="18" letter-spacing="0.72">だ</tspan>
                </text>

        After:  <text>
                    <tspan font-size="18" baseline-shift="-0.36"
                           letter-spacing="0.72">さ</tspan>
                    <tspan font-size="18" letter-spacing="0.72">すだ</tspan>
                </text>

    Note:
        - Only merges elements with the same tag name
        - Only merges elements with identical attribute sets
        - Preserves document order
        - Does not merge elements with child elements
        - Empty elements (no text or tail) are removed
    """
    # First, recursively process all children
    for child in list(element):
        merge_consecutive_siblings(child)

    # Then merge consecutive siblings with identical attributes
    children = list(element)
    if len(children) < 2:
        return

    i = 0
    while i < len(children):
        current = children[i]

        # Skip if current element has children (don't merge complex structures)
        if len(current) > 0:
            i += 1
            continue

        # Find consecutive siblings with same tag and attributes
        merge_group = [current]
        j = i + 1

        while j < len(children):
            next_elem = children[j]

            # Stop if next element has children
            if len(next_elem) > 0:
                break

            # Check if tags and attributes match
            if next_elem.tag == current.tag and next_elem.attrib == current.attrib:
                merge_group.append(next_elem)
                j += 1
            else:
                break

        # If we found consecutive siblings to merge (2 or more)
        if len(merge_group) >= 2:
            # Merge all text content into the first element
            merged_text = ""
            for elem in merge_group:
                if elem.text:
                    merged_text += elem.text

            # Set merged text to first element (or None if empty)
            merge_group[0].text = merged_text if merged_text else None

            # Preserve the tail of the last element in the group
            last_tail = merge_group[-1].tail

            # Remove all but the first element
            for elem in merge_group[1:]:
                element.remove(elem)

            # Set the tail to the first element
            merge_group[0].tail = last_tail

            # If the merged element is empty (no text, no tail), remove it
            if not merge_group[0].text and not merge_group[0].tail:
                element.remove(merge_group[0])

            # Update children list after removals
            children = list(element)
        else:
            i += 1


# Attributes that can be expressed as per-character coordinate lists on an SVG
# element. Every other attribute is treated as "style" and must match exactly
# for two elements to be merged by merge_offset_siblings.
_POSITIONAL_ATTRS = ("x", "y", "dx", "dy")


def _non_positional_attrib(element: ET.Element) -> dict[str, str]:
    """Return an element's attributes excluding positional coordinate ones."""
    return {
        key: value
        for key, value in element.attrib.items()
        if key not in _POSITIONAL_ATTRS
    }


def _has_combining_marks(text: str) -> bool:
    """Return True if text contains Unicode combining marks (Mn/Mc/Me).

    Combining marks make Python's ``len(text)`` diverge from the number of
    addressable characters an SVG renderer counts, which would misalign the
    per-character coordinate lists built by merge_offset_siblings. Groups that
    contain them are therefore left unmerged.
    """
    return any(unicodedata.category(char) in ("Mn", "Mc", "Me") for char in text)


def _serialize_relative_offsets(values: list[str | None]) -> str | None:
    """Serialize a relative (dx/dy) coordinate list.

    Unset entries default to 0 and trailing zeros are trimmed, since a relative
    offset defaults to 0 for characters past the end of the list.

    Returns:
        The space-separated list, or None if every entry is zero/unset.
    """
    last_nonzero = -1
    for index, value in enumerate(values):
        if value is not None and float(value) != 0.0:
            last_nonzero = index
    if last_nonzero < 0:
        return None
    return " ".join(values[index] or "0" for index in range(last_nonzero + 1))


def _serialize_absolute_offsets(
    values: list[str | None],
) -> tuple[bool, str | None]:
    """Serialize an absolute (x/y) coordinate list.

    Unlike relative offsets, an absolute coordinate list has no way to express
    an "unset" character in the middle of the list (there is no natural-advance
    sentinel). A group that would require such a gap cannot be merged.

    Returns:
        A ``(ok, value)`` tuple. ``ok`` is False when an internal gap would be
        required. ``value`` is None when no entry is set.
    """
    last_set = -1
    for index, value in enumerate(values):
        if value is not None:
            last_set = index
    if last_set < 0:
        return True, None
    prefix = values[: last_set + 1]
    if any(value is None for value in prefix):
        return False, None
    return True, " ".join(value for value in prefix if value is not None)


def _merge_offset_group(parent: ET.Element, group: list[ET.Element]) -> bool:
    """Merge a run of leaf siblings into the first element with position lists.

    Args:
        parent: The parent element that owns the group.
        group: Consecutive leaf siblings sharing identical non-positional
            attributes.

    Returns:
        True if the group was merged (positional attributes rewritten as lists
        and the remaining members removed). False if the group cannot be safely
        merged, in which case the tree is left unchanged.
    """
    texts = [element.text or "" for element in group]

    # Combining marks make len(text) diverge from the addressable-character
    # count, which would misalign the coordinate lists.
    if any(_has_combining_marks(text) for text in texts):
        return False

    # Build per-character value lists (None marks an unset position).
    per_char: dict[str, list[str | None]] = {attr: [] for attr in _POSITIONAL_ATTRS}
    for element, text in zip(group, texts):
        char_count = len(text)
        for attr in _POSITIONAL_ATTRS:
            value = element.attrib.get(attr)
            if char_count == 0:
                # An empty span hosts no character, so a coordinate on it is
                # ambiguous and the group cannot be merged safely.
                if value is not None:
                    return False
                continue
            per_char[attr].append(value)
            per_char[attr].extend([None] * (char_count - 1))

    serialized: dict[str, str | None] = {}
    for attr in ("dx", "dy"):
        serialized[attr] = _serialize_relative_offsets(per_char[attr])
    for attr in ("x", "y"):
        ok, value = _serialize_absolute_offsets(per_char[attr])
        if not ok:
            return False
        serialized[attr] = value

    merged = group[0]
    merged.text = "".join(texts) or None
    for attr in _POSITIONAL_ATTRS:
        value = serialized[attr]
        if value is None:
            merged.attrib.pop(attr, None)
        else:
            merged.attrib[attr] = value
    # Only the last member may carry a tail (see merge_offset_siblings), so
    # preserving it keeps any following content in place.
    merged.tail = group[-1].tail
    for element in group[1:]:
        parent.remove(element)
    return True


def merge_offset_siblings(element: ET.Element) -> None:
    """Recursively merge consecutive siblings that differ only in position.

    Photoshop kerning is emitted as a ``dx`` value on individual per-character
    <tspan> elements, so merge_consecutive_siblings (which only merges elements
    with identical attributes) leaves them unmerged. This function consolidates
    such runs into a single element carrying per-character coordinate lists,
    turning e.g.

        <tspan>a</tspan><tspan dx="0.1">b</tspan><tspan>c</tspan>

    into

        <tspan dx="0 0.1">abc</tspan>

    The ``x``/``y``/``dx``/``dy`` attributes become space-separated lists whose
    n-th value applies to the n-th character of the merged text.

    Args:
        element: The XML element to process recursively.

    Note:
        - Only leaf elements (no child elements) are merged.
        - Non-positional attributes must be identical across the whole group.
        - ``dx``/``dy`` are relative (default 0), so gaps are filled with 0 and
          trailing zeros are trimmed.
        - ``x``/``y`` are absolute; a group that would need an internal unset
          gap is left unmerged.
    """
    # First, recursively process all children
    for child in list(element):
        merge_offset_siblings(child)

    children = list(element)
    if len(children) < 2:
        return

    i = 0
    while i < len(children):
        current = children[i]

        # Skip elements with children (don't merge complex structures)
        if len(current) > 0:
            i += 1
            continue

        current_style = _non_positional_attrib(current)

        # Collect a run of mergeable leaf siblings with matching style.
        group = [current]
        j = i + 1
        while j < len(children):
            next_elem = children[j]
            if len(next_elem) > 0:
                break
            if next_elem.tag != current.tag:
                break
            if _non_positional_attrib(next_elem) != current_style:
                break
            # A non-empty tail carries content that merging would drop, so stop
            # the run before crossing it.
            if group[-1].tail:
                break
            group.append(next_elem)
            j += 1

        if len(group) >= 2 and _merge_offset_group(element, group):
            # The merged element remains at index i; refresh and re-scan.
            children = list(element)
        else:
            i += 1


def merge_singleton_children(element: ET.Element) -> None:
    """Recursively merge singleton child nodes into their parent nodes.

    This utility removes redundant wrapper elements when a parent has exactly one child
    and there are no conflicting attributes. The child's attributes and text content
    are moved to the parent element.

    Args:
        element: The XML element to process recursively.

    Example:
        Before: <text><tspan>Hello</tspan></text>
        After:  <text>Hello</text>

        Before: <text x="10"><tspan font-weight="700">Bold</tspan></text>
        After:  <text x="10" font-weight="700">Bold</text>

        Not merged (conflicting attributes):
        Before: <text x="10"><tspan x="20">Text</tspan></text>
        After:  <text x="10"><tspan x="20">Text</tspan></text>  (unchanged)

        Not merged (child has children):
        Before: <text><tspan><tspan>A</tspan><tspan>B</tspan></tspan></text>
        After:  <text><tspan><tspan>A</tspan><tspan>B</tspan></tspan></text>
                (unchanged)
    """
    # First, recursively process all children
    for child in list(element):
        merge_singleton_children(child)

    # Merge singleton child if present (checking AFTER recursion)
    if len(element) == 1:
        child = element[0]

        # If the child has its own children, we can still optimize by
        # "unwrapping" it: move the grandchildren up to be direct children of
        # element, removing the wrapper
        if len(child) > 0:
            # Only unwrap if there are no attribute conflicts and no text
            # content to preserve
            has_conflict = (
                len(set(element.attrib.keys()) & set(child.attrib.keys())) > 0
            )
            has_text = child.text is not None and child.text.strip() != ""

            if not has_conflict and not has_text:
                # Move child's attributes to parent
                for key, value in child.attrib.items():
                    element.attrib[key] = value

                # Unwrap the wrapper, appending grandchildren to end
                _unwrap_wrapper_element(element, child, insert_position=None)

            return

        # Check for attribute conflicts
        if len(set(element.attrib.keys()) & set(child.attrib.keys())) > 0:
            return  # Conflicting attributes, do not merge

        # Move child's text content to parent
        # Note: child.text comes before any children in document order
        if child.text:
            element.text = (element.text or "") + child.text

        # Move child's tail to parent's text
        # Note: When we remove the child, its tail (which comes after </child>)
        # should become part of the parent's text content
        if child.tail:
            element.text = (element.text or "") + child.tail

        # Move all child's attributes to parent
        for key, value in child.attrib.items():
            element.attrib[key] = value

        # Remove the now-merged child
        element.remove(child)


def consolidate_defs(svg: ET.Element) -> None:
    """Consolidate all <defs> and definition elements into a global <defs>.

    This optimization improves SVG structure by:
    1. Creating a single global <defs> element at the beginning of the SVG
    2. Moving all definition elements (filters, gradients, patterns, etc.) into it
    3. Removing now-empty inline <defs> elements

    Definition elements that are moved:
    - <defs> (contents merged into global defs)
    - <filter>
    - <linearGradient>
    - <radialGradient>
    - <pattern>
    - <clipPath>
    - <marker>
    - <symbol>

    Args:
        svg: The root SVG element to optimize (modified in-place).

    Note:
        This function preserves all id references and element ordering within defs.

        **Mask Element Exclusion:**

        This function does NOT move <mask> elements for the following technical reasons:

        1. **Coordinate Systems**: Masks use ``maskContentUnits="userSpaceOnUse"``
           by default, meaning mask content coordinates are evaluated at reference
           time (where ``mask="url(#id)"`` is applied), not at definition time.
           Moving masks to a different DOM position could affect coordinate system
           evaluation.

        2. **Property Inheritance**: Masks inherit CSS properties (fill, stroke,
           opacity, etc.) from their DOM ancestors. Moving a mask to <defs> changes
           its inheritance chain, which can alter rendering for masks with styled
           content.

        3. **Transform Handling**: psd2svg uses special transform workarounds for
           masked elements that rely on specific mask positioning in the DOM tree.

        4. **Renderer Compatibility**: Known compatibility issues exist with some
           SVG renderers regarding mask positioning and interactions with other
           elements (e.g., clipPath-mask interactions).

        **Nested Definitions Are Consolidated:**

        While <mask> elements themselves are not moved, any nested <defs> and
        definition elements (filters, gradients, etc.) WITHIN masks ARE moved
        to the global defs. This provides optimization benefits while preserving
        mask rendering fidelity. See ``test_consolidate_complex_real_world_example``
        in tests/test_optimize.py for demonstration.

    Example:
        Before:
            <svg>
                <rect fill="url(#g1)"/>
                <linearGradient id="g1">...</linearGradient>
                <defs><filter id="f1">...</filter></defs>
            </svg>

        After:
            <svg>
                <defs>
                    <linearGradient id="g1">...</linearGradient>
                    <filter id="f1">...</filter>
                </defs>
                <rect fill="url(#g1)"/>
            </svg>
    """
    # Definition element tags to consolidate (without namespace)
    definition_tags = {
        "filter",
        "linearGradient",
        "radialGradient",
        "pattern",
        "clipPath",
        "marker",
        "symbol",
    }

    # Find or create global <defs> element at the beginning
    global_defs = None
    for child in svg:
        tag = child.tag
        local_name = tag.split("}")[-1] if "}" in tag else tag
        if local_name == "defs":
            global_defs = child
            break

    if global_defs is None:
        # Create new global defs as first child
        global_defs = ET.Element("defs")
        svg.insert(0, global_defs)
    else:
        # Ensure global_defs is the first child
        if svg[0] is not global_defs:
            svg.remove(global_defs)
            svg.insert(0, global_defs)

    # Collect all definition elements from the entire SVG tree
    definitions_to_move: list[tuple[ET.Element, ET.Element]] = []  # (element, parent)

    def collect_definitions(element: ET.Element) -> None:
        """Recursively collect definition elements to move."""
        for child in list(element):
            tag = child.tag
            local_name = tag.split("}")[-1] if "}" in tag else tag

            # If it's a <defs> element (not the global one), collect its
            # children
            if local_name == "defs" and child is not global_defs:
                for def_child in list(child):
                    definitions_to_move.append((def_child, child))
                # Continue recursing into defs (in case of nested
                # structures)
                collect_definitions(child)
            # If it's a definition element (not inside global defs), collect it
            elif local_name in definition_tags and element is not global_defs:
                definitions_to_move.append((child, element))
                # Still recurse into the element (e.g., filters can contain
                # other elements)
                collect_definitions(child)
            else:
                # Recurse into other elements
                collect_definitions(child)

    # Collect definitions directly from SVG root level
    for child in list(svg):
        if child is global_defs:
            continue

        tag = child.tag
        local_name = tag.split("}")[-1] if "}" in tag else tag

        # If it's a <defs> element, collect its children
        if local_name == "defs":
            for def_child in list(child):
                definitions_to_move.append((def_child, child))
            # Also recurse into it
            collect_definitions(child)
        # If it's a definition element, collect it
        elif local_name in definition_tags:
            definitions_to_move.append((child, svg))
            # Also recurse into it
            collect_definitions(child)
        else:
            # For non-definition elements, recurse to find nested definitions
            collect_definitions(child)

    # Move all collected definitions to global defs
    for element, parent in definitions_to_move:
        # Skip if element has already been moved (e.g., parent was removed)
        if element not in parent:
            continue
        parent.remove(element)
        global_defs.append(element)

    # Remove now-empty <defs> elements
    def remove_empty_defs(element: ET.Element) -> None:
        """Recursively remove empty <defs> elements."""
        for child in list(element):
            tag = child.tag
            local_name = tag.split("}")[-1] if "}" in tag else tag
            if local_name == "defs" and child is not global_defs and len(child) == 0:
                element.remove(child)
            else:
                remove_empty_defs(child)

    remove_empty_defs(svg)

    # Remove global defs if it's empty (no definitions were found)
    if len(global_defs) == 0:
        svg.remove(global_defs)


def _normalize_element_for_comparison(element: ET.Element) -> str:
    """Create normalized string for structural comparison.

    This function creates a canonical string representation of an element
    for content-based comparison, excluding identity attributes like 'id'.

    Normalizations applied:
    - Remove id attribute (identity, not equality)
    - Sort attributes alphabetically (consistent ordering)
    - Recursively sort child attributes
    - Strip whitespace from text and tail
    - Serialize without whitespace

    Args:
        element: The element to normalize.

    Returns:
        Canonical string representation suitable for deduplication.
    """
    # Deep copy to avoid modifying original
    temp = copy.deepcopy(element)

    # Remove id attribute - it represents identity, not content equality
    temp.attrib.pop("id", None)

    # Sort all attributes and normalize whitespace recursively
    # (XML doesn't guarantee attribute order, and whitespace can vary)
    for elem in temp.iter():
        sorted_attrib = dict(sorted(elem.attrib.items()))
        elem.attrib.clear()
        elem.attrib.update(sorted_attrib)

        # Normalize text and tail whitespace
        if elem.text:
            elem.text = elem.text.strip() or None
        if elem.tail:
            elem.tail = elem.tail.strip() or None

    # Serialize to string for comparison
    return ET.tostring(temp, encoding="unicode", method="xml")


def _update_url_references(
    svg: ET.Element,
    id_mapping: dict[str, str],
) -> None:
    """Update all url(#id) references using id mapping.

    Searches the SVG tree for elements with URL reference attributes
    (fill, stroke, filter, clip-path, mask, marker-*) and updates
    any url(#id) references according to the provided mapping.

    Note:
        The converter only creates URL references in direct attributes,
        never in style attributes. Style attributes only contain
        font-family properties.

    Args:
        svg: The root SVG element to search.
        id_mapping: Mapping from old element IDs to canonical IDs.
    """
    # Attributes that can contain url() references
    url_attrs = {
        "fill",
        "stroke",
        "filter",
        "clip-path",
        "mask",
        "marker-start",
        "marker-mid",
        "marker-end",
    }

    # Pattern to match url(#id)
    url_pattern = re.compile(r"url\(#([^)]+)\)")

    updated_count = 0

    # Only iterate over elements that actually have URL reference attributes
    # This is more efficient than checking every element in the tree
    for attr in url_attrs:
        # Use XPath to find elements with this attribute
        for element in svg.findall(f".//*[@{attr}]"):
            value = element.get(attr)
            if value and "url(#" in value:

                def replace_url(match: re.Match[str]) -> str:
                    nonlocal updated_count
                    old_id = match.group(1)
                    if old_id in id_mapping:
                        new_id = id_mapping[old_id]
                        if new_id != old_id:
                            updated_count += 1
                            return f"url(#{new_id})"
                    return match.group(0)

                new_value = url_pattern.sub(replace_url, value)
                if new_value != value:
                    element.set(attr, new_value)

    if updated_count > 0:
        logger.debug(f"Updated {updated_count} url(#id) references")


def deduplicate_definitions(svg: ET.Element) -> None:
    """Deduplicate identical definition elements in <defs>.

    Identifies structurally identical definition elements (filter, gradients,
    patterns, clipPath, marker, symbol) and merges duplicates by keeping the
    first occurrence and updating all url(#id) references throughout the SVG tree.

    This function should be called AFTER consolidate_defs() to ensure all
    definition elements are in a single global <defs>.

    Priority order (based on PSD per-layer structure):
    1. filter, linearGradient, radialGradient, pattern (most common duplicates)
    2. clipPath, marker, symbol (less common but still beneficial)

    Args:
        svg: The root SVG element (modified in-place).

    Note:
        Elements are considered identical if they have:
        - Same tag
        - Same attributes (except 'id')
        - Same child structure and content

    Example:
        Before:
            <defs>
                <linearGradient id="g1"><stop offset="0%"/></linearGradient>
                <linearGradient id="g2"><stop offset="0%"/></linearGradient>
            </defs>
            <rect fill="url(#g1)"/>
            <circle fill="url(#g2)"/>

        After:
            <defs>
                <linearGradient id="g1"><stop offset="0%"/></linearGradient>
            </defs>
            <rect fill="url(#g1)"/>
            <circle fill="url(#g1)"/>
    """
    # Phase 1: Find global <defs> and extract definition elements
    global_defs = None
    for child in svg:
        tag = child.tag
        local_name = tag.split("}")[-1] if "}" in tag else tag
        if local_name == "defs":
            global_defs = child
            break

    if global_defs is None:
        return

    # All definition types from consolidate_defs
    # Prioritize high-duplication types (filters, gradients, patterns)
    definition_tags = {
        "filter",
        "linearGradient",
        "radialGradient",
        "pattern",
        "clipPath",
        "marker",
        "symbol",
    }

    definitions = []
    for child in global_defs:
        tag = child.tag
        local_name = tag.split("}")[-1] if "}" in tag else tag
        if local_name in definition_tags:
            definitions.append(child)

    if not definitions:
        return

    # Phase 2: Build canonical mapping using normalized serialization
    content_to_id: dict[str, str] = {}  # normalized_content -> canonical_id
    id_to_canonical: dict[str, str] = {}  # element_id -> canonical_id
    duplicates_to_remove: list[ET.Element] = []

    for element in definitions:
        element_id = element.get("id")
        if not element_id:
            logger.warning(f"Definition element missing id: {element.tag}")
            continue

        # Normalize element for comparison (remove id, sort attributes, serialize)
        normalized = _normalize_element_for_comparison(element)

        if normalized in content_to_id:
            # Duplicate found - map to canonical (first occurrence)
            canonical_id = content_to_id[normalized]
            id_to_canonical[element_id] = canonical_id
            duplicates_to_remove.append(element)
        else:
            # First occurrence - this becomes the canonical element
            content_to_id[normalized] = element_id
            id_to_canonical[element_id] = element_id  # Maps to itself

    # Phase 3: Update all url(#id) references
    if id_to_canonical:
        _update_url_references(svg, id_to_canonical)

    # Phase 4: Remove duplicates from defs
    for element in duplicates_to_remove:
        global_defs.remove(element)

    if duplicates_to_remove:
        logger.debug(f"Deduplicated {len(duplicates_to_remove)} definition elements")


def _is_unwrappable_group(group: ET.Element) -> bool:
    """Check if a <g> element can be safely unwrapped.

    Returns True if group has no attributes (or only empty class), and no <title>
    child elements. Returns False if group has ANY meaningful attributes or contains
    <title> children that could conflict if moved up.

    Meaningful attributes that prevent unwrapping:
    - id (may be referenced by <use> or JavaScript)
    - opacity (affects rendering)
    - style (may contain mix-blend-mode, isolation, etc.)
    - filter, clip-path, mask (affect rendering)
    - transform (affects coordinate space)
    - Any other unknown attributes (conservative approach)

    Args:
        group: The <g> element to check.

    Returns:
        True if safe to unwrap, False otherwise.
    """
    # Check attributes first
    if group.attrib:
        # Check each attribute
        for attr_name, attr_value in group.attrib.items():
            # Strip namespace from attribute name
            local_attr = attr_name.split("}")[-1] if "}" in attr_name else attr_name

            # Empty class is safe (debugging attribute, usually disabled)
            if local_attr == "class":
                if not attr_value or attr_value.strip() == "":
                    continue
                return False  # Non-empty class

            # Any other attribute prevents unwrapping
            return False

    # Check for <title> children that would conflict if moved up
    for child in group:
        tag = child.tag
        local_tag = tag.split("}")[-1] if "}" in tag else tag
        if local_tag == "title":
            return False  # Preserve groups with <title> children

    return True


def _unwrap_groups_recursive(element: ET.Element) -> None:
    """Recursively unwrap attribute-less <g> elements (helper for unwrap_groups).

    Processes the tree bottom-up: children first, then parent. This allows
    nested unwrappable groups to be eliminated in a single traversal.

    Args:
        element: Element to process recursively.
    """
    # Step 1: Recursively process all children first (bottom-up)
    for child in list(element):
        _unwrap_groups_recursive(child)

    # Step 2: After recursion, check for unwrappable <g> children
    children = list(element)
    for i, child in enumerate(children):
        # Get local tag name (strip namespace)
        tag = child.tag
        local_name = tag.split("}")[-1] if "}" in tag else tag

        # Only process <g> elements
        if local_name != "g":
            continue

        # Check if this group can be unwrapped
        if not _is_unwrappable_group(child):
            continue

        # Empty group after recursion? Remove it entirely
        if len(child) == 0:
            element.remove(child)
            continue

        # Unwrap: move grandchildren up to parent level
        # Find current position of child in parent
        child_index = list(element).index(child)
        # Reuse existing helper (handles tail, order, etc.)
        _unwrap_wrapper_element(element, child, insert_position=child_index)


def unwrap_groups(svg: ET.Element) -> None:
    """Unwrap <g> elements that have no meaningful attributes.

    This optimization removes redundant <g> wrapper elements that don't affect
    rendering, moving their children directly to the parent level. This reduces
    SVG nesting depth and file size.

    Groups are unwrapped if they have NO attributes (or only empty class), AND
    no <title> child elements. Groups with rendering attributes (opacity, style,
    filter, mask, clip-path, transform) or identity attributes (id) are preserved.

    Empty groups (no children) are removed entirely.

    Args:
        svg: The root SVG element to optimize (modified in-place).

    Example:
        Before:
            <svg>
                <g>
                    <rect x="0" y="0" width="100" height="100"/>
                </g>
            </svg>

        After:
            <svg>
                <rect x="0" y="0" width="100" height="100"/>
            </svg>

        Preserved (has opacity):
            <svg>
                <g opacity="0.5">
                    <rect x="0" y="0" width="100" height="100"/>
                </g>
            </svg>

    Note:
        This function is automatically called when optimize=True in save()
        and tostring(). It processes the tree recursively, unwrapping all
        eligible groups in a single pass.
    """
    _unwrap_groups_recursive(svg)


def extract_font_families(svg: ET.Element) -> set[str]:
    """Extract all unique font families from font-family attributes in SVG tree.

    Scans the SVG element tree for all font-family attributes (both as direct
    attributes and within style attributes) and extracts all font families
    from comma-separated lists.

    Args:
        svg: The SVG element tree to scan.

    Returns:
        Set of unique font family names found in the SVG.

    Note:
        - Extracts ALL fonts from comma-separated font-family lists
        - Strips quotes from font family names
        - Searches both font-family attributes and CSS style attributes

    Example:
        >>> svg = fromstring(
        ...     '<svg><text font-family="Arial, sans-serif">Hi</text></svg>'
        ... )
        >>> families = extract_font_families(svg)
        >>> "Arial" in families
        True
        >>> "sans-serif" in families
        True
    """
    font_families = set()

    # Find all elements with font-family attribute or style
    for elem in svg.iter():
        # Check font-family attribute
        font_family = elem.get("font-family")
        if font_family:
            # Parse comma-separated list, extract all fonts, strip quotes
            for font in font_family.split(","):
                font_name = font.strip().strip("'\"")
                if font_name:
                    font_families.add(font_name)

        # Also check style attribute for font-family
        style = elem.get("style")
        if style and "font-family" in style:
            # Parse style attribute (simple approach)
            for part in style.split(";"):
                if "font-family" in part and ":" in part:
                    value = part.split(":", 1)[1].strip()
                    # Parse comma-separated list, extract all fonts
                    for font in value.split(","):
                        font_name = font.strip().strip("'\"")
                        if font_name:
                            font_families.add(font_name)

    return font_families


def find_elements_with_font_family(
    svg: ET.Element, font_family: str, include_inherited: bool = True
) -> list[ET.Element]:
    """Find all text/tspan and XHTML text elements that use the given font family.

    This function searches for text, tspan, and XHTML text elements (p, span from
    foreignObject) that have the specified font-family applied, either directly via
    attributes or through CSS inheritance from parent elements.

    Args:
        svg: SVG element tree to search.
        font_family: Font family name to search for (case-insensitive).
        include_inherited: If True, include elements that inherit the font from
            parents.
            If False, only include elements with direct font-family
            declarations. Default is True for backward compatibility.

    Returns:
        List of text/tspan/p/span elements that use the specified font family.

    Note:
        - Searches both font-family attributes and style attributes
        - Supports CSS inheritance (walks up parent chain) when
          include_inherited=True
        - Case-insensitive font family matching
        - Only returns text and tspan elements (not their parents)

    Example:
        >>> svg = svg_utils.fromstring(
        ...     '<svg><text font-family="Arial">Hi</text></svg>'
        ... )
        >>> elements = find_elements_with_font_family(svg, "Arial")
        >>> len(elements)
        1
        >>> elements = find_elements_with_font_family(
        ...     svg, "Arial", include_inherited=False
        ... )
        >>> len(elements)
        1
    """
    matching_elements: list[ET.Element] = []
    font_family_lower = font_family.lower()

    # Build parent map for inheritance lookup
    parent_map = {c: p for p in svg.iter() for c in p}

    for element in svg.iter():
        # Get local tag name (strip namespace if present)
        tag = element.tag
        if "}" in tag:
            tag = tag.split("}", 1)[1]

        # Only process text/tspan and XHTML text elements (p, span from foreignObject)
        if tag not in ("text", "tspan", "p", "span"):
            continue

        # Check if element uses target font (with or without inheritance)
        if _element_uses_font_family(
            element, parent_map, font_family_lower, include_inherited
        ):
            matching_elements.append(element)

    return matching_elements


def _element_uses_font_family(
    element: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    target_font: str,
    include_inherited: bool = True,
) -> bool:
    """Check if element uses the target font (direct or inherited).

    Helper function for find_elements_with_font_family that walks up the
    parent
    chain to check for font-family declarations.

    Args:
        element: Element to check.
        parent_map: Dictionary mapping children to parents.
        target_font: Target font family name (lowercase).
        include_inherited: If True, walk up parent chain. If False, check only
            this element.

    Returns:
        True if element uses the target font, False otherwise.

    Note:
        Ignores CSS 'font' shorthand property, only checks 'font-family'.
    """
    current = element
    while True:
        # Check direct font-family attribute
        elem_font_family = current.get("font-family")
        if elem_font_family:
            clean_family = elem_font_family.strip("'\"").split(",")[0].strip("'\"")
            return clean_family.lower() == target_font

        # Check style attribute for font-family
        style = current.get("style")
        if style and "font-family:" in style:
            match = re.search(r"font-family:\s*([^;]+)", style)
            if match:
                font_family_value = match.group(1).strip()
                families = [
                    f.strip().strip("'\"") for f in font_family_value.split(",")
                ]
                if families:
                    return families[0].lower() == target_font

        # If not checking inheritance, stop here
        if not include_inherited:
            return False

        # Walk up to parent
        if current not in parent_map:
            break
        current = parent_map[current]

    return False


def extract_text_characters(element: ET.Element) -> str:
    """Extract text characters from an element for font subsetting.

    This function extracts both element.text and element.tail with HTML entity
    decoding. The tail is included because it's rendered using the element's
    font-family (not the parent's), which is important for accurate font subsetting.

    Control characters, format characters, and combining marks (like variation
    selectors) are filtered out as they are not rendered in SVG text elements
    and should not be included in charset matching for font resolution.

    Args:
        element: XML element to extract text from (typically text or tspan).

    Returns:
        Text content (text + tail) with HTML entities decoded and non-renderable
        characters removed.

    Note:
        - Extracts element.text (content before first child element)
        - ALSO extracts tail (content after element's closing tag)
        - Does NOT include text from child elements
        - Decodes HTML/XML entities (e.g., &lt; → <, &#x4E00; → 一)
        - Filters out:
          * Control characters (Cc, Cf): newlines, tabs, format controls
          * Surrogate characters (Cs): invalid in UTF-8
          * Unassigned characters (Cn): not valid Unicode
          * Combining marks (Mn, Mc, Me): variation selectors, diacritics
        - Tail is included because SVG inherits font-family: the tail is rendered
          using the element's font, not the parent's font

    Example:
        >>> elem = ET.fromstring('<text>Hello &amp; world</text>')
        >>> extract_text_characters(elem)
        'Hello & world'

        >>> root = ET.fromstring('<text><tspan>A</tspan>B</text>')
        >>> tspan = root[0]
        >>> extract_text_characters(tspan)  # Returns 'AB' (text +
        ...                                  # tail)
        'AB'

        >>> elem = ET.fromstring('<text>Hello\\nWorld</text>')
        >>> extract_text_characters(elem)  # Newline filtered
        'HelloWorld'

        >>> elem = ET.fromstring('<text>©\\uFE0E</text>')
        >>> # Copyright + variation selector
        >>> extract_text_characters(elem)  # Variation selector filtered
        '©'
    """
    result = ""
    if element.text:
        result += html.unescape(element.text)
    if element.tail:
        result += html.unescape(element.tail)

    # Filter out non-renderable characters using Unicode categories
    # These characters have no glyphs and cause incorrect font matching in fontconfig
    def should_keep(char: str) -> bool:
        category = unicodedata.category(char)
        # Keep everything except:
        # - Cc: Control characters (newlines, tabs, etc.)
        # - Cf: Format characters (zero-width, direction marks, etc.)
        # - Cs: Surrogate characters (invalid in UTF-8)
        # - Cn: Unassigned characters
        # - Mn: Nonspacing marks (variation selectors, combining diacritics)
        # - Mc: Spacing marks (some combining characters)
        # - Me: Enclosing marks
        return category not in ("Cc", "Cf", "Cs", "Cn", "Mn", "Mc", "Me")

    result = "".join(char for char in result if should_keep(char))

    return result


def replace_font_family(
    element: ET.Element, old_font_family: str, new_font_family: str
) -> None:
    """Replace a font family with another in the given element.

    This function modifies an SVG text/tspan element by replacing occurrences
    of old_font_family with new_font_family in font-family specifications.
    It handles both font-family attributes and style attributes.

    Args:
        element: Element to update (typically text or tspan element).
        old_font_family: Font family name to replace.
        new_font_family: Font family name to use as replacement.

    Example:
        Before: <text font-family="ArialMT">Hello</text>
        After:  <text font-family="Arial">Hello</text>

        Before: <text font-family="ArialMT, Helvetica">Hello</text>
        After:  <text font-family="Arial, Helvetica">Hello</text>

        Before: <text style="font-family: ArialMT">Hello</text>
        After:  <text style="font-family: 'Arial'">Hello</text>

    Note:
        - Replaces first occurrence of old_font_family in comma-separated list
        - If old_font_family not found, does nothing
        - For font-family attributes: no quotes (attribute delimiter is sufficient)
        - For style attributes: quotes font names for CSS compliance
        - Updates font-family attribute with higher priority than style
    """
    # Check font-family attribute first (higher priority)
    existing_font_family = element.get("font-family")
    if existing_font_family:
        # Parse existing font families
        families = [f.strip().strip("'\"") for f in existing_font_family.split(",")]
        # Replace old font with new font
        if old_font_family in families:
            families = [
                new_font_family if f == old_font_family else f for f in families
            ]
            # No quotes for SVG attributes (attribute delimiter is sufficient)
            element.set("font-family", ", ".join(families))
        return  # Attribute has priority, don't check style

    # Check style attribute for font-family
    style = element.get("style")
    if style and "font-family:" in style:

        def replace_in_style(match: re.Match[str]) -> str:
            font_family_value = match.group(1).strip()
            # Parse existing font families
            families = [f.strip().strip("'\"") for f in font_family_value.split(",")]
            # Replace old font with new font
            if old_font_family in families:
                families = [
                    new_font_family if f == old_font_family else f for f in families
                ]
            # Quote all families for CSS compliance
            return "font-family: " + ", ".join(f"'{f}'" for f in families)

        # Replace font-family in style attribute
        updated_style = re.sub(r"font-family:\s*([^;]+)", replace_in_style, style)
        if updated_style != style:
            element.set("style", updated_style)


def add_font_family(element: ET.Element, font_family: str) -> None:
    """Add font family to font-family specification in the given element.

    This function modifies an SVG text/tspan element by appending a font family
    to its existing font-family specification if not already present. It handles both
    font-family attributes and font-family declarations within style attributes.

    Behavior:
        - If element has font-family attribute: append font to it
        - Else if element has font-family in style: append font to style
        - Else: create new font-family attribute with the font
        - If both attribute and style exist: append to attribute (higher priority)

    Args:
        element: Element to update (typically text or tspan element).
        font_family: Font family name to add.

    Example:
        Before: <text font-family="Arial">Hello</text>
        After:  <text font-family="Arial, Helvetica">Hello</text>

        Before: <text style="font-family: Arial">Hello</text>
        After:  <text style="font-family: 'Arial', 'Helvetica'">Hello</text>

        Before: <text>Hello</text>
        After:  <text font-family="Helvetica">Hello</text>

    Note:
        - Updates font-family attribute with higher priority than style
        - For font-family attributes: no quotes (attribute delimiter is sufficient)
        - For style attributes: quotes font names for CSS compliance
        - Idempotent: does not add font if already present in the chain
        - Ignores CSS 'font' shorthand property, only handles 'font-family'
    """
    # Check font-family attribute first (higher priority)
    existing_font_family = element.get("font-family")
    if existing_font_family:
        # Parse existing font families
        families = [f.strip().strip("'\"") for f in existing_font_family.split(",")]
        # Only add if not already present
        if font_family not in families:
            families.append(font_family)
            # No quotes for SVG attributes (attribute delimiter is sufficient)
            element.set("font-family", ", ".join(families))
        return  # Attribute has priority, don't check style

    # Check style attribute for font-family
    style = element.get("style")
    if style and "font-family:" in style:

        def replace_font_family(match: re.Match[str]) -> str:
            font_family_value = match.group(1).strip()
            # Parse existing font families
            families = [f.strip().strip("'\"") for f in font_family_value.split(",")]
            # Only add if not already present
            if font_family not in families:
                families.append(font_family)
            # Quote all families for CSS compliance
            return "font-family: " + ", ".join(f"'{f}'" for f in families)

        # Replace font-family in style attribute
        updated_style = re.sub(r"font-family:\s*([^;]+)", replace_font_family, style)
        if updated_style != style:
            element.set("style", updated_style)
        return

    # No font-family found, create new attribute
    element.set("font-family", font_family)


def insert_or_update_style_element(svg: ET.Element, css_content: str) -> None:
    """Insert or update a <style> element in the SVG root.

    Args:
        svg: SVG root element to modify.
        css_content: CSS content to insert or append.

    Note:
        - If a <style> element exists as first child, appends to it
        - Otherwise creates a new <style> element as first child
        - Idempotent: skips if CSS content already present
    """
    # Find existing <style> element (check first child only)
    style_element = None
    if len(svg) > 0:
        first_child = svg[0]
        # Check if it's a style element (handle namespaced tags)
        tag = first_child.tag
        local_name = tag.split("}")[-1] if "}" in tag else tag
        if local_name == "style":
            style_element = first_child

    if style_element is not None:
        # Update existing style element
        existing_text = style_element.text or ""
        # Check if our fonts are already embedded (idempotent check)
        if css_content in existing_text:
            logger.debug("CSS content already present, skipping")
            return
        # Append to existing styles
        style_element.text = existing_text + "\n" + css_content
    else:
        # Create new style element as first child
        style_element = ET.Element("style")
        style_element.text = css_content
        svg.insert(0, style_element)
