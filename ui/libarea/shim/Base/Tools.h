// SPDX-License-Identifier: LGPL-2.1-or-later
// Stand-in for FreeCAD's src/Base/Tools.h (Qt and more): the two templates Base/Vector3D.cpp and Voronoi.cpp use from
// it, as FreeCAD 3160daf1e2b6 writes them.
#pragma once
#include <algorithm>
#include <numbers>

namespace Base
{
template<class T>
inline T clamp(T num, T lower, T upper)
{
    return std::clamp<T>(num, lower, upper);
}

template<class T>
constexpr T toRadians(T degrees)
{
    constexpr auto degToRad = std::numbers::pi_v<T> / T(180);
    return degrees * degToRad;
}
}  // namespace Base
