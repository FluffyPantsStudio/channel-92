"""One box whose base sits `lift` metres above the instance's origin."""


def build(ctx, settings):
    sx, sy, sz = settings["size"]
    ctx.box((0.0, 0.0, settings["lift"] + sz / 2), (sx, sy, sz), settings["surface"], name="box", yaw=settings["yaw"])
