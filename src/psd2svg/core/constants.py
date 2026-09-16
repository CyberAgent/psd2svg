from typing import NamedTuple, Optional, Union

from psd_tools.constants import BlendMode
from psd_tools.terminology import Enum

# https://helpx.adobe.com/photoshop/using/blending-modes.html
BLEND_MODE: dict[Union[BlendMode, bytes], str] = {
    # Layer modes.
    BlendMode.PASS_THROUGH: "pass-through",
    BlendMode.NORMAL: "normal",
    BlendMode.DISSOLVE: "normal",
    BlendMode.DARKEN: "darken",
    BlendMode.MULTIPLY: "multiply",
    BlendMode.COLOR_BURN: "color-burn",
    BlendMode.LINEAR_BURN: "plus-darker",
    BlendMode.DARKER_COLOR: "darken",
    BlendMode.LIGHTEN: "lighten",
    BlendMode.SCREEN: "screen",
    BlendMode.COLOR_DODGE: "color-dodge",
    BlendMode.LINEAR_DODGE: "plus-lighter",
    BlendMode.LIGHTER_COLOR: "lighten",
    BlendMode.OVERLAY: "overlay",
    BlendMode.SOFT_LIGHT: "soft-light",
    BlendMode.HARD_LIGHT: "hard-light",
    BlendMode.VIVID_LIGHT: "lighten",
    BlendMode.LINEAR_LIGHT: "darken",
    BlendMode.PIN_LIGHT: "normal",
    BlendMode.HARD_MIX: "normal",
    BlendMode.DIFFERENCE: "difference",
    BlendMode.EXCLUSION: "exclusion",
    BlendMode.SUBTRACT: "difference",
    BlendMode.DIVIDE: "difference",
    BlendMode.HUE: "hue",
    BlendMode.SATURATION: "saturation",
    BlendMode.COLOR: "color",
    BlendMode.LUMINOSITY: "luminosity",
    # Descriptor values. Photoshop writes an enumerated blend mode either as the
    # four-character key or as the long string ID; recent versions (verified with
    # Photoshop 2026) always write the long form, so both are listed here.
    Enum.Normal: "normal",
    b"normal": "normal",
    Enum.Dissolve: "normal",
    b"dissolve": "normal",
    Enum.Darken: "darken",
    b"darken": "darken",
    Enum.Multiply: "multiply",
    b"multiply": "multiply",
    Enum.ColorBurn: "color-burn",
    b"colorBurn": "color-burn",
    b"linearBurn": "plus-darker",
    b"darkerColor": "darken",
    Enum.Lighten: "lighten",
    b"lighten": "lighten",
    Enum.Screen: "screen",
    b"screen": "screen",
    Enum.ColorDodge: "color-dodge",
    b"colorDodge": "color-dodge",
    b"linearDodge": "plus-lighter",
    b"lighterColor": "lighten",
    Enum.Overlay: "overlay",
    b"overlay": "overlay",
    Enum.SoftLight: "soft-light",
    b"softLight": "soft-light",
    Enum.HardLight: "hard-light",
    b"hardLight": "hard-light",
    b"vividLight": "lighten",
    b"linearLight": "darken",
    b"pinLight": "normal",
    b"hardMix": "normal",
    Enum.Difference: "difference",
    b"difference": "difference",
    Enum.Exclusion: "exclusion",
    b"exclusion": "exclusion",
    b"blendSubtraction": "difference",
    b"blendDivide": "difference",
    Enum.Hue: "hue",
    b"hue": "hue",
    Enum.Saturation: "saturation",
    b"saturation": "saturation",
    Enum.Color: "color",
    b"color": "color",
    Enum.Luminosity: "luminosity",
    b"luminosity": "luminosity",
    b"passThrough": "pass-through",
}

# Blend modes that are not accurately supported in SVG and are mapped to approximations.
# These will trigger warnings when used. Overlay effects reproduce the four modes in
# FILTER_BLEND_MODES exactly and never consult this set, so the entries below cover the
# layer-level blend mode and the vector overlay path only.
INACCURATE_BLEND_MODES: set[Union[BlendMode, bytes]] = {
    # Dissolve mode uses random pixel patterns, not supported in SVG
    BlendMode.DISSOLVE,
    Enum.Dissolve,
    b"dissolve",
    # Linear burn uses plus-darker which has limited browser support
    BlendMode.LINEAR_BURN,
    b"linearBurn",
    # Linear dodge uses plus-lighter which has limited browser support
    BlendMode.LINEAR_DODGE,
    b"linearDodge",
    # Darker/Lighter Color modes compare color values, approximated with darken/lighten
    BlendMode.DARKER_COLOR,
    b"darkerColor",
    BlendMode.LIGHTER_COLOR,
    b"lighterColor",
    # Advanced light modes approximated with simpler modes
    BlendMode.VIVID_LIGHT,
    b"vividLight",
    BlendMode.LINEAR_LIGHT,
    b"linearLight",
    BlendMode.PIN_LIGHT,
    b"pinLight",
    BlendMode.HARD_MIX,
    b"hardMix",
    # Subtract and Divide modes approximated with difference
    BlendMode.SUBTRACT,
    b"blendSubtraction",
    BlendMode.DIVIDE,
    b"blendDivide",
}


class FilterBlend(NamedTuple):
    """Recipe reproducing a blend mode that ``mix-blend-mode`` cannot express.

    Photoshop's separable blend functions relate Divide/Subtract to the neighbouring,
    natively supported modes applied to an inverted blend layer, and make Linear
    Burn/Linear Dodge plain sums::

        Divide(b, s)     = min(1, b / s)     = ColorDodge(b, 1 - s)
        Subtract(b, s)   = max(0, b - s)     = LinearBurn(b, 1 - s)
        LinearBurn(b, s) = max(0, b + s - 1)
        LinearDodge(b, s)= min(1, b + s)

    So each is exact wherever the blend layer is synthesised inside a filter and can
    be rewritten there.

    Attributes:
        invert: Invert the blend layer's color channels first.
        css_mode: ``mix-blend-mode`` to blend the rewritten layer with, or None to
            sum it with the layer inside the filter via
            ``feComposite operator="arithmetic"``.
        offset: ``k4`` of that sum, i.e. the constant added to ``b + s``.
    """

    invert: bool
    css_mode: Optional[str] = None
    offset: float = 0.0


# Keyed by descriptor value, since only layer effects synthesise their blend layer.
FILTER_BLEND_MODES: dict[bytes, FilterBlend] = {
    b"blendDivide": FilterBlend(invert=True, css_mode="color-dodge"),
    b"blendSubtraction": FilterBlend(invert=True, offset=-1.0),
    b"linearBurn": FilterBlend(invert=False, offset=-1.0),
    b"linearDodge": FilterBlend(invert=False),
}
