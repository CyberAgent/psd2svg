"""Tests for SVG utility functions."""

import xml.etree.ElementTree as ET

import pytest

from psd2svg import svg_utils


class TestNum2Str:
    """Test the num2str function for number formatting."""

    def test_boolean_true(self) -> None:
        """Test that boolean True converts to 'true'."""
        assert svg_utils.num2str(True) == "true"

    def test_boolean_false(self) -> None:
        """Test that boolean False converts to 'false'."""
        assert svg_utils.num2str(False) == "false"

    def test_integer(self) -> None:
        """Test that integers are converted to strings."""
        assert svg_utils.num2str(42) == "42"
        assert svg_utils.num2str(0) == "0"
        assert svg_utils.num2str(-100) == "-100"

    def test_integer_like_float(self) -> None:
        """Test that floats with integer values are formatted as integers."""
        assert svg_utils.num2str(1.0) == "1"
        assert svg_utils.num2str(100.0) == "100"
        assert svg_utils.num2str(-5.0) == "-5"

    def test_float_default_precision(self) -> None:
        """Test float formatting with default precision (2 digits)."""
        assert svg_utils.num2str(0.5) == "0.5"
        assert svg_utils.num2str(0.12) == "0.12"
        assert svg_utils.num2str(0.123) == "0.12"  # Rounded to 2 digits

    def test_float_trailing_zeros_removed(self) -> None:
        """Test that trailing zeros are removed."""
        assert svg_utils.num2str(0.10) == "0.1"
        assert svg_utils.num2str(1.50) == "1.5"
        assert svg_utils.num2str(0.100) == "0.1"

    def test_float_custom_precision(self) -> None:
        """Test float formatting with custom digit precision."""
        assert svg_utils.num2str(0.123456, digit=4) == "0.1235"  # Rounded
        assert svg_utils.num2str(0.123456, digit=6) == "0.123456"
        assert svg_utils.num2str(0.123456, digit=1) == "0.1"

    def test_no_scientific_notation_very_small(self) -> None:
        """Test that very small numbers don't use scientific notation."""
        # These would be 1e-05, 1e-06, etc. with 'g' format
        assert svg_utils.num2str(0.00001, digit=5) == "0.00001"
        assert svg_utils.num2str(0.000001, digit=6) == "0.000001"
        assert svg_utils.num2str(0.0000001, digit=7) == "0.0000001"

    def test_no_scientific_notation_very_large(self) -> None:
        """Test that large numbers don't use scientific notation."""
        assert svg_utils.num2str(1000000.0, digit=2) == "1000000"
        assert svg_utils.num2str(999999.99, digit=2) == "999999.99"
        assert svg_utils.num2str(123456.789, digit=3) == "123456.789"

    def test_negative_numbers(self) -> None:
        """Test formatting of negative numbers."""
        assert svg_utils.num2str(-0.5) == "-0.5"
        assert svg_utils.num2str(-0.123, digit=2) == "-0.12"
        assert svg_utils.num2str(-1.0) == "-1"

    def test_zero_variations(self) -> None:
        """Test various representations of zero."""
        assert svg_utils.num2str(0) == "0"
        assert svg_utils.num2str(0.0) == "0"
        assert svg_utils.num2str(-0.0) == "0"
        assert svg_utils.num2str(0.00, digit=4) == "0"

    def test_sign_preservation_on_small_negative(self) -> None:
        """Test that negative sign is preserved, even for very small values."""
        result = svg_utils.num2str(-0.00001, digit=5)
        assert result == "-0.00001"
        assert result[0] == "-"

    def test_rounding_behavior(self) -> None:
        """Test that rounding works correctly at boundaries."""
        assert svg_utils.num2str(0.125, digit=2) == "0.12"  # Rounds down
        assert svg_utils.num2str(0.126, digit=2) == "0.13"  # Rounds up
        assert svg_utils.num2str(0.995, digit=2) == "0.99"  # Truncated at 2 digits
        assert svg_utils.num2str(0.999, digit=2) == "1"  # Rounds to integer

    def test_invalid_type_raises_error(self) -> None:
        """Test that unsupported types raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported type"):
            svg_utils.num2str("string")  # type: ignore
        with pytest.raises(ValueError, match="Unsupported type"):
            svg_utils.num2str([1, 2, 3])  # type: ignore


class TestSeq2Str:
    """Test the seq2str function for sequence formatting."""

    def test_empty_sequence(self) -> None:
        """Test that empty sequences produce empty strings."""
        assert svg_utils.seq2str([]) == ""

    def test_single_element(self) -> None:
        """Test formatting of single-element sequences."""
        assert svg_utils.seq2str([42]) == "42"
        assert svg_utils.seq2str([0.5]) == "0.5"
        assert svg_utils.seq2str([True]) == "true"

    def test_multiple_integers(self) -> None:
        """Test formatting of integer sequences."""
        assert svg_utils.seq2str([1, 2, 3]) == "1,2,3"
        assert svg_utils.seq2str([10, 20, 30, 40]) == "10,20,30,40"

    def test_multiple_floats(self) -> None:
        """Test formatting of float sequences."""
        assert svg_utils.seq2str([0.5, 1.5, 2.5]) == "0.5,1.5,2.5"
        assert svg_utils.seq2str([0.1, 0.2, 0.3]) == "0.1,0.2,0.3"

    def test_mixed_types(self) -> None:
        """Test formatting of sequences with mixed types."""
        assert svg_utils.seq2str([1, 0.5, 2]) == "1,0.5,2"
        assert svg_utils.seq2str([True, 0, 1.0]) == "true,0,1"

    def test_custom_separator(self) -> None:
        """Test formatting with custom separators."""
        assert svg_utils.seq2str([1, 2, 3], sep=" ") == "1 2 3"
        assert svg_utils.seq2str([0.5, 1.5], sep=";") == "0.5;1.5"
        assert svg_utils.seq2str([10, 20], sep=" , ") == "10 , 20"

    def test_custom_precision(self) -> None:
        """Test formatting with custom digit precision."""
        assert svg_utils.seq2str([0.123456, 0.789012], digit=4) == "0.1235,0.789"
        assert svg_utils.seq2str([0.1, 0.2, 0.3], digit=3) == "0.1,0.2,0.3"

    def test_custom_separator_and_precision(self) -> None:
        """Test formatting with both custom separator and precision."""
        assert svg_utils.seq2str([0.123, 0.456], sep=" ", digit=2) == "0.12 0.46"
        assert (
            svg_utils.seq2str([1.111, 2.222, 3.333], sep=",", digit=1) == "1.1,2.2,3.3"
        )

    def test_no_scientific_notation_in_sequence(self) -> None:
        """Test that no element in sequence uses scientific notation."""
        result = svg_utils.seq2str([0.00001, 0.00002, 0.00003], digit=5)
        assert result == "0.00001,0.00002,0.00003"
        assert "e" not in result.lower()  # No exponential notation

    def test_trailing_zeros_removed_in_sequence(self) -> None:
        """Test that trailing zeros are removed in sequences."""
        assert svg_utils.seq2str([1.0, 2.0, 3.0]) == "1,2,3"
        assert svg_utils.seq2str([0.10, 0.20, 0.30]) == "0.1,0.2,0.3"

    def test_matrix_transform_values(self) -> None:
        """Test formatting typical SVG matrix transform values."""
        # Typical matrix transform: a, b, c, d, e, f
        matrix = [1.0, 0.0, 0.0, 1.0, 100.5, 200.75]
        assert svg_utils.seq2str(matrix, sep=" ", digit=4) == "1 0 0 1 100.5 200.75"

    def test_coordinate_pairs(self) -> None:
        """Test formatting coordinate pairs as used in SVG."""
        coords = [10.5, 20.75, 30.25, 40.125]
        assert svg_utils.seq2str(coords, sep=" ", digit=3) == "10.5 20.75 30.25 40.125"

    def test_tuple_input(self) -> None:
        """Test that tuples work as well as lists."""
        assert svg_utils.seq2str((1, 2, 3)) == "1,2,3"
        assert svg_utils.seq2str((0.5, 1.5), sep=" ") == "0.5 1.5"


class TestSvgFormatting:
    """Integration tests for SVG-specific formatting scenarios."""

    def test_transform_translate(self) -> None:
        """Test formatting for SVG translate transform."""
        # translate(x, y)
        coords = (100.5, 200.75)
        assert svg_utils.seq2str(coords, sep=" ", digit=4) == "100.5 200.75"

    def test_transform_scale(self) -> None:
        """Test formatting for SVG scale transform."""
        # scale(sx, sy) - common case for gradient transforms
        scale = [0.5, 1.0]
        assert svg_utils.seq2str(scale, sep=" ", digit=4) == "0.5 1"

    def test_transform_matrix(self) -> None:
        """Test formatting for SVG matrix transform."""
        # matrix(a b c d e f)
        matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        result = svg_utils.seq2str(matrix, sep=" ", digit=4)
        assert result == "1 0 0 1 0 0"
        # Ensure no scientific notation
        assert "e" not in result.lower()

    def test_opacity_values(self) -> None:
        """Test formatting for SVG opacity values."""
        # Opacity should be between 0 and 1
        assert svg_utils.num2str(0.5) == "0.5"
        assert svg_utils.num2str(0.75) == "0.75"
        assert svg_utils.num2str(1.0) == "1"
        assert svg_utils.num2str(0.0) == "0"

    def test_gradient_transform_with_very_small_scale(self) -> None:
        """Test that very small scale values don't produce scientific notation."""
        # This was the original bug - small values producing 1e-05
        small_scale = 0.00001
        result = svg_utils.num2str(small_scale, digit=5)
        assert result == "0.00001"
        assert "e" not in result.lower()
        assert "E" not in result

    def test_reference_point_coordinates(self) -> None:
        """Test formatting reference points for gradient transforms."""
        reference = (0.5, 0.5)
        assert svg_utils.seq2str(reference, sep=" ", digit=4) == "0.5 0.5"

        negative_reference = (-100.5, -200.75)
        assert (
            svg_utils.seq2str(negative_reference, sep=" ", digit=4) == "-100.5 -200.75"
        )


class TestMergeAttributeLessChildren:
    """Test the merge_attribute_less_children function."""

    def test_simple_attribute_less_children(self) -> None:
        """Test merging simple children without attributes."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan")
        tspan1.text = "Hello"
        tspan2 = ET.SubElement(text, "tspan")  # No attributes
        tspan2.text = " World"

        svg_utils.merge_attribute_less_children(text)

        # Both tspans should be merged into parent text
        assert len(text) == 0
        assert text.text == "Hello World"

    def test_preserve_order_with_styled_elements(self) -> None:
        """Test that text order is preserved when merging around styled elements."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"font-weight": "700"})
        tspan1.text = "Bold"
        tspan2 = ET.SubElement(text, "tspan")  # No attributes
        tspan2.text = " Regular"

        svg_utils.merge_attribute_less_children(text)

        # Should have one child (the bold tspan) with text after it
        assert len(text) == 1
        assert text[0].attrib.get("font-weight") == "700"
        assert text[0].text == "Bold"
        assert text[0].tail == " Regular"

    def test_nested_attribute_less_children(self) -> None:
        """Test merging nested children without attributes."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"x": "10"})
        tspan2 = ET.SubElement(tspan1, "tspan")  # No attributes, nested
        tspan2.text = "Nested text"

        svg_utils.merge_attribute_less_children(text)

        # Nested tspan should be merged into parent tspan
        assert len(text) == 1
        assert text[0].attrib.get("x") == "10"
        assert len(text[0]) == 0  # No children
        assert text[0].text == "Nested text"

    def test_multiple_attribute_less_between_styled(self) -> None:
        """Test multiple attribute-less children between styled elements."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"font-weight": "700"})
        tspan1.text = "Bold"
        tspan2 = ET.SubElement(text, "tspan")  # No attributes
        tspan2.text = " and "
        tspan3 = ET.SubElement(text, "tspan", attrib={"font-style": "italic"})
        tspan3.text = "italic"

        svg_utils.merge_attribute_less_children(text)

        # Should have two children (bold and italic) with text between them
        assert len(text) == 2
        assert text[0].attrib.get("font-weight") == "700"
        assert text[0].text == "Bold"
        assert text[0].tail == " and "
        assert text[1].attrib.get("font-style") == "italic"
        assert text[1].text == "italic"

    def test_all_children_have_attributes(self) -> None:
        """Test that nothing changes when all children have attributes."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"font-weight": "700"})
        tspan1.text = "Bold"
        tspan2 = ET.SubElement(text, "tspan", attrib={"font-style": "italic"})
        tspan2.text = "Italic"

        svg_utils.merge_attribute_less_children(text)

        # Nothing should change
        assert len(text) == 2
        assert text[0].attrib.get("font-weight") == "700"
        assert text[0].text == "Bold"
        assert text[1].attrib.get("font-style") == "italic"
        assert text[1].text == "Italic"

    def test_first_child_without_attributes(self) -> None:
        """Test merging when first child has no attributes."""

        text = ET.Element("text")
        text.text = "Start "
        tspan1 = ET.SubElement(text, "tspan")  # No attributes
        tspan1.text = "Middle"
        tspan2 = ET.SubElement(text, "tspan", attrib={"font-weight": "700"})
        tspan2.text = "End"

        svg_utils.merge_attribute_less_children(text)

        # First tspan should merge into parent text
        assert len(text) == 1
        assert text.text == "Start Middle"
        assert text[0].attrib.get("font-weight") == "700"
        assert text[0].text == "End"

    def test_tail_handling(self) -> None:
        """Test that tail text is properly preserved."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"font-weight": "700"})
        tspan1.text = "Bold"
        tspan2 = ET.SubElement(text, "tspan")  # No attributes
        tspan2.text = "Regular"
        tspan2.tail = " after"

        svg_utils.merge_attribute_less_children(text)

        # The tail should be preserved
        assert len(text) == 1
        assert text[0].tail == "Regular after"

    def test_empty_attribute_less_children(self) -> None:
        """Test merging children with no text content."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"x": "10"})
        tspan1.text = "Text"
        ET.SubElement(text, "tspan")  # No attributes, no text - will be removed
        tspan3 = ET.SubElement(text, "tspan", attrib={"y": "20"})
        tspan3.text = "More"

        svg_utils.merge_attribute_less_children(text)

        # Empty tspan should be removed
        assert len(text) == 2
        assert text[0].attrib.get("x") == "10"
        assert text[1].attrib.get("y") == "20"

    def test_deeply_nested_structure(self) -> None:
        """Test merging in deeply nested structures."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"x": "10"})
        tspan2 = ET.SubElement(tspan1, "tspan", attrib={"font-weight": "700"})
        tspan3 = ET.SubElement(tspan2, "tspan")  # No attributes
        tspan3.text = "Deep text"

        svg_utils.merge_attribute_less_children(text)

        # Should recursively merge from innermost to outermost
        assert len(text) == 1
        assert len(text[0]) == 1
        assert len(text[0][0]) == 0
        assert text[0][0].text == "Deep text"

    def test_complex_real_world_scenario(self) -> None:
        """Test a complex real-world SVG text structure."""

        # Simulate: <text>First <tspan font-weight="700">bold</tspan> then
        # <tspan>normal</tspan> end</text>
        text = ET.Element("text")
        text.text = "First "
        tspan1 = ET.SubElement(text, "tspan", attrib={"font-weight": "700"})
        tspan1.text = "bold"
        tspan1.tail = " then "
        tspan2 = ET.SubElement(text, "tspan")  # No attributes
        tspan2.text = "normal"
        tspan2.tail = " end"

        svg_utils.merge_attribute_less_children(text)

        # tspan2 should be merged, preserving all text
        assert len(text) == 1
        assert text.text == "First "
        assert text[0].text == "bold"
        assert text[0].tail == " then normal end"

    def test_attribute_less_child_with_nested_children(self) -> None:
        """Test that attribute-less children with nested elements are unwrapped.

        This is a regression test for a bug where attribute-less children
        would be merged even if they contained nested elements, causing
        those nested elements to be lost.

        Now it unwraps them: moves the nested children up to the parent level.
        """
        # Create: <text><tspan><tspan font-size="18">A</tspan><tspan
        # font-size="20">B</tspan></tspan></text>
        text = ET.Element("text")
        outer_tspan = ET.SubElement(text, "tspan")  # No attributes

        inner1 = ET.SubElement(outer_tspan, "tspan", attrib={"font-size": "18"})
        inner1.text = "A"

        inner2 = ET.SubElement(outer_tspan, "tspan", attrib={"font-size": "20"})
        inner2.text = "B"

        svg_utils.merge_attribute_less_children(text)

        # outer_tspan should be unwrapped - its children moved up to text
        assert len(text) == 2
        assert text[0].attrib.get("font-size") == "18"
        assert text[0].text == "A"
        assert text[1].attrib.get("font-size") == "20"
        assert text[1].text == "B"

    def test_mixed_attribute_less_with_nested(self) -> None:
        """Test mixed scenario: attribute-less children with nested elements."""
        # <text><tspan font-weight="700">Bold</tspan><tspan><tspan
        # font-size="18">Nested</tspan></tspan></text>
        text = ET.Element("text")

        tspan1 = ET.SubElement(text, "tspan", attrib={"font-weight": "700"})
        tspan1.text = "Bold"

        tspan2 = ET.SubElement(text, "tspan")  # No attributes
        inner = ET.SubElement(tspan2, "tspan", attrib={"font-size": "18"})
        inner.text = "Nested"

        svg_utils.merge_attribute_less_children(text)

        # tspan2 should be unwrapped - inner moved up to text level
        assert len(text) == 2
        assert text[0].text == "Bold"
        assert text[1].attrib.get("font-size") == "18"
        assert text[1].text == "Nested"


class TestMergeCommonChildAttributes:
    """Tests for merge_common_child_attributes utility function."""

    def test_simple_common_attributes(self) -> None:
        """Test merging common attributes from all children."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"fill": "red", "font-size": "12"})
        tspan1.text = "A"
        tspan2 = ET.SubElement(text, "tspan", attrib={"fill": "red", "font-size": "12"})
        tspan2.text = "B"

        svg_utils.merge_common_child_attributes(text)

        # Common attributes should be hoisted to parent
        assert text.attrib.get("fill") == "red"
        assert text.attrib.get("font-size") == "12"
        # Children should have attributes removed
        assert "fill" not in tspan1.attrib
        assert "font-size" not in tspan1.attrib
        assert "fill" not in tspan2.attrib
        assert "font-size" not in tspan2.attrib

    def test_partial_common_attributes(self) -> None:
        """Test that only truly common attributes are hoisted."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"fill": "red", "font-size": "12"})
        tspan1.text = "A"
        tspan2 = ET.SubElement(text, "tspan", attrib={"fill": "red", "font-size": "14"})
        tspan2.text = "B"

        svg_utils.merge_common_child_attributes(text)

        # Only fill is common, font-size differs
        assert text.attrib.get("fill") == "red"
        assert "font-size" not in text.attrib
        # Children should keep differing attributes
        assert "fill" not in tspan1.attrib
        assert tspan1.attrib.get("font-size") == "12"
        assert "fill" not in tspan2.attrib
        assert tspan2.attrib.get("font-size") == "14"

    def test_no_common_attributes(self) -> None:
        """Test when no attributes are common."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"fill": "red"})
        tspan1.text = "A"
        tspan2 = ET.SubElement(text, "tspan", attrib={"font-size": "12"})
        tspan2.text = "B"

        svg_utils.merge_common_child_attributes(text)

        # No common attributes, parent should be unchanged
        assert "fill" not in text.attrib
        assert "font-size" not in text.attrib
        # Children should keep their attributes
        assert tspan1.attrib.get("fill") == "red"
        assert tspan2.attrib.get("font-size") == "12"

    def test_excludes_parameter(self) -> None:
        """Test that excluded attributes are not hoisted."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(
            text, "tspan", attrib={"x": "10", "y": "20", "fill": "red"}
        )
        tspan1.text = "A"
        tspan2 = ET.SubElement(
            text, "tspan", attrib={"x": "30", "y": "20", "fill": "red"}
        )
        tspan2.text = "B"

        svg_utils.merge_common_child_attributes(text, excludes={"x", "y"})

        # fill should be hoisted, x and y should not
        assert text.attrib.get("fill") == "red"
        assert "x" not in text.attrib
        assert "y" not in text.attrib
        # Children should keep excluded attributes
        assert tspan1.attrib.get("x") == "10"
        assert tspan1.attrib.get("y") == "20"
        assert tspan2.attrib.get("x") == "30"
        assert tspan2.attrib.get("y") == "20"
        assert "fill" not in tspan1.attrib
        assert "fill" not in tspan2.attrib

    def test_recursive_processing(self) -> None:
        """Test that function processes nested children recursively."""

        text = ET.Element("text")
        g1 = ET.SubElement(text, "g")
        tspan1 = ET.SubElement(g1, "tspan", attrib={"fill": "red"})
        tspan1.text = "A"
        tspan2 = ET.SubElement(g1, "tspan", attrib={"fill": "red"})
        tspan2.text = "B"
        g2 = ET.SubElement(text, "g")
        tspan3 = ET.SubElement(g2, "tspan", attrib={"fill": "red"})
        tspan3.text = "C"

        svg_utils.merge_common_child_attributes(text)

        # Common attribute should be hoisted all the way to text
        # since all nested tspans have fill="red"
        assert text.attrib.get("fill") == "red"
        assert "fill" not in g1.attrib
        assert "fill" not in g2.attrib
        assert "fill" not in tspan1.attrib
        assert "fill" not in tspan2.attrib
        assert "fill" not in tspan3.attrib

    def test_empty_element(self) -> None:
        """Test with element that has no children."""

        text = ET.Element("text")
        text.text = "No children"

        # Should not raise an error
        svg_utils.merge_common_child_attributes(text)

        assert text.text == "No children"
        assert len(text.attrib) == 0

    def test_single_child(self) -> None:
        """Test with element that has only one child."""

        text = ET.Element("text")
        tspan = ET.SubElement(text, "tspan", attrib={"fill": "red"})
        tspan.text = "Only child"

        svg_utils.merge_common_child_attributes(text)

        # Single child's attributes should be hoisted
        assert text.attrib.get("fill") == "red"
        assert "fill" not in tspan.attrib


class TestMergeConsecutiveSiblings:
    """Tests for merge_consecutive_siblings utility function."""

    def test_merge_identical_consecutive_tspans(self) -> None:
        """Test merging consecutive tspans with identical attributes."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(
            text, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan1.text = "す"
        tspan2 = ET.SubElement(
            text, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan2.text = "だ"
        tspan3 = ET.SubElement(
            text, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan3.text = "け"

        svg_utils.merge_consecutive_siblings(text)

        # Should merge into single tspan
        assert len(text) == 1
        assert text[0].text == "すだけ"
        assert text[0].attrib["font-size"] == "18"
        assert text[0].attrib["letter-spacing"] == "0.72"

    def test_merge_stops_at_different_attributes(self) -> None:
        """Test that merging stops when attributes differ."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(
            text,
            "tspan",
            attrib={
                "font-size": "18",
                "baseline-shift": "-0.36",
                "letter-spacing": "0.72",
            },
        )
        tspan1.text = "さ"
        tspan2 = ET.SubElement(
            text, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan2.text = "す"
        tspan3 = ET.SubElement(
            text, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan3.text = "だ"
        tspan4 = ET.SubElement(
            text,
            "tspan",
            attrib={
                "font-size": "20.85",
                "baseline-shift": "-0.36",
                "letter-spacing": "0.83",
            },
        )
        tspan4.text = "！"

        svg_utils.merge_consecutive_siblings(text)

        # Should have 3 tspans: "さ", "すだ", "！"
        assert len(text) == 3
        assert text[0].text == "さ"
        assert text[0].attrib["baseline-shift"] == "-0.36"
        assert text[1].text == "すだ"
        assert "baseline-shift" not in text[1].attrib
        assert text[2].text == "！"
        assert text[2].attrib["font-size"] == "20.85"

    def test_merge_removes_empty_tspans(self) -> None:
        """Test that empty tspans (no text or tail) are removed."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(
            text, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan1.text = "text"
        tspan2 = ET.SubElement(
            text, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan2.text = None  # Empty
        tspan3 = ET.SubElement(
            text, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan3.text = None  # Empty

        svg_utils.merge_consecutive_siblings(text)

        # All should merge, and since only first has text, result is just "text"
        assert len(text) == 1
        assert text[0].text == "text"

    def test_merge_preserves_tail(self) -> None:
        """Test that the tail of the last element is preserved."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"font-size": "18"})
        tspan1.text = "A"
        tspan2 = ET.SubElement(text, "tspan", attrib={"font-size": "18"})
        tspan2.text = "B"
        tspan2.tail = " after"

        svg_utils.merge_consecutive_siblings(text)

        # Should merge and preserve tail
        assert len(text) == 1
        assert text[0].text == "AB"
        assert text[0].tail == " after"

    def test_no_merge_with_children(self) -> None:
        """Test that elements with children are not merged."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"font-size": "18"})
        tspan1.text = "A"
        tspan2 = ET.SubElement(text, "tspan", attrib={"font-size": "18"})
        # tspan2 has a child
        child = ET.SubElement(tspan2, "tspan")
        child.text = "B"
        tspan3 = ET.SubElement(text, "tspan", attrib={"font-size": "18"})
        tspan3.text = "C"

        svg_utils.merge_consecutive_siblings(text)

        # tspan1 should not merge with tspan2 (has children)
        # tspan2 should not merge with tspan3 (has children)
        assert len(text) == 3

    def test_merge_different_tags(self) -> None:
        """Test that elements with different tags are not merged."""

        g = ET.Element("g")
        ET.SubElement(g, "rect", attrib={"fill": "red"})
        ET.SubElement(g, "circle", attrib={"fill": "red"})
        ET.SubElement(g, "rect", attrib={"fill": "red"})

        svg_utils.merge_consecutive_siblings(g)

        # Different tags should not merge
        assert len(g) == 3

    def test_recursive_processing(self) -> None:
        """Test that function processes nested children recursively."""

        text = ET.Element("text")
        g = ET.SubElement(text, "g")
        tspan1 = ET.SubElement(g, "tspan", attrib={"fill": "red"})
        tspan1.text = "A"
        tspan2 = ET.SubElement(g, "tspan", attrib={"fill": "red"})
        tspan2.text = "B"

        svg_utils.merge_consecutive_siblings(text)

        # Should merge nested tspans
        assert len(text) == 1  # g
        assert len(g) == 1  # merged tspan
        assert g[0].text == "AB"

    def test_empty_element(self) -> None:
        """Test with element that has no children."""

        text = ET.Element("text")
        text.text = "No children"

        # Should not raise an error
        svg_utils.merge_consecutive_siblings(text)

        assert text.text == "No children"
        assert len(text) == 0

    def test_single_child(self) -> None:
        """Test with element that has only one child."""

        text = ET.Element("text")
        tspan = ET.SubElement(text, "tspan", attrib={"fill": "red"})
        tspan.text = "Only child"

        svg_utils.merge_consecutive_siblings(text)

        # Single child should not be modified
        assert len(text) == 1
        assert text[0].text == "Only child"


class TestMergeOffsetSiblings:
    """Tests for merge_offset_siblings utility function."""

    def test_merge_dx_into_list(self) -> None:
        """Consecutive tspans differing only in dx merge into a dx list."""
        text = ET.fromstring(
            '<text><tspan>a</tspan><tspan dx="0.1">b</tspan><tspan>c</tspan></text>'
        )

        svg_utils.merge_offset_siblings(text)

        assert len(text) == 1
        assert text[0].text == "abc"
        # Trailing zero for 'c' is trimmed (dx defaults to 0 past the list end).
        assert text[0].attrib["dx"] == "0 0.1"

    def test_merge_dy_into_list(self) -> None:
        """dy offsets are merged the same way as dx."""
        text = ET.fromstring(
            '<text><tspan>a</tspan><tspan dy="2">b</tspan>'
            '<tspan dy="3">c</tspan></text>'
        )

        svg_utils.merge_offset_siblings(text)

        assert len(text) == 1
        assert text[0].text == "abc"
        assert text[0].attrib["dy"] == "0 2 3"

    def test_multi_character_spans(self) -> None:
        """A dx applies only to the first char of a multi-character span."""
        text = ET.fromstring('<text><tspan>ab</tspan><tspan dx="-1">cd</tspan></text>')

        svg_utils.merge_offset_siblings(text)

        assert len(text) == 1
        assert text[0].text == "abcd"
        # Chars: a=0, b=0, c=-1, d=0(trimmed) -> "0 0 -1".
        assert text[0].attrib["dx"] == "0 0 -1"

    def test_first_span_keeps_absolute_position(self) -> None:
        """x/y on the first char and dx on the rest merge together."""
        text = ET.fromstring(
            '<text><tspan x="10" y="20">L</tspan>'
            '<tspan dx="-0.8">o</tspan><tspan dx="-3.2">r</tspan></text>'
        )

        svg_utils.merge_offset_siblings(text)

        assert len(text) == 1
        merged = text[0]
        assert merged.text == "Lor"
        assert merged.attrib["x"] == "10"
        assert merged.attrib["y"] == "20"
        assert merged.attrib["dx"] == "0 -0.8 -3.2"

    def test_no_merge_on_absolute_gap(self) -> None:
        """An internal unset x cannot be expressed as a list, so no merge."""
        text = ET.fromstring(
            '<text><tspan x="10">ab</tspan><tspan x="50">c</tspan></text>'
        )

        svg_utils.merge_offset_siblings(text)

        # 'b' would need an unset (natural-advance) x between the two set
        # values, which an SVG coordinate list cannot express.
        assert len(text) == 2

    def test_no_merge_different_style(self) -> None:
        """Spans differing in a non-positional attribute are not merged."""
        text = ET.fromstring(
            '<text><tspan fill="red" dx="1">a</tspan>'
            '<tspan fill="blue" dx="2">b</tspan></text>'
        )

        svg_utils.merge_offset_siblings(text)

        assert len(text) == 2

    def test_all_zero_dx_omitted(self) -> None:
        """Merging identical spans produces no positional attribute."""
        text = ET.fromstring("<text><tspan>a</tspan><tspan>b</tspan></text>")

        svg_utils.merge_offset_siblings(text)

        assert len(text) == 1
        assert text[0].text == "ab"
        assert "dx" not in text[0].attrib
        assert "dy" not in text[0].attrib

    def test_empty_span_with_offset_blocks_merge(self) -> None:
        """An empty span carrying a positional attribute is ambiguous."""
        text = ET.fromstring(
            '<text><tspan>a</tspan><tspan dx="1" /><tspan>b</tspan></text>'
        )

        svg_utils.merge_offset_siblings(text)

        # The empty span hosts no character, so the group cannot be merged.
        assert len(text) == 3

    def test_empty_span_without_offset_dropped(self) -> None:
        """An empty span without a positional attribute is merged away."""
        text = ET.fromstring(
            '<text><tspan dx="1">a</tspan><tspan /><tspan>b</tspan></text>'
        )

        svg_utils.merge_offset_siblings(text)

        assert len(text) == 1
        assert text[0].text == "ab"
        assert text[0].attrib["dx"] == "1"

    def test_combining_marks_block_merge(self) -> None:
        """Combining marks make len(text) diverge from addressable chars."""
        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan")
        # 'e' + U+0301 COMBINING ACUTE ACCENT: two code points, one glyph.
        tspan1.text = "e\u0301"
        tspan2 = ET.SubElement(text, "tspan", attrib={"dx": "1"})
        tspan2.text = "a"

        svg_utils.merge_offset_siblings(text)

        assert len(text) == 2

    def test_no_merge_across_tail(self) -> None:
        """A non-empty tail on a non-last member stops the run."""
        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan", attrib={"dx": "1"})
        tspan1.text = "a"
        tspan1.tail = " gap"
        tspan2 = ET.SubElement(text, "tspan", attrib={"dx": "2"})
        tspan2.text = "b"

        svg_utils.merge_offset_siblings(text)

        # The tail between them is real content, so they are not merged.
        assert len(text) == 2
        assert text[0].tail == " gap"

    def test_recursive_processing(self) -> None:
        """Nested children are processed recursively."""
        text = ET.fromstring(
            '<text><tspan x="1" dy="2"><tspan>L</tspan>'
            '<tspan dx="-1">o</tspan></tspan></text>'
        )

        svg_utils.merge_offset_siblings(text)

        paragraph = text[0]
        assert len(paragraph) == 1
        assert paragraph[0].text == "Lo"
        assert paragraph[0].attrib["dx"] == "0 -1"
        # The paragraph wrapper's own position is untouched.
        assert paragraph.attrib["x"] == "1"
        assert paragraph.attrib["dy"] == "2"


class TestMergeSingletonChildren:
    """Tests for merge_singleton_children utility function."""

    def test_simple_singleton_merge(self) -> None:
        """Test merging a simple singleton child."""

        text = ET.Element("text")
        tspan = ET.SubElement(text, "tspan")
        tspan.text = "Hello"

        svg_utils.merge_singleton_children(text)

        # Singleton child should be merged into parent
        assert len(text) == 0
        assert text.text == "Hello"

    def test_singleton_with_attributes(self) -> None:
        """Test merging singleton child with attributes."""

        text = ET.Element("text", attrib={"x": "10"})
        tspan = ET.SubElement(text, "tspan", attrib={"font-weight": "700"})
        tspan.text = "Bold"

        svg_utils.merge_singleton_children(text)

        # Child's attributes should be moved to parent
        assert len(text) == 0
        assert text.text == "Bold"
        assert text.attrib.get("x") == "10"
        assert text.attrib.get("font-weight") == "700"

    def test_conflicting_attributes_no_merge(self) -> None:
        """Test that singleton with conflicting attributes is not merged."""

        text = ET.Element("text", attrib={"x": "10"})
        tspan = ET.SubElement(text, "tspan", attrib={"x": "20"})
        tspan.text = "Text"

        svg_utils.merge_singleton_children(text)

        # Should not merge due to conflicting 'x' attribute
        assert len(text) == 1
        assert text[0] is tspan
        assert text.attrib.get("x") == "10"
        assert tspan.attrib.get("x") == "20"

    def test_singleton_with_tail(self) -> None:
        """Test that singleton's tail is properly handled."""

        # Create: <g><text>Hello</text> World</g>
        g = ET.Element("g")
        text = ET.SubElement(g, "text")
        text.text = "Hello"
        text.tail = " World"

        svg_utils.merge_singleton_children(g)

        # The tail should become part of parent's text
        assert len(g) == 0
        assert g.text == "Hello World"

    def test_multiple_children_no_merge(self) -> None:
        """Test that element with multiple children is not merged."""

        text = ET.Element("text")
        tspan1 = ET.SubElement(text, "tspan")
        tspan1.text = "A"
        tspan2 = ET.SubElement(text, "tspan")
        tspan2.text = "B"

        svg_utils.merge_singleton_children(text)

        # Should not merge, still has two children
        assert len(text) == 2
        assert text[0] is tspan1
        assert text[1] is tspan2

    def test_recursive_processing(self) -> None:
        """Test that function processes nested singletons recursively."""

        # Create: <text><g><tspan>Hello</tspan></g></text>
        text = ET.Element("text")
        g = ET.SubElement(text, "g")
        tspan = ET.SubElement(g, "tspan")
        tspan.text = "Hello"

        svg_utils.merge_singleton_children(text)

        # Should merge both levels: tspan into g, then g into text
        assert len(text) == 0
        assert text.text == "Hello"

    def test_parent_with_existing_text(self) -> None:
        """Test merging when parent already has text."""

        text = ET.Element("text")
        text.text = "Start "
        tspan = ET.SubElement(text, "tspan")
        tspan.text = "End"

        svg_utils.merge_singleton_children(text)

        # Child's text should be appended to parent's text
        assert len(text) == 0
        assert text.text == "Start End"

    def test_parent_with_text_and_child_with_tail(self) -> None:
        """Test complex case with both parent text and child tail."""

        # This is unusual but possible: <text>Before<tspan>Middle</tspan>After</text>
        text = ET.Element("text")
        text.text = "Before"
        tspan = ET.SubElement(text, "tspan")
        tspan.text = "Middle"
        tspan.tail = "After"

        svg_utils.merge_singleton_children(text)

        # All text should be merged in document order
        assert len(text) == 0
        assert text.text == "BeforeMiddleAfter"

    def test_empty_singleton_child(self) -> None:
        """Test merging an empty singleton child."""

        text = ET.Element("text")
        ET.SubElement(text, "tspan", attrib={"font-weight": "700"})
        # No text in tspan

        svg_utils.merge_singleton_children(text)

        # Empty child should still be merged, attributes moved
        assert len(text) == 0
        assert text.text is None
        assert text.attrib.get("font-weight") == "700"

    def test_multi_child_parent_with_nested_singletons(
        self,
    ) -> None:
        """Test parent with multiple children is not merged.

        Even when nested children are singletons. This is a regression test for
        a bug where recursive processing would merge nested singletons first,
        reducing the parent's child count and causing it to be incorrectly
        merged.
        """
        # Create structure: <text><tspan><tspan>A</tspan><tspan>B</tspan></tspan></text>
        # The outer tspan has 2 children initially, so it shouldn't be merged
        # But if we process recursively first, both inner tspans might disappear
        text = ET.Element(
            "text",
            attrib={
                "transform": "matrix(3.36,0,-0.68,3.35,253.68,244.16)",
                "font-family": "Kozuka Gothic Pr6N",
                "font-weight": "700",
                "fill": "#0000ff",
            },
        )
        outer_tspan = ET.SubElement(text, "tspan")

        # Add multiple inner tspans
        tspan1 = ET.SubElement(
            outer_tspan,
            "tspan",
            attrib={
                "font-size": "18",
                "baseline-shift": "-0.36",
                "letter-spacing": "0.72",
            },
        )
        tspan1.text = "さ"

        tspan2 = ET.SubElement(
            outer_tspan, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan2.text = "す"

        tspan3 = ET.SubElement(
            outer_tspan, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan3.text = "だ"

        tspan4 = ET.SubElement(
            outer_tspan, "tspan", attrib={"font-size": "18", "letter-spacing": "0.72"}
        )
        tspan4.text = "け"

        tspan5 = ET.SubElement(
            outer_tspan,
            "tspan",
            attrib={
                "font-size": "20.85",
                "baseline-shift": "-0.36",
                "letter-spacing": "0.83",
            },
        )
        tspan5.text = "！"

        ET.SubElement(
            outer_tspan,
            "tspan",
            attrib={
                "font-size": "20.85",
                "baseline-shift": "-0.36",
                "letter-spacing": "0.83",
            },
        )
        # Last tspan has no text (empty)

        svg_utils.merge_singleton_children(text)

        # The outer tspan wrapper should be unwrapped, moving its children
        # directly under text
        assert len(text) == 6  # Now has 6 direct children (the inner tspans)

        # The inner tspans should be direct children of text now
        assert text[0].text == "さ"
        assert text[1].text == "す"
        assert text[2].text == "だ"
        assert text[3].text == "け"
        assert text[4].text == "！"
        assert text[5].text is None  # Empty tspan

    def test_unwrap_singleton_with_nested_children(self) -> None:
        """Test that singleton wrappers without attributes are unwrapped."""
        # <text><tspan><tspan baseline-shift="-0.36">A</tspan><tspan
        # letter-spacing="0.72">B</tspan></tspan></text>
        text = ET.Element("text")
        outer_tspan = ET.SubElement(text, "tspan")  # No attributes, no text
        inner1 = ET.SubElement(outer_tspan, "tspan", attrib={"baseline-shift": "-0.36"})
        inner1.text = "A"
        inner2 = ET.SubElement(outer_tspan, "tspan", attrib={"letter-spacing": "0.72"})
        inner2.text = "B"

        svg_utils.merge_singleton_children(text)

        # outer_tspan should be unwrapped - its children moved up to text
        assert len(text) == 2
        assert text[0].attrib.get("baseline-shift") == "-0.36"
        assert text[0].text == "A"
        assert text[1].attrib.get("letter-spacing") == "0.72"
        assert text[1].text == "B"

    def test_unwrap_singleton_with_attributes(self) -> None:
        """Test that singleton wrappers with attributes are unwrapped.

        Attributes should be moved to parent.
        """
        # <text><tspan fill="red"><tspan>A</tspan><tspan>B</tspan></tspan></text>
        text = ET.Element("text")
        outer_tspan = ET.SubElement(text, "tspan", attrib={"fill": "red"})
        inner1 = ET.SubElement(outer_tspan, "tspan")
        inner1.text = "A"
        inner2 = ET.SubElement(outer_tspan, "tspan")
        inner2.text = "B"

        svg_utils.merge_singleton_children(text)

        # outer_tspan should be unwrapped, fill moved to text
        assert len(text) == 2
        assert text.attrib.get("fill") == "red"
        assert text[0].text == "A"
        assert text[1].text == "B"


class TestAddFontFamily:
    """Tests for add_font_family utility function.

    The add_font_family function adds a fallback font family to an element's
    font-family declaration if not already present. It's a general utility that
    handles various scenarios with consistent priority rules.
    """

    # Test cases for font-family attribute
    def test_add_fallback_to_single_font_attribute(self) -> None:
        """Test adding fallback font to single font-family attribute."""
        text = ET.Element("text", attrib={"font-family": "Arial"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        assert text.attrib.get("font-family") == "Arial, Helvetica"

    def test_add_fallback_to_quoted_font_family(self) -> None:
        """Test adding fallback when original font-family has single quotes."""
        text = ET.Element("text", attrib={"font-family": "'Arial'"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        assert text.attrib.get("font-family") == "Arial, Helvetica"

    def test_add_fallback_to_double_quoted_font_family(self) -> None:
        """Test adding fallback when original font-family has double quotes."""
        text = ET.Element("text", attrib={"font-family": '"Arial"'})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        assert text.attrib.get("font-family") == "Arial, Helvetica"

    def test_idempotent_does_not_add_duplicate_attribute(self) -> None:
        """Test that function is idempotent - doesn't add duplicate fallback."""
        text = ET.Element("text", attrib={"font-family": "Arial, Helvetica"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        # Should remain unchanged - Helvetica already present
        assert text.attrib.get("font-family") == "Arial, Helvetica"

    def test_add_second_fallback_to_chain(self) -> None:
        """Test adding a second fallback to existing fallback chain."""
        text = ET.Element("text", attrib={"font-family": "Arial, Helvetica"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "sans-serif")

        # Should append new fallback
        assert text.attrib.get("font-family") == "Arial, Helvetica, sans-serif"

    def test_unquoted_font_list_in_attribute(self) -> None:
        """Test handling unquoted font list in attribute."""
        text = ET.Element(
            "text", attrib={"font-family": "Arial, Helvetica, sans-serif"}
        )
        text.text = "Hello"

        svg_utils.add_font_family(text, "DejaVu Sans")

        # Should add DejaVu Sans if not present
        assert (
            text.attrib.get("font-family")
            == "Arial, Helvetica, sans-serif, DejaVu Sans"
        )

    # Test cases for style attribute
    def test_add_fallback_to_style_attribute(self) -> None:
        """Test adding fallback to font-family in style attribute."""
        text = ET.Element(
            "text", attrib={"style": "font-family: Arial; font-size: 12px"}
        )
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        style = text.attrib.get("style")
        assert style is not None
        assert "font-family: 'Arial', 'Helvetica'" in style
        assert "font-size: 12px" in style

    def test_add_fallback_to_style_with_quoted_font(self) -> None:
        """Test adding fallback to quoted font-family in style attribute."""
        text = ET.Element(
            "text", attrib={"style": "font-family: 'Arial'; font-size: 12px"}
        )
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        style = text.attrib.get("style")
        assert style is not None
        assert "font-family: 'Arial', 'Helvetica'" in style

    def test_idempotent_style_does_not_add_duplicate(self) -> None:
        """Test idempotent behavior in style attribute."""
        text = ET.Element(
            "text",
            attrib={"style": "font-family: 'Arial', 'Helvetica'; color: red"},
        )
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        style = text.attrib.get("style")
        assert style is not None
        # Should remain unchanged
        assert "font-family: 'Arial', 'Helvetica'" in style
        assert style.count("Helvetica") == 1

    def test_add_fallback_with_font_family_at_end_of_style(self) -> None:
        """Test adding fallback when font-family is at the end of style.

        No semicolon case.
        """
        text = ET.Element("text", attrib={"style": "color: red; font-family: Arial"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        style = text.attrib.get("style")
        assert style is not None
        assert "font-family: 'Arial', 'Helvetica'" in style
        assert "color: red" in style

    def test_add_fallback_with_spaces_in_style(self) -> None:
        """Test adding fallback with various whitespace in style."""
        text = ET.Element(
            "text", attrib={"style": "font-family:   Arial  ; font-size: 12px"}
        )
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        style = text.attrib.get("style")
        assert style is not None
        assert "font-family: 'Arial', 'Helvetica'" in style

    # Test priority: attribute > style
    def test_attribute_has_priority_over_style(self) -> None:
        """Test that font-family attribute has priority over style.

        When both attribute and style have font-family, the function should
        update the attribute and ignore the style (attribute has higher CSS priority).
        """
        text = ET.Element(
            "text",
            attrib={"font-family": "Arial", "style": "font-family: Times; color: red"},
        )
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        # Attribute should be updated
        assert text.attrib.get("font-family") == "Arial, Helvetica"
        # Style should remain unchanged
        style = text.attrib.get("style")
        assert style is not None
        assert "font-family: Times" in style
        assert "Helvetica" not in style

    # Test case: no font-family exists
    def test_create_font_family_attribute_when_none_exists(
        self,
    ) -> None:
        """Test creating font-family when element has no font."""
        text = ET.Element("text", attrib={"font-size": "12px"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        # Should create new font-family attribute
        assert text.attrib.get("font-family") == "Helvetica"
        assert text.attrib.get("font-size") == "12px"

    def test_create_font_family_when_style_has_no_font(self) -> None:
        """Test creating font-family attribute when style exists.

        But has no font-family.
        """
        text = ET.Element("text", attrib={"style": "color: red; font-size: 12px"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        # Should create font-family attribute (not add to style)
        assert text.attrib.get("font-family") == "Helvetica"
        # Style should remain unchanged
        style = text.attrib.get("style")
        assert style is not None
        assert style == "color: red; font-size: 12px"

    def test_empty_element_creates_font_family(self) -> None:
        """Test with element that has no attributes at all."""
        text = ET.Element("text")
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        # Should create font-family attribute
        assert text.attrib.get("font-family") == "Helvetica"

    # Test cases with various font names
    def test_add_fallback_tspan_element(self) -> None:
        """Test adding fallback to tspan element."""
        tspan = ET.Element("tspan", attrib={"font-family": "Kozuka Gothic Pr6N"})
        tspan.text = "日本語"

        svg_utils.add_font_family(tspan, "Noto Sans CJK JP")

        assert tspan.attrib.get("font-family") == "Kozuka Gothic Pr6N, Noto Sans CJK JP"

    def test_add_fallback_with_font_name_with_spaces(self) -> None:
        """Test adding fallback for font names containing spaces."""
        text = ET.Element("text", attrib={"font-family": "Times New Roman"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Liberation Serif")

        assert text.attrib.get("font-family") == "Times New Roman, Liberation Serif"

    def test_mixed_quoting_styles(self) -> None:
        """Test handling of mixed quoting styles in font list."""
        text = ET.Element(
            "text", attrib={"font-family": "'Arial', \"Times New Roman\", sans-serif"}
        )
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        # Should normalize quoting and add new font
        assert (
            text.attrib.get("font-family")
            == "Arial, Times New Roman, sans-serif, Helvetica"
        )

    def test_whitespace_handling_in_font_names(self) -> None:
        """Test proper handling of whitespace in font names."""
        text = ET.Element("text", attrib={"font-family": "  Arial  ,  Helvetica  "})
        text.text = "Hello"

        svg_utils.add_font_family(text, "DejaVu Sans")

        # Should trim whitespace and add new font
        font_family = text.attrib.get("font-family")
        assert font_family == "Arial, Helvetica, DejaVu Sans"

    # Test preservation of other properties
    def test_preserve_other_style_properties(self) -> None:
        """Test that other style properties are preserved.

        When updating font-family.
        """
        text = ET.Element(
            "text",
            attrib={
                "style": (
                    "font-family: Arial; font-size: 16px; "
                    "font-weight: bold; color: blue"
                )
            },
        )
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        style = text.attrib.get("style")
        assert style is not None
        assert "font-family: 'Arial', 'Helvetica'" in style
        assert "font-size: 16px" in style
        assert "font-weight: bold" in style
        assert "color: blue" in style

    def test_preserve_other_attributes(self) -> None:
        """Test that other attributes are preserved when updating font-family."""
        text = ET.Element(
            "text",
            attrib={
                "font-family": "Arial",
                "font-size": "12",
                "transform": "matrix(1,0,0,1,0,0)",
            },
        )
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        assert text.attrib.get("font-family") == "Arial, Helvetica"
        assert text.attrib.get("font-size") == "12"
        assert text.attrib.get("transform") == "matrix(1,0,0,1,0,0)"

    # Real-world scenarios
    def test_real_world_cjk_font_substitution(self) -> None:
        """Test real-world scenario: CJK font substitution.

        This mimics the actual use case where Kozuka Gothic gets substituted
        with Noto Sans CJK when the original font is unavailable.
        """
        text = ET.Element(
            "text",
            attrib={
                "font-family": "Kozuka Gothic Pr6N",
                "transform": "matrix(3.36,0,-0.68,3.35,253.68,244.16)",
            },
        )
        text.text = "さすだけ！"

        svg_utils.add_font_family(text, "Noto Sans CJK JP")

        assert text.attrib.get("font-family") == "Kozuka Gothic Pr6N, Noto Sans CJK JP"
        assert text.attrib.get("transform") == "matrix(3.36,0,-0.68,3.35,253.68,244.16)"

    def test_multiple_calls_build_fallback_chain(self) -> None:
        """Test that calling add_font_family multiple times builds fallback chain."""
        text = ET.Element("text", attrib={"font-family": "Arial"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")
        assert text.attrib.get("font-family") == "Arial, Helvetica"

        # Second call with same fallback - should be idempotent
        svg_utils.add_font_family(text, "Helvetica")
        assert text.attrib.get("font-family") == "Arial, Helvetica"

        # Third call with different fallback - should append
        svg_utils.add_font_family(text, "DejaVu Sans")
        assert text.attrib.get("font-family") == "Arial, Helvetica, DejaVu Sans"

        # Fourth call with another fallback
        svg_utils.add_font_family(text, "sans-serif")
        assert (
            text.attrib.get("font-family")
            == "Arial, Helvetica, DejaVu Sans, sans-serif"
        )

    def test_generic_font_family_names(self) -> None:
        """Test handling of generic font family names (sans-serif, serif, etc)."""
        text = ET.Element("text", attrib={"font-family": "Arial, sans-serif"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        assert text.attrib.get("font-family") == "Arial, sans-serif, Helvetica"

    def test_case_sensitive_duplicate_detection(self) -> None:
        """Test that duplicate detection is case-sensitive."""
        text = ET.Element("text", attrib={"font-family": "Arial"})
        text.text = "Hello"

        # Add with different case
        svg_utils.add_font_family(text, "arial")

        # Should add because case doesn't match
        assert text.attrib.get("font-family") == "Arial, arial"

    def test_only_style_updated_when_no_attribute(self) -> None:
        """Test that only style is updated when element has no font-family attribute."""
        text = ET.Element("text", attrib={"style": "font-family: Arial; color: red"})
        text.text = "Hello"

        svg_utils.add_font_family(text, "Helvetica")

        style = text.attrib.get("style")
        assert style is not None
        assert "font-family: 'Arial', 'Helvetica'" in style
        # No attribute should be created (style has the font)
        assert text.get("font-family") is None


class TestExtractTextCharacters:
    """Tests for extract_text_characters utility function."""

    def test_simple_text_extraction(self) -> None:
        """Test extracting plain text from element."""
        elem = ET.fromstring("<text>Hello World</text>")
        result = svg_utils.extract_text_characters(elem)
        assert result == "Hello World"

    def test_html_entity_decoding(self) -> None:
        """Test that HTML entities are properly decoded."""
        elem = ET.fromstring("<text>Hello &amp; world &#x4E00;</text>")
        result = svg_utils.extract_text_characters(elem)
        assert result == "Hello & world 一"

    def test_filters_control_characters(self) -> None:
        """Test that control characters (Cc) are filtered out."""
        elem = ET.fromstring("<text>Hello\nWorld\tTest\r\n</text>")
        result = svg_utils.extract_text_characters(elem)
        assert result == "HelloWorldTest"
        assert "\n" not in result
        assert "\t" not in result
        assert "\r" not in result

    def test_filters_variation_selectors(self) -> None:
        """Test that variation selectors (Mn) are filtered out."""
        # U+FE0E is VARIATION SELECTOR-15 (text presentation)
        # U+FE0F is VARIATION SELECTOR-16 (emoji presentation)
        elem = ET.Element("text")
        # Copyright with text selector, registered with emoji selector
        elem.text = "©\ufe0e®\ufe0f"
        result = svg_utils.extract_text_characters(elem)
        assert result == "©®"
        assert "\ufe0e" not in result
        assert "\ufe0f" not in result

    def test_filters_combining_marks(self) -> None:
        """Test that combining marks (Mn, Mc, Me) are filtered out."""
        # Combining diacritical marks
        elem = ET.Element("text")
        elem.text = "e\u0301"  # e + combining acute accent
        result = svg_utils.extract_text_characters(elem)
        assert result == "e"
        assert "\u0301" not in result

    def test_filters_format_characters(self) -> None:
        """Test that format characters (Cf) are filtered out."""
        # U+200B is ZERO WIDTH SPACE
        # U+200C is ZERO WIDTH NON-JOINER
        # U+200D is ZERO WIDTH JOINER
        elem = ET.Element("text")
        elem.text = "Hello\u200bWorld\u200c\u200d"
        result = svg_utils.extract_text_characters(elem)
        assert result == "HelloWorld"

    def test_preserves_normal_unicode_characters(self) -> None:
        """Test that normal Unicode characters are preserved."""
        # Test various Unicode categories that should be preserved
        elem = ET.Element("text")
        elem.text = "Hello 世界 مرحبا שלום"  # Latin, CJK, Arabic, Hebrew
        result = svg_utils.extract_text_characters(elem)
        assert result == "Hello 世界 مرحبا שלום"

    def test_preserves_symbols_and_punctuation(self) -> None:
        """Test that symbols and punctuation are preserved."""
        elem = ET.Element("text")
        elem.text = "©®™«»×÷"
        result = svg_utils.extract_text_characters(elem)
        assert result == "©®™«»×÷"

    def test_extracts_text_and_tail(self) -> None:
        """Test that both text and tail are extracted."""
        root = ET.fromstring("<text><tspan>A</tspan>B</text>")
        tspan = root[0]
        result = svg_utils.extract_text_characters(tspan)
        assert result == "AB"

    def test_tail_with_control_characters_filtered(self) -> None:
        """Test that control characters in tail are also filtered."""
        root = ET.fromstring("<text><tspan>A</tspan>B\nC</text>")
        tspan = root[0]
        result = svg_utils.extract_text_characters(tspan)
        assert result == "ABC"
        assert "\n" not in result

    def test_regression_copyright_with_variation_selector(self) -> None:
        """Regression test: copyright sign with variation selector.

        This is the actual case that caused .LastResort font substitution.
        U+FE0E (VARIATION SELECTOR-15) should be filtered out.
        """
        elem = ET.Element("text")
        elem.text = "©\ufe0e"  # Copyright with text presentation selector
        result = svg_utils.extract_text_characters(elem)
        assert result == "©"
        assert len(result) == 1
        assert ord(result[0]) == 0x00A9  # COPYRIGHT SIGN

    def test_cjk_text_with_variation_selectors(self) -> None:
        """Test CJK text with variation selectors."""
        # Japanese text with variation selector
        elem = ET.Element("text")
        elem.text = "少\ufe0e年\ufe0e社\ufe0e"
        result = svg_utils.extract_text_characters(elem)
        assert result == "少年社"
        assert "\ufe0e" not in result

    def test_empty_text(self) -> None:
        """Test with element containing no text."""
        elem = ET.Element("text")
        result = svg_utils.extract_text_characters(elem)
        assert result == ""

    def test_only_tail(self) -> None:
        """Test with element having only tail text."""
        root = ET.fromstring("<text><tspan/>After</text>")
        tspan = root[0]
        result = svg_utils.extract_text_characters(tspan)
        assert result == "After"

    def test_real_world_mixed_content(self) -> None:
        """Test real-world scenario with mixed content."""
        # Simulate actual PSD text: Japanese with copyright, variation selectors, spaces
        elem = ET.Element("text")
        elem.text = "画像肥谷©\ufe0e/報介僕×年／少社『」「"
        result = svg_utils.extract_text_characters(elem)
        # Variation selector should be removed, everything else preserved
        assert "画像肥谷" in result
        assert "©" in result
        assert "\ufe0e" not in result
        assert "/" in result
        assert "×" in result


def _get_local_tag(element: ET.Element) -> str:
    """Get local tag name without namespace prefix.

    Helper function to strip namespace from element tags for testing.
    """
    tag = element.tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def test_find_elements_with_font_family_foreignobject() -> None:
    """Test finding XHTML elements with specific font-family in foreignObject."""
    svg = ET.fromstring(
        """<svg xmlns="http://www.w3.org/2000/svg">
            <foreignObject>
                <div xmlns="http://www.w3.org/1999/xhtml">
                    <p style="font-family: 'Times-Roman'">Test text</p>
                    <span style="font-family: 'Arial-Bold'">More text</span>
                </div>
            </foreignObject>
        </svg>"""
    )

    # Test finding p element with Times-Roman
    elements = svg_utils.find_elements_with_font_family(svg, "Times-Roman")
    assert len(elements) == 1
    assert _get_local_tag(elements[0]) == "p"

    # Test finding span element with Arial-Bold
    elements = svg_utils.find_elements_with_font_family(svg, "Arial-Bold")
    assert len(elements) == 1
    assert _get_local_tag(elements[0]) == "span"


def test_find_elements_with_font_family_mixed_content() -> None:
    """Test finding elements in SVG with both text and foreignObject."""
    svg = ET.fromstring(
        """<svg xmlns="http://www.w3.org/2000/svg">
            <text font-family="Helvetica">Traditional text</text>
            <foreignObject>
                <p xmlns="http://www.w3.org/1999/xhtml" style="font-family: Arial">
                    Foreign text
                </p>
            </foreignObject>
        </svg>"""
    )

    # Test finding traditional text element
    elements = svg_utils.find_elements_with_font_family(svg, "Helvetica")
    assert len(elements) == 1
    assert _get_local_tag(elements[0]) == "text"

    # Test finding foreignObject p element
    elements = svg_utils.find_elements_with_font_family(svg, "Arial")
    assert len(elements) == 1
    assert _get_local_tag(elements[0]) == "p"


def test_strip_text_element_whitespace_with_xml_space() -> None:
    """Test that xml:space='preserve' is compatible with indentation stripping.

    The _strip_text_element_whitespace function should remove whitespace-only
    text/tail (from pretty-printing indentation) while preserving actual content
    whitespace in elements with xml:space='preserve'.
    """
    # Create SVG with xml:space and pretty-printing indentation
    svg_string = """<svg xmlns="http://www.w3.org/2000/svg">
  <text xml:space="preserve">
    <tspan> Lorem </tspan>
    <tspan>  Test  </tspan>
  </text>
</svg>"""

    svg = ET.fromstring(svg_string)

    # Before stripping: text element has whitespace-only text (indentation)
    text = svg.find(".//{http://www.w3.org/2000/svg}text")
    assert text is not None

    # Verify indentation exists before stripping
    assert text.text is not None
    assert text.text.strip() == ""  # It's whitespace-only

    # Apply whitespace stripping
    svg_utils._strip_text_element_whitespace(svg)

    # After stripping: verify correct behavior
    text = svg.find(".//{http://www.w3.org/2000/svg}text")
    assert text is not None

    # xml:space attribute should still be present (not touched)
    assert (
        text.attrib.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve"
    ), "xml:space attribute should be preserved"

    # Indentation whitespace should be removed (whitespace-only text)
    assert text.text is None or text.text.strip() == "", (
        "Whitespace-only text (indentation) should be stripped"
    )

    # Content whitespace should be preserved (actual text with spaces)
    tspans = text.findall(".//{http://www.w3.org/2000/svg}tspan")
    assert len(tspans) == 2
    assert tspans[0].text == " Lorem ", (
        f"Content whitespace should be preserved, got: {repr(tspans[0].text)}"
    )
    assert tspans[1].text == "  Test  ", (
        f"Content whitespace should be preserved, got: {repr(tspans[1].text)}"
    )

    # Tails (whitespace between elements) should be removed
    assert tspans[0].tail is None or tspans[0].tail.strip() == "", (
        "Whitespace-only tail should be stripped"
    )


class TestSafeUtf8:
    """Tests for safe_utf8 utility function.

    The safe_utf8 function removes illegal and problematic XML characters
    by replacing them with spaces. This is critical for XML sanitization
    and addresses CodeQL security alert for overly permissive regex.
    """

    def test_filters_nel_character(self) -> None:
        """Test that U+0085 (NEL - Next Line) is filtered.

        This is the specific character that was excluded due to the gap
        in the regex pattern (\x7f-\x84\x86-\x9f). This test ensures
        the security fix properly filters U+0085.
        """
        text = "Hello\x85World"
        result = svg_utils.safe_utf8(text)
        assert result == "Hello World"
        assert "\x85" not in result

    def test_preserves_legal_xml_whitespace(self) -> None:
        """Test that legal XML whitespace characters (TAB, LF) are preserved.

        TAB (0x09) and LF (0x0A) are explicitly allowed in XML 1.0.
        Note: CR (0x0D) is also technically legal in XML 1.0, but the
        regex pattern intentionally filters it (part of \x0b-\x1f range).
        This is a conservative design choice for XML sanitization.
        """
        text = "Hello\tWorld\nTest"
        result = svg_utils.safe_utf8(text)
        assert "\t" in result  # TAB (0x09) preserved
        assert "\n" in result  # LF (0x0A) preserved
        assert result == "Hello\tWorld\nTest"

    def test_filters_cr_character(self) -> None:
        """Test that CR (0x0D) is filtered.

        While CR is technically legal in XML 1.0, the regex pattern
        intentionally filters it as part of the \x0b-\x1f range.
        This is a conservative sanitization choice.
        """
        text = "Hello\rWorld"
        result = svg_utils.safe_utf8(text)
        assert "\r" not in result
        assert result == "Hello World"

    def test_filters_all_c1_controls(self) -> None:
        """Test that all C1 control characters (0x7F-0x9F) are filtered.

        The regex should now properly filter the entire C1 control block
        including 0x85 (NEL) which was previously excluded.
        """
        # Test boundary and middle characters from C1 range
        for code in [0x7F, 0x80, 0x84, 0x85, 0x86, 0x90, 0x9F]:
            text = f"Before{chr(code)}After"
            result = svg_utils.safe_utf8(text)
            assert chr(code) not in result, f"Character 0x{code:02X} should be filtered"
            assert result == "Before After"

    def test_filters_c0_controls(self) -> None:
        """Test that C0 control characters are filtered (except TAB, LF, CR)."""
        # Test NULL and other C0 controls (excluding TAB, LF, CR)
        for code in [0x00, 0x01, 0x02, 0x08, 0x0B, 0x0C, 0x0E, 0x1F]:
            text = f"Before{chr(code)}After"
            result = svg_utils.safe_utf8(text)
            assert chr(code) not in result, f"Character 0x{code:02X} should be filtered"
            assert result == "Before After"

    def test_filters_surrogates(self) -> None:
        """Test that UTF-16 surrogate pairs (0xD800-0xDFFF) are filtered.

        Surrogate pairs are illegal in XML documents.
        """
        # Test surrogate range boundaries
        text = "Before\ud800After"  # High surrogate
        result = svg_utils.safe_utf8(text)
        assert "\ud800" not in result

        text = "Before\udfff After"  # Low surrogate
        result = svg_utils.safe_utf8(text)
        assert "\udfff" not in result

    def test_filters_non_characters(self) -> None:
        """Test that non-characters (0xFDD0-0xFDDF, 0xFFFE-0xFFFF) are filtered."""
        # Test non-character range
        text = "Before\ufdd0After"  # Start of non-character range
        result = svg_utils.safe_utf8(text)
        assert "\ufdd0" not in result

        text = "Before\ufffe After"  # U+FFFE
        result = svg_utils.safe_utf8(text)
        assert "\ufffe" not in result

        text = "Before\uffff After"  # U+FFFF
        result = svg_utils.safe_utf8(text)
        assert "\uffff" not in result

    def test_preserves_normal_text(self) -> None:
        """Test that normal text is preserved unchanged."""
        text = "Hello World! This is normal text."
        result = svg_utils.safe_utf8(text)
        assert result == text

    def test_preserves_unicode_text(self) -> None:
        """Test that normal Unicode characters are preserved."""
        # Various Unicode scripts
        text = "Hello 世界 مرحبا שלום Здравствуй"
        result = svg_utils.safe_utf8(text)
        assert result == text

    def test_preserves_special_characters(self) -> None:
        """Test that symbols and punctuation are preserved."""
        text = "©®™«»×÷±≠≤≥"
        result = svg_utils.safe_utf8(text)
        assert result == text

    def test_multiple_illegal_characters(self) -> None:
        """Test filtering multiple illegal characters in one string."""
        text = "Start\x00Middle\x85End\ud800Final"
        result = svg_utils.safe_utf8(text)
        assert "\x00" not in result
        assert "\x85" not in result
        assert "\ud800" not in result
        assert "Start" in result
        assert "Middle" in result
        assert "End" in result
        assert "Final" in result

    def test_empty_string(self) -> None:
        """Test that empty strings are handled correctly."""
        text = ""
        result = svg_utils.safe_utf8(text)
        assert result == ""

    def test_only_illegal_characters(self) -> None:
        """Test string containing only illegal characters."""
        text = "\x00\x85\ud800"
        result = svg_utils.safe_utf8(text)
        # All illegal characters replaced with spaces
        assert result == "   "
        assert len(result) == 3

    def test_real_world_xml_text(self) -> None:
        """Test real-world SVG text scenario."""
        # Simulate text that might come from a PSD file
        text = "Hello World\x85Copyright © 2024\ufffe"
        result = svg_utils.safe_utf8(text)
        # NEL and non-character should be replaced
        assert "\x85" not in result
        assert "\ufffe" not in result
        # Normal text and copyright symbol should be preserved
        assert "Hello World" in result
        assert "Copyright © 2024" in result

    def test_preserves_space_character(self) -> None:
        """Test that normal space character (0x20) is preserved."""
        text = "Hello World"
        result = svg_utils.safe_utf8(text)
        assert result == "Hello World"
        assert " " in result

    def test_regex_pattern_consistency(self) -> None:
        """Test that the regex pattern is applied consistently.

        This test verifies that the fix for CodeQL alert properly
        includes U+0085 without breaking other character ranges.
        """
        # Before fix: 0x85 was excluded (gap in \x7f-\x84\x86-\x9f)
        # After fix: 0x85 is included (continuous range \x7f-\x9f)

        # Test characters around the gap
        assert "\x84" not in svg_utils.safe_utf8("Test\x84")  # Should be filtered
        assert "\x85" not in svg_utils.safe_utf8(
            "Test\x85"
        )  # Should NOW be filtered (was the gap)
        assert "\x86" not in svg_utils.safe_utf8("Test\x86")  # Should be filtered

        # Verify legal characters around the range are preserved
        assert "\x09" in svg_utils.safe_utf8("Test\x09")  # TAB
        assert "\x0a" in svg_utils.safe_utf8("Test\x0a")  # LF
        assert "\x20" in svg_utils.safe_utf8("Test\x20")  # Space
