// SPDX-License-Identifier: LGPL-2.1-or-later
// Stand-in for OCCT's Precision.hxx, which libarea's AreaClipper.cpp includes for Precision::Confusion() alone.
// The values are OCCT's (Precision.hxx: Confusion 1.e-7), as FreeCAD's own src/Base/Precision.h copies them.
#ifndef CAD_AGENT_LIBAREA_PRECISION_HXX
#define CAD_AGENT_LIBAREA_PRECISION_HXX
#include <Base/Precision.h>
using Base::Precision;
#endif
