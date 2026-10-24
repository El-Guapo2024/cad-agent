// SPDX-License-Identifier: LGPL-2.1-or-later
// Stand-in for FreeCAD's Base/Console.h: PlaneGCS writes debug logs and one warning through it. They
// are dropped here; the solver's results do not depend on them.
#pragma once
#include <string>

namespace Base
{
struct ConsoleStub
{
    template<typename... Args>
    void log(const char*, Args&&...) {}
    template<typename... Args>
    void warning(const char*, Args&&...) {}
    template<typename... Args>
    void error(const char*, Args&&...) {}
    template<typename... Args>
    void message(const char*, Args&&...) {}
};
inline ConsoleStub& Console()
{
    static ConsoleStub c;
    return c;
}
}  // namespace Base
