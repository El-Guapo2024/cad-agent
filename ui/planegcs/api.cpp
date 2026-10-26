// SPDX-License-Identifier: LGPL-2.1-or-later
//
// Flat C API over the Sketcher port (sketch.h), for ctypes (cad_agent/planegcs.py) and for
// WebAssembly (ui/src/planegcs.ts). Sketches come in and results go out as JSON strings.
//
// A sketch is {"geometry": [G, ...], "constraints": [C, ...], "options": {...}} with
//   G = {"type": "Point", "at": [x, y]}
//     | {"type": "LineSegment", "start": [x, y], "end": [x, y]}
//     | {"type": "Circle", "center": [x, y], "radius": r}
//     | {"type": "ArcOfCircle", "center": [x, y], "radius": r, "start_angle": a1, "end_angle": a2}
//     | {"type": "Ellipse", "center": [x, y], "major_radius": a, "minor_radius": b, "x_axis": [dx, dy]}
//     | {"type": "ArcOfEllipse", ...the Ellipse's keys, "start_angle": u1, "end_angle": u2}
//     | {"type": "ArcOfHyperbola", ...the same keys as ArcOfEllipse}
//     | {"type": "ArcOfParabola", "center": [x, y] (the vertex), "focal": f, "x_axis": [dx, dy],
//        "start_angle": u1, "end_angle": u2}
//     | {"type": "BSplineCurve", "poles": [[x, y], ...], "weights": [w, ...] (default 1),
//        "knots": [k, ...], "mults": [m, ...], "degree": d, "periodic": false}
//   each with "construction": true|false (default false) and "layer": 0|1|2 (default 0; the
//   Sketcher's Gui-only visual layer, carried through untouched). A conic's x_axis is Part's XAxis (the
//   major axis, towards the first focus; a parabola's axis, towards its focus), and its angles are
//   the trim parameters of the conic (FirstParameter, LastParameter), as Part.ArcOfEllipse(ellipse,
//   u1, u2) takes them; the conics are built as Part's Python makes them (Part.Ellipse(center, a,
//   b) then .XAxis; Part.Hyperbola() and Part.Parabola() then .Center, the radii or .Focal, and
//   .XAxis). A B-spline is Part.BSplineCurve(poles, mults, knots, periodic, degree, weights); its
//   weights are written back only while they differ (Geom_BSplineCurve's rational flag), else 1.
//   The conic arcs are written with "start_point" and "end_point" as well. Arcs run counter-clockwise from
//   start_angle to end_angle (radians), as FreeCAD's sketch arcs do. Part's Python constructor
//   arguments are accepted too: {"type": "LineSegment", "args": [[x1, y1], [x2, y2]]},
//   {"type": "Circle", "args": [[cx, cy], [0, 0, 1], r]}, {"type": "ArcOfCircle",
//   "args": [[[cx, cy], [0, 0, 1], r], a1, a2]} (Part.ArcOfCircle(Part.Circle(...), a1, a2)),
//   {"type": "Point", "args": [[x, y]]}; only the normal +Z is supported.
//   C = {"type": "DistanceX", "args": [0, 1, 0, 2], "value": 40.0, "driving": true,
//        "active": true, "name": "", "orientation": flags}
//   : Sketcher.Constraint's Python argument list after the type, the value (if any) last and kept
//   apart. driving false makes a reference constraint; orientation (FreeCAD's
//   ConstraintOrientations) is computed from the geometry when absent, as SketchObject does.
//   Without "value", "args" is the whole Python list, written as an array ["Distance", 0, 5.0]
//   or as {"type", "args"}: integers (no '.' or exponent) are Python ints, the rest floats, and
//   trailing booleans are activated/driving, dispatched exactly as ConstraintPy::PyInit does.
//   InternalAlignment constraints are written as Python writes them, with the alignment in the
//   type: ["InternalAlignment:EllipseMajorDiameter", line, ellipse], ["InternalAlignment:
//   EllipseFocus1", point, 1, ellipse], ["InternalAlignment:BSplineControlPoint", circle, 3,
//   spline, index]; and "Weight" (a pole circle's weight) as ["Weight", circle, w].
// "external": [G, ...] is the sketch's external geometry (SketchObject's ExternalGeo after the H and V
//   axes): GeoId -3, -4, ... in that order, fixed for the solver as Sketch::setUpSketch makes it.
// options: {"solver": "DogLeg"|"LevenbergMarquardt"|"BFGS",
//           "recalculate_initial_solution_while_moving_point": bool}
//
// A result is
//   {"status": "solved"|"failed"|"conflicting"|"redundant"|"malformed" (from SketchObject.solve()'s
//    code: Success, SolverError, ConflictingConstraints or Overconstrained, RedundantConstraints,
//    MalformedConstraints), "status_code" (that code: 0, -1, -3/-4, -2, -5), "status_name",
//    "solver_status" (GCS: 0 success, 1 converged, 2 failed, 3 invalid), "dof",
//    "fully_constrained", "conflicting", "redundant", "partially_redundant", "malformed"
//    (constraint indices from 0; FreeCAD's messages count from 1), "geometry" (the solver's,
//    which the Sketcher draws), "stored_geometry" (the Geometry property: FreeCAD writes the
//    solution there only on success), "constraints": [{"type", "value", "orientation",
//    "driving", "active"}] (reference values measured, tangency/perpendicularity values as
//    locked on adding), "dependent": [[geoId, pos, index]...], "dependency_groups"}
//   or {"error": "..."}.
//
// Stateless: pgcs_solve(sketch) solves; with "drags": [{"geo": g, "pos": p, "to": [x, y],
// "relative": false}, ...] each drag is then applied as SketchObject.moveGeometry() (Python) does.
// Stateful, for interactive dragging: pgcs_new(sketch) -> handle; pgcs_handle_solve,
// pgcs_init_move(h, [[geo, pos], ...]), pgcs_move(h, x, y, relative) (the Sketcher view
// provider's temporary moves), pgcs_end_move(h), pgcs_move_geometry (SketchObject.moveGeometry),
// pgcs_result(h), pgcs_free(h).
// Returned strings belong to the library and stay valid until the next call.

#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "sketch.h"

using namespace Sketcher;

namespace
{

// A small JSON value and parser (numbers remember whether they were written as integers) ----

struct Json
{
    enum Kind
    {
        Null,
        Bool,
        Int,
        Float,
        String,
        Array,
        Object
    } kind = Null;
    bool b = false;
    double num = 0;
    long long integer = 0;
    std::string str;
    std::vector<Json> items;
    std::vector<std::string> keys;  // an object's keys, and its values in values
    std::vector<Json> values;

    const Json* get(const char* key) const
    {
        for (size_t k = 0; k < keys.size(); ++k) {
            if (keys[k] == key) {
                return &values[k];
            }
        }
        return nullptr;
    }
    bool isNumber() const
    {
        return kind == Int || kind == Float || kind == Bool;
    }
    double asDouble() const
    {
        if (kind == Int) {
            return double(integer);
        }
        if (kind == Bool) {
            return b ? 1.0 : 0.0;
        }
        if (kind == Float) {
            return num;
        }
        throw std::invalid_argument("expected a number");
    }
    // Python's "i": an int or a bool
    bool isInt() const
    {
        return kind == Int || kind == Bool;
    }
    int asInt() const
    {
        if (kind == Int) {
            return int(integer);
        }
        if (kind == Bool) {
            return b ? 1 : 0;
        }
        throw std::invalid_argument("expected an integer");
    }
};

struct Parser
{
    const char* s;
    size_t i = 0;
    size_t n;

    explicit Parser(const char* text)
        : s(text)
        , n(std::strlen(text))
    {}

    [[noreturn]] void fail(const char* what)
    {
        throw std::invalid_argument(std::string("JSON: ") + what + " at offset " + std::to_string(i));
    }
    void ws()
    {
        while (i < n && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) {
            ++i;
        }
    }
    Json parse()
    {
        Json v = value();
        ws();
        if (i != n) {
            fail("trailing characters");
        }
        return v;
    }
    Json value()
    {
        ws();
        if (i >= n) {
            fail("unexpected end");
        }
        char c = s[i];
        Json v;
        if (c == '{') {
            v.kind = Json::Object;
            ++i;
            ws();
            if (i < n && s[i] == '}') {
                ++i;
                return v;
            }
            while (true) {
                ws();
                if (i >= n || s[i] != '"') {
                    fail("expected a key");
                }
                std::string key = string();
                ws();
                if (i >= n || s[i] != ':') {
                    fail("expected ':'");
                }
                ++i;
                v.keys.push_back(key);
                v.values.push_back(value());
                ws();
                if (i < n && s[i] == ',') {
                    ++i;
                    continue;
                }
                if (i < n && s[i] == '}') {
                    ++i;
                    return v;
                }
                fail("expected ',' or '}'");
            }
        }
        if (c == '[') {
            v.kind = Json::Array;
            ++i;
            ws();
            if (i < n && s[i] == ']') {
                ++i;
                return v;
            }
            while (true) {
                v.items.push_back(value());
                ws();
                if (i < n && s[i] == ',') {
                    ++i;
                    continue;
                }
                if (i < n && s[i] == ']') {
                    ++i;
                    return v;
                }
                fail("expected ',' or ']'");
            }
        }
        if (c == '"') {
            v.kind = Json::String;
            v.str = string();
            return v;
        }
        if (std::strncmp(s + i, "true", 4) == 0) {
            i += 4;
            v.kind = Json::Bool;
            v.b = true;
            return v;
        }
        if (std::strncmp(s + i, "false", 5) == 0) {
            i += 5;
            v.kind = Json::Bool;
            return v;
        }
        if (std::strncmp(s + i, "null", 4) == 0) {
            i += 4;
            return v;
        }
        // number
        size_t start = i;
        bool isFloat = false;
        if (s[i] == '-' || s[i] == '+') {
            ++i;
        }
        while (i < n && ((s[i] >= '0' && s[i] <= '9') || s[i] == '.' || s[i] == 'e' || s[i] == 'E'
                         || s[i] == '-' || s[i] == '+')) {
            if (s[i] == '.' || s[i] == 'e' || s[i] == 'E') {
                isFloat = true;
            }
            ++i;
        }
        if (i == start) {
            fail("unexpected character");
        }
        std::string tok(s + start, i - start);
        if (tok == "NaN" || tok == "Infinity") {
            fail("bad number");
        }
        if (isFloat) {
            v.kind = Json::Float;
            v.num = std::strtod(tok.c_str(), nullptr);
        }
        else {
            v.kind = Json::Int;
            v.integer = std::strtoll(tok.c_str(), nullptr, 10);
        }
        return v;
    }
    std::string string()
    {
        std::string out;
        ++i;  // opening quote
        while (i < n && s[i] != '"') {
            if (s[i] == '\\' && i + 1 < n) {
                ++i;
                switch (s[i]) {
                    case 'n':
                        out += '\n';
                        break;
                    case 't':
                        out += '\t';
                        break;
                    case 'r':
                        out += '\r';
                        break;
                    case 'b':
                        out += '\b';
                        break;
                    case 'f':
                        out += '\f';
                        break;
                    case 'u': {
                        if (i + 4 >= n) {
                            fail("bad escape");
                        }
                        unsigned cp = std::strtoul(std::string(s + i + 1, 4).c_str(), nullptr, 16);
                        i += 4;
                        if (cp < 0x80) {
                            out += char(cp);
                        }
                        else if (cp < 0x800) {
                            out += char(0xC0 | (cp >> 6));
                            out += char(0x80 | (cp & 0x3F));
                        }
                        else {
                            out += char(0xE0 | (cp >> 12));
                            out += char(0x80 | ((cp >> 6) & 0x3F));
                            out += char(0x80 | (cp & 0x3F));
                        }
                        break;
                    }
                    default:
                        out += s[i];
                }
                ++i;
            }
            else {
                out += s[i++];
            }
        }
        if (i >= n) {
            fail("unterminated string");
        }
        ++i;  // closing quote
        return out;
    }
};

// JSON writing ---------------------------------------------------------------------------------

struct Writer
{
    std::string out;
    void num(double v)
    {
        if (!std::isfinite(v)) {
            out += "null";
            return;
        }
        char buf[32];
        std::snprintf(buf, sizeof buf, "%.17g", v);
        out += buf;
    }
    void integer(long long v)
    {
        out += std::to_string(v);
    }
    void str(const std::string& v)
    {
        out += '"';
        for (char c : v) {
            if (c == '"' || c == '\\') {
                out += '\\';
                out += c;
            }
            else if (c == '\n') {
                out += "\\n";
            }
            else if (static_cast<unsigned char>(c) < 0x20) {
                char buf[8];
                std::snprintf(buf, sizeof buf, "\\u%04x", c);
                out += buf;
            }
            else {
                out += c;
            }
        }
        out += '"';
    }
    void key(const char* k)
    {
        if (!out.empty() && out.back() != '{' && out.back() != '[') {
            out += ',';
        }
        str(k);
        out += ':';
    }
    void sep()
    {
        if (!out.empty() && out.back() != '{' && out.back() != '[') {
            out += ',';
        }
    }
    void vec(Vec v)
    {
        out += '[';
        num(v.x);
        out += ',';
        num(v.y);
        out += ']';
    }
    void ints(const std::vector<int>& v)
    {
        out += '[';
        for (size_t k = 0; k < v.size(); ++k) {
            if (k) {
                out += ',';
            }
            integer(v[k]);
        }
        out += ']';
    }
};

// Sketch input ---------------------------------------------------------------------------------

Vec toVec(const Json& j)
{
    if (j.kind != Json::Array || j.items.size() < 2 || j.items.size() > 3) {
        throw std::invalid_argument("a point must be [x, y] or [x, y, z]");
    }
    if (j.items.size() == 3 && j.items[2].asDouble() != 0.0) {
        throw std::invalid_argument("points must lie in the sketch plane (z = 0)");
    }
    return Vec {j.items[0].asDouble(), j.items[1].asDouble()};
}

// Part.Circle(center, normal, radius) or (center, radius)
void circleArgs(const Json& args, Vec& center, double& radius)
{
    if (args.kind != Json::Array || args.items.size() < 2 || args.items.size() > 3) {
        throw std::invalid_argument("Circle args must be [center, normal, radius] or [center, radius]");
    }
    center = toVec(args.items[0]);
    if (args.items.size() == 3) {
        const Json& nrm = args.items[1];
        if (nrm.kind != Json::Array || nrm.items.size() != 3 || nrm.items[0].asDouble() != 0.0
            || nrm.items[1].asDouble() != 0.0 || !(nrm.items[2].asDouble() > 0.0)) {
            throw std::invalid_argument("only circles with normal +Z (0, 0, 1) are supported");
        }
    }
    radius = args.items.back().asDouble();
}

const Json* need(const Json& j, const char* key)
{
    const Json* v = j.get(key);
    if (!v) {
        throw std::invalid_argument(std::string("a geometry needs \"") + key + "\"");
    }
    return v;
}

std::vector<double> doubles(const Json& j, const char* what)
{
    if (j.kind != Json::Array) {
        throw std::invalid_argument(std::string(what) + " must be a list of numbers");
    }
    std::vector<double> out;
    for (const auto& v : j.items) {
        out.push_back(v.asDouble());
    }
    return out;
}

Sketcher::Geometry parseGeometry(const Json& j)
{
    if (j.kind != Json::Object) {
        throw std::invalid_argument("a geometry must be an object");
    }
    const Json* type = j.get("type");
    if (!type || type->kind != Json::String) {
        throw std::invalid_argument("a geometry needs a \"type\"");
    }
    const Json* args = j.get("args");
    const std::string& t = type->str;
    Sketcher::Geometry g;
    if (t == "Point") {
        if (args) {
            if (args->kind != Json::Array || args->items.size() != 1) {
                throw std::invalid_argument("Point args must be [[x, y]]");
            }
            g = Sketcher::Geometry::makePoint(toVec(args->items[0]));
        }
        else {
            g = Sketcher::Geometry::makePoint(toVec(*need(j, "at")));
        }
    }
    else if (t == "LineSegment") {
        Vec a, b;
        if (args) {
            if (args->kind != Json::Array || args->items.size() != 2) {
                throw std::invalid_argument("LineSegment args must be [[x1, y1], [x2, y2]]");
            }
            a = toVec(args->items[0]);
            b = toVec(args->items[1]);
        }
        else {
            a = toVec(*need(j, "start"));
            b = toVec(*need(j, "end"));
        }
        if (a.x == b.x && a.y == b.y) {
            throw std::invalid_argument("LineSegment: both points are equal");
        }
        g = Sketcher::Geometry::makeLineSegment(a, b);
    }
    else if (t == "Circle") {
        Vec c;
        double r;
        if (args) {
            circleArgs(*args, c, r);
        }
        else {
            c = toVec(*need(j, "center"));
            r = need(j, "radius")->asDouble();
        }
        g = Sketcher::Geometry::makeCircle(c, r);
    }
    else if (t == "ArcOfCircle") {
        Vec c;
        double r, a1, a2;
        if (args) {
            if (args->kind != Json::Array || args->items.size() != 3) {
                throw std::invalid_argument("ArcOfCircle args must be [circle args, a1, a2]");
            }
            const Json& circ = args->items[0];
            circleArgs(circ.kind == Json::Object ? *circ.get("args") : circ, c, r);
            a1 = args->items[1].asDouble();
            a2 = args->items[2].asDouble();
        }
        else {
            c = toVec(*need(j, "center"));
            r = need(j, "radius")->asDouble();
            a1 = need(j, "start_angle")->asDouble();
            a2 = need(j, "end_angle")->asDouble();
        }
        g = Sketcher::Geometry::makeArcOfCircle(c, r, a1, a2);
    }
    else if (t == "Ellipse" || t == "ArcOfEllipse" || t == "ArcOfHyperbola") {
        Vec c = toVec(*need(j, "center"));
        double a = need(j, "major_radius")->asDouble();
        double b = need(j, "minor_radius")->asDouble();
        Vec x = j.get("x_axis") ? toVec(*j.get("x_axis")) : Vec {1.0, 0.0};
        if (t == "Ellipse") {
            g = Sketcher::Geometry::makeEllipse(c, a, b, x);
        }
        else {
            double u1 = need(j, "start_angle")->asDouble();
            double u2 = need(j, "end_angle")->asDouble();
            g = t == "ArcOfEllipse" ? Sketcher::Geometry::makeArcOfEllipse(c, a, b, x, u1, u2)
                                    : Sketcher::Geometry::makeArcOfHyperbola(c, a, b, x, u1, u2);
        }
    }
    else if (t == "ArcOfParabola") {
        Vec c = toVec(*need(j, "center"));
        double f = need(j, "focal")->asDouble();
        Vec x = j.get("x_axis") ? toVec(*j.get("x_axis")) : Vec {1.0, 0.0};
        double u1 = need(j, "start_angle")->asDouble();
        double u2 = need(j, "end_angle")->asDouble();
        g = Sketcher::Geometry::makeArcOfParabola(c, f, x, u1, u2);
    }
    else if (t == "BSplineCurve") {
        BSplineData d;
        const Json* poles = need(j, "poles");
        if (poles->kind != Json::Array) {
            throw std::invalid_argument("BSplineCurve poles must be a list of points");
        }
        for (const auto& pt : poles->items) {
            d.poles.push_back(toVec(pt));
        }
        if (const Json* w = j.get("weights")) {
            d.weights = doubles(*w, "BSplineCurve weights");
        }
        d.knots = doubles(*need(j, "knots"), "BSplineCurve knots");
        for (double m : doubles(*need(j, "mults"), "BSplineCurve mults")) {
            d.mults.push_back(int(m));
        }
        d.degree = need(j, "degree")->asInt();
        if (const Json* per = j.get("periodic")) {
            d.periodic = per->kind == Json::Bool && per->b;
        }
        g = Sketcher::Geometry::makeBSpline(std::move(d));
    }
    else {
        throw std::invalid_argument("unsupported geometry type: " + t);
    }
    if (const Json* constr = j.get("construction")) {
        g.construction = constr->kind == Json::Bool && constr->b;
    }
    if (const Json* layer = j.get("layer")) {
        g.layer = layer->isInt() ? layer->asInt() : 0;
    }
    return g;
}

// ConstraintPy::PyInit's argument dispatch, for the constraint types in scope.
Constraint parseConstraintArgs(const std::string& type, const std::vector<Json>& a)
{
    const char* ConstraintType = type.c_str();
    Constraint c;
    Constraint* constraint = &c;
    size_t n = a.size();
    auto isBool = [&](size_t k) {
        return a[k].kind == Json::Bool;
    };
    auto allInt = [&](size_t count) {
        if (n < count) {
            return false;
        }
        for (size_t k = 0; k < count; ++k) {
            if (!a[k].isInt()) {
                return false;
            }
        }
        return true;
    };

    int FirstIndex = GeoEnum::GeoUndef;
    int FirstPos = static_cast<int>(PointPos::none);
    int SecondIndex = GeoEnum::GeoUndef;
    int SecondPos = static_cast<int>(PointPos::none);
    int ThirdIndex = GeoEnum::GeoUndef;
    int ThirdPos = static_cast<int>(PointPos::none);
    double Value = 0;
    int intArg1 = 0, intArg2 = 0, intArg3 = 0, intArg4 = 0, intArg5 = 0;
    int any_index = 0;
    const Json* index_or_value = nullptr;
    const Json* oNumArg4 = nullptr;
    const Json* oNumArg5 = nullptr;

    for (const auto& arg : a) {
        if (!arg.isNumber()) {
            throw std::invalid_argument("Invalid argument type for Constraint " + type);
        }
    }

    auto setDriving = [&](const Json& driving) {
        if (constraint->isDimensional()) {
            constraint->isDriving = driving.b;
        }
    };

    auto handleSi = [&]() -> bool {
        if (strcmp("Horizontal", ConstraintType) == 0) {
            constraint->Type = Horizontal;
        }
        else if (strcmp("Vertical", ConstraintType) == 0) {
            constraint->Type = Vertical;
        }
        else if (strcmp("Block", ConstraintType) == 0) {
            constraint->Type = Block;
        }
        else {
            return false;
        }
        constraint->First = FirstIndex;
        return true;
    };

    // ConstraintType, GeoIndex
    if (n == 1 && allInt(1)) {
        FirstIndex = a[0].asInt();
        if (handleSi()) {
            return c;
        }
    }
    // ConstraintType, GeoIndex, activated
    if (n == 2 && allInt(1)) {
        FirstIndex = a[0].asInt();
        if (isBool(1)) {
            if (handleSi()) {
                constraint->isActive = a[1].b;
                return c;
            }
        }
    }

    auto handleSiO = [&]() -> bool {
        // ConstraintType, GeoIndex1, GeoIndex2
        if (index_or_value->isInt()) {
            SecondIndex = index_or_value->asInt();
            bool valid = false;
            if (strcmp("Tangent", ConstraintType) == 0) {
                constraint->Type = Tangent;
                valid = true;
            }
            else if (strcmp("Parallel", ConstraintType) == 0) {
                constraint->Type = Parallel;
                valid = true;
            }
            else if (strcmp("Perpendicular", ConstraintType) == 0) {
                constraint->Type = Perpendicular;
                valid = true;
            }
            else if (strcmp("Equal", ConstraintType) == 0) {
                constraint->Type = Equal;
                valid = true;
            }
            else if (strstr(ConstraintType, "InternalAlignment")) {
                constraint->Type = InternalAlignment;

                valid = true;
                if (strstr(ConstraintType, "EllipseMajorDiameter")) {
                    constraint->AlignmentType = EllipseMajorDiameter;
                }
                else if (strstr(ConstraintType, "EllipseMinorDiameter")) {
                    constraint->AlignmentType = EllipseMinorDiameter;
                }
                else if (strstr(ConstraintType, "HyperbolaMajor")) {
                    constraint->AlignmentType = HyperbolaMajor;
                }
                else if (strstr(ConstraintType, "HyperbolaMinor")) {
                    constraint->AlignmentType = HyperbolaMinor;
                }
                else if (strstr(ConstraintType, "ParabolaFocalAxis")) {
                    constraint->AlignmentType = ParabolaFocalAxis;
                }
                else {
                    constraint->AlignmentType = Undef;
                    valid = false;
                }
            }
            if (valid) {
                constraint->First = FirstIndex;
                constraint->Second = SecondIndex;
                return true;
            }
        }
        // ConstraintType, GeoIndex, Value
        if (index_or_value->isNumber()) {  // can be float or int
            Value = index_or_value->asDouble();
            if (strcmp("Distance", ConstraintType) == 0) {
                constraint->Type = Distance;
            }
            else if (strcmp("Angle", ConstraintType) == 0) {
                constraint->Type = Angle;
            }
            else if (strcmp("DistanceX", ConstraintType) == 0) {
                constraint->Type = DistanceX;
            }
            else if (strcmp("DistanceY", ConstraintType) == 0) {
                constraint->Type = DistanceY;
            }
            else if (strcmp("Radius", ConstraintType) == 0) {
                constraint->Type = Radius;
            }
            else if (strcmp("Diameter", ConstraintType) == 0) {
                constraint->Type = Diameter;
            }
            else if (strcmp("Weight", ConstraintType) == 0) {
                constraint->Type = Weight;
            }
            else {
                return false;
            }

            constraint->First = FirstIndex;
            constraint->setValue(Value);
            return true;
        }
        return false;
    };

    if (n == 2 && allInt(1)) {
        FirstIndex = a[0].asInt();
        index_or_value = &a[1];
        if (handleSiO()) {
            return c;
        }
    }
    if (n == 3 && allInt(1)) {
        FirstIndex = a[0].asInt();
        index_or_value = &a[1];
        if (isBool(2)) {
            if (handleSiO()) {
                constraint->isActive = a[2].b;
                return c;
            }
        }
    }
    if (n == 4 && allInt(1)) {
        FirstIndex = a[0].asInt();
        index_or_value = &a[1];
        if (isBool(2) && isBool(3)) {
            if (handleSiO()) {
                constraint->isActive = a[2].b;
                setDriving(a[3]);
                return c;
            }
        }
    }

    auto handleSiiO = [&]() -> bool {
        // ConstraintType, GeoIndex1, PosIndex1, GeoIndex2
        if (index_or_value->isInt()) {
            FirstPos = any_index;
            SecondIndex = index_or_value->asInt();
            bool valid = false;
            if (strcmp("Perpendicular", ConstraintType) == 0) {
                constraint->Type = Perpendicular;
                valid = true;
            }
            else if (strcmp("Tangent", ConstraintType) == 0) {
                constraint->Type = Tangent;
                valid = true;
            }
            else if (strcmp("PointOnObject", ConstraintType) == 0) {
                constraint->Type = PointOnObject;
                valid = true;
            }
            else if (strstr(ConstraintType, "InternalAlignment")) {
                constraint->Type = InternalAlignment;

                valid = true;

                if (strstr(ConstraintType, "EllipseFocus1")) {
                    constraint->AlignmentType = EllipseFocus1;
                }
                else if (strstr(ConstraintType, "EllipseFocus2")) {
                    constraint->AlignmentType = EllipseFocus2;
                }
                else if (strstr(ConstraintType, "HyperbolaFocus")) {
                    constraint->AlignmentType = HyperbolaFocus;
                }
                else if (strstr(ConstraintType, "ParabolaFocus")) {
                    constraint->AlignmentType = ParabolaFocus;
                }
                else {
                    constraint->AlignmentType = Undef;
                    valid = false;
                }
            }
            if (valid) {
                constraint->First = FirstIndex;
                constraint->FirstPos = static_cast<PointPos>(FirstPos);
                constraint->Second = SecondIndex;
                return true;
            }
        }
        // ConstraintType, GeoIndex1, GeoIndex2, Value
        // ConstraintType, GeoIndex, PosIndex, Value
        if (index_or_value->isNumber()) {  // can be float or int
            SecondIndex = any_index;
            Value = index_or_value->asDouble();
            if (strcmp("Angle", ConstraintType) == 0) {
                constraint->Type = Angle;
                constraint->Second = SecondIndex;
            }
            else if (strcmp("Distance", ConstraintType) == 0) {
                constraint->Type = Distance;
                constraint->Second = SecondIndex;
            }
            else if (strcmp("DistanceX", ConstraintType) == 0) {
                FirstPos = SecondIndex;
                SecondIndex = -1;
                constraint->Type = DistanceX;
                constraint->FirstPos = static_cast<PointPos>(FirstPos);
            }
            else if (strcmp("DistanceY", ConstraintType) == 0) {
                FirstPos = SecondIndex;
                SecondIndex = -1;
                constraint->Type = DistanceY;
                constraint->FirstPos = static_cast<PointPos>(FirstPos);
            }
            else {
                return false;
            }

            constraint->First = FirstIndex;
            constraint->setValue(Value);
            return true;
        }
        return false;
    };

    for (size_t extra = 0; extra < 3; ++extra) {  // siiO, siiOO, siiOOO
        if (n == 3 + extra && allInt(2)) {
            FirstIndex = a[0].asInt();
            any_index = a[1].asInt();
            index_or_value = &a[2];
            if (extra >= 1 && !isBool(3)) {
                continue;
            }
            if (extra == 2 && !isBool(4)) {
                continue;
            }
            if (handleSiiO()) {
                if (extra >= 1) {
                    constraint->isActive = a[3].b;
                }
                if (extra == 2) {
                    setDriving(a[4]);
                }
                return c;
            }
        }
    }

    auto handleSiiiO = [&]() -> bool {
        // Value, ConstraintType, GeoIndex1, PosIndex1, GeoIndex2, PosIndex2
        if (oNumArg4->isInt()) {
            intArg4 = oNumArg4->asInt();
            bool valid = false;
            if (strcmp("Coincident", ConstraintType) == 0) {
                constraint->Type = Coincident;
                valid = true;
            }
            else if (strcmp("Horizontal", ConstraintType) == 0) {
                constraint->Type = Horizontal;
                valid = true;
            }
            else if (strcmp("Vertical", ConstraintType) == 0) {
                constraint->Type = Vertical;
                valid = true;
            }
            else if (strcmp("Perpendicular", ConstraintType) == 0) {
                constraint->Type = Perpendicular;
                valid = true;
            }
            else if (strcmp("Tangent", ConstraintType) == 0) {
                constraint->Type = Tangent;
                valid = true;
            }
            else if (strcmp("TangentViaPoint", ConstraintType) == 0) {
                constraint->Type = Tangent;
                constraint->First = intArg1;
                constraint->FirstPos = PointPos::none;
                constraint->Second = intArg2;
                constraint->SecondPos = PointPos::none;
                constraint->Third = intArg3;
                constraint->ThirdPos = static_cast<PointPos>(intArg4);
                return true;
            }
            else if (strcmp("PerpendicularViaPoint", ConstraintType) == 0) {
                constraint->Type = Perpendicular;
                constraint->First = intArg1;
                constraint->FirstPos = PointPos::none;
                constraint->Second = intArg2;
                constraint->SecondPos = PointPos::none;
                constraint->Third = intArg3;
                constraint->ThirdPos = static_cast<PointPos>(intArg4);
                return true;
            }
            else if (strstr(ConstraintType, "InternalAlignment")) {
                // InteralAlignment with InternalElementIndex argument
                constraint->Type = InternalAlignment;

                valid = true;

                if (strstr(ConstraintType, "BSplineControlPoint")) {
                    constraint->AlignmentType = BSplineControlPoint;
                }
                else if (strstr(ConstraintType, "BSplineKnotPoint")) {
                    constraint->AlignmentType = BSplineKnotPoint;
                }
                else {
                    constraint->AlignmentType = Undef;
                    valid = false;
                }

                if (valid) {
                    constraint->First = intArg1;
                    constraint->FirstPos = static_cast<PointPos>(intArg2);
                    constraint->Second = intArg3;
                    constraint->InternalAlignmentIndex = intArg4;
                    return true;
                }
            }
            if (valid) {
                constraint->First = intArg1;
                constraint->FirstPos = static_cast<PointPos>(intArg2);
                constraint->Second = intArg3;
                constraint->SecondPos = static_cast<PointPos>(intArg4);
                return true;
            }
        }
        // ConstraintType, GeoIndex1, PosIndex1, GeoIndex2, Value
        if (oNumArg4->isNumber()) {  // can be float or int
            Value = oNumArg4->asDouble();
            if (strcmp("Distance", ConstraintType) == 0) {
                constraint->Type = Distance;
                constraint->First = intArg1;
                constraint->FirstPos = static_cast<PointPos>(intArg2);
                constraint->Second = intArg3;
                constraint->setValue(Value);
                return true;
            }
        }
        return false;
    };

    for (size_t extra = 0; extra < 3; ++extra) {  // siiiO, siiiOO, siiiOOO
        if (n == 4 + extra && allInt(3)) {
            intArg1 = a[0].asInt();
            intArg2 = a[1].asInt();
            intArg3 = a[2].asInt();
            oNumArg4 = &a[3];
            if (extra >= 1 && !isBool(4)) {
                continue;
            }
            if (extra == 2 && !isBool(5)) {
                continue;
            }
            if (handleSiiiO()) {
                if (extra >= 1) {
                    constraint->isActive = a[4].b;
                }
                if (extra == 2) {
                    setDriving(a[5]);
                }
                return c;
            }
        }
    }

    auto handleSiiiiO = [&]() -> bool {
        // ConstraintType, GeoIndex1, PosIndex1, GeoIndex2, PosIndex2, GeoIndex3
        if (oNumArg5->isInt()) {
            intArg5 = oNumArg5->asInt();
            if (strcmp("Symmetric", ConstraintType) == 0) {
                constraint->Type = Symmetric;
                constraint->First = intArg1;
                constraint->FirstPos = static_cast<PointPos>(intArg2);
                constraint->Second = intArg3;
                constraint->SecondPos = static_cast<PointPos>(intArg4);
                constraint->Third = intArg5;
                return true;
            }
            if (strcmp("Perpendicular", ConstraintType) == 0) {
                constraint->Type = Perpendicular;
                constraint->First = intArg1;
                constraint->FirstPos = static_cast<PointPos>(intArg2);
                constraint->Second = intArg3;
                constraint->SecondPos = static_cast<PointPos>(intArg4);
                constraint->Third = intArg5;
                return true;
            }
        }
        // ConstraintType, GeoIndex1, PosIndex1, GeoIndex2, PosIndex2, Value
        if (oNumArg5->isNumber()) {  // can be float or int
            Value = oNumArg5->asDouble();
            if (strcmp("Distance", ConstraintType) == 0) {
                constraint->Type = Distance;
            }
            else if (strcmp("DistanceX", ConstraintType) == 0) {
                constraint->Type = DistanceX;
            }
            else if (strcmp("DistanceY", ConstraintType) == 0) {
                constraint->Type = DistanceY;
            }
            else if (strcmp("Angle", ConstraintType) == 0) {
                constraint->Type = Angle;
            }
            else if (strcmp("AngleViaPoint", ConstraintType) == 0) {
                constraint->Type = Angle;
                constraint->First = intArg1;
                constraint->FirstPos = PointPos::none;
                constraint->Second = intArg2;  // let's goof up all the terminology =)
                constraint->SecondPos = PointPos::none;
                constraint->Third = intArg3;
                constraint->ThirdPos = static_cast<PointPos>(intArg4);
                constraint->setValue(Value);
                return true;
            }
            else {
                return false;
            }

            constraint->First = intArg1;
            constraint->FirstPos = static_cast<PointPos>(intArg2);
            constraint->Second = intArg3;
            constraint->SecondPos = static_cast<PointPos>(intArg4);
            constraint->setValue(Value);
            return true;
        }
        return false;
    };

    for (size_t extra = 0; extra < 3; ++extra) {  // siiiiO, siiiiOO, siiiiOOO
        if (n == 5 + extra && allInt(4)) {
            intArg1 = a[0].asInt();
            intArg2 = a[1].asInt();
            intArg3 = a[2].asInt();
            intArg4 = a[3].asInt();
            oNumArg5 = &a[4];
            if (extra >= 1 && !isBool(5)) {
                continue;
            }
            if (extra == 2 && !isBool(6)) {
                continue;
            }
            if (handleSiiiiO()) {
                if (extra >= 1) {
                    constraint->isActive = a[5].b;
                }
                if (extra == 2) {
                    setDriving(a[6]);
                }
                return c;
            }
        }
    }

    auto handleSiiiiiO = [&]() -> bool {
        if (index_or_value->isInt()) {
            ThirdPos = index_or_value->asInt();
            // ConstraintType, GeoIndex1, PosIndex1, GeoIndex2, PosIndex2, GeoIndex3, PosIndex3
            if (strcmp("Symmetric", ConstraintType) == 0) {
                constraint->Type = Symmetric;
                constraint->First = FirstIndex;
                constraint->FirstPos = static_cast<PointPos>(FirstPos);
                constraint->Second = SecondIndex;
                constraint->SecondPos = static_cast<PointPos>(SecondPos);
                constraint->Third = ThirdIndex;
                constraint->ThirdPos = static_cast<PointPos>(ThirdPos);
                return true;
            }
        }
        if (index_or_value->isNumber()) {  // can be float or int
            Value = index_or_value->asDouble();
            if (strcmp("SnellsLaw", ConstraintType) == 0) {
                constraint->Type = SnellsLaw;
                constraint->First = FirstIndex;
                constraint->FirstPos = static_cast<PointPos>(FirstPos);
                constraint->Second = SecondIndex;
                constraint->SecondPos = static_cast<PointPos>(SecondPos);
                constraint->Third = ThirdIndex;
                constraint->ThirdPos = PointPos::none;
                constraint->setValue(Value);
                return true;
            }
        }
        return false;
    };

    for (size_t extra = 0; extra < 3; ++extra) {  // siiiiiO, siiiiiOO, siiiiiOOO
        if (n == 6 + extra && allInt(5)) {
            FirstIndex = a[0].asInt();
            FirstPos = a[1].asInt();
            SecondIndex = a[2].asInt();
            SecondPos = a[3].asInt();
            ThirdIndex = a[4].asInt();
            index_or_value = &a[5];
            if (extra >= 1 && !isBool(6)) {
                continue;
            }
            if (extra == 2 && !isBool(7)) {
                continue;
            }
            if (handleSiiiiiO()) {
                if (extra >= 1) {
                    constraint->isActive = a[6].b;
                }
                if (extra == 2) {
                    setDriving(a[7]);
                }
                return c;
            }
        }
    }

    throw std::invalid_argument("Invalid or unsupported parameters for Constraint " + type);
}

Constraint parseConstraint(const Json& j)
{
    Constraint c;
    if (j.kind == Json::Array) {
        if (j.items.empty() || j.items[0].kind != Json::String) {
            throw std::invalid_argument("a constraint array must start with its type");
        }
        std::vector<Json> args(j.items.begin() + 1, j.items.end());
        return parseConstraintArgs(j.items[0].str, args);
    }
    if (j.kind != Json::Object) {
        throw std::invalid_argument("a constraint must be an array or an object");
    }
    const Json* type = j.get("type");
    const Json* args = j.get("args");
    if (!type || type->kind != Json::String || !args || args->kind != Json::Array) {
        throw std::invalid_argument("a constraint object needs \"type\" and \"args\"");
    }
    if (const Json* value = j.get("value")) {
        // {type, args, value}: the args are the geoIds and positions, the value goes last, a float
        std::vector<Json> items;
        for (const auto& a : args->items) {
            Json k;
            k.kind = Json::Int;
            k.integer = static_cast<long long>(std::llround(a.asDouble()));
            if (a.kind == Json::Bool || double(k.integer) != a.asDouble()) {
                throw std::invalid_argument("constraint args must be integers when \"value\" is given");
            }
            items.push_back(k);
        }
        Json v;
        v.kind = Json::Float;
        v.num = value->asDouble();
        items.push_back(v);
        c = parseConstraintArgs(type->str, items);
    }
    else {
        c = parseConstraintArgs(type->str, args->items);
    }
    if (const Json* v = j.get("driving")) {
        // SketchObject::setDriving: only dimensional constraints can be reference ones
        if (c.isDimensional()) {
            c.isDriving = v->kind == Json::Bool ? v->b : v->asDouble() != 0;
        }
    }
    if (const Json* v = j.get("active")) {
        c.isActive = v->kind == Json::Bool ? v->b : v->asDouble() != 0;
    }
    if (const Json* v = j.get("name")) {
        if (v->kind == Json::String) {
            c.Name = v->str;
        }
    }
    if (const Json* v = j.get("orientation")) {
        c.Orientation.i = v->asInt();
    }
    return c;
}

PointPos toPos(int p)
{
    if (p < 0 || p > 3) {
        throw std::invalid_argument("a point position must be 0 (edge), 1 (start), 2 (end) or 3 (mid)");
    }
    return static_cast<PointPos>(p);
}

std::vector<GeoElementId> parseElements(const Json& j)
{
    // [[geo, pos], ...] or [geo, pos]
    std::vector<GeoElementId> out;
    if (j.kind != Json::Array) {
        throw std::invalid_argument("elements must be [[geoId, pos], ...]");
    }
    if (j.items.size() == 2 && j.items[0].isInt()) {
        out.push_back(GeoElementId {j.items[0].asInt(), toPos(j.items[1].asInt())});
        return out;
    }
    for (const auto& e : j.items) {
        if (e.kind != Json::Array || e.items.size() != 2) {
            throw std::invalid_argument("elements must be [[geoId, pos], ...]");
        }
        out.push_back(GeoElementId {e.items[0].asInt(), toPos(e.items[1].asInt())});
    }
    return out;
}

struct Handle
{
    SketchDoc doc;
    std::vector<GeoElementId> moving;
    int lastStatus = 0;
    std::string lastOp = "none";
    int lastMoveStatus = -1;
};

std::unique_ptr<Handle> build(const Json& sketch)
{
    if (sketch.kind != Json::Object) {
        throw std::invalid_argument("a sketch must be an object");
    }
    auto h = std::make_unique<Handle>();
    if (const Json* geos = sketch.get("geometry")) {
        for (const auto& g : geos->items) {
            h->doc.addGeometry(parseGeometry(g));
        }
    }
    // External geometry (SketchObject's ExternalGeo after the H and V axes, as rebuildExternalGeometry leaves
    // it): GeoId -3, -4, ... in this order, which setUpSketch hands the solver as fixed geometry.
    if (const Json* ext = sketch.get("external")) {
        for (const auto& g : ext->items) {
            h->doc.externalGeo.push_back(parseGeometry(g));
        }
    }
    if (const Json* opts = sketch.get("options")) {
        if (const Json* solver = opts->get("solver")) {
            if (solver->str == "DogLeg") {
                h->doc.solvedSketch.defaultSolver = GCS::DogLeg;
            }
            else if (solver->str == "LevenbergMarquardt") {
                h->doc.solvedSketch.defaultSolver = GCS::LevenbergMarquardt;
            }
            else if (solver->str == "BFGS") {
                h->doc.solvedSketch.defaultSolver = GCS::BFGS;
            }
            else {
                throw std::invalid_argument("options.solver must be DogLeg, LevenbergMarquardt or BFGS");
            }
        }
        if (const Json* r = opts->get("recalculate_initial_solution_while_moving_point")) {
            h->doc.solvedSketch.setRecalculateInitialSolutionWhileMovingPoint(r->b);
        }
    }
    if (const Json* cons = sketch.get("constraints")) {
        std::vector<Constraint> list;
        for (const auto& c : cons->items) {
            list.push_back(parseConstraint(c));
        }
        if (!h->doc.addConstraints(list)) {
            throw std::invalid_argument("The constraint has invalid index information and is malformed.");
        }
    }
    return h;
}

const char* statusName(int s)
{
    switch (s) {
        case 0:
            return "Success";
        case -4:
            return "Overconstrained";
        case -3:
            return "ConflictingConstraints";
        case -5:
            return "MalformedConstraints";
        case -1:
            return "SolverError";
        case -2:
            return "RedundantConstraints";
        case -6:
            return "InvalidGeometry";
    }
    return "Unknown";
}

const char* typeName(ConstraintType t)
{
    static const char* names[] = {"None",          "Coincident", "Horizontal",   "Vertical",
                                  "Parallel",      "Tangent",    "Distance",     "DistanceX",
                                  "DistanceY",     "Angle",      "Perpendicular", "Radius",
                                  "Equal",         "PointOnObject", "Symmetric", "InternalAlignment",
                                  "SnellsLaw",     "Block",      "Diameter",     "Weight",
                                  "Group",         "Text"};
    return (t >= 0 && t < NumConstraintTypes) ? names[t] : "None";
}

void writeDoubles(Writer& w, const std::vector<double>& v)
{
    w.out += '[';
    for (size_t k = 0; k < v.size(); ++k) {
        if (k) {
            w.out += ',';
        }
        w.num(v[k]);
    }
    w.out += ']';
}

void writeGeometry(Writer& w, const Sketcher::Geometry& g)
{
    w.out += '{';
    switch (g.kind) {
        case Sketcher::Geometry::Ellipse:
        case Sketcher::Geometry::ArcOfEllipse:
        case Sketcher::Geometry::ArcOfHyperbola:
        case Sketcher::Geometry::ArcOfParabola: {
            static const char* names[] = {"Ellipse", "ArcOfEllipse", "ArcOfHyperbola", "ArcOfParabola"};
            w.key("type");
            w.str(names[g.kind - Sketcher::Geometry::Ellipse]);
            w.key("center");
            w.vec(g.getCenter());
            if (g.kind == Sketcher::Geometry::ArcOfParabola) {
                w.key("focal");
                w.num(g.getFocal());
            }
            else {
                w.key("major_radius");
                w.num(g.getMajorRadius());
                w.key("minor_radius");
                w.num(g.getMinorRadius());
            }
            w.key("x_axis");
            w.vec(g.getMajorAxisDir());
            if (g.kind != Sketcher::Geometry::Ellipse) {
                w.key("start_angle");
                w.num(g.getFirstParameter());
                w.key("end_angle");
                w.num(g.getLastParameter());
                w.key("start_point");
                w.vec(g.getStartPoint());
                w.key("end_point");
                w.vec(g.getEndPoint());
            }
            break;
        }
        case Sketcher::Geometry::BSplineCurve: {
            const auto& b = g.bspline();
            w.key("type");
            w.str("BSplineCurve");
            w.key("poles");
            w.out += '[';
            for (size_t k = 0; k < b.poles.size(); ++k) {
                if (k) {
                    w.out += ',';
                }
                w.vec(b.poles[k]);
            }
            w.out += ']';
            w.key("weights");
            writeDoubles(w, g.getWeights());
            w.key("knots");
            writeDoubles(w, b.knots);
            w.key("mults");
            w.ints(b.mults);
            w.key("degree");
            w.integer(b.degree);
            w.key("periodic");
            w.out += b.periodic ? "true" : "false";
            break;
        }
        case Sketcher::Geometry::Point:
            w.key("type");
            w.str("Point");
            w.key("at");
            w.vec(g.getPoint());
            break;
        case Sketcher::Geometry::LineSegment:
            w.key("type");
            w.str("LineSegment");
            w.key("start");
            w.vec(g.getStartPoint());
            w.key("end");
            w.vec(g.getEndPoint());
            break;
        case Sketcher::Geometry::Circle:
            w.key("type");
            w.str("Circle");
            w.key("center");
            w.vec(g.getCenter());
            w.key("radius");
            w.num(g.getRadius());
            break;
        case Sketcher::Geometry::ArcOfCircle: {
            // as FreeCAD stores (and Python reads) them: the trim range after Geom_TrimmedCurve::SetTrim
            double u = g.getFirstParameter(), v = g.getLastParameter();
            w.key("type");
            w.str("ArcOfCircle");
            w.key("center");
            w.vec(g.getCenter());
            w.key("radius");
            w.num(g.getRadius());
            w.key("start_angle");
            w.num(u);
            w.key("end_angle");
            w.num(v);
            break;
        }
    }
    w.key("construction");
    w.out += g.construction ? "true" : "false";
    if (g.layer) {
        w.key("layer");
        w.integer(g.layer);
    }
    w.out += '}';
}

void writeGeometries(Writer& w, const std::vector<Sketcher::Geometry>& geos)
{
    w.out += '[';
    for (const auto& g : geos) {
        w.sep();
        writeGeometry(w, g);
    }
    w.out += ']';
}

// FreeCAD numbers constraints from 1 in its solver messages; the result numbers them from 0.
std::vector<int> zeroBased(std::vector<int> v)
{
    for (auto& i : v) {
        --i;
    }
    return v;
}

const char* statusWord(int s)
{
    switch (s) {
        case 0:
            return "solved";
        case -2:
            return "redundant";
        case -3:
        case -4:
            return "conflicting";
        case -5:
            return "malformed";
    }
    return "failed";
}

std::string result(Handle& h)
{
    SketchDoc& d = h.doc;
    Writer w;
    w.out += '{';
    w.key("status");
    w.str(statusWord(h.lastStatus));
    w.key("status_code");
    w.integer(h.lastStatus);
    w.key("status_name");
    w.str(statusName(h.lastStatus));
    w.key("op");
    w.str(h.lastOp);
    w.key("solver_status");
    w.integer(static_cast<int>(d.lastSolverStatus));
    if (h.lastMoveStatus >= 0) {
        w.key("move_status");
        w.integer(h.lastMoveStatus);
    }
    w.key("dof");
    w.integer(d.lastDoF);
    w.key("fully_constrained");
    w.out += d.FullyConstrained ? "true" : "false";
    w.key("conflicting");
    w.ints(zeroBased(d.lastConflicting));
    w.key("redundant");
    w.ints(zeroBased(d.lastRedundant));
    w.key("partially_redundant");
    w.ints(zeroBased(d.lastPartiallyRedundant));
    w.key("malformed");
    w.ints(zeroBased(d.lastMalformedConstraints));
    // geometry: the solver's, which the Sketcher draws; stored_geometry: the Geometry property,
    // which FreeCAD updates only when a solve or move succeeds.
    w.key("geometry");
    if (d.solvedSketch.getGeometrySize() > 0) {
        writeGeometries(w, d.solvedSketch.extractGeometry());
    }
    else {
        writeGeometries(w, d.geometry);
    }
    w.key("stored_geometry");
    writeGeometries(w, d.geometry);
    w.key("constraints");
    w.out += '[';
    for (const auto& c : d.constraints) {
        w.sep();
        w.out += '{';
        w.key("type");
        w.str(typeName(c.Type));
        w.key("value");
        w.num(c.Value);
        w.key("orientation");
        w.integer(c.Orientation.i);
        w.key("driving");
        w.out += c.isDriving ? "true" : "false";
        w.key("active");
        w.out += c.isActive ? "true" : "false";
        if (!c.Name.empty()) {
            w.key("name");
            w.str(c.Name);
        }
        w.out += '}';
    }
    w.out += ']';
    w.key("dependent");
    w.out += '[';
    for (auto& [geo, pos, idx] : d.solvedSketch.getDependentParameterElements()) {
        w.sep();
        w.out += '[';
        w.integer(geo);
        w.out += ',';
        w.integer(static_cast<int>(pos));
        w.out += ',';
        w.integer(idx);
        w.out += ']';
    }
    w.out += ']';
    w.key("dependency_groups");
    w.out += '[';
    for (const auto& grp : d.solvedSketch.getDependencyGroups()) {
        w.sep();
        w.out += '[';
        for (const auto& [geo, pos] : grp) {
            w.sep();
            w.out += '[';
            w.integer(geo);
            w.out += ',';
            w.integer(static_cast<int>(pos));
            w.out += ']';
        }
        w.out += ']';
    }
    w.out += ']';
    w.out += '}';
    return w.out;
}

std::string errorJson(const std::string& msg)
{
    Writer w;
    w.out += '{';
    w.key("error");
    w.str(msg);
    w.out += '}';
    return w.out;
}

std::string& buffer()
{
    static std::string buf;
    return buf;
}

const char* give(std::string s)
{
    buffer() = std::move(s);
    return buffer().c_str();
}

std::map<int, std::unique_ptr<Handle>>& handles()
{
    static std::map<int, std::unique_ptr<Handle>> h;
    return h;
}
int nextHandle = 1;

Handle* find(int id)
{
    auto it = handles().find(id);
    if (it == handles().end()) {
        throw std::invalid_argument("no such sketch handle");
    }
    return it->second.get();
}

void doSolve(Handle& h)
{
    h.lastOp = "solve";
    h.lastMoveStatus = -1;
    h.lastStatus = static_cast<int>(h.doc.solve());
}

void doMoveGeometry(Handle& h, const std::vector<GeoElementId>& elts, Vec to, bool relative)
{
    h.lastOp = "move_geometry";
    h.lastMoveStatus = -1;
    h.lastStatus = static_cast<int>(h.doc.moveGeometries(elts, to, relative));
}

template<class F>
const char* guarded(F&& f)
{
    try {
        return give(f());
    }
    catch (const std::exception& e) {
        return give(errorJson(e.what()));
    }
}

}  // namespace

extern "C" {

// Version of the port and the FreeCAD commit it follows.
const char* pgcs_version()
{
    return "planegcs-sketch 1 (FreeCAD 3160daf1e2b6)";
}

// Solve a sketch (and apply its "drags", if any) and return the result.
const char* pgcs_solve(const char* json)
{
    return guarded([&]() {
        Json sketch = Parser(json).parse();
        auto h = build(sketch);
        // "solve": false moves the geometry as it is, without solving first (SketchObject's
        // programmatic moves, as fillet() and extend() make them)
        const Json* first = sketch.get("solve");
        if (!(first && first->kind == Json::Bool && !first->b)) {
            doSolve(*h);
        }
        if (const Json* drags = sketch.get("drags")) {
            for (const auto& d : drags->items) {
                const Json* geo = d.get("geo");
                const Json* pos = d.get("pos");
                const Json* to = d.get("to");
                if (!geo || !pos || !to) {
                    throw std::invalid_argument("a drag needs \"geo\", \"pos\" and \"to\"");
                }
                // "update_geometry": moveGeometry(..., updateGeoBeforeMoving=true): the solver
                // set up again from the sketch's geometry before this move
                const Json* upd = d.get("update_geometry");
                if (upd && upd->kind == Json::Bool && upd->b) {
                    h->doc.solverNeedsUpdate = true;
                }
                const Json* rel = d.get("relative");
                std::vector<GeoElementId> elts {GeoElementId {geo->asInt(), toPos(pos->asInt())}};
                doMoveGeometry(*h, elts, toVec(*to), rel && rel->kind == Json::Bool && rel->b);
            }
        }
        return result(*h);
    });
}

// Make a sketch handle (> 0); 0 on error, with the message in pgcs_last_error(). The sketch is not
// solved yet.
static std::string lastError;
int pgcs_new(const char* json)
{
    try {
        Json sketch = Parser(json).parse();
        auto h = build(sketch);
        int id = nextHandle++;
        handles()[id] = std::move(h);
        lastError.clear();
        return id;
    }
    catch (const std::exception& e) {
        lastError = e.what();
        return 0;
    }
}

const char* pgcs_last_error()
{
    return lastError.c_str();
}

void pgcs_free(int handle)
{
    handles().erase(handle);
}

// SketchObject.solve()
const char* pgcs_handle_solve(int handle)
{
    return guarded([&]() {
        Handle* h = find(handle);
        doSolve(*h);
        return result(*h);
    });
}

// The current state, without solving.
const char* pgcs_result(int handle)
{
    return guarded([&]() { return result(*find(handle)); });
}

// SketchObject.moveGeometries(elements, to, relative): elements is [[geoId, pos], ...].
const char* pgcs_move_geometry(int handle, const char* elements, double x, double y, int relative)
{
    return guarded([&]() {
        Handle* h = find(handle);
        doMoveGeometry(*h, parseElements(Parser(elements).parse()), Vec {x, y}, relative != 0);
        return result(*h);
    });
}

// Start a drag as the Sketcher's view provider does (SketchObject::initTemporaryMove): elements is
// [[geoId, pos], ...]. Returns the result with "move_status" 0, or -1 if the sketch has
// conflicts (initMove refuses to move it).
const char* pgcs_init_move(int handle, const char* elements)
{
    return guarded([&]() {
        Handle* h = find(handle);
        h->moving = parseElements(Parser(elements).parse());
        h->lastOp = "init_move";
        int r = h->doc.initTemporaryMove(h->moving);
        h->lastMoveStatus = r == 0 ? 0 : 2;
        return result(*h);
    });
}

// One drag step (SketchObject::moveGeometriesTemporary): the solver's geometry follows,
// "move_status" is the GCS status of the step (0 success). The Geometry property is untouched.
const char* pgcs_move(int handle, double x, double y, int relative)
{
    return guarded([&]() {
        Handle* h = find(handle);
        if (h->moving.empty()) {
            throw std::invalid_argument("pgcs_move without pgcs_init_move");
        }
        h->lastOp = "move";
        auto s = h->doc.moveGeometriesTemporary(h->moving, Vec {x, y}, relative != 0);
        h->lastMoveStatus = static_cast<int>(s);
        return result(*h);
    });
}

// End a drag: forget the temporary move. (The view provider then commits the drag with
// moveGeometries, i.e. pgcs_move_geometry, from the solver's current state.)
void pgcs_end_move(int handle)
{
    auto it = handles().find(handle);
    if (it != handles().end()) {
        it->second->doc.solvedSketch.resetInitMove();
        it->second->moving.clear();
    }
}

}  // extern "C"
