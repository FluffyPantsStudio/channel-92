"""Pole, eyeball, then iris and pupil as flattened spheres pushed out along the line to the look point.

Sizes scale with the eyeball radius (street.py used 1 m): iris 0.86 r out, 0.17 r thick, 1.04 r across; pupil
0.95 r out, 0.14 r thick, 0.44 r across.
"""

import math


def build(ctx, settings):
    h, r = settings["height"], settings["radius"]
    ctx.tube((0.0, 0.0, h / 2), settings["pole"], h, "pole", name="pole", sides=16)
    centre_z = h + 0.95 * r
    ctx.ball((0.0, 0.0, centre_z), r, "eye-white", name="ball", sides=48, rings=24)
    tx, ty, _ = ctx.to_local(settings["look"])
    yaw = math.atan2(ty, tx)
    half = math.sin(yaw / 2), math.cos(yaw / 2)
    quat = (half[1], 0.0, 0.0, half[0])
    for name, dist, thick, across, mat in (("iris", 0.86, 0.17, 1.04, "iris"), ("pupil", 0.95, 0.14, 0.44, "pupil")):
        pos = (math.cos(yaw) * dist * r, math.sin(yaw) * dist * r, centre_z)
        ctx.ball(pos, (thick * r, across * r, across * r), mat, name=name, quat=quat, sides=32, rings=16)
