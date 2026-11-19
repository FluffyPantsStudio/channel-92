"""Lawn slab, blanket turned a little, a lidded basket on one corner and cups set down on the blanket."""

import math


def build(ctx, settings):
    rng = ctx.rng
    size = settings["size"]
    ctx.box((0.0, 0.0, -0.05), (size, size, 0.1), "grass", name="lawn")
    bw, bd = settings["blanket"]
    twist = settings["twist"]
    ctx.box((0.0, 0.0, 0.004), (bw, bd, 0.008), "gingham", name="blanket", yaw=twist)
    c, s = math.cos(math.radians(twist)), math.sin(math.radians(twist))

    def on_blanket(u, v):
        x, y = u * bw / 2, v * bd / 2
        return (x * c - y * s, x * s + y * c)

    if settings["basket"]:
        x, y = on_blanket(0.55, 0.45)
        ctx.box((x, y, 0.13), (0.46, 0.3, 0.26), "wicker", name="basket", yaw=twist)
        ctx.box((x, y, 0.27), (0.48, 0.32, 0.02), "wicker", name="basket-lid", yaw=twist + 4)
    for n in range(settings["cups"]):
        x, y = on_blanket(rng.uniform(-0.6, 0.2), rng.uniform(-0.6, 0.6))
        ctx.tube((x, y, 0.058), 0.04, 0.1, "cup", name=f"cup{n}", sides=20)
