"""Stand-in for FreeCAD's Materials module (src/Mod/Material/App): FEM's material object asks MaterialManager for the
library material matching its card to take its UUID. FreeCAD's material library is not here: the manager lists none, so
a FEM material's UUID stays empty (the analysis reads only the card's values)."""


class MaterialManager:
    Materials: dict = {}

    def getMaterial(self, uuid):
        raise LookupError(uuid)
