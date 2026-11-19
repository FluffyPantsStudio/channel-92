"""Street floor as in lab/blender/street.py: everything but the edge lines runs three lengths long, centred on the
middle of the street's length, so the viewpoint never sees an end."""


def build(ctx, settings):
    extent, width = settings["extent"], settings["width"]
    mid, run = extent / 2, extent * 3
    ctx.box((mid, 0.0, -0.11), (run, settings["ground_width"], 0.2), settings["ground"], name="ground")
    ctx.box((mid, 0.0, -0.05), (run, width, 0.1), settings["road"], name="road")
    walk_y = width / 2 + settings["walk_width"] / 2
    line_y = width / 2 - settings["line_inset"]
    for side in (-1, 1):
        ctx.box((mid, side * walk_y, 0.02), (run, settings["walk_width"], 0.26), settings["walk"], name="sidewalk")
        ctx.box((mid, side * line_y, 0.01), (extent, settings["line_width"], 0.02), settings["paint"], name="edge-line")
