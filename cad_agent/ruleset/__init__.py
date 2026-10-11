"""Rules, one module each: the place a new check goes.

A module here registers its rules with `registry.register` and nothing else changes. rules.py imports
this package after its own rules, so importing rules (which the runner does) imports every module in
this folder, and the run, the gate and `cad rules` see what each one registered. A module may import
what rules.py defines (it is already loaded by then); it must not be imported by it.

The rules written before step 6 stay in rules.py. A rule from step 6 on is a file here named for what it
judges (`com.py`, `heat.py`), with its docstring saying what it verifies, since `cad rules` prints the
first line.
"""
from ..registry import autoload

MODULES = autoload(__name__)
