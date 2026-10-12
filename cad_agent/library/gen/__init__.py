"""The generators: parts the repo draws itself, from numbers a maker's page gives.

A generator is a function that takes every dimension it draws as an argument, with no default for one: the numbers
and where each came from live in the catalog (cad_agent/library/catalog.toml), and `cad lib use` writes them into
the project's own module, so the project holds what its part was built from and the generator holds none of it.
What a generator does that no source says (the gap an envelope keeps between a block and its rail) is an
argument too, and the catalog lists it apart from the dimensions, as a choice of the model.

    mgn          the HIWIN MGN rail and carriage, envelopes
    extrusion    aluminium T-slot profiles: the real section (exact) and the box that stands for it (envelope)
    nema         a stepper motor of a NEMA frame, an envelope
    gt2          a smooth GT2 idler pulley, an envelope

These import the CAD kernel, unlike the rest of the library, and are imported only when a project builds a part
that was copied from one. verify.engine_hash covers this folder, so a change here changes every verdict that rests
on a generated part, as a change to a rule does. The evals' given files are drawn by the same functions, with the
numbers their own scripts hold, and tests/test_library.py holds each of those files to the bytes it had.
"""
