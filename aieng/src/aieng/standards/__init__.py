"""Standard mechanical parts library — Shape IR generators.

Reusable generators for fasteners, bearings, shafts, structural profiles,
and standard hole types.  Every function returns a Shape IR node dictionary
that can be compiled to build123d / OpenCASCADE B-Rep via the existing
Shape IR compilers.

Usage example::

    from aieng.standards import hex_bolt, deep_groove_ball_bearing
    bolt = hex_bolt(diameter=8.0, length=25.0)
    bearing = deep_groove_ball_bearing(bore=20.0, outer_diameter=47.0)
"""
from __future__ import annotations

from .bearings import (
    DEEP_GROOVE_BALL_BEARING_PRESETS,
    THRUST_BALL_BEARING_PRESETS,
    deep_groove_ball_bearing,
    thrust_ball_bearing,
)
from .fasteners import (
    METRIC_BOLT_PRESETS,
    METRIC_NUT_PRESETS,
    METRIC_SET_SCREW_PRESETS,
    METRIC_SOCKET_HEAD_PRESETS,
    METRIC_WASHER_PRESETS,
    hex_bolt,
    hex_nut,
    set_screw,
    socket_head_cap_screw,
    washer,
)
from .fastener_planner import (
    plan_fastener_for_hole,
    plan_fasteners_for_features,
)
from .holes import (
    blind_hole,
    counterbored_hole,
    countersunk_hole,
    tapped_hole,
    through_hole,
)
from .profiles import (
    angle_profile,
    channel_profile,
    i_beam_profile,
    rectangular_tube,
    round_tube,
)
from .shafts import (
    splined_shaft,
    stepped_shaft,
)

__all__ = [
    # fasteners
    "hex_bolt",
    "hex_nut",
    "washer",
    "socket_head_cap_screw",
    "set_screw",
    "METRIC_BOLT_PRESETS",
    "METRIC_NUT_PRESETS",
    "METRIC_WASHER_PRESETS",
    "METRIC_SOCKET_HEAD_PRESETS",
    "METRIC_SET_SCREW_PRESETS",
    "plan_fastener_for_hole",
    "plan_fasteners_for_features",
    # bearings
    "deep_groove_ball_bearing",
    "thrust_ball_bearing",
    "DEEP_GROOVE_BALL_BEARING_PRESETS",
    "THRUST_BALL_BEARING_PRESETS",
    # shafts
    "stepped_shaft",
    "splined_shaft",
    # profiles
    "angle_profile",
    "channel_profile",
    "i_beam_profile",
    "rectangular_tube",
    "round_tube",
    # holes
    "through_hole",
    "blind_hole",
    "countersunk_hole",
    "counterbored_hole",
    "tapped_hole",
]
