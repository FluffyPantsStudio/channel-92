"""python -m atomic_flix.cli: the same as the `atomic-flix` command."""

import sys

from . import main

if __name__ == "__main__":
    sys.exit(main())
