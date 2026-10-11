"""The sections of a project's spec.toml, one module each.

Importing this package registers every kind (`registry.spec_kind`): the seven that existed before
step 6 first, in the order a message lists them, and then every other module here by name. A new
section is a new file in this folder and no other edit: spec.py runs whatever is registered, the
"unknown section" message lists it (`spec.KINDS`), and `kit.py` has what a kind uses.

A kind lives in the module named for its section (`heat.py` for `[[heat]]`), and documents its format
in that module's docstring. Row order is the kind's `order`: the seven below hold 10 to 70 (envelope
10, size 20, position 30, clearance 40, keepout 50, interface 60, mass 70), so a new kind takes 80 or
more, and a number between two of them puts its rows among theirs. The listing order is the order below
and then alphabetical, so a section registered later is listed last.
"""
from ..registry import autoload

LISTED = ("envelope", "size", "position", "clearance", "keepout", "mass", "interface")
MODULES = autoload(__name__, first=LISTED)
