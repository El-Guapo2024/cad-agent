# PlaneGCS, FreeCAD's sketch solver, for the app

`freecad/Sketcher/App/planegcs/` is FreeCAD's solver copied unchanged from FreeCAD at 3160daf1e2b6
(`src/Mod/Sketcher/App/planegcs`, LGPL-2.1-or-later, (c) 2011 Konstantinos Poulios and FreeCAD's
contributors), with `freecad/Sketcher/SketcherGlobal.h`. `shim/` stands in for the few FreeCAD headers it
includes (FCGlobal.h, FCConfig.h, Base/Console.h, Base/Tools.h, the Boost graph wrapper): logging is
dropped and nothing else changes. It needs Eigen 3.4.0 and Boost 1.86 headers and C++23.

Native compile check:

    g++ -std=c++23 -O2 -c -I shim -I <eigen-3.4.0> -I <boost_1_86_0> freecad/Sketcher/App/planegcs/*.cpp
