"""Room shell centred on the origin, back wall at +y. The sconce is a steel plate with an emissive shade; the light
itself sits just in front of the shade so the wall around it is lit."""

WALL = 0.1


def build(ctx, settings):
    w, d, h = settings["width"], settings["depth"], settings["height"]
    walls, floor = settings["walls"], settings["floor"]
    ctx.box((0.0, 0.0, -WALL / 2), (w, d, WALL), floor, name="floor")
    ctx.box((0.0, d / 2 + WALL / 2, h / 2), (w + 2 * WALL, WALL, h), walls, name="back-wall")
    for side in (-1, 1):
        ctx.box((side * (w / 2 + WALL / 2), 0.0, h / 2), (WALL, d, h), walls, name="side-wall")
    if settings["ceiling"]:
        ctx.box((0.0, 0.0, h + WALL / 2), (w + 2 * WALL, d, WALL), walls, name="ceiling")
    lx, lz = settings["lamp_x"], settings["lamp_height"]
    face = d / 2
    ctx.box((lx, face - 0.01, lz), (0.12, 0.02, 0.2), "steel", name="sconce-plate")
    ctx.box((lx, face - 0.06, lz - 0.02), (0.02, 0.08, 0.02), "steel", name="sconce-arm")
    ctx.tube((lx, face - 0.12, lz + 0.04), 0.08, 0.15, "lamp-shade", name="sconce-shade", sides=24)
    ctx.light("point", (lx, face - 0.2, lz + 0.04), settings["lamp_power"], settings["lamp_color"], radius=0.05,
              name=f"{ctx.instance_id}-sconce")
