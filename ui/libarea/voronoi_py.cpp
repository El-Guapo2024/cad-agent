// SPDX-License-Identifier: LGPL-2.1-or-later
//
// This file is not MIT. It re-expresses FreeCAD's Python binding of Path.Voronoi (src/Mod/CAM/App/VoronoiPyImp.cpp,
// VoronoiEdgePyImp.cpp, VoronoiCellPyImp.cpp, VoronoiVertexPyImp.cpp, Copyright (c) 2020 sliptonic) in pybind11, and
// keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later version;
// the text is in ../LICENSE. FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6. See ../NOTICE.
//
// cam_voronoi: the module cad_agent/fcshim/top/PathApp.py gives FreeCAD's CAM Python as Path.Voronoi (Diagram, Edge,
// Cell, Vertex), over FreeCAD's own Voronoi classes (upstream/voronoi, unchanged). Each method is its *PyImp.cpp
// counterpart, line for line. What FreeCAD makes in C++ that lives in Python here, a Base.Vector and a Part.Edge, is
// made by the three callables PathApp hands set_factories: vector(x, y, z), line(p0, p1) (Part::GeomLineSegment's
// setPoints and BRepBuilderAPI_MakeEdge) and parabola(location, normal, xdir, focal, u0, u1) (Geom_Parabola,
// Part::GeomArcOfParabola's setRange and BRepBuilderAPI_MakeEdge).
#include <cmath>
#include <iostream>
#include <limits>
#include <map>
#include <numbers>
#include <set>
#include <sstream>

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "Voronoi.h"
#include "VoronoiCell.h"
#include "VoronoiEdge.h"
#include "VoronoiVertex.h"

namespace py = pybind11;
using namespace Path;

namespace
{
py::object makeVector;
py::object makeLine;
py::object makeParabola;

py::object vec(const Base::Vector3d& v)
{
    return makeVector(v.x, v.y, v.z);
}

// The Py classes hold the FreeCAD object, as VoronoiPy holds its Voronoi (PyObjectBase's _pcTwinPointer).
struct EdgePy
{
    std::unique_ptr<VoronoiEdge> e;
};
struct CellPy
{
    std::unique_ptr<VoronoiCell> c;
};
struct VertexPy
{
    std::unique_ptr<VoronoiVertex> v;
};

EdgePy edgePy(Voronoi::diagram_type* dia, const Voronoi::diagram_type::edge_type* e)
{
    return EdgePy {std::make_unique<VoronoiEdge>(dia, e)};
}
CellPy cellPy(Voronoi::diagram_type* dia, const Voronoi::diagram_type::cell_type* c)
{
    return CellPy {std::make_unique<VoronoiCell>(dia, c)};
}
VertexPy vertexPy(Voronoi::diagram_type* dia, const Voronoi::diagram_type::vertex_type* v)
{
    return VertexPy {std::make_unique<VoronoiVertex>(dia, v)};
}

// getVoronoiEdgeFromPy and its siblings
VoronoiEdge* bound(const EdgePy& p)
{
    if (!p.e->isBound()) {
        throw py::type_error("Edge not bound to voronoi diagram");
    }
    return p.e.get();
}
VoronoiCell* bound(const CellPy& p)
{
    if (!p.c->isBound()) {
        throw py::type_error("Cell not bound to voronoi diagram");
    }
    return p.c.get();
}
VoronoiVertex* bound(const VertexPy& p)
{
    if (!p.v->isBound()) {
        throw py::type_error("Vertex not bound to voronoi diagram");
    }
    return p.v.get();
}

// getPointFromPy: a Base.Vector or a Base.Vector2d, both of which have x and y
Voronoi::point_type pointFromPy(const py::handle& obj)
{
    if (!py::hasattr(obj, "x") || !py::hasattr(obj, "y")) {
        throw py::type_error("Points must be Base::Vector or Base::Vector2d");
    }
    return Voronoi::point_type(obj.attr("x").cast<double>(), obj.attr("y").cast<double>());
}

// VoronoiEdgePyImp.cpp's anonymous namespace
Voronoi::point_type pointFromVertex(const Voronoi::vertex_type v)
{
    Voronoi::point_type pt;
    pt.x(v.x());
    pt.y(v.y());
    return pt;
}

Voronoi::point_type orthognalProjection(const Voronoi::point_type& point, const Voronoi::segment_type& segment)
{
    Voronoi::point_type offset;
    {
        offset.x(low(segment).x());
        offset.y(low(segment).y());
    }
    Voronoi::point_type s;
    {
        s.x(high(segment).x() - offset.x());
        s.y(high(segment).y() - offset.y());
    }
    Voronoi::point_type p;
    {
        p.x(point.x() - offset.x());
        p.y(point.y() - offset.y());
    }
    const double proj = (p.x() * s.x() + p.y() * s.y())
        / (s.x() * s.x() + s.y() * s.y() + std::numeric_limits<double>::epsilon());
    Voronoi::point_type pt;
    {
        pt.x(offset.x() + proj * s.x());
        pt.y(offset.y() + proj * s.y());
    }
    return pt;
}

double length(const Voronoi::point_type& p)
{
    return sqrt(p.x() * p.x() + p.y() * p.y());
}

int sideOf(const Voronoi::point_type& p, const Voronoi::segment_type& s)
{
    Voronoi::coordinate_type dxp = p.x() - low(s).x();
    Voronoi::coordinate_type dyp = p.y() - low(s).y();
    Voronoi::coordinate_type dxs = high(s).x() - low(s).x();
    Voronoi::coordinate_type dys = high(s).y() - low(s).y();
    double d = -dxs * dyp + dys * dxp;
    if (d < 0) {
        return -1;
    }
    if (d > 0) {
        return +1;
    }
    return 0;
}

template<typename pt0_type, typename pt1_type>
double distanceBetween(const pt0_type& p0, const pt1_type& p1, double scale)
{
    Voronoi::point_type dist;
    dist.x(p0.x() - p1.x());
    dist.y(p0.y() - p1.y());
    return length(dist) / scale;
}

void addDistanceBetween(const Voronoi::diagram_type::vertex_type* v0, const Voronoi::point_type& p1, py::list* list,
                        double scale)
{
    if (v0) {
        list->append(py::float_(distanceBetween(*v0, p1, scale)));
    }
    else {
        list->append(py::none());
    }
}

void addProjectedDistanceBetween(const Voronoi::diagram_type::vertex_type* v0, const Voronoi::segment_type& segment,
                                 py::list* list, double scale)
{
    if (v0) {
        Voronoi::point_type p0;
        {
            p0.x(v0->x());
            p0.y(v0->y());
        }
        Voronoi::point_type p1 = orthognalProjection(p0, segment);
        list->append(py::float_(distanceBetween(*v0, p1, scale)));
    }
    else {
        list->append(py::none());
    }
}

bool addDistancesToPoint(const VoronoiEdge* edge, Voronoi::point_type p, py::list* list, double scale)
{
    addDistanceBetween(edge->ptr->vertex0(), p, list, scale);
    addDistanceBetween(edge->ptr->vertex1(), p, list, scale);
    return true;
}

bool retrieveDistances(const VoronoiEdge* edge, py::list* list)
{
    const Voronoi::diagram_type::cell_type* c0 = edge->ptr->cell();
    if (c0->contains_point()) {
        return addDistancesToPoint(edge, edge->dia->retrievePoint(c0), list, edge->dia->getScale());
    }
    const Voronoi::diagram_type::cell_type* c1 = edge->ptr->twin()->cell();
    if (c1->contains_point()) {
        return addDistancesToPoint(edge, edge->dia->retrievePoint(c1), list, edge->dia->getScale());
    }
    // at this point both cells are sourced from segments and it does not matter if we use c0 or c1
    Voronoi::segment_type segment = edge->dia->retrieveSegment(c0);
    addProjectedDistanceBetween(edge->ptr->vertex0(), segment, list, edge->dia->getScale());
    addProjectedDistanceBetween(edge->ptr->vertex1(), segment, list, edge->dia->getScale());
    return false;
}

bool pointsMatch(const Voronoi::point_type& p0, const Voronoi::point_type& p1, double scale)
{
    return 1e-6 > distanceBetween(p0, p1, scale);
}

bool isPointOnSegment(const Voronoi::point_type& point, const Voronoi::segment_type& segment, double scale)
{
    return pointsMatch(point, low(segment), scale) || pointsMatch(point, high(segment), scale);
}

template<typename T>
py::object makeLineSegment(const VoronoiEdge* e, const T& p0, double z0, const T& p1, double z1)
{
    return makeLine(vec(e->dia->scaledVector(p0, z0)), vec(e->dia->scaledVector(p1, z1)));
}

template<typename T>
bool sameIndex(const T& l, const T& r)
{
    return l->dia == r->dia && l->index == r->index;
}

// VoronoiPyImp.cpp's colorExterior callback
using exterior_map_t = std::map<uintptr_t, bool>;
using coordinate_map_t = std::map<int32_t, std::set<int32_t>>;

bool callbackWithVertex(Voronoi::diagram_type* dia, const py::object& callback,
                        const Voronoi::diagram_type::vertex_type* v, exterior_map_t& cache)
{
    bool rc = false;
    if (v->color() == 0) {
        auto it = cache.find(uintptr_t(v));
        if (it == cache.end()) {
            py::object result = callback(vertexPy(dia, v));   // a Python exception propagates, as FreeCAD's bail
            rc = result.ptr() == Py_True;
            cache.insert(exterior_map_t::value_type(uintptr_t(v), rc));
        }
        else {
            rc = it->second;
        }
    }
    return rc;
}
}  // namespace

namespace Path
{
// VoronoiPy: the name Voronoi.h makes a friend of, for vd
class VoronoiPy
{
public:
    static Voronoi::diagram_type* vd(Voronoi& vo)
    {
        return vo.vd;
    }

    static void colorExterior(Voronoi& vo, Voronoi::color_type color, const py::object& callback)
    {
        vo.colorExterior(color);
        if (callback.is_none()) {
            return;
        }
        exterior_map_t cache;
        coordinate_map_t pts;
        for (auto e = vo.vd->edges().begin(); e != vo.vd->edges().end(); ++e) {
            if (e->is_finite() && e->color() == 0) {
                const Voronoi::diagram_type::vertex_type* v0 = e->vertex0();
                const Voronoi::diagram_type::vertex_type* v1 = e->vertex1();
                if (callbackWithVertex(vo.vd, callback, v0, cache)
                    && callbackWithVertex(vo.vd, callback, v1, cache)) {
                    vo.colorExterior(&(*e), color);
                }
                else if (callbackWithVertex(vo.vd, callback, v1, cache)) {
                    if (pts.empty()) {
                        for (auto s = vo.vd->segments.begin(); s != vo.vd->segments.end(); ++s) {
                            pts[low(*s).x()].insert(low(*s).y());
                            pts[high(*s).x()].insert(high(*s).y());
                        }
                    }
                    auto ys = pts.find(int32_t(v0->x()));
                    if (ys != pts.end() && ys->second.find(v0->y()) != ys->second.end()) {
                        vo.colorExterior(&(*e), color);
                    }
                }
            }
        }
    }
};
}  // namespace Path

namespace
{
py::object edgeToShape(const EdgePy& self, double z0, py::object z1obj, bool dbg)
{
    double z1 = z1obj.is_none() ? std::numeric_limits<double>::max() : z1obj.cast<double>();
    if (z1 == std::numeric_limits<double>::max()) {
        z1 = z0;
    }
    VoronoiEdge* e = self.e.get();
    if (e->isBound()) {
        if (e->ptr->is_linear()) {
            if (e->ptr->is_finite()) {
                auto v0 = e->ptr->vertex0();
                auto v1 = e->ptr->vertex1();
                if (v0 && v1) {
                    return makeLineSegment(e, *v0, z0, *v1, z1);
                }
            }
            else {
                // infinite linear, need to clip somehow
                const Voronoi::diagram_type::cell_type* c0 = e->ptr->cell();
                const Voronoi::diagram_type::cell_type* c1 = e->ptr->twin()->cell();
                Voronoi::point_type origin;
                Voronoi::point_type direction;
                if (c0->contains_point() && c1->contains_point()) {
                    Voronoi::point_type p0 = e->dia->retrievePoint(c0);
                    Voronoi::point_type p1 = e->dia->retrievePoint(c1);
                    origin.x((p0.x() + p1.x()) / 2.);
                    origin.y((p0.y() + p1.y()) / 2.);
                    direction.x(p0.y() - p1.y());
                    direction.y(p1.x() - p0.x());
                }
                else {
                    origin = c0->contains_segment() ? e->dia->retrievePoint(c1) : e->dia->retrievePoint(c0);
                    Voronoi::segment_type segment = c0->contains_segment() ? e->dia->retrieveSegment(c0)
                                                                           : e->dia->retrieveSegment(c1);
                    Voronoi::coordinate_type dx = high(segment).x() - low(segment).x();
                    Voronoi::coordinate_type dy = high(segment).y() - low(segment).y();
                    if ((low(segment) == origin) ^ c0->contains_point()) {
                        direction.x(dy);
                        direction.y(-dx);
                    }
                    else {
                        direction.x(-dy);
                        direction.y(dx);
                    }
                }
                double k = 2.5;  // <-- need something smarter here
                Voronoi::point_type begin;
                Voronoi::point_type end;
                if (e->ptr->vertex0()) {
                    begin.x(e->ptr->vertex0()->x());
                    begin.y(e->ptr->vertex0()->y());
                }
                else {
                    begin.x(origin.x() - direction.x() * k);
                    begin.y(origin.y() - direction.y() * k);
                }
                if (e->ptr->vertex1()) {
                    end.x(e->ptr->vertex1()->x());
                    end.y(e->ptr->vertex1()->y());
                }
                else {
                    end.x(origin.x() + direction.x() * k);
                    end.y(origin.y() + direction.y() * k);
                }
                return makeLineSegment(e, begin, z0, end, z1);
            }
        }
        else {
            // parabolic curve, which is always formed by a point and an edge
            Voronoi::point_type point = e->ptr->cell()->contains_point()
                ? e->dia->retrievePoint(e->ptr->cell())
                : e->dia->retrievePoint(e->ptr->twin()->cell());
            Voronoi::segment_type segment = e->ptr->cell()->contains_point()
                ? e->dia->retrieveSegment(e->ptr->twin()->cell())
                : e->dia->retrieveSegment(e->ptr->cell());
            // the location is the mid point between the normal on the segment through point
            // this is only the mid point of the segment if the parabola is symmetric

            if (isPointOnSegment(point, segment, e->dia->getScale())) {
                return makeLineSegment(e, low(segment), z0, high(segment), z1);
            }

            Voronoi::point_type loc;
            {
                Voronoi::point_type proj = orthognalProjection(point, segment);
                // the location is the mid point between the projection on the segment and the point
                loc.x((proj.x() + point.x()) / 2);
                loc.y((proj.y() + point.y()) / 2);
            }
            Voronoi::point_type axis;
            {
                axis.x(point.x() - loc.x());
                axis.y(point.y() - loc.y());
            }
            Voronoi::segment_type xaxis;
            {
                xaxis.low(point);
                xaxis.high(loc);
            }

            // determine distances of the end points from the x-axis, those are the parameters for
            // the arc of the parabola in the horizontal plane
            auto pt0 = pointFromVertex(*e->ptr->vertex0());
            auto pt1 = pointFromVertex(*e->ptr->vertex1());
            Voronoi::point_type pt0x = orthognalProjection(pt0, xaxis);
            Voronoi::point_type pt1x = orthognalProjection(pt1, xaxis);
            double dist0 = distanceBetween(pt0, pt0x, e->dia->getScale()) * sideOf(pt0, xaxis);
            double dist1 = distanceBetween(pt1, pt1x, e->dia->getScale()) * sideOf(pt1, xaxis);
            if (dist1 < dist0) {
                // if the parabola is traversed in the opposite direction we have to swap the parameters
                dist0 = -dist0;
                dist1 = -dist1;
            }

            // at this point we have the arc of the parabola in the horizontal plane, but we still
            // need to tilt the parabola if the z-coordinates of the end points are not identical
            auto p0 = e->dia->scaledVector(pt0, z0);
            auto p1 = e->dia->scaledVector(pt1, z1);
            auto p_ = p0 + e->dia->scaledVector(axis, 0);
            auto norm = ((p_ - p0).Cross(p1 - p0)).Normalize();

            // the parabola is going to be tilted, need to figure out the new location and the new
            // focal length
            double zx = z0 - (dist0 / (dist0 - dist1)) * (z0 - z1);
            auto locn = e->dia->scaledVector(loc, zx);
            auto xdir = e->dia->scaledVector(axis, zx);

            double focal;
            if (z0 == z1) {
                // focal length if parabola in the xy-plane is simply half the distance between the
                // point and segment - aka the distance between point and location, aka the length of axis
                focal = length(axis) / e->dia->getScale();
                if (dbg) {
                    std::cerr << "focal = " << length(axis) << "/" << e->dia->getScale() << "\n";
                }
            }
            else {
                // if the parabola is not in the xy-plane we need to find the
                // (x,y) coordinates of a point on the parabola in the parabola's
                // coordinate system.
                // see:
                // http://amsi.org.au/ESA_Senior_Years/SeniorTopic2/2a/2a_2content_10.html
                // note that above website uses Y as the symmetry axis of the parabola whereas
                // OCC uses X as the symmetry axis. The math below is in the website's system.
                // We already know 2 points on the parabola (p0 and p1), we know their X values -
                // those are the parameters for the arc of the parabola in the horizontal plane
                // (dist0 and dist1) - we need to figure out their Y values. Note that since we are
                // in the parabola's coordinate system we have to translate the points to the
                // parabola's location.
                double flenX0 = sqrt(dist0 * dist0 + (z0 - zx) * (z0 - zx));
                double flenX1 = sqrt(dist1 * dist1 + (zx - z1) * (zx - z1));
                double flenX;
                double flenY;
                // if one of the points is the location, the other one has to be used to
                // determine the focal length - we avoid rounding errors by using the bigger one
                if (fabs(dist0) > fabs(dist1)) {
                    flenX = flenX0;
                    flenY = distanceBetween(loc, pt0x, e->dia->getScale());
                }
                else {
                    flenX = flenX1;
                    flenY = distanceBetween(loc, pt1x, e->dia->getScale());
                }
                focal = (flenX * flenX) / (4 * fabs(flenY));
                if (dbg) {
                    std::cerr << "  focal = (" << flenX << " * " << flenX << ") / (4 * fabs(" << flenY << "))\n";
                }
                // and we need to transform the parameters for the arc of the parabola to the new
                // coordinate system
                dist0 = dist0 >= 0 ? flenX0 : -flenX0;
                dist1 = dist1 >= 0 ? flenX1 : -flenX1;
            }
            return makeParabola(py::make_tuple(locn.x, locn.y, locn.z), py::make_tuple(norm.x, norm.y, norm.z),
                                py::make_tuple(xdir.x, xdir.y, 0.0), focal, dist0, dist1);
        }
    }
    return py::none();
}

py::object segmentAngle(const EdgePy& self)
{
    using std::numbers::pi;
    VoronoiEdge* e = bound(self);
    if (e->ptr->cell()->contains_segment() && e->ptr->twin()->cell()->contains_segment()) {
        int i0 = e->ptr->cell()->source_index() - e->dia->points.size();
        int i1 = e->ptr->twin()->cell()->source_index() - e->dia->points.size();
        if (e->dia->segmentsAreConnected(i0, i1)) {
            double a0 = e->dia->angleOfSegment(i0);
            double a1 = e->dia->angleOfSegment(i1);
            double a = a0 - a1;
            if (a > pi / 2) {
                a -= pi;
            }
            else if (a < -pi / 2) {
                a += pi;
            }
            return py::float_(a);
        }
    }
    return py::none();
}

std::string edgeRepr(const EdgePy& self)
{
    std::stringstream ss;
    ss.precision(5);
    ss << "VoronoiEdge(";
    VoronoiEdge* e = self.e.get();
    if (e->isBound()) {
        const Voronoi::diagram_type::vertex_type* v0 = e->ptr->vertex0();
        const Voronoi::diagram_type::vertex_type* v1 = e->ptr->vertex1();
        if (v0) {
            ss << "[" << (v0->x() / e->dia->getScale()) << ", " << (v0->y() / e->dia->getScale()) << "]";
        }
        else {
            ss << "[~]";
        }
        ss << ", ";
        if (v1) {
            ss << "[" << (v1->x() / e->dia->getScale()) << ", " << (v1->y() / e->dia->getScale()) << "]";
        }
        else {
            ss << "[~]";
        }
    }
    ss << ")";
    return ss.str();
}

const char* categoryName(const VoronoiCell* c)
{
    switch (c->ptr->source_category()) {
        case boost::polygon::SOURCE_CATEGORY_SINGLE_POINT:
            return "SINGLE_POINT";
        case boost::polygon::SOURCE_CATEGORY_SEGMENT_START_POINT:
            return "SEGMENT_START_POINT";
        case boost::polygon::SOURCE_CATEGORY_SEGMENT_END_POINT:
            return "SEGMENT_END_POINT";
        case boost::polygon::SOURCE_CATEGORY_INITIAL_SEGMENT:
            return "INITIAL_SEGMENT";
        case boost::polygon::SOURCE_CATEGORY_REVERSE_SEGMENT:
            return "REVERSE_SEGMENT";
        case boost::polygon::SOURCE_CATEGORY_GEOMETRY_SHIFT:
            return "GEOMETRY_SHIFT";
        case boost::polygon::SOURCE_CATEGORY_BITMASK:
            return "BITMASK";
    }
    return "";
}
}  // namespace

PYBIND11_MODULE(cam_voronoi, m)
{
    m.def("set_factories", [](py::object vector, py::object line, py::object parabola) {
        makeVector = vector;
        makeLine = line;
        makeParabola = parabola;
    });

    py::class_<Voronoi>(m, "Diagram")
        .def(py::init([](py::object scale) {
                 auto vo = std::make_unique<Voronoi>();
                 if (!scale.is_none()) {
                     vo->setScale(scale.cast<double>());
                 }
                 return vo;
             }),
             py::arg("scale") = py::none())
        .def("__repr__",
             [](Voronoi& vo) {
                 std::stringstream ss;
                 ss.precision(5);
                 ss << "VoronoiDiagram("
                    << "{" << vo.numSegments() << ", " << vo.numPoints() << "}"
                    << " -> "
                    << "{" << vo.numCells() << ", " << vo.numEdges() << ", " << vo.numVertices() << "}"
                    << ")";
                 return ss.str();
             })
        .def("addPoint", [](Voronoi& vo, py::object p) { vo.addPoint(pointFromPy(p)); })
        .def("addSegment",
             [](Voronoi& vo, py::object b, py::object e) {
                 auto p0 = pointFromPy(b);
                 auto p1 = pointFromPy(e);
                 vo.addSegment(Voronoi::segment_type(p0, p1));
             })
        .def("construct", &Voronoi::construct)
        .def("numCells", &Voronoi::numCells)
        .def("numEdges", &Voronoi::numEdges)
        .def("numVertices", &Voronoi::numVertices)
        .def("numPoints", [](Voronoi& vo) { return long(VoronoiPy::vd(vo)->points.size()); })
        .def("numSegments", [](Voronoi& vo) { return long(VoronoiPy::vd(vo)->segments.size()); })
        .def_property_readonly("Vertices",
                               [](Voronoi& vo) {
                                   py::list list;
                                   for (int i = 0; i < vo.numVertices(); ++i) {
                                       list.append(VertexPy {std::unique_ptr<VoronoiVertex>(vo.create<VoronoiVertex>(i))});
                                   }
                                   return list;
                               })
        .def_property_readonly("Edges",
                               [](Voronoi& vo) {
                                   py::list list;
                                   for (int i = 0; i < vo.numEdges(); ++i) {
                                       list.append(EdgePy {std::unique_ptr<VoronoiEdge>(vo.create<VoronoiEdge>(i))});
                                   }
                                   return list;
                               })
        .def_property_readonly("Cells",
                               [](Voronoi& vo) {
                                   py::list list;
                                   for (int i = 0; i < vo.numCells(); ++i) {
                                       list.append(CellPy {std::unique_ptr<VoronoiCell>(vo.create<VoronoiCell>(i))});
                                   }
                                   return list;
                               })
        .def("colorExterior", &VoronoiPy::colorExterior, py::arg("color"), py::arg("callback") = py::none())
        .def("colorTwins", &Voronoi::colorTwins)
        .def("colorColinear", &Voronoi::colorColinear, py::arg("color"), py::arg("degree") = 10.)
        .def("resetColor", &Voronoi::resetColor)
        .def(
            "getPoints",
            [](Voronoi& vo, double z) {
                py::list list;
                auto* vd = VoronoiPy::vd(vo);
                for (auto it = vd->points.begin(); it != vd->points.end(); ++it) {
                    list.append(vec(vd->scaledVector(*it, z)));
                }
                return list;
            },
            py::arg("z") = 0.0)
        .def(
            "getSegments",
            [](Voronoi& vo, double z) {
                py::list list;
                auto* vd = VoronoiPy::vd(vo);
                for (auto it = vd->segments.begin(); it != vd->segments.end(); ++it) {
                    list.append(py::make_tuple(vec(vd->scaledVector(low(*it), z)), vec(vd->scaledVector(high(*it), z))));
                }
                return list;
            },
            py::arg("z") = 0.0);

    py::class_<EdgePy>(m, "Edge")
        .def(py::init([]() { return EdgePy {std::make_unique<VoronoiEdge>()}; }))
        .def("__repr__", &edgeRepr)
        .def("__eq__", [](const EdgePy& l, py::object r) {
            return py::isinstance<EdgePy>(r) && sameIndex(l.e, r.cast<const EdgePy&>().e);
        })
        .def("__ne__", [](const EdgePy& l, py::object r) {
            return !(py::isinstance<EdgePy>(r) && sameIndex(l.e, r.cast<const EdgePy&>().e));
        })
        .def_property_readonly("Index", [](const EdgePy& s) { return s.e->isBound() ? long(s.e->dia->index(s.e->ptr)) : -1L; })
        .def_property(
            "Color",
            [](const EdgePy& s) { return s.e->isBound() ? std::size_t(s.e->ptr->color() & Voronoi::ColorMask) : 0; },
            [](const EdgePy& s, long color) {
                if (!s.e->isBound()) {
                    throw py::type_error("Edge not bound to voronoi diagram");
                }
                s.e->ptr->color(color & Voronoi::ColorMask);
            })
        .def_property_readonly("Vertices",
                               [](const EdgePy& s) {
                                   py::list list;
                                   VoronoiEdge* e = s.e.get();
                                   if (e->isBound()) {
                                       auto v0 = e->ptr->vertex0();
                                       auto v1 = e->ptr->vertex1();
                                       list.append(v0 ? py::cast(vertexPy(e->dia, v0)) : py::none());
                                       list.append(v1 ? py::cast(vertexPy(e->dia, v1)) : py::none());
                                   }
                                   return list;
                               })
        .def_property_readonly("Twin", [](const EdgePy& s) { auto e = bound(s); return edgePy(e->dia, e->ptr->twin()); })
        .def_property_readonly("Next", [](const EdgePy& s) { auto e = bound(s); return edgePy(e->dia, e->ptr->next()); })
        .def_property_readonly("Prev", [](const EdgePy& s) { auto e = bound(s); return edgePy(e->dia, e->ptr->prev()); })
        .def_property_readonly("RotNext", [](const EdgePy& s) { auto e = bound(s); return edgePy(e->dia, e->ptr->rot_next()); })
        .def_property_readonly("RotPrev", [](const EdgePy& s) { auto e = bound(s); return edgePy(e->dia, e->ptr->rot_prev()); })
        .def_property_readonly("Cell", [](const EdgePy& s) { auto e = bound(s); return cellPy(e->dia, e->ptr->cell()); })
        .def("isFinite", [](const EdgePy& s) { return bound(s)->ptr->is_finite(); })
        .def("isInfinite", [](const EdgePy& s) { return bound(s)->ptr->is_infinite(); })
        .def("isLinear", [](const EdgePy& s) { return bound(s)->ptr->is_linear(); })
        .def("isCurved", [](const EdgePy& s) { return bound(s)->ptr->is_curved(); })
        .def("isPrimary", [](const EdgePy& s) { return bound(s)->ptr->is_primary(); })
        .def("isSecondary", [](const EdgePy& s) { return bound(s)->ptr->is_secondary(); })
        .def("isBorderline",
             [](const EdgePy& s) {
                 VoronoiEdge* e = bound(s);
                 if (e->isBound() && !e->ptr->is_linear()) {
                     Voronoi::point_type point = e->ptr->cell()->contains_point()
                         ? e->dia->retrievePoint(e->ptr->cell())
                         : e->dia->retrievePoint(e->ptr->twin()->cell());
                     Voronoi::segment_type segment = e->ptr->cell()->contains_point()
                         ? e->dia->retrieveSegment(e->ptr->twin()->cell())
                         : e->dia->retrieveSegment(e->ptr->cell());
                     return isPointOnSegment(point, segment, e->dia->getScale());
                 }
                 return false;
             })
        .def("toShape", &edgeToShape, py::arg("z0") = 0.0, py::arg("z1") = py::none(), py::arg("dbg") = false)
        .def("getDistances",
             [](const EdgePy& s) {
                 py::list list;
                 retrieveDistances(bound(s), &list);
                 return list;
             })
        .def("getSegmentAngle", &segmentAngle);

    py::class_<CellPy>(m, "Cell")
        .def(py::init([]() { return CellPy {std::make_unique<VoronoiCell>()}; }))
        .def("__repr__",
             [](const CellPy& s) {
                 std::stringstream ss;
                 ss.precision(5);
                 ss << "VoronoiCell(";
                 if (s.c->isBound()) {
                     ss << s.c->ptr->source_category() << ":" << s.c->ptr->source_index();
                 }
                 ss << ")";
                 return ss.str();
             })
        .def("__eq__", [](const CellPy& l, py::object r) {
            return py::isinstance<CellPy>(r) && sameIndex(l.c, r.cast<const CellPy&>().c);
        })
        .def("__ne__", [](const CellPy& l, py::object r) {
            return !(py::isinstance<CellPy>(r) && sameIndex(l.c, r.cast<const CellPy&>().c));
        })
        .def_property_readonly("Index", [](const CellPy& s) { return s.c->isBound() ? long(s.c->dia->index(s.c->ptr)) : -1L; })
        .def_property(
            "Color",
            [](const CellPy& s) { return s.c->isBound() ? std::size_t(s.c->ptr->color() & Voronoi::ColorMask) : 0; },
            [](const CellPy& s, long color) {
                if (!s.c->isBound()) {
                    throw py::type_error("Cell not bound to voronoi diagram");
                }
                s.c->ptr->color(color & Voronoi::ColorMask);
            })
        .def_property_readonly("SourceIndex", [](const CellPy& s) { return long(bound(s)->ptr->source_index()); })
        .def_property_readonly("SourceCategory", [](const CellPy& s) { return long(bound(s)->ptr->source_category()); })
        .def_property_readonly("SourceCategoryName", [](const CellPy& s) { return std::string(categoryName(bound(s))); })
        .def_property_readonly("IncidentEdge", [](const CellPy& s) { auto c = bound(s); return edgePy(c->dia, c->ptr->incident_edge()); })
        .def("containsPoint", [](const CellPy& s) { return bound(s)->ptr->contains_point(); })
        .def("containsSegment", [](const CellPy& s) { return bound(s)->ptr->contains_segment(); })
        .def("isDegenerate", [](const CellPy& s) { return bound(s)->ptr->is_degenerate(); })
        .def(
            "getSource",
            [](const CellPy& s, double z) -> py::object {
                VoronoiCell* c = bound(s);
                if (c->ptr->contains_point()) {
                    return vec(c->dia->scaledVector(c->dia->retrievePoint(c->ptr), z));
                }
                Voronoi::segment_type seg = c->dia->retrieveSegment(c->ptr);
                py::list list;
                list.append(vec(c->dia->scaledVector(low(seg), z)));
                list.append(vec(c->dia->scaledVector(high(seg), z)));
                return list;
            },
            py::arg("z") = 0.0);

    py::class_<VertexPy>(m, "Vertex")
        .def(py::init([]() { return VertexPy {std::make_unique<VoronoiVertex>()}; }))
        .def("__repr__",
             [](const VertexPy& s) {
                 std::stringstream ss;
                 ss.precision(5);
                 ss << "VoronoiVertex(";
                 if (s.v->isBound()) {
                     ss << "[" << (s.v->ptr->x() / s.v->dia->getScale()) << ", "
                        << (s.v->ptr->y() / s.v->dia->getScale()) << "]";
                 }
                 ss << ")";
                 return ss.str();
             })
        .def("__eq__", [](const VertexPy& l, py::object r) {
            return py::isinstance<VertexPy>(r) && sameIndex(l.v, r.cast<const VertexPy&>().v);
        })
        .def("__ne__", [](const VertexPy& l, py::object r) {
            return !(py::isinstance<VertexPy>(r) && sameIndex(l.v, r.cast<const VertexPy&>().v));
        })
        .def_property_readonly("Index", [](const VertexPy& s) { return s.v->isBound() ? long(s.v->dia->index(s.v->ptr)) : -1L; })
        .def_property(
            "Color",
            [](const VertexPy& s) { return s.v->isBound() ? std::size_t(s.v->ptr->color() & Voronoi::ColorMask) : 0; },
            [](const VertexPy& s, long color) {
                if (!s.v->isBound()) {
                    throw py::type_error("Vertex not bound to voronoi diagram");
                }
                s.v->ptr->color(color & Voronoi::ColorMask);
            })
        .def_property_readonly("X", [](const VertexPy& s) { auto v = bound(s); return v->ptr->x() / v->dia->getScale(); })
        .def_property_readonly("Y", [](const VertexPy& s) { auto v = bound(s); return v->ptr->y() / v->dia->getScale(); })
        .def_property_readonly("IncidentEdge", [](const VertexPy& s) { auto v = bound(s); return edgePy(v->dia, v->ptr->incident_edge()); })
        .def(
            "toPoint",
            [](const VertexPy& s, double z) -> py::object {
                VoronoiVertex* v = s.v.get();
                if (v->isBound()) {
                    return makeVector(v->ptr->x() / v->dia->getScale(), v->ptr->y() / v->dia->getScale(), z);
                }
                return py::none();
            },
            py::arg("z") = 0.0);
}
