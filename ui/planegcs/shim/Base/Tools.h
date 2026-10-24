// SPDX-License-Identifier: LGPL-2.1-or-later
// Stand-in for FreeCAD's Base/Tools.h: PlaneGCS only times its QR decompositions for debug output.
#pragma once
#include <chrono>

namespace Base
{
class TimeElapsed
{
public:
    TimeElapsed() : t(std::chrono::steady_clock::now()) {}
    static double diffTimeF(const TimeElapsed& a, const TimeElapsed& b)
    {
        return std::chrono::duration<double>(b.t - a.t).count();
    }

private:
    std::chrono::steady_clock::time_point t;
};
}  // namespace Base
