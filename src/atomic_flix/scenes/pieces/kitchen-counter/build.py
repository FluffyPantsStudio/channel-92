"""Kitchen run. Doors are separate thin boxes so their gaps catch light; the sink is a steel tray set into the
worktop with a tap."""

PLINTH = 0.1
TOP = 0.04
SPLASH = 0.6
UPPER_DEPTH, UPPER_HEIGHT, UPPER_GAP = 0.35, 0.7, 0.55


def _doors(ctx, extent, face_y, z0, height, door, surface, tag):
    count = max(1, round(extent / door))
    width = extent / count
    for n in range(count):
        x = width * (n + 0.5)
        ctx.box((x, face_y - 0.01, z0 + height / 2), (width - 0.006, 0.02, height - 0.006), surface,
                name=f"{tag}-door{n}")
        handle_x = x + (width / 2 - 0.06) * (1 if n % 2 else -1)
        handle_z = z0 + height - 0.08 if tag == "base" else z0 + 0.08
        ctx.box((handle_x, face_y - 0.03, handle_z), (0.015, 0.02, 0.12), "steel", name=f"{tag}-handle{n}")


def build(ctx, settings):
    extent, depth, height = settings["extent"], settings["depth"], settings["height"]
    carcass_h = height - TOP - PLINTH
    ctx.box((extent / 2, -depth / 2 + 0.05, PLINTH / 2), (extent, depth - 0.1, PLINTH), settings["units"], name="plinth")
    ctx.box((extent / 2, -depth / 2 + 0.01, PLINTH + carcass_h / 2), (extent, depth - 0.02, carcass_h),
            settings["units"], name="carcass")
    _doors(ctx, extent, -depth + 0.02, PLINTH, carcass_h, settings["door"], settings["units"], "base")
    ctx.box((extent / 2, -depth / 2 - 0.01, height - TOP / 2), (extent, depth + 0.02, TOP), settings["top"],
            name="worktop")
    ctx.box((extent / 2, -0.01, height + SPLASH / 2), (extent, 0.02, SPLASH), settings["splash"], name="splashback")
    if settings["uppers"]:
        z0 = height + UPPER_GAP
        ctx.box((extent / 2, -UPPER_DEPTH / 2, z0 + UPPER_HEIGHT / 2), (extent, UPPER_DEPTH - 0.02, UPPER_HEIGHT),
                settings["units"], name="wall-units")
        _doors(ctx, extent, -UPPER_DEPTH, z0, UPPER_HEIGHT, settings["door"], settings["units"], "upper")
    if settings["sink"]:
        sx = min(extent * 0.6, extent - 0.4)
        ctx.box((sx, -depth / 2, height + 0.002), (0.6, 0.42, 0.008), "steel", name="sink-rim")
        ctx.box((sx, -depth / 2, height - 0.05), (0.5, 0.36, 0.1), "drawer-in", name="sink-bowl")
        ctx.tube((sx, -0.08, height + 0.15), 0.014, 0.3, "steel", name="tap")
        ctx.box((sx, -0.15, height + 0.29), (0.025, 0.14, 0.025), "steel", name="spout")
