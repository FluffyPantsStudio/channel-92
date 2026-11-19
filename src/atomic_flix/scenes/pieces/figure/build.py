"""Stand-in body: joints come from a few angles per frame (forward kinematics in the body's own frame: x forward,
y to the body's left, z up), then every part is laid between its joints for every frame.

Body points use the usual 18-point body names without the face points; "r_" is the body's own right (-y).
`tempo` scales every cycle; `speed` (metres per second) walks the body forward along +x.
"""

import math

REST = {  # metres for a 1.75 m body
    "hip_z": 0.95, "hip_y": 0.1, "thigh": 0.45, "shin": 0.42,
    "shoulder_z": 1.42, "shoulder_y": 0.19, "upper_arm": 0.28, "forearm": 0.26,
    "neck_z": 1.45, "head_z": 1.6,
}


def _angles(anim, t, tempo):
    """Per-frame angles in degrees and small offsets in metres (before scaling)."""
    tau = 2 * math.pi * tempo * t
    a = {"bob": 0.0, "sway": 0.02 * math.sin(tau * 0.25), "head_yaw": 6 * math.sin(tau * 0.13),
         "inhale": 0.006 * math.sin(tau * 0.3),
         "l_thigh": 0.0, "r_thigh": 0.0, "l_knee": 2.0, "r_knee": 2.0,
         "l_arm": 3 * math.sin(tau * 0.2), "r_arm": -3 * math.sin(tau * 0.2), "l_elbow": 8.0, "r_elbow": 8.0}
    if anim == "walk":
        phase = tau * 0.9
        a.update(bob=0.03 * abs(math.sin(phase)), sway=0.025 * math.sin(phase),
                 l_thigh=25 * math.sin(phase), r_thigh=-25 * math.sin(phase),
                 l_knee=20 + 20 * max(0.0, -math.sin(phase)), r_knee=20 + 20 * max(0.0, math.sin(phase)),
                 l_arm=-20 * math.sin(phase), r_arm=20 * math.sin(phase), l_elbow=15.0, r_elbow=15.0)
    elif anim == "sing":
        a.update(r_arm=25 + 20 * math.sin(tau * 0.5), r_elbow=55 + 25 * math.sin(tau * 0.5 + 0.8),
                 l_arm=8 + 6 * math.sin(tau * 0.31), l_elbow=20 + 10 * math.sin(tau * 0.31 + 1.0),
                 head_yaw=10 * math.sin(tau * 0.21), inhale=0.012 * math.sin(tau * 0.45))
    return a


def _swing(origin, extent, degrees, side_y=0.0):
    r = math.radians(degrees)
    return (origin[0] + extent * math.sin(r), origin[1] + side_y, origin[2] - extent * math.cos(r))


def joints(anim, t, tempo, k, walk_x):
    a = _angles(anim, t, tempo)
    L = {key: v * k for key, v in REST.items()}
    hip_c = (walk_x, a["sway"] * k, L["hip_z"] + a["bob"] * k)
    out = {}
    for side, sy in (("l", 1), ("r", -1)):
        hip = (hip_c[0], hip_c[1] + sy * L["hip_y"], hip_c[2])
        knee = _swing(hip, L["thigh"], a[f"{side}_thigh"])
        ankle = _swing(knee, L["shin"], a[f"{side}_thigh"] - a[f"{side}_knee"])
        shoulder = (walk_x, a["sway"] * k * 0.5 + sy * L["shoulder_y"], L["shoulder_z"] + a["bob"] * k + a["inhale"] * k)
        elbow = _swing(shoulder, L["upper_arm"], a[f"{side}_arm"], sy * 0.03 * k)
        wrist = _swing(elbow, L["forearm"], a[f"{side}_arm"] + a[f"{side}_elbow"], sy * 0.01 * k)
        out.update({f"{side}_hip": hip, f"{side}_knee": knee, f"{side}_ankle": ankle,
                    f"{side}_shoulder": shoulder, f"{side}_elbow": elbow, f"{side}_wrist": wrist})
    neck = (walk_x, a["sway"] * k * 0.5, L["neck_z"] + a["bob"] * k + a["inhale"] * k)
    head = (walk_x, neck[1], L["head_z"] + a["bob"] * k + a["inhale"] * k)
    yaw = math.radians(a["head_yaw"])
    out.update({"neck": neck, "head": head, "pelvis": hip_c,
                "nose": (head[0] + 0.1 * k * math.cos(yaw), head[1] + 0.1 * k * math.sin(yaw), head[2])})
    return out, yaw


LIMBS = [("l_hip", "l_knee", 0.065), ("l_knee", "l_ankle", 0.05), ("r_hip", "r_knee", 0.065),
         ("r_knee", "r_ankle", 0.05), ("l_shoulder", "l_elbow", 0.045), ("l_elbow", "l_wrist", 0.038),
         ("r_shoulder", "r_elbow", 0.045), ("r_elbow", "r_wrist", 0.038), ("pelvis", "neck", 0.13),
         ("neck", "head", 0.05)]


def _yaw_quat(yaw):
    return (math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2))


def build(ctx, settings):
    k = settings["height"] / 1.75
    mat = settings["surface"]
    frames = []
    yaws = []
    for n in range(ctx.frames):
        t = n / ctx.fps
        j, yaw = joints(settings["anim"], t, settings["tempo"], k, settings["speed"] * t)
        frames.append(j)
        yaws.append(yaw)
    for a, b, radius in LIMBS:
        ctx.limb(frames[0][a], frames[0][b], radius * k, mat, name=f"{a}-{b}",
                 keys=[(fr[a], fr[b]) for fr in frames])
    ctx.ball(frames[0]["head"], (0.2 * k, 0.17 * k, 0.24 * k), mat, name="head", sides=24, rings=12,
               keys=[(fr["head"], _yaw_quat(y)) for fr, y in zip(frames, yaws)])
    for side in ("l", "r"):
        ctx.ball(frames[0][f"{side}_wrist"], 0.05 * k, mat, name=f"{side}_hand", sides=16, rings=8,
                   keys=[(fr[f"{side}_wrist"], (1.0, 0.0, 0.0, 0.0)) for fr in frames])
        foot = [(fr[f"{side}_ankle"][0] + 0.06 * k, fr[f"{side}_ankle"][1], fr[f"{side}_ankle"][2] - 0.03 * k)
                for fr in frames]
        ctx.box(foot[0], (0.24 * k, 0.09 * k, 0.07 * k), mat, name=f"{side}_foot",
                keys=[(p, (1.0, 0.0, 0.0, 0.0)) for p in foot])
    keep = ("nose", "neck", "r_shoulder", "r_elbow", "r_wrist", "l_shoulder", "l_elbow", "l_wrist",
            "r_hip", "r_knee", "r_ankle", "l_hip", "l_knee", "l_ankle")
    ctx.rig([{name: fr[name] for name in keep} for fr in frames])
