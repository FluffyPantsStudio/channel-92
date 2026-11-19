"""One thin slab whose top is the instance's z."""


def build(ctx, settings):
    size = settings["size"]
    ctx.box((0.0, 0.0, -0.05), (size, size, 0.1), settings["surface"], name="flat")
