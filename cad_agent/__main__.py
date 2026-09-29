"""`python -m cad_agent` is the cad CLI, run cold (bin/cad adds the warm worker)."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
