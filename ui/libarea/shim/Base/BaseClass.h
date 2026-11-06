// SPDX-License-Identifier: LGPL-2.1-or-later
// Stand-in for FreeCAD's src/Base/BaseClass.h, which the Voronoi classes (src/Mod/CAM/App/Voronoi*.h) derive from for
// FreeCAD's run-time type system alone. Nothing here asks a Voronoi object its type, so the macros declare nothing.
#pragma once

namespace Base
{
class BaseClass
{
public:
    BaseClass() = default;
    virtual ~BaseClass() = default;
};
}  // namespace Base

#define TYPESYSTEM_HEADER_WITH_OVERRIDE()
#define TYPESYSTEM_SOURCE(_class_, _parentclass_)
