"""Body on four legs, one front per row with a steel handle; `open` rows (chosen by the instance's stream) slide
out with a dark inside showing."""

LEG = 0.08
GAP = 0.012
FRONT = 0.02


def build(ctx, settings):
    rng = ctx.rng
    w, d, h, rows = settings["width"], settings["depth"], settings["height"], settings["rows"]
    body_h = h - LEG
    ctx.box((0.0, 0.0, LEG + body_h / 2), (d, w, body_h), settings["body"], name="body")
    for sx in (-1, 1):
        for sy in (-1, 1):
            ctx.box((sx * (d / 2 - 0.04), sy * (w / 2 - 0.04), LEG / 2), (0.05, 0.05, LEG), settings["body"], name="leg")
    opened = set(rng.sample(range(rows), min(settings["open"], rows)))
    row_h = (body_h - GAP) / rows
    for r in range(rows):
        z = LEG + GAP + row_h * r + (row_h - GAP) / 2
        pull = rng.uniform(*settings["pull"]) if r in opened else 0.0
        x = d / 2 + FRONT / 2 + pull
        ctx.box((x, 0.0, z), (FRONT, w - 2 * GAP, row_h - GAP), settings["fronts"], name=f"front{r}")
        ctx.box((x + 0.02, 0.0, z), (0.02, w * 0.3, 0.025), "steel", name=f"handle{r}")
        if pull > 0:
            ctx.box((d / 2 + pull / 2, 0.0, z + (row_h - GAP) / 2 - 0.03), (pull, w - 4 * GAP, 0.02), "drawer-in",
                    name=f"inside{r}")
