"""Open drawers: a front box plus a dark slab near its top that reads as the open inside."""


def build(ctx, settings):
    rng = ctx.rng
    w, h = settings["width"], settings["height"]
    for n in range(settings["count"]):
        x = rng.uniform(*settings["x"])
        z = rng.uniform(*settings["z"])
        out = rng.uniform(*settings["out"])
        ctx.box((x, -out / 2, z), (w, out, h), settings["surface"], name=f"drawer{n}")
        ctx.box((x, -out / 2, z + h / 2 - 0.02), (w - 0.08, out - 0.06, 0.04), settings["inside"], name=f"inside{n}")
