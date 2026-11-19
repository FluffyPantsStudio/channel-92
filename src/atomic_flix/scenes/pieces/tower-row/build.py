"""Towers placed left to right until the row is full, as street.py lays out each side of the street."""


def build(ctx, settings):
    rng = ctx.rng
    x = rng.uniform(*settings["start"])
    n = 0
    while x < settings["extent"]:
        w = rng.uniform(*settings["width"])
        h = rng.uniform(*settings["height"])
        ctx.box((x + w / 2, 0.0, h / 2), (w, settings["depth"], h), settings["surface"], name=f"tower{n}")
        x += w + rng.uniform(*settings["gap"])
        n += 1
