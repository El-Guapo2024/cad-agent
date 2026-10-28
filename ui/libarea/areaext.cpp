// SPDX-License-Identifier: LGPL-2.1-or-later
//
// cam_areaext: the part of libarea that FreeCAD's Path::Area (src/Mod/CAM/App/Area.cpp) calls in C++ and that
// libarea's own Python binding (pyarea.cpp) does not expose: a CArea's curve list spliced and filtered in place,
// CArea::Clip with Clipper2's ClipType and FillRule, CCurve::Discretize, MakePocketToolpath with a pocket mode, the
// CArea parameters that CAreaConfig saves and applies (tolerance, fit_arcs, accuracy, clipper_scale). It is glue for
// cad_agent/fcshim/_fc_area.py, the Python port of Path::Area; libarea itself is FreeCAD's, unchanged. Its classes are
// module_local so they never clash with pyarea's in the same interpreter; both link the one libarea, so they share
// libarea's static parameters as FreeCAD's area module and PathApp do.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <list>
#include <tuple>
#include <vector>

#include "Area.h"
#include "Curve.h"

namespace py = pybind11;
using namespace heeks;

using VertexTuple = std::tuple<int, double, double, double, double>;

static std::vector<VertexTuple> curve_vertices(const CCurve& c)
{
    std::vector<VertexTuple> out;
    out.reserve(c.m_vertices.size());
    for (const auto& v : c.m_vertices) {
        out.emplace_back(v.m_type, v.m_p.x, v.m_p.y, v.m_c.x, v.m_c.y);
    }
    return out;
}

static void curve_set_vertices(CCurve& c, const std::vector<VertexTuple>& vs)
{
    c.m_vertices.clear();
    for (const auto& t : vs) {
        c.m_vertices.emplace_back(
            std::get<0>(t),
            Point(std::get<1>(t), std::get<2>(t)),
            Point(std::get<3>(t), std::get<4>(t))
        );
    }
}

PYBIND11_MODULE(cam_areaext, m)
{
    m.doc() = "libarea glue for cad_agent's port of FreeCAD's Path::Area";

    py::class_<CCurve>(m, "Curve", py::module_local())
        .def(py::init<>())
        .def(py::init<const CCurve&>())
        .def("append", [](CCurve& c, int type, double x, double y, double cx, double cy) {
            c.append(CVertex(type, Point(x, y), Point(cx, cy)));
        }, py::arg("type"), py::arg("x"), py::arg("y"), py::arg("cx") = 0.0, py::arg("cy") = 0.0)
        .def("append_point", [](CCurve& c, double x, double y) { c.append(CVertex(Point(x, y))); })
        .def("vertices", &curve_vertices)
        .def("set_vertices", &curve_set_vertices)
        .def("num_vertices", [](const CCurve& c) { return c.m_vertices.size(); })
        .def("pop_front", [](CCurve& c) { c.m_vertices.pop_front(); })
        .def("IsClosed", &CCurve::IsClosed)
        .def("IsClockwise", &CCurve::IsClockwise)
        .def("GetArea", &CCurve::GetArea)
        .def("Reverse", &CCurve::Reverse)
        .def("Discretize", &CCurve::Discretize);

    py::class_<CArea>(m, "Area", py::module_local())
        .def(py::init<>())
        .def(py::init<const CArea&>())
        .def("curves", [](const CArea& a) { return std::vector<CCurve>(a.m_curves.begin(), a.m_curves.end()); })
        .def("num_curves", [](const CArea& a) { return a.m_curves.size(); })
        .def("append", &CArea::append)
        .def("splice", [](CArea& a, CArea& other) { a.m_curves.splice(a.m_curves.end(), other.m_curves); })
        .def("clear", [](CArea& a) { a.m_curves.clear(); })
        .def("remove_closed_clockwise", [](CArea& a) {
            // Area::build's Outline: drop the holes
            for (auto it = a.m_curves.begin(), itNext = it; it != a.m_curves.end(); it = itNext) {
                ++itNext;
                if (it->IsClosed() && it->IsClockwise()) {
                    a.m_curves.erase(it);
                }
            }
        })
        .def("reverse_closed_clockwise", [](CArea& a) {
            // Area::addToBuild when projecting: every closed wire counter-clockwise
            for (auto& c : a.m_curves) {
                if (c.IsClosed() && c.IsClockwise()) {
                    c.Reverse();
                }
            }
        })
        .def("Clip", [](CArea& a, int op, const CArea& clip, int fill) {
            a.Clip(static_cast<Clipper2Lib::ClipType>(op), clip, static_cast<Clipper2Lib::FillRule>(fill));
        })
        .def("Offset", &CArea::Offset)
        .def("Thicken", &CArea::Thicken)
        .def("Union", &CArea::Union)
        .def("Subtract", &CArea::Subtract)
        .def("Intersect", &CArea::Intersect)
        .def("Xor", &CArea::Xor)
        .def("Reorder", &CArea::Reorder)
        .def("ClipperNoop", &CArea::ClipperNoop)
        .def("GetArea", &CArea::GetArea, py::arg("always_add") = false)
        .def("GetBox", [](CArea& a) {
            CBox2D box;
            a.GetBox(box);
            return std::make_tuple(box.m_valid, box.m_minxy.x, box.m_minxy.y, box.m_maxxy.x, box.m_maxxy.y);
        })
        .def("MakePocketToolpath", [](const CArea& a, double tool_radius, double extra_offset, double stepover,
                                      bool from_center, int mode, double zig_angle) {
            CAreaPocketParams params(tool_radius, extra_offset, stepover, from_center,
                                     static_cast<PocketMode>(mode), zig_angle);
            CArea out;
            a.MakePocketToolpath(out.m_curves, params);
            return out;
        })
        .def("Split", [](const CArea& a) {
            std::list<CArea> areas;
            a.Split(areas);
            return std::vector<CArea>(areas.begin(), areas.end());
        });

    m.def("get_tolerance", &CArea::get_tolerance);
    m.def("set_tolerance", &CArea::set_tolerance);
    m.def("get_fit_arcs", &CArea::get_fit_arcs);
    m.def("set_fit_arcs", &CArea::set_fit_arcs);
    m.def("get_accuracy", &CArea::get_accuracy);
    m.def("set_accuracy", &CArea::set_accuracy);
    m.def("get_clipper_scale", &CArea::get_clipper_scale);
    m.def("set_clipper_scale", &CArea::set_clipper_scale);
}
