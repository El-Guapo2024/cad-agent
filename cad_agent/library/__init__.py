"""The part library: parts a project copies in, each with where its numbers came from.

A machine is made of parts nobody here draws: rails, motors, extrusions, bearings, fasteners. A bought part with no
source is rejected (bought.py), a dimension remembered is how an assembly passes every check and does not fit, and a
mass or a temperature rating that nobody states is unknown to the rules of step 6. The library is how a design
starts to carry those: `cad lib use <project> <entry>` copies a part into the project's bought/ with the contract
keys of bought.py filled in from the sources, and after that the project is on its own.

    catalog.toml    what the repo ships, one table a part, every number beside its source (catalog.py describes it)
    gen/            the generators: parts the repo draws itself, from the numbers the catalog gives it
    catalog.py      reading the catalog and the user's own entries; what an entry becomes in a project
    store.py        the user's store of vendor files (`$CAD_LIBRARY`, else ~/.cad-agent/library), kept by hash
    use.py          `use`: the files that go into a project
    check.py        `check`: hashes against sidecars, pins and the catalog
    cli.py          `cad lib ls | info | add | use | check | fetch`

Three rules the library keeps, because they are what make it safe to copy from:

  A vendor's STEP file is never in the repo. The catalog pins where one can be had and what it must hash to; `fetch`
  downloads it into the user's store only where its licence lets the repo do that (CC-BY and the like, with the
  credit carried into the sidecar), and says to download it by hand and `add` it where it does not. A file that does
  not hash to its pin is refused, and is never written over anything.

  A number with no source is not in the catalog. What needs it is UNCHECKED: a part with no declared mass leaves the
  centre-of-mass rule unable to judge, a part with no rating leaves a heat zone unable to judge, and a dimension no
  maker publishes makes the part unconfirmed (the provenance rule says so) instead of being guessed.

  A project reads only its own tree. `use` copies the file or writes a module that holds the numbers, pinned by hash,
  so `cad verify`, the build cache, CI and the eval scorer never read the store or the catalog, and a verdict does not
  move when the library does.

The commands and the catalog import nothing from the CAD kernel, so `cad lib ls` answers at once; only the generators
(gen/) and the parts built from them do.
"""
