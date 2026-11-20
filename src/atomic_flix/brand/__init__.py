"""Channel 92's mark on a film: the logo every film keeps in its top right corner, and the optional intro.

The logo files ship inside the package (`brand/channel92-logo.png`, the channel's modern mark, and the era marks
of the 1950s to the 1990s in `brand/eras/`, RGBA PNGs). `logo_file(era_id)` finds an era's: its own mark, else the
modern one (the 2000s and a film with no era wear that, `DEFAULT_LOGO`). `logo_box` places it on a frame: 14 % of
the frame's width, 3 % of the width in from the top and right edges (inside the title-safe area), never scaled up
past its own size. `finish` lays it on (`finish/chain.py`), never
the cut, so the grade never sees it; `--no-logo` or film.json `brand.logo: false` leave it off. `join_intro` joins
an intro clip in front of a film; `era_intro.py` makes each era's own intro with ffmpeg.
"""

from __future__ import annotations

from .logo import DEFAULT_LOGO, ERA_LOGOS, LOGO_NATIVE, MARGIN_SHARE, WIDTH_SHARE, logo_box, logo_file, png_size
from .intro import IntroError, join_intro

__all__ = ["DEFAULT_LOGO", "ERA_LOGOS", "IntroError", "LOGO_NATIVE", "MARGIN_SHARE", "WIDTH_SHARE", "join_intro",
           "logo_box", "logo_file", "png_size"]
