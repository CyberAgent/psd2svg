from typing import Union

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
# These will trigger warnings when used.
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
