// SPDX-License-Identifier: LGPL-2.1-or-later
//
// Ported from FreeCAD's src/Mod/Sketcher/App/Sketch.cpp at FreeCAD commit 3160daf1e2b6
// (weekly-2026.09.30), (c) 2010 Juergen Riegel and FreeCAD's contributors, LGPL-2.1-or-later,
// with the parts of SketchObject.cpp, SketchObjectConstraints.cpp and SketchObjectOperations.cpp
// that drive it (SketchDoc at the end). See sketch.h for what is ported and what changes.
//
// The functions keep FreeCAD's names, order of operations and comments, so they can be read
// side by side with the original. Only the geometry types listed in sketch.h are handled; the
// branches of the original for other types are left out.

#include "sketch.h"

#include <algorithm>
#include <cfloat>
#include <cmath>
#include <functional>
#include <limits>
#include <numbers>
#include <optional>

using namespace Sketcher;

namespace
{

// OpenCascade's Precision:: values
constexpr double Confusion = 1e-7;
constexpr double SquareConfusion = Confusion * Confusion;
constexpr double PConfusion = Confusion * 0.01;
// gp::Resolution() (RealSmall())
constexpr double Resolution = DBL_MIN;

constexpr double twoPi = 2. * std::numbers::pi;  // Geom_Circle::LastParameter()

// ElCLib::AdjustPeriodic
void adjustPeriodic(double UFirst, double ULast, double Preci, double& U1, double& U2)
{
    double period = ULast - UFirst;
    U1 -= std::floor((U1 - UFirst) / period) * period;
    if (ULast - U1 < Preci) {
        U1 -= period;
    }
    U2 -= std::floor((U2 - U1) / period) * period;
    if (U2 - U1 < Preci) {
        U2 += period;
    }
}

// Geom_TrimmedCurve::SetTrim on a Geom_Circle (periodic, sense true, adjust periodic)
void setTrimPeriodic(double U1, double U2, double& uTrim1, double& uTrim2)
{
    if (U1 == U2) {
        throw GeometryError("Geom_TrimmedCurve::U1 == U2");
    }
    uTrim1 = U1;
    uTrim2 = U2;
    adjustPeriodic(0., twoPi, std::min(std::abs(uTrim2 - uTrim1) / 2, PConfusion), uTrim1, uTrim2);
}

// gp_Pnt::Distance in the XY plane (z = 0)
double pntDistance(Vec a, Vec b)
{
    double d = 0, dd;
    dd = a.x;
    dd -= b.x;
    dd *= dd;
    d += dd;
    dd = a.y;
    dd -= b.y;
    dd *= dd;
    d += dd;
    dd = 0.0;
    d += dd;
    return std::sqrt(d);
}

double vecLength(Vec v)
{
    return std::sqrt(v.x * v.x + v.y * v.y + 0.0 * 0.0);
}

/**
 * @brief Distance from a point to a line, signed by the side the point is on.
 * (Sketch.cpp, anonymous namespace)
 */
double signedDistanceToLine(const GCS::Line& line, double pointX, double pointY)
{
    const double startX = *line.p1.x;
    const double startY = *line.p1.y;
    const double deltaX = *line.p2.x - startX;
    const double deltaY = *line.p2.y - startY;
    const double length = std::hypot(deltaX, deltaY);

    if (length < Confusion) {
        return 0.0;
    }

    return (deltaX * (pointY - startY) - deltaY * (pointX - startX)) / length;
}

bool hasKnownSide(ConstraintOrientation orientation)
{
    return orientation.testFlag(ConstraintOrientations::CounterClockwise)
        || orientation.testFlag(ConstraintOrientations::Clockwise);
}

bool tangentSide(ConstraintOrientation orientation, const GCS::Line& line, const GCS::Circle& circle)
{
    if (hasKnownSide(orientation)) {
        return orientation.testFlag(ConstraintOrientations::CounterClockwise);
    }

    return signedDistanceToLine(line, *circle.center.x, *circle.center.y) > 0.0;
}

}  // namespace

// Geometry (stand-in for the Part geometry classes) ===========================================

Geometry Geometry::makePoint(Vec pt)
{
    Geometry g;
    g.kind = Point;
    g.p = pt;
    return g;
}

Geometry Geometry::makeLineSegment(Vec p1, Vec p2)
{
    Geometry g;
    g.kind = LineSegment;
    g.p = p1;
    g.setPoints(p1, p2);
    return g;
}

Geometry Geometry::makeCircle(Vec center, double radius)
{
    Geometry g;
    g.kind = Circle;
    g.p = center;
    g.r = radius;
    return g;
}

Geometry Geometry::makeArcOfCircle(Vec center, double radius, double a1, double a2)
{
    Geometry g;
    g.kind = ArcOfCircle;
    g.p = center;
    g.r = radius;
    setTrimPeriodic(a1, a2, g.u1, g.u2);
    return g;
}

Vec Geometry::getStartPoint(bool emulateCCWXY) const
{
    if (kind == LineSegment) {
        // ElCLib::LineValue: U * D + P
        return {u1 * dir.x + p.x, u1 * dir.y + p.y};
    }
    if (isTrimmedConic()) {
        // GeomArcOfConic::getStartPoint: Geom_TrimmedCurve::StartPoint
        return conicValue(emulateCCWXY && isReversed() ? u2 : u1);
    }
    if (kind == BSplineCurve) {
        // Geom_BSplineCurve::StartPoint
        if (bsp.mults.front() == bsp.degree + 1) {
            return bsp.poles.front();
        }
        return bsplineValue(bsplineFirstParameter());
    }
    // ElCLib::CircleValue with XDir (1,0,0), YDir (0,1,0)
    double A1 = r * std::cos(u1);
    double A2 = r * std::sin(u1);
    return {A1 * 1.0 + A2 * 0.0 + p.x, A1 * 0.0 + A2 * 1.0 + p.y};
}

Vec Geometry::getEndPoint(bool emulateCCWXY) const
{
    if (kind == LineSegment) {
        return {u2 * dir.x + p.x, u2 * dir.y + p.y};
    }
    if (isTrimmedConic()) {
        return conicValue(emulateCCWXY && isReversed() ? u1 : u2);
    }
    if (kind == BSplineCurve) {
        // Geom_BSplineCurve::EndPoint
        if (bsp.mults.back() == bsp.degree + 1) {
            return bsp.poles.back();
        }
        return bsplineValue(bsplineLastParameter());
    }
    double A1 = r * std::cos(u2);
    double A2 = r * std::sin(u2);
    return {A1 * 1.0 + A2 * 0.0 + p.x, A1 * 0.0 + A2 * 1.0 + p.y};
}

void Geometry::setPoints(Vec start, Vec end)
{
    // GeomLineSegment::setPoints
    if (pntDistance(start, end) < Resolution) {
        throw GeometryError("Both points are equal");
    }
    // GC_MakeSegment(p1, p2): gp_Lin(p1, gp_Dir(p2 - p1)), trimmed to [0, p1.Distance(p2)]
    double dist = pntDistance(start, end);
    double aX = end.x - start.x;
    double aY = end.y - start.y;
    double aZ = 0.0;
    double aD = std::sqrt(aX * aX + aY * aY + aZ * aZ);
    p = start;
    dir = {aX / aD, aY / aD};
    u1 = 0.;
    u2 = dist;
}

void Geometry::getRange(double& u, double& v) const
{
    // GeomArcOfCircle::getRange(u, v, emulateCCWXY=true), axis +Z, XDirection (1,0,0)
    const double angleXU = -0.0;
    u = u1 + angleXU;
    v = u2 + angleXU;
    if (v < u) {
        v += 2 * std::numbers::pi;
    }
    if (v - u > 2 * std::numbers::pi) {
        v -= 2 * std::numbers::pi;
    }
}

void Geometry::setRange(double u, double v)
{
    // GeomArcOfCircle::setRange(u, v, emulateCCWXY=true)
    const double angleXU = -0.0;
    setTrimPeriodic(u - angleXU, v - angleXU, u1, u2);
}

// The conics: gp_Ax2, ElCLib, Geom_TrimmedCurve ---------------------------------------------

namespace
{

// gp_XYZ::Modulus
double modulus(const V3& v)
{
    return std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
}

// gp_XYZ::Cross: a ^ right
V3 cross(const V3& a, const V3& right)
{
    double Xresult = a.y * right.z - a.z * right.y;
    double Yresult = a.z * right.x - a.x * right.z;
    double z = a.x * right.y - a.y * right.x;
    return {Xresult, Yresult, z};
}

// gp_XYZ::CrossCross: a ^ (coord1 ^ coord2)
V3 crossCross(const V3& a, const V3& Coord1, const V3& Coord2)
{
    double Xresult = a.y * (Coord1.x * Coord2.y - Coord1.y * Coord2.x)
        - a.z * (Coord1.z * Coord2.x - Coord1.x * Coord2.z);
    double Yresult = a.z * (Coord1.y * Coord2.z - Coord1.z * Coord2.y)
        - a.x * (Coord1.x * Coord2.y - Coord1.y * Coord2.x);
    double z = a.x * (Coord1.z * Coord2.x - Coord1.x * Coord2.z)
        - a.y * (Coord1.y * Coord2.z - Coord1.z * Coord2.y);
    return {Xresult, Yresult, z};
}

V3 divided(const V3& v, double d)
{
    return {v.x / d, v.y / d, v.z / d};
}

// gp_Dir::Crossed
V3 dirCrossed(const V3& a, const V3& right)
{
    V3 v = cross(a, right);
    double D = modulus(v);
    if (D <= Resolution) {
        throw GeometryError("gp_Dir::Crossed() - result vector has zero norm");
    }
    return divided(v, D);
}

// gp_Dir::CrossCrossed
V3 dirCrossCrossed(const V3& a, const V3& v1, const V3& v2)
{
    V3 v = crossCross(a, v1, v2);
    double D = modulus(v);
    if (D <= Resolution) {
        throw GeometryError("gp_Dir::CrossCrossed() - result vector has zero norm");
    }
    return divided(v, D);
}

double dot(const V3& a, const V3& b)
{
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

constexpr double Angular = 1.e-12;  // Precision::Angular()

// Standard_Real's Epsilon(): the distance to the next representable number away from zero
double Epsilon(double Value)
{
    if (Value >= 0.0) {
        return std::nextafter(Value, DBL_MAX) - Value;
    }
    return Value - std::nextafter(Value, -DBL_MAX);
}

}  // namespace

V3 Sketcher::makeDir(double x, double y, double z)
{
    // gp_Dir(Xv, Yv, Zv)
    double D = std::sqrt(x * x + y * y + z * z);
    if (D <= Resolution) {
        throw GeometryError("gp_Dir() - input vector has zero norm");
    }
    return {x / D, y / D, z / D};
}

void Ax2::setXDirection(const V3& theVx)
{
    // gp_Ax2::SetXDirection
    double aDot = dot(theVx, n);
    if (1. - std::abs(aDot) <= Angular) {
        throw GeometryError("gp_Ax2::SetXDirection() - parameter is parallel to main direction");
    }
    vx = dirCrossCrossed(n, theVx, n);
    vy = dirCrossed(n, vx);
}

void Ax2::setDirection(const V3& V)
{
    // gp_Ax2::SetDirection
    double A = dot(V, vx);
    if (1. - std::abs(A) <= Angular) {
        if (A > 0.) {
            vx = vy;
            vy = n;
            n = V;
        }
        else {
            vx = n;
            n = V;
        }
    }
    else {
        n = V;
        vx = dirCrossCrossed(V, vx, V);
        vy = dirCrossed(V, vx);
    }
}

Vec Geometry::conicValue(double U) const
{
    const V3& XDir = pos.vx;
    const V3& YDir = pos.vy;
    const V3& PLoc = pos.loc;
    double A1, A2;
    switch (kind) {
        case Ellipse:
        case ArcOfEllipse:
            // ElCLib::EllipseValue
            A1 = majR * std::cos(U);
            A2 = minR * std::sin(U);
            break;
        case ArcOfHyperbola:
            // ElCLib::HyperbolaValue
            A1 = majR * std::cosh(U);
            A2 = minR * std::sinh(U);
            break;
        case ArcOfParabola:
            // ElCLib::ParabolaValue
            if (focal == 0.0) {
                return {U * YDir.x + PLoc.x, U * YDir.y + PLoc.y};
            }
            A1 = U * U / (4.0 * focal);
            A2 = U;
            break;
        default:
            return {};
    }
    return {A1 * XDir.x + A2 * YDir.x + PLoc.x, A1 * XDir.y + A2 * YDir.y + PLoc.y};
}

void Geometry::setTrimConic(double U1, double U2, bool Sense, bool theAdjustPeriodic)
{
    // Geom_TrimmedCurve::SetTrim on an ellipse (periodic), a hyperbola or a parabola
    bool sameSense = true;
    if (U1 == U2) {
        throw GeometryError("Geom_TrimmedCurve::U1 == U2");
    }
    if (kind == ArcOfEllipse) {
        sameSense = Sense;
        u1 = U1;
        u2 = U2;
        if (theAdjustPeriodic) {
            adjustPeriodic(0., twoPi, std::min(std::abs(u2 - u1) / 2, PConfusion), u1, u2);
        }
    }
    else {
        if (U1 < U2) {
            sameSense = Sense;
            u1 = U1;
            u2 = U2;
        }
        else {
            sameSense = !Sense;
            u1 = U2;
            u2 = U1;
        }
        // (a hyperbola's and a parabola's parameters run over the whole real line)
    }
    if (!sameSense) {
        reverseTrimmed();
    }
}

void Geometry::reverseBasis()
{
    // Geom_Conic::Reverse
    V3 Vz = pos.n;
    Vz = {-Vz.x, -Vz.y, -Vz.z};
    pos.setDirection(Vz);
}

void Geometry::reverseTrimmed()
{
    // Geom_TrimmedCurve::Reverse: ReversedParameter is 2 pi - U on an ellipse, -U on a hyperbola
    // or a parabola
    auto reversed = [&](double U) {
        return kind == ArcOfEllipse ? twoPi - U : -U;
    };
    double U1 = reversed(u2);
    double U2 = reversed(u1);
    reverseBasis();
    setTrimConic(U1, U2, true, false);
}

Geometry Geometry::makeEllipse(Vec center, double major, double minor, Vec xaxis)
{
    // GC_MakeEllipse(gp_Ax2(center, +Z), major, minor): gp_Elips's checks
    if (minor < 0.0 || major < minor) {
        throw GeometryError("Geom_Ellipse: the major radius must be greater than or equal to the minor radius");
    }
    Geometry g;
    g.kind = Ellipse;
    g.pos.loc = V3 {center.x, center.y, 0.0};
    // gp_Ax2(P, (0, 0, 1)) picks X = (1, 0, -0)
    g.pos.vx = V3 {1.0, 0.0, -0.0};
    g.pos.vy = dirCrossed(g.pos.n, g.pos.vx);
    g.majR = major;
    g.minR = minor;
    // .XAxis = xaxis (ConicPy::setXAxis)
    g.pos.setXDirection(makeDir(xaxis.x, xaxis.y, 0.0));
    return g;
}

Geometry Geometry::makeArcOfEllipse(Vec center, double major, double minor, Vec xaxis, double U1, double U2)
{
    Geometry g = makeEllipse(center, major, minor, xaxis);
    g.kind = ArcOfEllipse;
    g.setTrimConic(U1, U2, true, true);
    return g;
}

Geometry Geometry::makeArcOfHyperbola(Vec center, double major, double minor, Vec xaxis, double U1, double U2)
{
    Geometry g;
    g.kind = ArcOfHyperbola;
    g.pos.loc = V3 {center.x, center.y, 0.0};
    g.setMajorRadius(major);
    g.setMinorRadius(minor);
    g.pos.setXDirection(makeDir(xaxis.x, xaxis.y, 0.0));
    g.setTrimConic(U1, U2, true, true);
    return g;
}

Geometry Geometry::makeArcOfParabola(Vec vertex, double f, Vec xaxis, double U1, double U2)
{
    Geometry g;
    g.kind = ArcOfParabola;
    g.pos.loc = V3 {vertex.x, vertex.y, 0.0};
    g.setFocal(f);
    g.pos.setXDirection(makeDir(xaxis.x, xaxis.y, 0.0));
    g.setTrimConic(U1, U2, true, true);
    return g;
}

void Geometry::setMajorRadius(double radius)
{
    if (kind == ArcOfHyperbola) {
        // gp_Hypr::SetMajorRadius
        if (radius < 0.0) {
            throw GeometryError("gp_Hypr::SetMajorRadius() - major radius should be greater or equal zero");
        }
    }
    else if (radius < minR) {
        // gp_Elips::SetMajorRadius
        throw GeometryError("gp_Elips::SetMajorRadius() - major radius should be greater or equal to minor radius");
    }
    majR = radius;
}

void Geometry::setMinorRadius(double radius)
{
    if (kind == ArcOfHyperbola) {
        // gp_Hypr::SetMinorRadius
        if (radius < 0.0) {
            throw GeometryError("gp_Hypr::SetMinorRadius() - minor radius should be greater or equal zero");
        }
    }
    else if (radius < 0.0 || majR < radius) {
        // gp_Elips::SetMinorRadius
        throw GeometryError(
            "gp_Elips::SetMinorRadius() - minor radius should be a positive number lesser or equal "
            "to major radius"
        );
    }
    minR = radius;
}

void Geometry::setMajorAxisDir(Vec newdir)
{
    // GeomEllipse::setMajorAxisDir / GeomArcOfConic::setXAxisDir
    double sqr = newdir.x * newdir.x + newdir.y * newdir.y + 0.0 * 0.0;  // Base::Vector3d::Sqr
    if (sqr < SquareConfusion) {
        return;  // zero vector was passed. Keep the old orientation.
    }
    pos.setXDirection(makeDir(newdir.x, newdir.y, 0.0));
}

void Geometry::setFocal(double f)
{
    // gp_Parab::SetFocal
    if (f < 0.0) {
        throw GeometryError("gp_Parab::SetFocal() - focal length should be greater or equal zero");
    }
    focal = f;
}

Vec Geometry::getFocus() const
{
    // Geom_Parabola::Focus
    return {pos.loc.x + focal * pos.vx.x, pos.loc.y + focal * pos.vx.y};
}

void Geometry::getConicRange(double& u, double& v)
{
    if (kind == ArcOfEllipse) {
        // GeomArcOfEllipse::getRange(u, v, emulateCCWXY=true)
        u = u1;
        v = u2;
        if (isReversed()) {
            std::swap(u, v);
            u = -u;
            v = -v;
            if (v < u) {
                v += 2 * std::numbers::pi;
            }
            if (v - u > 2 * std::numbers::pi) {
                v -= 2 * std::numbers::pi;
            }
        }
        return;
    }
    // GeomArcOfHyperbola / GeomArcOfParabola::getRange(u, v, emulateCCWXY=true)
    if (isReversed()) {
        reverseBasis();
    }
    u = u1;
    v = u2;
}

void Geometry::setConicRange(double u, double v)
{
    if (kind == ArcOfEllipse) {
        // GeomArcOfEllipse::setRange(u, v, emulateCCWXY=true)
        if (isReversed()) {
            std::swap(u, v);
            u = -u;
            v = -v;
        }
        setTrimConic(u, v, true, true);
        return;
    }
    // GeomArcOfHyperbola / GeomArcOfParabola::setRange(u, v, emulateCCWXY=true)
    setTrimConic(u, v, true, true);
    if (isReversed()) {
        reverseBasis();
    }
}

// The B-spline: Geom_BSplineCurve -----------------------------------------------------------

namespace
{
// Geom_BSplineCurve.cxx's Rational(): do the weights differ?
bool rationalWeights(const std::vector<double>& W)
{
    bool rat = false;
    for (size_t i = 0; i + 1 < W.size(); i++) {
        rat = std::abs(W[i] - W[i + 1]) > Resolution;
        if (rat) {
            break;
        }
    }
    return rat;
}
}  // namespace

Geometry Geometry::makeBSpline(BSplineData data)
{
    // Geom_BSplineCurve(Poles, Weights, Knots, Mults, Degree, Periodic): CheckCurveData's checks
    const int deg = data.degree;
    if (deg < 1 || deg > 25) {
        throw GeometryError("BSpline curve: invalid degree");
    }
    if (data.poles.size() < 2) {
        throw GeometryError("BSpline curve: at least 2 poles required");
    }
    if (data.knots.size() != data.mults.size() || data.knots.size() < 2) {
        throw GeometryError("BSpline curve: Knot and Mult array size mismatch");
    }
    for (size_t i = 1; i < data.knots.size(); i++) {
        if (data.knots[i] - data.knots[i - 1] <= Epsilon(std::abs(data.knots[i - 1]))) {
            throw GeometryError("BSpline curve: Knots interval values too close");
        }
    }
    int sum = 0;
    for (int m : data.mults) {
        sum += m;
    }
    const size_t nbpoles = data.poles.size();
    if (data.periodic) {
        if (data.mults.front() != data.mults.back() || int(nbpoles) != sum - data.mults.back()) {
            throw GeometryError("BSpline curve: # Poles and degree mismatch");
        }
    }
    else if (int(nbpoles) != sum - deg - 1) {
        throw GeometryError("BSpline curve: # Poles and degree mismatch");
    }
    if (!data.weights.empty()) {
        if (data.weights.size() != nbpoles) {
            throw GeometryError("BSpline curve: Weights and Poles array size mismatch");
        }
        for (double w : data.weights) {
            if (w <= Resolution) {
                throw GeometryError("BSpline curve: Weights values too small");
            }
        }
        if (!rationalWeights(data.weights)) {
            data.weights.clear();
        }
    }
    Geometry g;
    g.kind = BSplineCurve;
    g.bsp = std::move(data);
    return g;
}

std::vector<double> Geometry::getWeights() const
{
    if (bsp.weights.empty()) {
        return std::vector<double>(bsp.poles.size(), 1.0);
    }
    return bsp.weights;
}

void Geometry::setWeight(int index, double W)
{
    // Geom_BSplineCurve::SetWeight
    if (index < 0 || index >= int(bsp.poles.size())) {
        throw GeometryError("BSpline curve: SetWeight: Index and #pole mismatch");
    }
    if (W <= Resolution) {
        throw GeometryError("BSpline curve: SetWeight: Weight too small");
    }
    bool isRational = !bsp.weights.empty();
    bool rat = isRational || (std::abs(W - 1.) > Resolution);
    if (rat) {
        if (rat && !isRational) {
            bsp.weights.assign(bsp.poles.size(), 1.);
        }
        bsp.weights[index] = W;
        rat = rationalWeights(bsp.weights);
        if (!rat) {
            bsp.weights.clear();
        }
    }
}

void Geometry::setPoles(const std::vector<Vec>& poles, const std::vector<double>& weights)
{
    // GeomBSplineCurve::setPoles(poles, weights)
    if (poles.size() != weights.size()) {
        throw GeometryError("poles and weights mismatch");
    }
    // GeomBSplineCurve::workAroundOCCTBug
    if (weights.size() >= 2) {
        auto lastindex = bsp.poles.size();
        double lastbutonevalue = bsp.weights.empty() ? 1.0 : bsp.weights[lastindex - 2];
        double fakelastvalue = lastbutonevalue + weights[weights.size() - 2];
        setWeight(int(weights.size()) - 1, fakelastvalue);
    }
    for (size_t i = 0; i < poles.size(); i++) {
        // Geom_BSplineCurve::SetPole(Index, P, Weight)
        bsp.poles.at(i) = poles[i];
        setWeight(int(i), weights[i]);
    }
}

namespace
{
// The flat knots, padded for a periodic curve as GCS::BSpline::setupFlattenedKnots does.
std::vector<double> flatKnots(const BSplineData& b)
{
    std::vector<double> fk;
    for (size_t i = 0; i < b.knots.size(); ++i) {
        fk.insert(fk.end(), b.mults[i], b.knots[i]);
    }
    if (b.periodic) {
        double period = b.knots.back() - b.knots.front();
        int c = b.degree + 1 - b.mults[0];
        std::vector<double> frontNew(fk.end() - b.mults.back() - c, fk.end() - b.mults.back());
        std::vector<double> backNew(fk.begin() + b.mults.front(), fk.begin() + b.mults.front() + c);
        fk.insert(fk.end(), backNew.begin(), backNew.end());
        fk.insert(fk.begin(), frontNew.begin(), frontNew.end());
        for (int i = 0; i < c; ++i) {
            *(fk.begin() + i) -= period;
            *(fk.end() - 1 - i) += period;
        }
    }
    return fk;
}
}  // namespace

double Geometry::bsplineFirstParameter() const
{
    if (bsp.periodic) {
        return bsp.knots.front();
    }
    // Geom_BSplineCurve::FirstParameter: flatknots(deg + 1)
    return flatKnots(bsp)[bsp.degree];
}

double Geometry::bsplineLastParameter() const
{
    if (bsp.periodic) {
        return bsp.knots.back();
    }
    auto fk = flatKnots(bsp);
    return fk[fk.size() - 1 - bsp.degree];
}

namespace
{
// GCS::BSpline::splineValue: de Boor's recursion over d (p + 1 values) in the span ending at k
double splineValue(double x, size_t k, unsigned int p, std::vector<double>& d, const std::vector<double>& flatknots)
{
    for (size_t r = 1; r < p + 1; ++r) {
        for (size_t j = p; j > r - 1; --j) {
            double alpha = (x - flatknots[j + k - p]) / (flatknots[j + 1 + k - r] - flatknots[j + k - p]);
            d[j] = (1.0 - alpha) * d[j - 1] + alpha * d[j];
        }
    }
    return p < d.size() ? d[p] : 0.0;
}
}  // namespace

void Geometry::bsplineD1(double u, Vec& value, Vec& tangent) const
{
    // The rational curve and its first derivative at u, from the homogeneous poles as
    // GCS::BSpline::Value takes them (the span holding u, poles taken cyclically when periodic)
    const unsigned int p = bsp.degree;
    std::vector<double> fk = flatKnots(bsp);
    size_t k = p;
    while (k + 1 < fk.size() - p - 1 && fk[k + 1] <= u) {
        ++k;
    }
    const size_t n = bsp.poles.size();
    const size_t startpole = k - p;
    std::vector<double> wts = getWeights();
    auto px = [&](size_t i) {
        return bsp.poles[(startpole + i) % n].x;
    };
    auto py = [&](size_t i) {
        return bsp.poles[(startpole + i) % n].y;
    };
    auto pw = [&](size_t i) {
        return wts[(startpole + i) % n];
    };
    std::vector<double> d(p + 1);
    for (size_t i = 0; i <= p; ++i) {
        d[i] = px(i) * pw(i);
    }
    double xsum = splineValue(u, k, p, d, fk);
    for (size_t i = 0; i <= p; ++i) {
        d[i] = py(i) * pw(i);
    }
    double ysum = splineValue(u, k, p, d, fk);
    for (size_t i = 0; i <= p; ++i) {
        d[i] = pw(i);
    }
    double wsum = splineValue(u, k, p, d, fk);

    d.resize(p);
    auto slope = [&](auto&& q) {
        for (size_t i = 1; i <= p; ++i) {
            d[i - 1] = (q(i) - q(i - 1)) / (fk[startpole + i + p] - fk[startpole + i]);
        }
        return p * splineValue(u, k, p - 1, d, fk);
    };
    double xslope = slope([&](size_t i) { return px(i) * pw(i); });
    double yslope = slope([&](size_t i) { return py(i) * pw(i); });
    double wslope = slope([&](size_t i) { return pw(i); });

    value = {xsum / wsum, ysum / wsum};
    tangent = {(wsum * xslope - wslope * xsum) / wsum / wsum, (wsum * yslope - wslope * ysum) / wsum / wsum};
}

Vec Geometry::bsplineValue(double u) const
{
    Vec value, tangent;
    bsplineD1(u, value, tangent);
    return value;
}

namespace
{
// gp_Trsf::SetValues(a11 .. a34): the 3x3 part times 1/s (gp_Mat::Divide), s the signed cube root of its
// determinant, then Orthogonalize (columns, then rows); loc the last column.
struct Trsf
{
    double M[3][3];
    double scale;
    double loc[3];
};
void normalize3(double v[3])
{
    double d = std::sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);  // gp_XYZ::Modulus
    v[0] /= d;
    v[1] /= d;
    v[2] /= d;
}
double dot3(const double a[3], const double b[3])
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}
// gp_Trsf::Orthogonalize's Gram-Schmidt on three vectors
void orthonormal(double v1[3], double v2[3], double v3[3])
{
    normalize3(v1);
    double d = dot3(v2, v1);
    for (int k = 0; k < 3; ++k) {
        v2[k] -= v1[k] * d;
    }
    normalize3(v2);
    double d1 = dot3(v3, v1), d2 = dot3(v3, v2);
    for (int k = 0; k < 3; ++k) {
        v3[k] -= v1[k] * d1 + v2[k] * d2;
    }
    normalize3(v3);
}
Trsf setValues(const double m[3][4])
{
    Trsf t {};
    double M[3][3];
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            M[i][j] = m[i][j];
        }
    }
    double det = M[0][0] * (M[1][1] * M[2][2] - M[2][1] * M[1][2])
        - M[0][1] * (M[1][0] * M[2][2] - M[2][0] * M[1][2])
        + M[0][2] * (M[1][0] * M[2][1] - M[2][0] * M[1][1]);
    if (std::fabs(det) < DBL_MIN) {
        throw GeometryError("gp_Trsf::SetValues, null determinant");
    }
    double s = det > 0 ? std::pow(det, 1. / 3.) : -std::pow(-det, 1. / 3.);
    double inv = 1 / s;
    for (auto& row : M) {
        for (double& x : row) {
            x *= inv;
        }
    }
    double c[3][3];
    for (int j = 0; j < 3; ++j) {
        for (int i = 0; i < 3; ++i) {
            c[j][i] = M[i][j];
        }
    }
    orthonormal(c[0], c[1], c[2]);
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            M[i][j] = c[j][i];
        }
    }
    orthonormal(M[0], M[1], M[2]);
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            t.M[i][j] = M[i][j];
        }
        t.loc[i] = m[i][3];
    }
    t.scale = s;
    return t;
}
// gp_Pnt::Transform with a gp_CompoundTrsf (gp_Trsf::Transforms)
Vec apply(const Trsf& t, Vec p)
{
    double x = t.M[0][0] * p.x + t.M[0][1] * p.y + t.M[0][2] * 0.0;
    double y = t.M[1][0] * p.x + t.M[1][1] * p.y + t.M[1][2] * 0.0;
    if (t.scale != 1.0) {
        x *= t.scale;
        y *= t.scale;
    }
    return {x + t.loc[0], y + t.loc[1]};
}
// gp_Dir::Transform: the vectorial part, normalised, reversed for a negative scale
V3 applyDir(const Trsf& t, V3 d)
{
    double v[3] = {t.M[0][0] * d.x + t.M[0][1] * d.y + t.M[0][2] * d.z,
                   t.M[1][0] * d.x + t.M[1][1] * d.y + t.M[1][2] * d.z,
                   t.M[2][0] * d.x + t.M[2][1] * d.y + t.M[2][2] * d.z};
    normalize3(v);
    if (t.scale < 0.0) {
        v[0] = -v[0];
        v[1] = -v[1];
        v[2] = -v[2];
    }
    return {v[0], v[1], v[2]};
}
}  // namespace

void Geometry::transform(const double m[3][4])
{
    Trsf t = setValues(m);
    double as = std::fabs(t.scale);
    switch (kind) {
        case Point:
            p = apply(t, p);
            break;
        case LineSegment: {
            // Geom_TrimmedCurve::Transform: the line's location and direction, the trims times |scale|
            // (Geom_Line::TransformedParameter)
            p = apply(t, p);
            V3 d = applyDir(t, V3 {dir.x, dir.y, 0.0});
            dir = {d.x, d.y};
            u1 *= as;
            u2 *= as;
        } break;
        case Circle:
        case ArcOfCircle: {
            // The circle here keeps the X direction (1, 0): a turn of its frame moves the trims instead.
            V3 d = applyDir(t, V3 {1.0, 0.0, 0.0});
            double turn = std::atan2(d.y, d.x);
            p = apply(t, p);
            r *= as;
            if (kind == ArcOfCircle) {
                u1 += turn;
                u2 += turn;
            }
        } break;
        case Ellipse:
        case ArcOfEllipse:
        case ArcOfHyperbola:
        case ArcOfParabola: {
            // Geom_Conic::Transform: gp_Ax2 (location and directions), the radii or focal times |scale|
            Vec l = apply(t, Vec {pos.loc.x, pos.loc.y});
            pos.loc = V3 {l.x, l.y, 0.0};
            pos.n = applyDir(t, pos.n);
            pos.vx = applyDir(t, pos.vx);
            pos.vy = applyDir(t, pos.vy);
            majR *= as;
            minR *= as;
            focal *= as;
        } break;
        case BSplineCurve:
            // Geom_BSplineCurve::Transform: every pole
            for (auto& q : bsp.poles) {
                q = apply(t, q);
            }
            break;
    }
}

double Geometry::closestParameter(Vec point) const
{
    // GeomCurve::closestParameter: GeomAPI_ProjectPointOnCurve(point, curve)'s
    // LowerDistanceParameter, the nearest of the curve's orthogonal projections of the point
    // within its range (an end point counts only where it is one). Where there is none,
    // OpenCascade raises and FreeCAD takes the nearer end. The projections are found here as the
    // roots of (C(u) - P) . C'(u) on a sampling of the range, each refined by bisection to the bit.
    double first = 0, last = 0;
    std::function<void(double, Vec&, Vec&)> d1;
    switch (kind) {
        case Point:
            return 0.0;
        case LineSegment:
            first = u1;
            last = u2;
            d1 = [&](double u, Vec& c, Vec& t) {
                c = {u * dir.x + p.x, u * dir.y + p.y};
                t = dir;
            };
            break;
        case Circle:
        case ArcOfCircle:
            first = kind == Circle ? 0.0 : u1;
            last = kind == Circle ? twoPi : u2;
            d1 = [&](double u, Vec& c, Vec& t) {
                c = {r * std::cos(u) + p.x, r * std::sin(u) + p.y};
                t = {-r * std::sin(u), r * std::cos(u)};
            };
            break;
        case BSplineCurve:
            first = bsplineFirstParameter();
            last = bsplineLastParameter();
            d1 = [&](double u, Vec& c, Vec& t) { bsplineD1(u, c, t); };
            break;
        default:
            first = kind == Ellipse ? 0.0 : u1;
            last = kind == Ellipse ? twoPi : u2;
            d1 = [&](double u, Vec& c, Vec& t) {
                c = conicValue(u);
                double A1, A2;  // the derivative's coordinates along X and Y
                if (kind == ArcOfHyperbola) {
                    A1 = majR * std::sinh(u);
                    A2 = minR * std::cosh(u);
                }
                else if (kind == ArcOfParabola) {
                    A1 = focal == 0.0 ? 0.0 : u / (2.0 * focal);
                    A2 = 1.0;
                }
                else {
                    A1 = -majR * std::sin(u);
                    A2 = minR * std::cos(u);
                }
                t = {A1 * pos.vx.x + A2 * pos.vy.x, A1 * pos.vx.y + A2 * pos.vy.y};
            };
            break;
    }
    auto f = [&](double u) {
        Vec c, t;
        d1(u, c, t);
        return (c.x - point.x) * t.x + (c.y - point.y) * t.y;
    };
    auto dist2 = [&](double u) {
        Vec c, t;
        d1(u, c, t);
        return (c.x - point.x) * (c.x - point.x) + (c.y - point.y) * (c.y - point.y);
    };
    int samples = 64;
    if (kind == BSplineCurve) {
        samples = 32 * int(std::max<size_t>(1, bsp.poles.size()));
    }
    else if (kind == LineSegment) {
        samples = 1;
    }
    double best = 0, bestd = DBL_MAX;
    bool found = false;
    auto consider = [&](double u) {
        double d = dist2(u);
        if (!found || d < bestd) {
            best = u;
            bestd = d;
            found = true;
        }
    };
    double ua = first, fa = f(first);
    for (int i = 1; i <= samples; ++i) {
        double ub = i == samples ? last : first + (last - first) * i / samples;
        double fb = f(ub);
        if (fa == 0.0) {
            consider(ua);
        }
        else if ((fa < 0) != (fb < 0) && fb != 0.0) {
            double lo = ua, hi = ub, flo = fa;
            for (int it = 0; it < 200; ++it) {
                double mid = lo + (hi - lo) / 2;
                if (mid <= lo || mid >= hi) {
                    break;
                }
                double fm = f(mid);
                if (fm == 0.0) {
                    lo = hi = mid;
                    break;
                }
                if ((fm < 0) == (flo < 0)) {
                    lo = mid;
                    flo = fm;
                }
                else {
                    hi = mid;
                }
            }
            consider(std::abs(f(lo)) <= std::abs(f(hi)) ? lo : hi);
        }
        ua = ub;
        fa = fb;
    }
    if (fa == 0.0) {
        consider(ua);
    }
    if (found) {
        return best;
    }
    // GeomCurve::closestParameter's fallback for a bounded curve: the nearer end
    Vec s, e, t;
    d1(first, s, t);
    d1(last, e, t);
    double ds = (s.x - point.x) * (s.x - point.x) + (s.y - point.y) * (s.y - point.y);
    double de = (e.x - point.x) * (e.x - point.x) + (e.y - point.y) * (e.y - point.y);
    return de < ds ? last : first;
}
// Sketch ======================================================================================

Sketch::Sketch()
    : defaultSolver(GCS::DogLeg)
    , defaultSolverRedundant(GCS::DogLeg)
    , RecalculateInitialSolutionWhileMovingPoint(false)
    , resolveAfterGeometryUpdated(false)
    , GCSsys()
    , ConstraintsCounter(0)
    , isInitMove(false)
    , moveStep(0)
    , debugMode(GCS::Minimal)
{}

Sketch::~Sketch()
{
    clear();
}

void Sketch::clear()
{
    // clear all internal data sets
    Points.clear();
    Lines.clear();
    Arcs.clear();
    Circles.clear();
    Ellipses.clear();
    ArcsOfEllipse.clear();
    ArcsOfHyperbola.clear();
    ArcsOfParabola.clear();
    BSplines.clear();
    resolveAfterGeometryUpdated = false;

    // (FreeCAD deletes the doubles allocated with new; here they live in paramPool, see newParam)
    Parameters.clear();
    DrivenParameters.clear();
    FixParameters.clear();
    paramPool.clear();
    paramPoolUsed = paramPoolSize = 0;

    param2geoelement.clear();
    pDependencyGroups.clear();

    internalAlignmentGeometryMap.clear();

    Geoms.clear();
    Constrs.clear();

    GCSsys.clear();
    isInitMove = false;
    ConstraintsCounter = 0;
    Conflicting.clear();
    Redundant.clear();
    PartiallyRedundant.clear();
    MalformedConstraints.clear();
}

bool Sketch::analyseBlockedGeometry(
    const std::vector<Geometry>& internalGeoList,
    const std::vector<Constraint*>& constraintList,
    std::vector<bool>& onlyblockedGeometry,
    std::vector<int>& blockedGeoIds
) const
{
    // To understand this function read the documentation in Sketch.h
    // It is important that "onlyblockedGeometry" ONLY identifies blocked geometry
    // that is not affected by any other driving constraint
    bool doesBlockAffectOtherConstraints = false;

    int geoindex = 0;
    for (const auto& g : internalGeoList) {
        if (g.blocked) {
            // is it only affected by one constraint, the block constraint (and this is driving), or
            // by any other driving constraint ?
            bool blockOnly = true;
            bool blockisDriving = false;

            for (auto c : constraintList) {
                // is block driving
                if (c->Type == Sketcher::Block && c->isActive && c->First == geoindex) {
                    blockisDriving = true;
                }
                // We have another driving constraint (which may be InternalAlignment)
                if (c->Type != Sketcher::Block && c->isDriving
                    && (c->First == geoindex || c->Second == geoindex || c->Third == geoindex)) {
                    blockOnly = false;
                }
            }

            if (blockisDriving) {
                if (blockOnly) {
                    onlyblockedGeometry[geoindex] = true;  // we pre-fix this geometry
                }
                else {
                    // we will have to pos-analyse the first diagnose result for these geometries
                    // in order to avoid redundant constraints
                    doesBlockAffectOtherConstraints = true;
                    blockedGeoIds.push_back(geoindex);
                }
            }
        }
        geoindex++;
    }

    return doesBlockAffectOtherConstraints;
}

double* Sketch::newParam(double value)
{
    if (paramPoolUsed == paramPoolSize) {
        reserveParams(256);
    }
    double* p = &paramPool.back()[paramPoolUsed++];
    *p = value;
    return p;
}

void Sketch::reserveParams(size_t count)
{
    paramPool.push_back(std::make_unique<double[]>(count));
    paramPoolUsed = 0;
    paramPoolSize = count;
}

int Sketch::setUpSketch(
    const std::vector<Geometry>& GeoList,
    const std::vector<Constraint*>& ConstraintList,
    int extGeoCount
)
{
    clear();

    // All parameters in one block, in the order they are made (see newParam): 11 is the most a
    // curve other than a B-spline takes; a B-spline takes 3 per pole, 1 per knot and 4; a
    // constraint at most 4 (a value and the curve parameters of a tangency via a point).
    size_t count = 4 * ConstraintList.size() + 16;
    for (const auto& g : GeoList) {
        count += g.kind == Geometry::BSplineCurve
            ? 3 * g.bspline().poles.size() + g.bspline().knots.size() + 4
            : 11;
    }
    reserveParams(count);

    // The geometries that are in groups are going to be ignored by the solver.
    std::set<int> inGroupGeoIds;
    for (const auto& c : ConstraintList) {
        if (c->Type == Group || c->Type == Text) {
            // Start from index 1, as 0 is the frame.
            for (int i = 1; c->hasElement(i); ++i) {
                inGroupGeoIds.insert(c->getGeoId(i));
            }
        }
    }

    std::vector<Geometry> intGeoList, extGeoList;
    std::copy(GeoList.begin(), GeoList.end() - extGeoCount, std::back_inserter(intGeoList));
    std::copy(GeoList.end() - extGeoCount, GeoList.end(), std::back_inserter(extGeoList));

    // these geometries are blocked, frozen and sent as fixed parameters to the solver
    std::vector<bool> onlyBlockedGeometry(intGeoList.size(), false);
    // these constraints are unenforceable due to a Blocked constraint
    std::vector<bool> unenforceableConstraints(ConstraintList.size(), false);

    // Pre-analysis of blocked geometry (new block constraint) to fix geometry only affected by a
    // block constraint (see comment in Sketch.h)
    std::vector<int> blockedGeoIds;
    bool doesBlockAffectOtherConstraints
        = analyseBlockedGeometry(intGeoList, ConstraintList, onlyBlockedGeometry, blockedGeoIds);

    buildInternalAlignmentGeometryMap(ConstraintList);

    addGeometry(intGeoList, onlyBlockedGeometry, inGroupGeoIds);
    int extStart = Geoms.size();
    addGeometry(extGeoList, true);
    int extEnd = Geoms.size() - 1;
    for (int i = extStart; i <= extEnd; i++) {
        Geoms[i].external = true;
    }

    // The Geoms list might be empty after an undo/redo
    if (!Geoms.empty()) {
        // Disable any constraint that act on geometries that are in a group.
        for (size_t i = 0; i < ConstraintList.size(); ++i) {
            const auto& c = ConstraintList[i];

            if (c->Type == Group || c->Type == Text) {
                continue;
            }

            for (int j = 0; c->hasElement(j); ++j) {
                if (inGroupGeoIds.count(c->getGeoId(j))) {
                    unenforceableConstraints[i] = true;
                    break;
                }
            }
        }

        addConstraints(ConstraintList, unenforceableConstraints);
    }
    clearTemporaryConstraints();
    GCSsys.declareUnknowns(Parameters);
    GCSsys.declareDrivenParams(DrivenParameters);
    GCSsys.initSolution(defaultSolverRedundant);

    // Post-analysis
    // Now that we have all the parameters information, we deal properly with the block constraints
    // if necessary
    if (doesBlockAffectOtherConstraints) {

        std::vector<double*> params_to_block;

        bool unsatisfied_groups
            = analyseBlockedConstraintDependentParameters(blockedGeoIds, params_to_block);

        // I am unsure if more than one QR iterations are needed with the current implementation.
        //
        // With previous implementations mostly one QR iteration was enough, but if block constraint
        // is abused, more iterations were needed.
        while (unsatisfied_groups) {
            // We tried hard not to arrive to an unsatisfied group, so we try harder
            // This loop has the advantage that the user will notice increased effort to solve,
            // so they may understand that they are abusing the block constraint, while guaranteeing
            // that wrong behaviour of the block constraint is not undetected.

            // Another QR iteration
            fixParametersAndDiagnose(params_to_block);

            unsatisfied_groups
                = analyseBlockedConstraintDependentParameters(blockedGeoIds, params_to_block);
        }

        // 2. If something needs blocking, block-it
        fixParametersAndDiagnose(params_to_block);
    }

    // Now we set the Sketch status with the latest solver information
    GCSsys.getConflicting(Conflicting);
    GCSsys.getRedundant(Redundant);
    GCSsys.getPartiallyRedundant(PartiallyRedundant);
    GCSsys.getDependentParams(pDependentParametersList);

    calculateDependentParametersElements();

    return GCSsys.dofsNumber();
}

void Sketch::buildInternalAlignmentGeometryMap(const std::vector<Constraint*>& constraintList)
{
    for (auto* c : constraintList) {
        if (c->Type == InternalAlignment) {
            internalAlignmentGeometryMap[c->First] = c->Second;
        }
    }
}

void Sketch::fixParametersAndDiagnose(std::vector<double*>& params_to_block)
{
    if (!params_to_block.empty()) {  // only there are parameters to fix
        for (auto p : params_to_block) {
            if (auto findparam = std::ranges::find(Parameters, p); findparam != Parameters.end()) {
                FixParameters.push_back(*findparam);
                Parameters.erase(findparam);
            }
        }

        pDependencyGroups.clear();
        clearTemporaryConstraints();
        GCSsys.invalidatedDiagnosis();
        GCSsys.declareUnknowns(Parameters);
        GCSsys.declareDrivenParams(DrivenParameters);
        GCSsys.initSolution(defaultSolverRedundant);
    }
}

bool Sketch::analyseBlockedConstraintDependentParameters(
    std::vector<int>& blockedGeoIds,
    std::vector<double*>& params_to_block
) const
{
    // 1. Retrieve solver information
    std::vector<std::vector<double*>> groups;
    GCSsys.getDependentParamsGroups(groups);

    // 2. Determine blockable parameters for each group (see documentation in header file).
    struct group
    {
        std::vector<double*> blockable_params_in_group;
        double* blocking_param_in_group = nullptr;
    };

    std::vector<group> prop_groups(groups.size());

    for (size_t i = 0; i < groups.size(); i++) {
        for (size_t j = 0; j < groups[i].size(); j++) {

            double* thisparam = *std::next(groups[i].begin(), j);

            if (auto element = param2geoelement.find(thisparam); element != param2geoelement.end()) {

                if (auto blockable = std::ranges::find(blockedGeoIds, std::get<0>(element->second));
                    blockable != blockedGeoIds.end()) {
                    // This dependent parameter group contains at least one parameter that should be
                    // blocked, so added to the blockable list.
                    prop_groups[i].blockable_params_in_group.push_back(thisparam);
                }
            }
        }
    }

    // 3. Apply heuristic - pick the last blockable param available to block the group, starting
    // from the last group
    for (size_t i = prop_groups.size(); i-- > 0;) {
        for (size_t j = prop_groups[i].blockable_params_in_group.size(); j-- > 0;) {
            // check if parameter is already satisfying one group
            double* thisparam = prop_groups[i].blockable_params_in_group[j];
            auto pos = std::ranges::find(params_to_block, thisparam);

            if (pos == params_to_block.end()) {  // not found, so add
                params_to_block.push_back(thisparam);
                prop_groups[i].blocking_param_in_group = thisparam;
                break;
            }
        }
    }

    // 4. Check if groups are satisfied or are licitly unsatisfiable and thus deemed as satisfied
    bool unsatisfied_groups = false;
    for (auto& prop_group : prop_groups) {
        // 4.1. unsatisfiable group
        if (prop_group.blockable_params_in_group.empty()) {
            // this group does not contain any blockable parameter, so it is by definition satisfied
            // (or impossible to satisfy by block constraints)
            continue;
        }
        // 4.2. satisfiable and not satisfied
        if (!prop_group.blocking_param_in_group) {
            unsatisfied_groups = true;
        }
    }

    return unsatisfied_groups;
}

void Sketch::clearTemporaryConstraints()
{
    GCSsys.clearByTag(GCS::DefaultTemporaryConstraint);
}

void Sketch::calculateDependentParametersElements()
{
    // (The per-geometry SolverGeometryExtension is not kept; getDependentParameterElements()
    // reports the same information.)

    std::vector<std::vector<double*>> groups;
    GCSsys.getDependentParamsGroups(groups);

    pDependencyGroups.resize(groups.size());

    // translate parameters into elements (Geoid, PointPos)
    for (size_t i = 0; i < groups.size(); i++) {
        for (size_t j = 0; j < groups[i].size(); j++) {

            auto element = param2geoelement.find(groups[i][j]);

            if (element != param2geoelement.end()) {
                pDependencyGroups[i].insert(
                    std::pair(std::get<0>(element->second), std::get<1>(element->second))
                );
            }
        }
    }

    // check if groups have a common element, if yes merge the groups
    auto havecommonelement = [](std::set<std::pair<int, PointPos>>::iterator begin1,
                                std::set<std::pair<int, PointPos>>::iterator end1,
                                std::set<std::pair<int, PointPos>>::iterator begin2,
                                std::set<std::pair<int, PointPos>>::iterator end2) {
        while (begin1 != end1 && begin2 != end2) {
            if (*begin1 < *begin2) {
                ++begin1;
            }
            else if (*begin2 < *begin1) {
                ++begin2;
            }
            else {
                return true;
            }
        }

        return false;
    };

    if (pDependencyGroups.size() > 1) {  // only if there is more than 1 group
        size_t endcount = pDependencyGroups.size() - 1;

        for (size_t i = 0; i < endcount; i++) {
            if (havecommonelement(
                    pDependencyGroups[i].begin(),
                    pDependencyGroups[i].end(),
                    pDependencyGroups[i + 1].begin(),
                    pDependencyGroups[i + 1].end()
                )) {
                pDependencyGroups[i].insert(
                    pDependencyGroups[i + 1].begin(),
                    pDependencyGroups[i + 1].end()
                );
                pDependencyGroups.erase(pDependencyGroups.begin() + i + 1);
                endcount--;
            }
        }
    }
}

std::vector<std::tuple<int, PointPos, int>> Sketch::getDependentParameterElements() const
{
    std::vector<std::tuple<int, PointPos, int>> out;
    for (auto param : pDependentParametersList) {
        auto element = param2geoelement.find(param);
        if (element != param2geoelement.end()) {
            out.push_back(element->second);
        }
    }
    return out;
}

std::set<std::pair<int, PointPos>> Sketch::getDependencyGroup(int geoId, PointPos pos) const
{
    geoId = checkGeoId(geoId);

    std::set<std::pair<int, PointPos>> group;

    auto key = std::make_pair(geoId, pos);

    for (auto& set : pDependencyGroups) {
        if (set.find(key) != set.end()) {
            group = set;
            break;
        }
    }

    return group;
}

int Sketch::resetSolver()
{
    clearTemporaryConstraints();
    GCSsys.declareUnknowns(Parameters);
    GCSsys.declareDrivenParams(DrivenParameters);
    GCSsys.initSolution(defaultSolverRedundant);
    GCSsys.getConflicting(Conflicting);
    GCSsys.getRedundant(Redundant);
    GCSsys.getPartiallyRedundant(PartiallyRedundant);
    GCSsys.getDependentParams(pDependentParametersList);

    calculateDependentParametersElements();

    return GCSsys.dofsNumber();
}

// Geometry adding ==========================================================

int Sketch::addGeometry(const Geometry& geo, bool fixed)
{
    switch (geo.kind) {
        case Geometry::Point:
            return addPoint(geo, fixed);
        case Geometry::LineSegment:
            return addLineSegment(geo, fixed);
        case Geometry::Circle:
            return addCircle(geo, fixed);
        case Geometry::ArcOfCircle:
            return addArc(geo, fixed);
        case Geometry::Ellipse:
            return addEllipse(geo, fixed);
        case Geometry::ArcOfEllipse:
            return addArcOfEllipse(geo, fixed);
        case Geometry::ArcOfHyperbola:
            return addArcOfHyperbola(geo, fixed);
        case Geometry::ArcOfParabola:
            return addArcOfParabola(geo, fixed);
        case Geometry::BSplineCurve:
            // Current B-Spline implementation relies on OCCT calculations, so a second solve
            // is necessary to update actual solver implementation to account for changes in B-Spline
            // geometry
            resolveAfterGeometryUpdated = true;
            return addBSpline(geo, fixed);
    }
    throw std::invalid_argument("Sketch::addGeometry(): Unknown or unsupported type added to a sketch");
}

int Sketch::addGeometry(const std::vector<Geometry>& geos, bool fixed)
{
    int ret = -1;
    for (const auto& geo : geos) {
        ret = addGeometry(geo, fixed);
    }
    return ret;
}

int Sketch::addGeometry(const std::vector<Geometry>& geos, const std::vector<bool>& blockedGeometry)
{
    int ret = -1;
    auto bit = blockedGeometry.begin();
    for (auto it = geos.begin(); it != geos.end() && bit != blockedGeometry.end(); ++it, ++bit) {
        ret = addGeometry(*it, *bit);
    }
    return ret;
}

int Sketch::addGeometry(
    const std::vector<Geometry>& geos,
    const std::vector<bool>& blockedGeometry,
    const std::set<int>& inGroupGeoIds
)
{
    int ret = -1;
    int geoIdCounter = 0;
    auto bit = blockedGeometry.begin();
    for (auto it = geos.begin(); it != geos.end() && bit != blockedGeometry.end(); ++it, ++bit, ++geoIdCounter) {
        // Check if the current geometry is in group: kept, but not given to the solver.
        if (inGroupGeoIds.count(geoIdCounter)) {
            GeoDef def;
            def.geo = *it;
            Geoms.push_back(def);
        }
        else {
            ret = addGeometry(*it, *bit);
        }
    }
    return ret;
}

int Sketch::addPoint(const Geometry& point, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = point;
    def.type = Point;

    // set the parameter for the solver
    params.push_back(newParam(point.getPoint().x));
    params.push_back(newParam(point.getPoint().y));

    // set the points for later constraints
    GCS::Point p1;
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];
    def.startPointId = Points.size();
    def.endPointId = Points.size();
    def.midPointId = Points.size();
    Points.push_back(p1);

    // store complete set
    Geoms.push_back(def);

    if (!fixed) {
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p1.x),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::start, 0)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p1.y),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::start, 1)
        );
    }

    // return the position of the newly added geometry
    return Geoms.size() - 1;
}

int Sketch::addLineSegment(const Geometry& lineSegment, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = lineSegment;
    def.type = Line;

    // get the points from the line
    Vec start = lineSegment.getStartPoint();
    Vec end = lineSegment.getEndPoint();

    // the points for later constraints
    GCS::Point p1, p2;

    params.push_back(newParam(start.x));
    params.push_back(newParam(start.y));
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];

    params.push_back(newParam(end.x));
    params.push_back(newParam(end.y));
    p2.x = params[params.size() - 2];
    p2.y = params[params.size() - 1];

    // add the points
    def.startPointId = Points.size();
    def.endPointId = Points.size() + 1;
    Points.push_back(p1);
    Points.push_back(p2);

    // set the line for later constraints
    GCS::Line l;
    l.p1 = p1;
    l.p2 = p2;
    def.index = Lines.size();
    Lines.push_back(l);

    // store complete set
    Geoms.push_back(def);

    if (!fixed) {
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p1.x),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::start, 0)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p1.y),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::start, 1)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p2.x),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::end, 0)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p2.y),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::end, 1)
        );
    }

    // return the position of the newly added geometry
    return Geoms.size() - 1;
}

int Sketch::addArc(const Geometry& circleSegment, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = circleSegment;
    def.type = Arc;

    Vec center = circleSegment.getCenter();
    Vec startPnt = circleSegment.getStartPoint(/*emulateCCW=true*/);
    Vec endPnt = circleSegment.getEndPoint(/*emulateCCW=true*/);
    double radius = circleSegment.getRadius();
    double startAngle, endAngle;
    circleSegment.getRange(startAngle, endAngle /*, emulateCCW=true*/);

    GCS::Point p1, p2, p3;

    params.push_back(newParam(startPnt.x));
    params.push_back(newParam(startPnt.y));
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];

    params.push_back(newParam(endPnt.x));
    params.push_back(newParam(endPnt.y));
    p2.x = params[params.size() - 2];
    p2.y = params[params.size() - 1];

    params.push_back(newParam(center.x));
    params.push_back(newParam(center.y));
    p3.x = params[params.size() - 2];
    p3.y = params[params.size() - 1];

    def.startPointId = Points.size();
    Points.push_back(p1);
    def.endPointId = Points.size();
    Points.push_back(p2);
    def.midPointId = Points.size();
    Points.push_back(p3);

    params.push_back(newParam(radius));
    double* r = params[params.size() - 1];
    params.push_back(newParam(startAngle));
    double* a1 = params[params.size() - 1];
    params.push_back(newParam(endAngle));
    double* a2 = params[params.size() - 1];

    // set the arc for later constraints
    GCS::Arc a;
    a.start = p1;
    a.end = p2;
    a.center = p3;
    a.rad = r;
    a.startAngle = a1;
    a.endAngle = a2;
    def.index = Arcs.size();
    Arcs.push_back(a);

    // store complete set
    Geoms.push_back(def);

    // arcs require an ArcRules constraint for the end points
    if (!fixed) {
        GCSsys.addConstraintArcRules(a);
    }

    if (!fixed) {
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p1.x),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::start, 0)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p1.y),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::start, 1)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p2.x),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::end, 0)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p2.y),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::end, 1)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p3.x),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::mid, 0)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p3.y),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::mid, 1)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(r),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::none, 0)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(a1),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::none, 1)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(a2),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::none, 2)
        );
    }

    // return the position of the newly added geometry
    return Geoms.size() - 1;
}

int Sketch::addCircle(const Geometry& cir, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = cir;
    def.type = Circle;

    Vec center = cir.getCenter();
    double radius = cir.getRadius();

    GCS::Point p1;

    params.push_back(newParam(center.x));
    params.push_back(newParam(center.y));
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];

    params.push_back(newParam(radius));

    def.midPointId = Points.size();
    Points.push_back(p1);

    // add the radius parameter
    double* r = params[params.size() - 1];

    // set the circle for later constraints
    GCS::Circle c;
    c.center = p1;
    c.rad = r;
    def.index = Circles.size();
    Circles.push_back(c);

    // store complete set
    Geoms.push_back(def);

    if (!fixed) {
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p1.x),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::mid, 0)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(p1.y),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::mid, 1)
        );
        param2geoelement.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(r),
            std::forward_as_tuple(Geoms.size() - 1, PointPos::none, 0)
        );
    }

    // return the position of the newly added geometry
    return Geoms.size() - 1;
}

int Sketch::addArcOfEllipse(const Geometry& ellipseSegment, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = ellipseSegment;
    def.type = ArcOfEllipse;
    Geometry* aoe = &def.geo;

    Vec center = aoe->getCenter();
    Vec startPnt = aoe->getStartPoint(/*emulateCCW=*/true);
    Vec endPnt = aoe->getEndPoint(/*emulateCCW=*/true);
    double radmaj = aoe->getMajorRadius();
    double radmin = aoe->getMinorRadius();
    Vec radmajdir = aoe->getMajorAxisDir();

    double dist_C_F = sqrt(radmaj * radmaj - radmin * radmin);
    // solver parameters
    Vec focus1 {center.x + dist_C_F * radmajdir.x, center.y + dist_C_F * radmajdir.y};

    double startAngle, endAngle;
    aoe->getConicRange(startAngle, endAngle /*, emulateCCW=true*/);

    GCS::Point p1, p2, p3;

    params.push_back(newParam(startPnt.x));
    params.push_back(newParam(startPnt.y));
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];

    params.push_back(newParam(endPnt.x));
    params.push_back(newParam(endPnt.y));
    p2.x = params[params.size() - 2];
    p2.y = params[params.size() - 1];

    params.push_back(newParam(center.x));
    params.push_back(newParam(center.y));
    p3.x = params[params.size() - 2];
    p3.y = params[params.size() - 1];

    params.push_back(newParam(focus1.x));
    params.push_back(newParam(focus1.y));
    double* f1X = params[params.size() - 2];
    double* f1Y = params[params.size() - 1];

    def.startPointId = Points.size();
    Points.push_back(p1);
    def.endPointId = Points.size();
    Points.push_back(p2);
    def.midPointId = Points.size();
    Points.push_back(p3);

    // add the radius parameters
    params.push_back(newParam(radmin));
    double* rmin = params[params.size() - 1];
    params.push_back(newParam(startAngle));
    double* a1 = params[params.size() - 1];
    params.push_back(newParam(endAngle));
    double* a2 = params[params.size() - 1];

    // set the arc for later constraints
    GCS::ArcOfEllipse a;
    a.start = p1;
    a.end = p2;
    a.center = p3;
    a.focus1.x = f1X;
    a.focus1.y = f1Y;
    a.radmin = rmin;
    a.startAngle = a1;
    a.endAngle = a2;
    def.index = ArcsOfEllipse.size();
    ArcsOfEllipse.push_back(a);

    // store complete set
    Geoms.push_back(def);

    // arcs require an ArcRules constraint for the end points
    if (!fixed) {
        GCSsys.addConstraintArcOfEllipseRules(a);
    }

    if (!fixed) {
        int g = Geoms.size() - 1;
        param2geoelement.emplace(p1.x, std::tuple(g, PointPos::start, 0));
        param2geoelement.emplace(p1.y, std::tuple(g, PointPos::start, 1));
        param2geoelement.emplace(p2.x, std::tuple(g, PointPos::end, 0));
        param2geoelement.emplace(p2.y, std::tuple(g, PointPos::end, 1));
        param2geoelement.emplace(p3.x, std::tuple(g, PointPos::mid, 0));
        param2geoelement.emplace(p3.y, std::tuple(g, PointPos::mid, 1));
        param2geoelement.emplace(f1X, std::tuple(g, PointPos::none, 0));
        param2geoelement.emplace(f1Y, std::tuple(g, PointPos::none, 1));
        param2geoelement.emplace(rmin, std::tuple(g, PointPos::none, 2));
        param2geoelement.emplace(a1, std::tuple(g, PointPos::none, 3));
        param2geoelement.emplace(a2, std::tuple(g, PointPos::none, 4));
    }

    // return the position of the newly added geometry
    return Geoms.size() - 1;
}

int Sketch::addArcOfHyperbola(const Geometry& hyperbolaSegment, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = hyperbolaSegment;
    def.type = ArcOfHyperbola;
    Geometry* aoh = &def.geo;

    Vec center = aoh->getCenter();
    Vec startPnt = aoh->getStartPoint();
    Vec endPnt = aoh->getEndPoint();
    double radmaj = aoh->getMajorRadius();
    double radmin = aoh->getMinorRadius();
    Vec radmajdir = aoh->getMajorAxisDir();

    double dist_C_F = sqrt(radmaj * radmaj + radmin * radmin);
    // solver parameters
    Vec focus1 {center.x + dist_C_F * radmajdir.x, center.y + dist_C_F * radmajdir.y};  //+x

    double startAngle, endAngle;
    aoh->getConicRange(startAngle, endAngle /*, emulateCCW=true*/);

    GCS::Point p1, p2, p3;

    params.push_back(newParam(startPnt.x));
    params.push_back(newParam(startPnt.y));
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];

    params.push_back(newParam(endPnt.x));
    params.push_back(newParam(endPnt.y));
    p2.x = params[params.size() - 2];
    p2.y = params[params.size() - 1];

    params.push_back(newParam(center.x));
    params.push_back(newParam(center.y));
    p3.x = params[params.size() - 2];
    p3.y = params[params.size() - 1];

    params.push_back(newParam(focus1.x));
    params.push_back(newParam(focus1.y));
    double* f1X = params[params.size() - 2];
    double* f1Y = params[params.size() - 1];

    def.startPointId = Points.size();
    Points.push_back(p1);
    def.endPointId = Points.size();
    Points.push_back(p2);
    def.midPointId = Points.size();
    Points.push_back(p3);

    // add the radius parameters
    params.push_back(newParam(radmin));
    double* rmin = params[params.size() - 1];
    params.push_back(newParam(startAngle));
    double* a1 = params[params.size() - 1];
    params.push_back(newParam(endAngle));
    double* a2 = params[params.size() - 1];

    // set the arc for later constraints
    GCS::ArcOfHyperbola a;
    a.start = p1;
    a.end = p2;
    a.center = p3;
    a.focus1.x = f1X;
    a.focus1.y = f1Y;
    a.radmin = rmin;
    a.startAngle = a1;
    a.endAngle = a2;
    def.index = ArcsOfHyperbola.size();
    ArcsOfHyperbola.push_back(a);

    // store complete set
    Geoms.push_back(def);

    // arcs require an ArcRules constraint for the end points
    if (!fixed) {
        GCSsys.addConstraintArcOfHyperbolaRules(a);
    }

    if (!fixed) {
        int g = Geoms.size() - 1;
        param2geoelement.emplace(p1.x, std::tuple(g, PointPos::start, 0));
        param2geoelement.emplace(p1.y, std::tuple(g, PointPos::start, 1));
        param2geoelement.emplace(p2.x, std::tuple(g, PointPos::end, 0));
        param2geoelement.emplace(p2.y, std::tuple(g, PointPos::end, 1));
        param2geoelement.emplace(p3.x, std::tuple(g, PointPos::mid, 0));
        param2geoelement.emplace(p3.y, std::tuple(g, PointPos::mid, 1));
        param2geoelement.emplace(f1X, std::tuple(g, PointPos::none, 0));
        param2geoelement.emplace(f1Y, std::tuple(g, PointPos::none, 1));
        param2geoelement.emplace(rmin, std::tuple(g, PointPos::none, 2));
        param2geoelement.emplace(a1, std::tuple(g, PointPos::none, 3));
        param2geoelement.emplace(a2, std::tuple(g, PointPos::none, 4));
    }

    // return the position of the newly added geometry
    return Geoms.size() - 1;
}

int Sketch::addArcOfParabola(const Geometry& parabolaSegment, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = parabolaSegment;
    def.type = ArcOfParabola;
    Geometry* aop = &def.geo;

    Vec vertex = aop->getCenter();
    Vec startPnt = aop->getStartPoint();
    Vec endPnt = aop->getEndPoint();
    Vec focus = aop->getFocus();

    double startAngle, endAngle;
    aop->getConicRange(startAngle, endAngle /*, emulateCCW=true*/);

    GCS::Point p1, p2, p3, p4;

    params.push_back(newParam(startPnt.x));
    params.push_back(newParam(startPnt.y));
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];

    params.push_back(newParam(endPnt.x));
    params.push_back(newParam(endPnt.y));
    p2.x = params[params.size() - 2];
    p2.y = params[params.size() - 1];

    params.push_back(newParam(vertex.x));
    params.push_back(newParam(vertex.y));
    p3.x = params[params.size() - 2];
    p3.y = params[params.size() - 1];

    params.push_back(newParam(focus.x));
    params.push_back(newParam(focus.y));
    p4.x = params[params.size() - 2];
    p4.y = params[params.size() - 1];

    def.startPointId = Points.size();
    Points.push_back(p1);
    def.endPointId = Points.size();
    Points.push_back(p2);
    def.midPointId = Points.size();
    Points.push_back(p3);

    // add the radius parameters
    params.push_back(newParam(startAngle));
    double* a1 = params[params.size() - 1];
    params.push_back(newParam(endAngle));
    double* a2 = params[params.size() - 1];

    // set the arc for later constraints
    GCS::ArcOfParabola a;
    a.start = p1;
    a.end = p2;
    a.vertex = p3;
    a.focus1 = p4;
    a.startAngle = a1;
    a.endAngle = a2;
    def.index = ArcsOfParabola.size();
    ArcsOfParabola.push_back(a);

    // store complete set
    Geoms.push_back(def);

    // arcs require an ArcRules constraint for the end points
    if (!fixed) {
        GCSsys.addConstraintArcOfParabolaRules(a);
    }

    if (!fixed) {
        int g = Geoms.size() - 1;
        param2geoelement.emplace(p1.x, std::tuple(g, PointPos::start, 0));
        param2geoelement.emplace(p1.y, std::tuple(g, PointPos::start, 1));
        param2geoelement.emplace(p2.x, std::tuple(g, PointPos::end, 0));
        param2geoelement.emplace(p2.y, std::tuple(g, PointPos::end, 1));
        param2geoelement.emplace(p3.x, std::tuple(g, PointPos::mid, 0));
        param2geoelement.emplace(p3.y, std::tuple(g, PointPos::mid, 1));
        param2geoelement.emplace(p4.x, std::tuple(g, PointPos::none, 0));
        param2geoelement.emplace(p4.y, std::tuple(g, PointPos::none, 1));
        param2geoelement.emplace(a1, std::tuple(g, PointPos::none, 2));
        param2geoelement.emplace(a2, std::tuple(g, PointPos::none, 3));
    }

    // return the position of the newly added geometry
    return Geoms.size() - 1;
}

int Sketch::addBSpline(const Geometry& bspline, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = bspline;
    def.type = BSpline;
    const Geometry* bsp = &def.geo;

    std::vector<Vec> poles = bsp->bspline().poles;
    std::vector<double> weights = bsp->getWeights();
    std::vector<double> knots = bsp->bspline().knots;
    std::vector<int> mult = bsp->bspline().mults;
    int degree = bsp->bspline().degree;
    bool periodic = bsp->bspline().periodic;

    // OCC hack
    // c means there is a constraint on that weight, nc no constraint
    // OCC provides normalized weights when polynomic [1 1 1] [c c c] and unnormalized weights when
    // rational [5 1 5] [c nc c] then when changing from polynomic to rational, after the first
    // solve any not-constrained pole circle gets normalized to 1. This only happens when changing
    // from polynomic to rational, any subsequent change remains unnormalized [5 1 5] [c nc nc] This
    // creates a visual problem that one of the poles shrinks to 1 mm when deleting an equality
    // constraint.

    int lastoneindex = -1;
    int countones = 0;
    double lastnotone = 1.0;

    for (size_t i = 0; i < weights.size(); i++) {
        if (weights[i] != 1.0) {
            lastnotone = weights[i];
        }
        else {  // is 1.0
            lastoneindex = i;
            countones++;
        }
    }

    if (countones == 1) {
        weights[lastoneindex] = (lastnotone * 0.99);
    }

    // end hack

    Vec startPnt = bsp->getStartPoint();
    Vec endPnt = bsp->getEndPoint();

    std::vector<GCS::Point> spoles;

    int g = Geoms.size();
    int i = 0;
    for (const auto& pole : poles) {
        params.push_back(newParam(pole.x));
        params.push_back(newParam(pole.y));

        GCS::Point p;
        p.x = params[params.size() - 2];
        p.y = params[params.size() - 1];

        spoles.push_back(p);

        if (!fixed) {
            param2geoelement.emplace(p.x, std::tuple(g, PointPos::none, i++));
            param2geoelement.emplace(p.y, std::tuple(g, PointPos::none, i++));
        }
    }

    std::vector<double*> sweights;

    for (const auto& weight : weights) {
        auto r = newParam(weight);
        params.push_back(r);
        sweights.push_back(params[params.size() - 1]);

        if (!fixed) {
            param2geoelement.emplace(r, std::tuple(g, PointPos::none, i++));
        }
    }

    std::vector<double*> sknots;

    for (const auto& knot : knots) {
        double* _knot = newParam(knot);
        // params.push_back(knot);
        sknots.push_back(_knot);
    }

    GCS::Point p1, p2;

    double* p1x = newParam(startPnt.x);
    double* p1y = newParam(startPnt.y);

    // If periodic, startpoint and endpoint do not play a role in the solver, this can remove
    // unnecessary DoF of determining where in the curve the start and the stop should be. However,
    // since start and end points are placed above knots, removing them leads to that knot being
    // unusable.
    params.push_back(p1x);
    params.push_back(p1y);

    p1.x = p1x;
    p1.y = p1y;

    double* p2x = newParam(endPnt.x);
    double* p2y = newParam(endPnt.y);

    params.push_back(p2x);
    params.push_back(p2y);

    p2.x = p2x;
    p2.y = p2y;

    def.startPointId = Points.size();
    Points.push_back(p1);
    def.endPointId = Points.size();
    Points.push_back(p2);

    GCS::BSpline bs;
    bs.start = p1;
    bs.end = p2;
    bs.poles = spoles;
    bs.weights = sweights;
    bs.knots = sknots;
    bs.mult = mult;
    bs.degree = degree;
    bs.periodic = periodic;
    def.index = BSplines.size();

    // non-solver related, just to enable initialization of knotspoints which is not a parameter of
    // the solver
    bs.knotpointGeoids.resize(knots.size());

    for (auto& kpGeoId : bs.knotpointGeoids) {
        kpGeoId = GeoEnum::GeoUndef;
    }

    BSplines.push_back(bs);

    // store complete set
    Geoms.push_back(def);

    // WARNING: This is only valid where the multiplicity of the endpoints conforms with a BSpline
    // only then the startpoint is the first control point and the endpoint is the last control
    // point accordingly, it is never the case for a periodic BSpline. NOTE: For an external
    // B-spline (i.e. fixed=true) we must not set the coincident constraints as the points are not
    // movable anyway. See #issue 0003176: Sketcher: always over-constrained when referencing
    // external B-Spline
    if (!fixed && !bs.periodic) {
        if (bs.mult[0] > bs.degree) {
            GCSsys.addConstraintP2PCoincident(*(bs.poles.begin()), bs.start);
        }
        if (bs.mult[mult.size() - 1] > bs.degree) {
            GCSsys.addConstraintP2PCoincident(*(bs.poles.end() - 1), bs.end);
        }
    }

    if (!fixed) {
        // Note: Poles and weight parameters are emplaced above
        param2geoelement.emplace(p1.x, std::tuple(g, PointPos::start, 0));
        param2geoelement.emplace(p1.y, std::tuple(g, PointPos::start, 1));
        param2geoelement.emplace(p2.x, std::tuple(g, PointPos::end, 0));
        param2geoelement.emplace(p2.y, std::tuple(g, PointPos::end, 1));
    }

    // return the position of the newly added geometry
    return Geoms.size() - 1;
}

int Sketch::addEllipse(const Geometry& elip, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = elip;
    def.type = Ellipse;
    const Geometry* elips = &def.geo;

    Vec center = elips->getCenter();
    double radmaj = elips->getMajorRadius();
    double radmin = elips->getMinorRadius();
    Vec radmajdir = elips->getMajorAxisDir();

    double dist_C_F = sqrt(radmaj * radmaj - radmin * radmin);
    // solver parameters
    Vec focus1 {center.x + dist_C_F * radmajdir.x, center.y + dist_C_F * radmajdir.y};  //+x

    GCS::Point c;

    params.push_back(newParam(center.x));
    params.push_back(newParam(center.y));
    c.x = params[params.size() - 2];
    c.y = params[params.size() - 1];

    def.midPointId = Points.size();  // this takes midPointId+1
    Points.push_back(c);

    params.push_back(newParam(focus1.x));
    params.push_back(newParam(focus1.y));
    double* f1X = params[params.size() - 2];
    double* f1Y = params[params.size() - 1];

    // add the radius parameters
    params.push_back(newParam(radmin));
    double* rmin = params[params.size() - 1];

    // set the ellipse for later constraints
    GCS::Ellipse e;
    e.focus1.x = f1X;
    e.focus1.y = f1Y;
    e.center = c;
    e.radmin = rmin;

    def.index = Ellipses.size();
    Ellipses.push_back(e);

    // store complete set
    Geoms.push_back(def);

    if (!fixed) {
        int g = Geoms.size() - 1;
        param2geoelement.emplace(c.x, std::tuple(g, PointPos::mid, 0));
        param2geoelement.emplace(c.y, std::tuple(g, PointPos::mid, 1));
        param2geoelement.emplace(f1X, std::tuple(g, PointPos::none, 0));
        param2geoelement.emplace(f1Y, std::tuple(g, PointPos::none, 1));
        param2geoelement.emplace(rmin, std::tuple(g, PointPos::none, 2));
    }

    // return the position of the newly added geometry
    return Geoms.size() - 1;
}

std::vector<Geometry> Sketch::extractGeometry(bool withConstructionElements, bool withExternalElements) const
{
    std::vector<Geometry> temp;
    temp.reserve(Geoms.size());
    for (const auto& geom : Geoms) {
        if ((!geom.external || withExternalElements)
            && (!geom.geo.construction || withConstructionElements)) {
            temp.push_back(geom.geo);
        }
    }

    return temp;
}

int Sketch::checkGeoId(int geoId) const
{
    if (geoId < 0) {
        geoId += Geoms.size();  // convert negative external-geometry index to index into Geoms
    }
    if (!(geoId >= 0 && geoId < int(Geoms.size()))) {
        throw std::out_of_range("Sketch::checkGeoId. GeoId index out range.");
    }
    return geoId;
}

GCS::Curve* Sketch::getGCSCurveByGeoId(int geoId)
{
    geoId = checkGeoId(geoId);
    switch (Geoms[geoId].type) {
        case Line:
            return &Lines[Geoms[geoId].index];
            break;
        case Circle:
            return &Circles[Geoms[geoId].index];
            break;
        case Arc:
            return &Arcs[Geoms[geoId].index];
            break;
        case Ellipse:
            return &Ellipses[Geoms[geoId].index];
            break;
        case ArcOfEllipse:
            return &ArcsOfEllipse[Geoms[geoId].index];
            break;
        case ArcOfHyperbola:
            return &ArcsOfHyperbola[Geoms[geoId].index];
            break;
        case ArcOfParabola:
            return &ArcsOfParabola[Geoms[geoId].index];
            break;
        case BSpline:
            return &BSplines[Geoms[geoId].index];
            break;
        default:
            return nullptr;
    };
}

// constraint adding ==========================================================

int Sketch::addConstraint(const Constraint* constraint)
{
    if (Geoms.empty()) {
        throw std::invalid_argument(
            "Sketch::addConstraint. Can't add constraint to a sketch with no geometry!"
        );
    }
    int rtn = -1;

    ConstrDef c;
    c.constr = const_cast<Constraint*>(constraint);
    c.driving = constraint->isDriving;

    // the datum of a dimensional constraint: a fixed parameter when driving, else a driven one
    auto newValue = [&]() {
        c.value = newParam(constraint->getValue());
        if (c.driving) {
            FixParameters.push_back(c.value);
        }
        else {
            Parameters.push_back(c.value);
            DrivenParameters.push_back(c.value);
        }
    };

    switch (constraint->Type) {
        case DistanceX:
            if (constraint->FirstPos == PointPos::none) {  // horizontal length of a line
                newValue();
                rtn = addDistanceXConstraint(constraint->First, c.value, c.driving);
            }
            else if (constraint->Second == GeoEnum::GeoUndef) {  // point on fixed x-coordinate
                newValue();
                rtn = addCoordinateXConstraint(constraint->First, constraint->FirstPos, c.value, c.driving);
            }
            else if (constraint->SecondPos != PointPos::none) {  // point to point horizontal distance
                newValue();
                rtn = addDistanceXConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    c.value,
                    c.driving
                );
            }
            break;
        case DistanceY:
            if (constraint->FirstPos == PointPos::none) {  // vertical length of a line
                newValue();
                rtn = addDistanceYConstraint(constraint->First, c.value, c.driving);
            }
            else if (constraint->Second == GeoEnum::GeoUndef) {  // point on fixed y-coordinate
                newValue();
                rtn = addCoordinateYConstraint(constraint->First, constraint->FirstPos, c.value, c.driving);
            }
            else if (constraint->SecondPos != PointPos::none) {  // point to point vertical distance
                newValue();
                rtn = addDistanceYConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    c.value,
                    c.driving
                );
            }
            break;
        case Horizontal:
            if (constraint->Second == GeoEnum::GeoUndef) {  // horizontal line
                rtn = addHorizontalConstraint(constraint->First);
            }
            else {  // two points on the same horizontal line
                rtn = addHorizontalConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos
                );
            }
            break;
        case Vertical:
            if (constraint->Second == GeoEnum::GeoUndef) {  // vertical line
                rtn = addVerticalConstraint(constraint->First);
            }
            else {  // two points on the same vertical line
                rtn = addVerticalConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos
                );
            }
            break;
        case Coincident:
            rtn = addPointCoincidentConstraint(
                constraint->First,
                constraint->FirstPos,
                constraint->Second,
                constraint->SecondPos
            );
            break;
        case PointOnObject:
            if (Geoms[checkGeoId(constraint->Second)].type == BSpline) {
                c.value = newParam(constraint->getValue());
                // Driving doesn't make sense here
                Parameters.push_back(c.value);

                rtn = addPointOnObjectConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    c.value
                );
            }
            else {
                rtn = addPointOnObjectConstraint(constraint->First, constraint->FirstPos, constraint->Second);
            }
            break;
        case Parallel:
            rtn = addParallelConstraint(constraint->First, constraint->Second);
            break;
        case Perpendicular:
            if (constraint->FirstPos != PointPos::none && constraint->SecondPos != PointPos::none
                && constraint->Third != GeoEnum::GeoUndef) {
                // point point line perpendicularity
                rtn = addPerpendicularConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    constraint->Third
                );
            }
            else if (
                constraint->FirstPos == PointPos::none && constraint->SecondPos == PointPos::none
                && constraint->Third == GeoEnum::GeoUndef
            ) {
                // simple perpendicularity
                rtn = addPerpendicularConstraint(constraint->First, constraint->Second);
            }
            else {
                // any other point-wise perpendicularity
                newValue();
                rtn = addAngleAtPointConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    constraint->Third,
                    constraint->ThirdPos,
                    c.value,
                    constraint->Type,
                    c.driving
                );
            }
            break;
        case Tangent: {
            bool isSpecialCase = false;

            if (constraint->FirstPos == PointPos::none && constraint->SecondPos == PointPos::none
                && constraint->Third == GeoEnum::GeoUndef) {
                // simple tangency
                rtn = addTangentConstraint(constraint->First, constraint->Second, constraint->Orientation);

                isSpecialCase = true;
            }
            else if (constraint->FirstPos == PointPos::start && constraint->Third == GeoEnum::GeoUndef) {
                // check for B-Spline Knot to curve tangency
                auto knotgeoId = checkGeoId(constraint->First);
                if (Geoms[knotgeoId].type == Point) {
                    const Geometry* point = &Geoms[knotgeoId].geo;

                    if (point->internalType == InternalType::BSplineKnotPoint) {
                        auto bsplinegeoid = internalAlignmentGeometryMap.at(constraint->First);

                        bsplinegeoid = checkGeoId(bsplinegeoid);

                        auto linegeoid = checkGeoId(constraint->Second);

                        if (Geoms[linegeoid].type == Line) {
                            if (constraint->SecondPos == PointPos::none) {
                                rtn = addTangentLineAtBSplineKnotConstraint(linegeoid, bsplinegeoid, knotgeoId);

                                isSpecialCase = true;
                            }
                            else if (
                                constraint->SecondPos == PointPos::start
                                || constraint->SecondPos == PointPos::end
                            ) {
                                rtn = addTangentLineEndpointAtBSplineKnotConstraint(
                                    linegeoid,
                                    constraint->SecondPos,
                                    bsplinegeoid,
                                    knotgeoId
                                );

                                isSpecialCase = true;
                            }
                        }
                    }
                }
            }
            if (!isSpecialCase) {
                // any other point-wise tangency (endpoint-to-curve, endpoint-to-endpoint,
                // tangent-via-point)
                newValue();
                rtn = addAngleAtPointConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    constraint->Third,
                    constraint->ThirdPos,
                    c.value,
                    constraint->Type,
                    c.driving
                );
            }
            break;
        }
        case Distance:
            if (constraint->SecondPos != PointPos::none) {  // point to point distance
                newValue();
                rtn = addDistanceConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    c.value,
                    c.driving
                );
            }
            else if (
                constraint->FirstPos == PointPos::none && constraint->SecondPos == PointPos::none
                && constraint->Second != GeoEnum::GeoUndef && constraint->Third == GeoEnum::GeoUndef
            ) {  // circle to circle, circle to
                 // arc, etc.
                newValue();
                rtn = addDistanceConstraint(
                    constraint->First,
                    constraint->Second,
                    c.value,
                    constraint->Orientation,
                    c.driving
                );
            }
            else if (constraint->Second != GeoEnum::GeoUndef) {
                if (constraint->FirstPos != PointPos::none) {  // point to line distance
                    newValue();
                    rtn = addDistanceConstraint(
                        constraint->First,
                        constraint->FirstPos,
                        constraint->Second,
                        c.value,
                        constraint->Orientation,
                        c.driving
                    );
                }
            }
            else {  // line length, arc length
                newValue();
                rtn = addDistanceConstraint(constraint->First, c.value, c.driving);
            }
            break;
        case Angle:
            if (constraint->Third != GeoEnum::GeoUndef) {
                newValue();
                rtn = addAngleAtPointConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    constraint->Third,
                    constraint->ThirdPos,
                    c.value,
                    constraint->Type,
                    c.driving
                );
            }
            // angle between two lines (with explicit start points)
            else if (constraint->SecondPos != PointPos::none) {
                newValue();
                rtn = addAngleConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    c.value,
                    c.driving
                );
            }
            else if (constraint->Second != GeoEnum::GeoUndef) {  // angle between two lines
                newValue();
                rtn = addAngleConstraint(constraint->First, constraint->Second, c.value, c.driving);
            }
            else if (constraint->First != GeoEnum::GeoUndef) {  // orientation angle of a line
                newValue();
                rtn = addAngleConstraint(constraint->First, c.value, c.driving);
            }
            break;
        case Radius: {
            newValue();
            rtn = addRadiusConstraint(constraint->First, c.value, c.driving);
            break;
        }
        case Diameter: {
            newValue();
            rtn = addDiameterConstraint(constraint->First, c.value, c.driving);
            break;
        }
        case Weight: {
            newValue();
            rtn = addRadiusConstraint(constraint->First, c.value, c.driving);
            break;
        }
        case Equal:
            rtn = addEqualConstraint(constraint->First, constraint->Second);
            break;
        case Symmetric:
            if (constraint->ThirdPos != PointPos::none) {
                rtn = addSymmetricConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    constraint->Third,
                    constraint->ThirdPos
                );
            }
            else {
                rtn = addSymmetricConstraint(
                    constraint->First,
                    constraint->FirstPos,
                    constraint->Second,
                    constraint->SecondPos,
                    constraint->Third
                );
            }
            break;
        case InternalAlignment:
            switch (constraint->AlignmentType) {
                case EllipseMajorDiameter:
                    rtn = addInternalAlignmentEllipseMajorDiameter(constraint->First, constraint->Second);
                    break;
                case EllipseMinorDiameter:
                    rtn = addInternalAlignmentEllipseMinorDiameter(constraint->First, constraint->Second);
                    break;
                case EllipseFocus1:
                    rtn = addInternalAlignmentEllipseFocus1(constraint->First, constraint->Second);
                    break;
                case EllipseFocus2:
                    rtn = addInternalAlignmentEllipseFocus2(constraint->First, constraint->Second);
                    break;
                case HyperbolaMajor:
                    rtn = addInternalAlignmentHyperbolaMajorDiameter(constraint->First, constraint->Second);
                    break;
                case HyperbolaMinor:
                    rtn = addInternalAlignmentHyperbolaMinorDiameter(constraint->First, constraint->Second);
                    break;
                case HyperbolaFocus:
                    rtn = addInternalAlignmentHyperbolaFocus(constraint->First, constraint->Second);
                    break;
                case ParabolaFocus:
                    rtn = addInternalAlignmentParabolaFocus(constraint->First, constraint->Second);
                    break;
                case BSplineControlPoint:
                    rtn = addInternalAlignmentBSplineControlPoint(
                        constraint->First,
                        constraint->Second,
                        constraint->InternalAlignmentIndex
                    );
                    break;
                case BSplineKnotPoint:
                    rtn = addInternalAlignmentKnotPoint(
                        constraint->First,
                        constraint->Second,
                        constraint->InternalAlignmentIndex
                    );
                    break;
                case ParabolaFocalAxis:
                    rtn = addInternalAlignmentParabolaFocalDistance(constraint->First, constraint->Second);
                    break;
                default:
                    break;
            }
            break;
        case SnellsLaw: {
            c.value = newParam(constraint->getValue());
            c.secondvalue = newParam(constraint->getValue());

            if (c.driving) {
                FixParameters.push_back(c.value);
                FixParameters.push_back(c.secondvalue);
            }
            else {
                Parameters.push_back(c.value);
                Parameters.push_back(c.secondvalue);
                DrivenParameters.push_back(c.value);
                DrivenParameters.push_back(c.secondvalue);
            }

            // assert(constraint->ThirdPos==none); //will work anyway...
            rtn = addSnellsLawConstraint(
                constraint->First,
                constraint->FirstPos,
                constraint->Second,
                constraint->SecondPos,
                constraint->Third,
                c.value,
                c.secondvalue,
                c.driving
            );
        } break;
        case Text:
        case Group: {
            if (constraint->isElementsEmpty()) {
                return -1;
            }
            // Check that the first element is correctly the group construction line
            if (Geoms[checkGeoId(constraint->getGeoId(0))].type != Line) {
                return -1;
            }

            rtn = ++ConstraintsCounter;
            break;
        }
        case Sketcher::None:   // ambiguous enum value
        case Sketcher::Block:  // handled separately while adding geometry
        case NumConstraintTypes:
            break;
    }

    Constrs.push_back(c);
    return rtn;
}

int Sketch::addConstraints(
    const std::vector<Constraint*>& ConstraintList,
    const std::vector<bool>& unenforceableConstraints
)
{
    int rtn = -1;

    int cid = 0;
    for (auto it = ConstraintList.cbegin(); it != ConstraintList.cend(); ++it, ++cid) {
        if (!unenforceableConstraints[cid] && (*it)->Type != Block && (*it)->isActive) {
            rtn = addConstraint(*it);

            if (rtn == -1) {
                int humanConstraintId = cid + 1;
                MalformedConstraints.push_back(humanConstraintId);
            }
        }
        else {
            ++ConstraintsCounter;  // For correct solver redundant reporting
        }
    }

    return rtn;
}

int Sketch::addCoordinateXConstraint(int geoId, PointPos pos, double* value, bool driving)
{
    geoId = checkGeoId(geoId);

    int pointId = getPointId(geoId, pos);

    if (pointId >= 0 && pointId < int(Points.size())) {

        GCS::Point& p = Points[pointId];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintCoordinateX(p, value, tag, driving);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addCoordinateYConstraint(int geoId, PointPos pos, double* value, bool driving)
{
    geoId = checkGeoId(geoId);

    int pointId = getPointId(geoId, pos);

    if (pointId >= 0 && pointId < int(Points.size())) {
        GCS::Point& p = Points[pointId];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintCoordinateY(p, value, tag, driving);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addDistanceXConstraint(int geoId, double* value, bool driving)
{
    geoId = checkGeoId(geoId);

    if (Geoms[geoId].type != Line) {
        return -1;
    }

    GCS::Line& l = Lines[Geoms[geoId].index];

    int tag = ++ConstraintsCounter;
    GCSsys.addConstraintDifference(l.p1.x, l.p2.x, value, tag, driving);
    return ConstraintsCounter;
}

int Sketch::addDistanceYConstraint(int geoId, double* value, bool driving)
{
    geoId = checkGeoId(geoId);

    if (Geoms[geoId].type != Line) {
        return -1;
    }

    GCS::Line& l = Lines[Geoms[geoId].index];

    int tag = ++ConstraintsCounter;
    GCSsys.addConstraintDifference(l.p1.y, l.p2.y, value, tag, driving);
    return ConstraintsCounter;
}

int Sketch::addDistanceXConstraint(
    int geoId1,
    PointPos pos1,
    int geoId2,
    PointPos pos2,
    double* value,
    bool driving
)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    int pointId1 = getPointId(geoId1, pos1);
    int pointId2 = getPointId(geoId2, pos2);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintDifference(p1.x, p2.x, value, tag, driving);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addDistanceYConstraint(
    int geoId1,
    PointPos pos1,
    int geoId2,
    PointPos pos2,
    double* value,
    bool driving
)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    int pointId1 = getPointId(geoId1, pos1);
    int pointId2 = getPointId(geoId2, pos2);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintDifference(p1.y, p2.y, value, tag, driving);
        return ConstraintsCounter;
    }
    return -1;
}

// horizontal line constraint
int Sketch::addHorizontalConstraint(int geoId)
{
    geoId = checkGeoId(geoId);

    if (Geoms[geoId].type != Line) {
        return -1;
    }

    GCS::Line& l = Lines[Geoms[geoId].index];
    int tag = ++ConstraintsCounter;
    GCSsys.addConstraintHorizontal(l, tag);
    return ConstraintsCounter;
}

// two points on a horizontal line constraint
int Sketch::addHorizontalConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    int pointId1 = getPointId(geoId1, pos1);
    int pointId2 = getPointId(geoId2, pos2);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintHorizontal(p1, p2, tag);
        return ConstraintsCounter;
    }
    return -1;
}

// vertical line constraint
int Sketch::addVerticalConstraint(int geoId)
{
    geoId = checkGeoId(geoId);

    if (Geoms[geoId].type != Line) {
        return -1;
    }

    GCS::Line& l = Lines[Geoms[geoId].index];
    int tag = ++ConstraintsCounter;
    GCSsys.addConstraintVertical(l, tag);
    return ConstraintsCounter;
}

// two points on a vertical line constraint
int Sketch::addVerticalConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    int pointId1 = getPointId(geoId1, pos1);
    int pointId2 = getPointId(geoId2, pos2);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintVertical(p1, p2, tag);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addPointCoincidentConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    int pointId1 = getPointId(geoId1, pos1);
    int pointId2 = getPointId(geoId2, pos2);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2PCoincident(p1, p2, tag);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addParallelConstraint(int geoId1, int geoId2)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != Line || Geoms[geoId2].type != Line) {
        return -1;
    }

    GCS::Line& l1 = Lines[Geoms[geoId1].index];
    GCS::Line& l2 = Lines[Geoms[geoId2].index];
    int tag = ++ConstraintsCounter;
    GCSsys.addConstraintParallel(l1, l2, tag);
    return ConstraintsCounter;
}

// simple perpendicularity constraint
int Sketch::addPerpendicularConstraint(int geoId1, int geoId2)
{
    // accepts the following combinations:
    // 1) Line1, Line2/Circle2/Arc2
    // 2) Circle1, Line2 (converted to case #1)
    // 3) Arc1, Line2 (converted to case #1)
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId2].type == Line) {
        if (Geoms[geoId1].type == Line) {
            GCS::Line& l1 = Lines[Geoms[geoId1].index];
            GCS::Line& l2 = Lines[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPerpendicular(l1, l2, tag);
            return ConstraintsCounter;
        }
        else {
            std::swap(geoId1, geoId2);
        }
    }

    if (Geoms[geoId1].type == Line) {
        GCS::Line& l1 = Lines[Geoms[geoId1].index];
        if (Geoms[geoId2].type == Arc || Geoms[geoId2].type == Circle) {
            GCS::Point& p2 = Points[Geoms[geoId2].midPointId];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPointOnLine(p2, l1, tag);
            return ConstraintsCounter;
        }
    }

    // "Perpendicular constraints between {} and {} are not supported."
    return -1;
}

int Sketch::addPerpendicularConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, int geoId3)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);
    geoId3 = checkGeoId(geoId3);
    int pointId1 = getPointId(geoId1, pos1);
    int pointId2 = getPointId(geoId2, pos2);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size()) && Geoms[geoId3].type == Line) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];
        // As in FreeCAD: Lines is indexed by the geoId here, not by Geoms[geoId3].index.
        GCS::Line& l = Lines[geoId3];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintPerpendicular(p1, p2, l, tag);
        return ConstraintsCounter;
    }
    // "Perpendicular constraints need a line."
    return -1;
}

// simple tangency constraint
int Sketch::addTangentConstraint(int geoId1, int geoId2, ConstraintOrientation orientation)
{
    // accepts the following combinations:
    // 1) Line1, Line2/Circle2/Arc2
    // 2) Circle1, Line2 (converted to case #1)
    //    Circle1, Circle2/Arc2
    // 3) Arc1, Line2 (converted to case #1)
    //    Arc1, Circle2/Arc2
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId2].type == Line) {
        if (Geoms[geoId1].type == Line) {
            GCS::Line& l1 = Lines[Geoms[geoId1].index];
            GCS::Point& l2p1 = Points[Geoms[geoId2].startPointId];
            GCS::Point& l2p2 = Points[Geoms[geoId2].endPointId];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPointOnLine(l2p1, l1, tag);
            GCSsys.addConstraintPointOnLine(l2p2, l1, tag);
            return ConstraintsCounter;
        }
        else {
            std::swap(geoId1, geoId2);
        }
    }

    if (Geoms[geoId1].type == Line) {
        GCS::Line& l = Lines[Geoms[geoId1].index];
        if (Geoms[geoId2].type == Arc) {
            GCS::Arc& a = Arcs[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(l, a, tangentSide(orientation, l, a), tag);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == Circle) {
            GCS::Circle& c = Circles[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(l, c, tangentSide(orientation, l, c), tag);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == Ellipse) {
            GCS::Ellipse& e = Ellipses[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(l, e, tag);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == ArcOfEllipse) {
            GCS::ArcOfEllipse& a = ArcsOfEllipse[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(l, a, tag);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == BSpline) {
            // "Direct tangency constraint between line and B-spline is not supported. Use
            // tangent-via-point instead."
            return -1;
        }
    }
    else if (Geoms[geoId1].type == Circle) {
        GCS::Circle& c = Circles[Geoms[geoId1].index];
        if (Geoms[geoId2].type == Circle) {
            GCS::Circle& c2 = Circles[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(c, c2, tag);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == Ellipse) {
            // "Direct tangency constraint between circle and ellipse is not supported. ..."
            return -1;
        }
        else if (Geoms[geoId2].type == Arc) {
            GCS::Arc& a = Arcs[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(c, a, tag);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == BSpline) {
            // "Direct tangency constraint between circle and B-spline is not supported. ..."
            return -1;
        }
    }
    else if (Geoms[geoId1].type == Ellipse) {
        if (Geoms[geoId2].type == Circle || Geoms[geoId2].type == Arc
            || Geoms[geoId2].type == BSpline) {
            // "Direct tangency constraint between ... and ellipse is not supported. Use
            // tangent-via-point instead."
            return -1;
        }
    }
    else if (Geoms[geoId1].type == Arc) {
        GCS::Arc& a = Arcs[Geoms[geoId1].index];
        if (Geoms[geoId2].type == Circle) {
            GCS::Circle& c = Circles[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(c, a, tag);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == Ellipse) {
            // "Direct tangency constraint between arc and ellipse is not supported. ..."
            return -1;
        }
        else if (Geoms[geoId2].type == Arc) {
            GCS::Arc& a2 = Arcs[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(a, a2, tag);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == BSpline) {
            // "Direct tangency constraint between arc and B-spline is not supported. ..."
            return -1;
        }
    }
    else if (Geoms[geoId1].type == BSpline) {
        // "Direct tangency constraint including B-splines is not supported. Use tangent-via-point
        // instead."
        return -1;
    }

    return -1;
}

int Sketch::addTangentLineAtBSplineKnotConstraint(
    int checkedlinegeoId,
    int checkedbsplinegeoId,
    int checkedknotgeoid
)
{
    GCS::BSpline& b = BSplines[Geoms[checkedbsplinegeoId].index];
    GCS::Line& l = Lines[Geoms[checkedlinegeoId].index];

    size_t knotindex = b.knots.size();

    const auto knotIt = std::ranges::find(b.knotpointGeoids, checkedknotgeoid);

    knotindex = std::distance(b.knotpointGeoids.begin(), knotIt);

    if (knotindex >= b.knots.size()) {
        // "addConstraint: Knot index out-of-range!"
        return -1;
    }

    if (b.mult[knotindex] >= b.degree) {
        // "cannot set constraint when B-spline slope is discontinuous at knot!" or "This method
        // cannot set tangent constraints at end knots of a B-spline. Constrain the start/end
        // points instead."
        return -1;
    }
    else {
        // increases ConstraintsCounter
        int tag = Sketch::addPointOnObjectConstraint(checkedknotgeoid, PointPos::start, checkedlinegeoId);
        GCSsys.addConstraintTangentAtBSplineKnot(b, l, knotindex, tag);
        return ConstraintsCounter;
    }
}

int Sketch::addTangentLineEndpointAtBSplineKnotConstraint(
    int checkedlinegeoId,
    PointPos endpointPos,
    int checkedbsplinegeoId,
    int checkedknotgeoid
)
{
    GCS::BSpline& b = BSplines[Geoms[checkedbsplinegeoId].index];
    GCS::Line& l = Lines[Geoms[checkedlinegeoId].index];
    auto pointId = getPointId(checkedlinegeoId, endpointPos);
    auto pointIdKnot = getPointId(checkedknotgeoid, PointPos::start);
    GCS::Point& p = Points[pointId];
    GCS::Point& pk = Points[pointIdKnot];

    size_t knotindex = b.knots.size();

    auto knotIt = std::ranges::find(b.knotpointGeoids, checkedknotgeoid);

    knotindex = std::distance(b.knotpointGeoids.begin(), knotIt);

    if (knotindex >= b.knots.size()) {
        // "addConstraint: Knot index out-of-range!"
        return -1;
    }

    if (b.mult[knotindex] >= b.degree) {
        // (as above)
        return -1;
    }
    else {
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2PCoincident(p, pk, tag);
        GCSsys.addConstraintTangentAtBSplineKnot(b, l, knotindex, tag);
        return ConstraintsCounter;
    }
}

int Sketch::addAngleAtPointConstraint(
    int geoId1,
    PointPos pos1,
    int geoId2,
    PointPos pos2,
    int geoId3,
    PointPos pos3,
    double* value,
    ConstraintType cTyp,
    bool driving
)
{
    using std::numbers::pi;
    if (!(cTyp == Angle || cTyp == Tangent || cTyp == Perpendicular)) {
        // assert(0);//none of the three types. Why are we here??
        return -1;
    }

    bool avp = geoId3 != GeoEnum::GeoUndef;                       // is angle-via-point?
    bool e2c = pos2 == PointPos::none && pos1 != PointPos::none;  // is endpoint-to-curve?
    bool e2e = pos2 != PointPos::none && pos1 != PointPos::none;  // is endpoint-to-endpoint?

    if (!(avp || e2c || e2e)) {
        // assert(0);//none of the three types. Why are we here??
        return -1;
    }

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);
    if (avp) {
        geoId3 = checkGeoId(geoId3);
    }

    if (Geoms[geoId1].type == Point || Geoms[geoId2].type == Point) {
        // "addAngleAtPointConstraint: one of the curves is a point!"
        return -1;
    }

    GCS::Curve* crv1 = getGCSCurveByGeoId(geoId1);
    GCS::Curve* crv2 = getGCSCurveByGeoId(geoId2);
    if (!crv1 || !crv2) {
        return -1;
    }

    int pointId = -1;
    if (avp) {
        pointId = getPointId(geoId3, pos3);
    }
    else if (e2e || e2c) {
        pointId = getPointId(geoId1, pos1);
    }

    if (pointId < 0 || pointId >= int(Points.size())) {
        // "addAngleAtPointConstraint: point index out of range."
        return -1;
    }
    GCS::Point& p = Points[pointId];
    GCS::Point* p2 = nullptr;
    if (e2e) {  // we need second point
        int pointId = getPointId(geoId2, pos2);
        if (pointId < 0 || pointId >= int(Points.size())) {
            return -1;
        }
        p2 = &(Points[pointId]);
    }

    double* angle = value;

    // For tangency/perpendicularity, we don't just copy the angle.
    // The angle stored for tangency/perpendicularity is offset, so that the options
    //  are -Pi/2 and Pi/2. If value is 0 - this is an indicator of an old sketch.
    //  Use autodetect then.
    // The same functionality is implemented in SketchObject.cpp, where
    //  it is used to permanently lock down the autodecision.
    if (cTyp != Angle) {
        // the difference between the datum value and the actual angle to apply.
        // (datum=angle+offset)
        double angleOffset = 0.0;
        // the desired angle value (and we are to decide if 180* should be added to it)
        double angleDesire = 0.0;
        if (cTyp == Tangent) {
            angleOffset = -pi / 2;
            angleDesire = 0.0;
        }
        if (cTyp == Perpendicular) {
            angleOffset = 0;
            angleDesire = pi / 2;
        }

        if (*value == 0.0) {  // autodetect tangency internal/external (and same for perpendicularity)
            double angleErr = GCSsys.calculateAngleViaPoint(*crv1, *crv2, p) - angleDesire;
            // bring angleErr to -pi..pi
            if (angleErr > pi) {
                angleErr -= pi * 2;
            }
            if (angleErr < -pi) {
                angleErr += pi * 2;
            }

            // the autodetector
            if (fabs(angleErr) > pi / 2) {
                angleDesire += pi;
            }

            *angle = angleDesire;
        }
        else {
            *angle = *value - angleOffset;
        }
    }

    int tag = -1;
    // FIXME: Perform construction of any parameters where this method is called instead of here
    if (e2c) {
        if (Geoms[geoId2].type == BSpline) {
            GCS::Point& p1 = Points[getPointId(geoId1, pos1)];
            const Geometry* partBsp = &Geoms[geoId2].geo;
            double uNear = partBsp->closestParameter(Vec {*p1.x, *p1.y});
            double* pointparam = newParam(uNear);
            Parameters.push_back(pointparam);
            --ConstraintsCounter;  // Do this just before point-on-object because ConstraintsCounter
                                   // is increased again before being used
            tag = addPointOnObjectConstraint(geoId1, pos1, geoId2, pointparam, driving);  // increases ConstraintsCounter
            GCSsys.addConstraintAngleViaPointAndParam(*crv2, *crv1, p, pointparam, angle, tag, driving);
        }
        else {
            // increases ConstraintsCounter
            tag = Sketch::addPointOnObjectConstraint(geoId1, pos1, geoId2, driving);
            GCSsys.addConstraintAngleViaPoint(*crv1, *crv2, p, angle, tag, driving);
        }
    }
    if (e2e) {
        tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2PCoincident(p, *p2, tag, driving);
        if (Geoms[geoId1].type == BSpline && Geoms[geoId2].type == BSpline) {
            GCSsys.addConstraintAngleViaTwoPoints(*crv1, *crv2, p, *p2, angle, tag, driving);
        }
        else {
            GCSsys.addConstraintAngleViaPoint(*crv1, *crv2, p, angle, tag, driving);
        }
    }
    if (avp) {
        tag = ++ConstraintsCounter;
        if (Geoms[geoId1].type == BSpline || Geoms[geoId2].type == BSpline) {
            if (Geoms[geoId1].type == BSpline && Geoms[geoId2].type == BSpline) {
                GCS::Point& p3 = Points[getPointId(geoId3, pos3)];
                const Geometry* partBsp = &Geoms[geoId1].geo;
                double uNear = partBsp->closestParameter(Vec {*p3.x, *p3.y});
                double* pointparam1 = newParam(uNear);
                Parameters.push_back(pointparam1);
                --ConstraintsCounter;  // Do this just before point-on-object because
                                       // ConstraintsCounter is increased again before being used
                addPointOnObjectConstraint(geoId3, pos3, geoId1, pointparam1, driving);  // increases ConstraintsCounter
                partBsp = &Geoms[geoId2].geo;
                uNear = partBsp->closestParameter(Vec {*p3.x, *p3.y});
                double* pointparam2 = newParam(uNear);
                --ConstraintsCounter;  // Do this just before point-on-object because
                                       // ConstraintsCounter is increased again before being used
                addPointOnObjectConstraint(geoId3, pos3, geoId2, pointparam2, driving);  // increases ConstraintsCounter
                Parameters.push_back(pointparam2);
                GCSsys.addConstraintAngleViaPointAndTwoParams(
                    *crv1,
                    *crv2,
                    p,
                    pointparam1,
                    pointparam2,
                    angle,
                    tag,
                    driving
                );
            }
            else {
                if (Geoms[geoId1].type != BSpline) {
                    std::swap(geoId1, geoId2);
                    std::swap(crv1, crv2);
                    std::swap(pos1, pos2);
                    // FIXME: Confirm whether or not this is needed
                    // *angle = -*angle;
                }
                GCS::Point& p3 = Points[getPointId(geoId3, pos3)];
                const Geometry* partBsp = &Geoms[geoId1].geo;
                double uNear = partBsp->closestParameter(Vec {*p3.x, *p3.y});
                double* pointparam = newParam(uNear);
                Parameters.push_back(pointparam);
                --ConstraintsCounter;  // Do this just before point-on-object because
                                       // ConstraintsCounter is increased again before being used
                addPointOnObjectConstraint(geoId3, pos3, geoId1, pointparam, driving);  // increases ConstraintsCounter
                GCSsys.addConstraintAngleViaPointAndParam(*crv1, *crv2, p, pointparam, angle, tag, driving);
            }
        }
        else {
            GCSsys.addConstraintAngleViaPoint(*crv1, *crv2, p, angle, tag, driving);
        }
    }

    return ConstraintsCounter;
}

// line length and arc length constraint
int Sketch::addDistanceConstraint(int geoId, double* value, bool driving)
{
    geoId = checkGeoId(geoId);

    int tag = ++ConstraintsCounter;
    if (Geoms[geoId].type == Line) {
        GCS::Line& l = Lines[Geoms[geoId].index];
        GCSsys.addConstraintP2PDistance(l.p1, l.p2, value, tag, driving);
    }
    else if (Geoms[geoId].type == Arc) {
        GCS::Arc& a = Arcs[Geoms[geoId].index];
        GCSsys.addConstraintArcLength(a, value, tag, driving);
    }
    else {
        return -1;
    }
    return ConstraintsCounter;
}

// point to line or circular distance constraint
int Sketch::addDistanceConstraint(
    int geoId1,
    PointPos pos1,
    int geoId2,
    double* value,
    ConstraintOrientation orientation,
    bool driving
)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    int pointId1 = getPointId(geoId1, pos1);
    if (pointId1 < 0 || pointId1 >= int(Points.size())) {
        return -1;
    }
    GCS::Point& p1 = Points[pointId1];

    if (Geoms[geoId2].type == Line) {
        GCS::Line& l2 = Lines[Geoms[geoId2].index];

        const bool counterClockwise = hasKnownSide(orientation)
            ? orientation.testFlag(ConstraintOrientations::CounterClockwise)
            : signedDistanceToLine(l2, *p1.x, *p1.y) > 0.0;

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2LDistance(p1, l2, value, counterClockwise, tag, driving);
        return ConstraintsCounter;
    }
    else {
        GCS::Circle* c2;
        if (Geoms[geoId2].type == Circle) {
            c2 = &Circles[Geoms[geoId2].index];
        }
        else if (Geoms[geoId2].type == Arc) {
            c2 = &Arcs[Geoms[geoId2].index];
        }
        else {
            return -1;
        }
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2CDistance(p1, *c2, value, tag, driving);
        return ConstraintsCounter;
    }
}

// point to point distance constraint
int Sketch::addDistanceConstraint(
    int geoId1,
    PointPos pos1,
    int geoId2,
    PointPos pos2,
    double* value,
    bool driving
)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    int pointId1 = getPointId(geoId1, pos1);
    int pointId2 = getPointId(geoId2, pos2);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2PDistance(p1, p2, value, tag, driving);
        return ConstraintsCounter;
    }
    return -1;
}

// circular-(circular or line) distance constraint
int Sketch::addDistanceConstraint(
    int geoId1,
    int geoId2,
    double* value,
    ConstraintOrientation orientation,
    bool driving
)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId2].type == Line) {
        GCS::Circle* c1;
        if (Geoms[geoId1].type == Circle) {
            c1 = &Circles[Geoms[geoId1].index];
        }
        else if (Geoms[geoId1].type == Arc) {
            c1 = &Arcs[Geoms[geoId1].index];
        }
        else {
            return -1;
        }

        GCS::Line* l = &Lines[Geoms[geoId2].index];

        bool counterClockwise = orientation.testFlag(ConstraintOrientations::CounterClockwise);
        bool internal = orientation.testFlag(ConstraintOrientations::Internal);
        if (!hasKnownSide(orientation)) {
            const double signedDistance = signedDistanceToLine(*l, *c1->center.x, *c1->center.y);
            counterClockwise = signedDistance > 0.0;
            internal = std::abs(signedDistance) < *c1->rad;
        }

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintC2LDistance(*c1, *l, value, counterClockwise, internal, tag, driving);
        return ConstraintsCounter;
    }
    else {
        GCS::Circle *c1 {}, *c2 {};
        if (Geoms[geoId1].type == Circle) {
            c1 = &Circles[Geoms[geoId1].index];
        }
        else if (Geoms[geoId1].type == Arc) {
            c1 = &Arcs[Geoms[geoId1].index];
        }
        if (Geoms[geoId2].type == Circle) {
            c2 = &Circles[Geoms[geoId2].index];
        }
        else if (Geoms[geoId2].type == Arc) {
            c2 = &Arcs[Geoms[geoId2].index];
        }
        if (c1 == nullptr || c2 == nullptr) {
            return -1;
        }

        int tag = ++ConstraintsCounter;

        std::optional<bool> c1Bigger = std::nullopt;
        if (orientation.testFlag(ConstraintOrientations::Internal)) {
            c1Bigger = false;
        }
        else if (orientation.testFlag(ConstraintOrientations::External)) {
            c1Bigger = true;
        }

        GCSsys.addConstraintC2CDistance(*c1, *c2, value, c1Bigger, tag, driving);
        return ConstraintsCounter;
    }
}

int Sketch::addRadiusConstraint(int geoId, double* value, bool driving)
{
    geoId = checkGeoId(geoId);

    if (Geoms[geoId].type == Circle) {
        GCS::Circle& c = Circles[Geoms[geoId].index];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintCircleRadius(c, value, tag, driving);
        return ConstraintsCounter;
    }
    else if (Geoms[geoId].type == Arc) {
        GCS::Arc& a = Arcs[Geoms[geoId].index];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintArcRadius(a, value, tag, driving);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addDiameterConstraint(int geoId, double* value, bool driving)
{
    geoId = checkGeoId(geoId);

    if (Geoms[geoId].type == Circle) {
        GCS::Circle& c = Circles[Geoms[geoId].index];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintCircleDiameter(c, value, tag, driving);
        return ConstraintsCounter;
    }
    else if (Geoms[geoId].type == Arc) {
        GCS::Arc& a = Arcs[Geoms[geoId].index];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintArcDiameter(a, value, tag, driving);
        return ConstraintsCounter;
    }
    return -1;
}

// line orientation angle constraint
int Sketch::addAngleConstraint(int geoId, double* value, bool driving)
{
    geoId = checkGeoId(geoId);

    if (Geoms[geoId].type == Line) {
        GCS::Line& l = Lines[Geoms[geoId].index];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2PAngle(l.p1, l.p2, value, tag, driving);
        return ConstraintsCounter;
    }
    else if (Geoms[geoId].type == Arc) {
        GCS::Arc& a = Arcs[Geoms[geoId].index];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintL2LAngle(a.center, a.start, a.center, a.end, value, tag, driving);
        return ConstraintsCounter;
    }
    return -1;
}

// line to line angle constraint
int Sketch::addAngleConstraint(int geoId1, int geoId2, double* value, bool driving)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != Line || Geoms[geoId2].type != Line) {
        return -1;
    }

    GCS::Line& l1 = Lines[Geoms[geoId1].index];
    GCS::Line& l2 = Lines[Geoms[geoId2].index];

    int tag = ++ConstraintsCounter;
    GCSsys.addConstraintL2LAngle(l1, l2, value, tag, driving);
    return ConstraintsCounter;
}

// line to line angle constraint (with explicitly given start points)
int Sketch::addAngleConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, double* value, bool driving)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != Line || Geoms[geoId2].type != Line) {
        return -1;
    }

    GCS::Point *l1p1 = nullptr, *l1p2 = nullptr;
    if (pos1 == PointPos::start) {
        l1p1 = &Points[Geoms[geoId1].startPointId];
        l1p2 = &Points[Geoms[geoId1].endPointId];
    }
    else if (pos1 == PointPos::end) {
        l1p1 = &Points[Geoms[geoId1].endPointId];
        l1p2 = &Points[Geoms[geoId1].startPointId];
    }

    GCS::Point *l2p1 = nullptr, *l2p2 = nullptr;
    if (pos2 == PointPos::start) {
        l2p1 = &Points[Geoms[geoId2].startPointId];
        l2p2 = &Points[Geoms[geoId2].endPointId];
    }
    else if (pos2 == PointPos::end) {
        l2p1 = &Points[Geoms[geoId2].endPointId];
        l2p2 = &Points[Geoms[geoId2].startPointId];
    }

    if (!l1p1 || !l2p1) {
        return -1;
    }

    int tag = ++ConstraintsCounter;
    GCSsys.addConstraintL2LAngle(*l1p1, *l1p2, *l2p1, *l2p2, value, tag, driving);
    return ConstraintsCounter;
}

int Sketch::addEqualConstraint(int geoId1, int geoId2)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type == Line && Geoms[geoId2].type == Line) {
        GCS::Line& l1 = Lines[Geoms[geoId1].index];
        GCS::Line& l2 = Lines[Geoms[geoId2].index];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintEqualLength(l1, l2, tag);
        return ConstraintsCounter;
    }

    if (Geoms[geoId2].type == Circle) {
        if (Geoms[geoId1].type == Circle) {
            GCS::Circle& c1 = Circles[Geoms[geoId1].index];
            GCS::Circle& c2 = Circles[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintEqualRadius(c1, c2, tag);
            return ConstraintsCounter;
        }
        else {
            std::swap(geoId1, geoId2);
        }
    }

    if (Geoms[geoId2].type == Ellipse) {
        if (Geoms[geoId1].type == Ellipse) {
            GCS::Ellipse& e1 = Ellipses[Geoms[geoId1].index];
            GCS::Ellipse& e2 = Ellipses[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintEqualRadii(e1, e2, tag);
            return ConstraintsCounter;
        }
        else {
            std::swap(geoId1, geoId2);
        }
    }

    if (Geoms[geoId1].type == Circle) {
        GCS::Circle& c1 = Circles[Geoms[geoId1].index];
        if (Geoms[geoId2].type == Arc) {
            GCS::Arc& a2 = Arcs[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintEqualRadius(c1, a2, tag);
            return ConstraintsCounter;
        }
    }

    if (Geoms[geoId1].type == Arc && Geoms[geoId2].type == Arc) {
        GCS::Arc& a1 = Arcs[Geoms[geoId1].index];
        GCS::Arc& a2 = Arcs[Geoms[geoId2].index];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintEqualRadius(a1, a2, tag);
        return ConstraintsCounter;
    }

    if (Geoms[geoId2].type == ArcOfEllipse) {
        if (Geoms[geoId1].type == ArcOfEllipse) {
            GCS::ArcOfEllipse& a1 = ArcsOfEllipse[Geoms[geoId1].index];
            GCS::ArcOfEllipse& a2 = ArcsOfEllipse[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintEqualRadii(a1, a2, tag);
            return ConstraintsCounter;
        }
    }

    if (Geoms[geoId2].type == ArcOfHyperbola) {
        if (Geoms[geoId1].type == ArcOfHyperbola) {
            GCS::ArcOfHyperbola& a1 = ArcsOfHyperbola[Geoms[geoId1].index];
            GCS::ArcOfHyperbola& a2 = ArcsOfHyperbola[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintEqualRadii(a1, a2, tag);
            return ConstraintsCounter;
        }
    }

    if (Geoms[geoId2].type == ArcOfParabola) {
        if (Geoms[geoId1].type == ArcOfParabola) {
            GCS::ArcOfParabola& a1 = ArcsOfParabola[Geoms[geoId1].index];
            GCS::ArcOfParabola& a2 = ArcsOfParabola[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintEqualFocus(a1, a2, tag);
            return ConstraintsCounter;
        }
    }

    if (Geoms[geoId1].type == Ellipse) {
        GCS::Ellipse& e1 = Ellipses[Geoms[geoId1].index];
        if (Geoms[geoId2].type == ArcOfEllipse) {
            GCS::ArcOfEllipse& a2 = ArcsOfEllipse[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintEqualRadii(a2, e1, tag);
            return ConstraintsCounter;
        }
    }

    // "Equality constraints between {} and {} are not supported."
    return -1;
}

// point on object constraint
int Sketch::addPointOnObjectConstraint(int geoId1, PointPos pos1, int geoId2, bool driving)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    int pointId1 = getPointId(geoId1, pos1);

    if (pointId1 >= 0 && pointId1 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];

        if (Geoms[geoId2].type == Line) {
            GCS::Line& l2 = Lines[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPointOnLine(p1, l2, tag, driving);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == Arc) {
            GCS::Arc& a = Arcs[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPointOnArc(p1, a, tag, driving);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == Circle) {
            GCS::Circle& c = Circles[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPointOnCircle(p1, c, tag, driving);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == Ellipse) {
            GCS::Ellipse& e = Ellipses[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPointOnEllipse(p1, e, tag, driving);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == ArcOfEllipse) {
            GCS::ArcOfEllipse& a = ArcsOfEllipse[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPointOnEllipse(p1, a, tag, driving);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == ArcOfHyperbola) {
            GCS::ArcOfHyperbola& a = ArcsOfHyperbola[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPointOnHyperbolicArc(p1, a, tag, driving);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == ArcOfParabola) {
            GCS::ArcOfParabola& a = ArcsOfParabola[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintPointOnParabolicArc(p1, a, tag, driving);
            return ConstraintsCounter;
        }
    }
    return -1;
}

int Sketch::addPointOnObjectConstraint(int geoId1, PointPos pos1, int geoId2, double* pointparam, bool driving)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    int pointId1 = getPointId(geoId1, pos1);

    if (pointId1 >= 0 && pointId1 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];

        if (Geoms[geoId2].type == BSpline) {
            GCS::BSpline& b = BSplines[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            const Geometry* partBsp = &Geoms[geoId2].geo;
            double uNear = partBsp->closestParameter(Vec {*p1.x, *p1.y});
            *pointparam = uNear;
            GCSsys.addConstraintPointOnBSpline(p1, b, pointparam, tag, driving);

            return ConstraintsCounter;
        }
    }
    return -1;
}

// symmetric points constraint
int Sketch::addSymmetricConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, int geoId3)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);
    geoId3 = checkGeoId(geoId3);

    if (Geoms[geoId3].type != Line) {
        return -1;
    }

    // Special handling for arc endpoint symmetry when the arc's center is on the symmetry axis.
    // In this specific geometric configuration, the perpendicularity part of the symmetry
    // constraint is inherently redundant. Applying it would lead to solver errors.
    // We detect this case and add only the midpoint-on-line part of the constraint,
    // which is sufficient to enforce symmetry without causing redundancy.

    // Step 1: Check if the two points (p1, p2) are endpoints of the same arc.
    // We iterate through all geometries to find an arc whose start/end points match our input
    // points.
    int arcGeoId = -1;
    for (int i = 0; i < (int)Geoms.size(); ++i) {
        if (Geoms[i].type == Arc) {
            int arcStartPointId = Geoms[i].startPointId;
            int arcEndPointId = Geoms[i].endPointId;

            int p1_Id = getPointId(geoId1, pos1);
            int p2_Id = getPointId(geoId2, pos2);

            if ((p1_Id == arcStartPointId && p2_Id == arcEndPointId)
                || (p1_Id == arcEndPointId && p2_Id == arcStartPointId)) {
                arcGeoId = i;
                break;
            }
        }
    }

    if (arcGeoId != -1) {
        // Step 2: We found the arc. Now check if its center lies on the symmetry line.
        int centerPointId = Geoms[arcGeoId].midPointId;
        GCS::Point& center = Points[centerPointId];
        GCS::Line& l = Lines[Geoms[geoId3].index];  // The symmetry line

        double dx = *l.p2.x - *l.p1.x;
        double dy = *l.p2.y - *l.p1.y;
        double line_len_sq = dx * dx + dy * dy;

        if (line_len_sq > SquareConfusion) {
            double area = (*center.x - *l.p1.x) * dy - (*center.y - *l.p1.y) * dx;
            if (std::abs(area) / sqrt(line_len_sq) < Confusion) {
                // The center IS on the symmetry line. This is the degenerate case.
                // Weaken the constraint by only adding the midpoint part.
                int pointId1 = getPointId(geoId1, pos1);
                int pointId2 = getPointId(geoId2, pos2);
                GCS::Point& p1 = Points[pointId1];
                GCS::Point& p2 = Points[pointId2];
                int tag = ++ConstraintsCounter;
                // addConstraintMidpointOnLine is a GCS::System method, but we can call it from
                // here.
                GCSsys.addConstraintMidpointOnLine(p1, p2, l.p1, l.p2, tag);
                return ConstraintsCounter;
            }
        }
    }

    int pointId1 = getPointId(geoId1, pos1);
    int pointId2 = getPointId(geoId2, pos2);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];
        GCS::Line& l = Lines[Geoms[geoId3].index];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2PSymmetric(p1, p2, l, tag);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addSymmetricConstraint(
    int geoId1,
    PointPos pos1,
    int geoId2,
    PointPos pos2,
    int geoId3,
    PointPos pos3
)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);
    geoId3 = checkGeoId(geoId3);

    int pointId1 = getPointId(geoId1, pos1);
    int pointId2 = getPointId(geoId2, pos2);
    int pointId3 = getPointId(geoId3, pos3);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size()) && pointId3 >= 0 && pointId3 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];
        GCS::Point& p = Points[pointId3];
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2PSymmetric(p1, p2, p, tag);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addSnellsLawConstraint(
    int geoIdRay1,
    PointPos posRay1,
    int geoIdRay2,
    PointPos posRay2,
    int geoIdBnd,
    double* value,
    double* secondvalue,
    bool driving
)
{

    geoIdRay1 = checkGeoId(geoIdRay1);
    geoIdRay2 = checkGeoId(geoIdRay2);
    geoIdBnd = checkGeoId(geoIdBnd);

    if (Geoms[geoIdRay1].type == Point || Geoms[geoIdRay2].type == Point) {
        // "addSnellsLawConstraint: point is not a curve. Not applicable!"
        return -1;
    }

    GCS::Curve* ray1 = getGCSCurveByGeoId(geoIdRay1);
    GCS::Curve* ray2 = getGCSCurveByGeoId(geoIdRay2);
    GCS::Curve* boundary = getGCSCurveByGeoId(geoIdBnd);
    if (!ray1 || !ray2 || !boundary) {
        // "addSnellsLawConstraint: getGCSCurveByGeoId returned NULL!"
        return -1;
    }

    int pointId1 = getPointId(geoIdRay1, posRay1);
    int pointId2 = getPointId(geoIdRay2, posRay2);
    if (pointId1 < 0 || pointId1 >= int(Points.size()) || pointId2 < 0
        || pointId2 >= int(Points.size())) {
        // "addSnellsLawConstraint: point index out of range."
        return -1;
    }
    GCS::Point& p1 = Points[pointId1];

    // add the parameters (refractive indexes)
    // n1 uses the place hold by n2divn1, so that is retrievable in updateNonDrivingConstraints
    double* n1 = value;
    double* n2 = secondvalue;

    double n2divn1 = *value;

    if (fabs(n2divn1) >= 1.0) {
        *n2 = n2divn1;
        *n1 = 1.0;
    }
    else {
        *n2 = 1.0;
        *n1 = 1 / n2divn1;
    }

    int tag = -1;
    // increases ConstraintsCounter
    // tag = Sketch::addPointOnObjectConstraint(geoIdRay1, posRay1, geoIdBnd);
    tag = ++ConstraintsCounter;
    // GCSsys.addConstraintP2PCoincident(p1, p2, tag);
    GCSsys.addConstraintSnellsLaw(
        *ray1,
        *ray2,
        *boundary,
        p1,
        n1,
        n2,
        posRay1 == PointPos::start,
        posRay2 == PointPos::end,
        tag,
        driving
    );
    return ConstraintsCounter;
}


int Sketch::addInternalAlignmentEllipseMajorDiameter(int geoId1, int geoId2)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != Ellipse && Geoms[geoId1].type != ArcOfEllipse) {
        return -1;
    }
    if (Geoms[geoId2].type != Line) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);
    int pointId2 = getPointId(geoId2, PointPos::end);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];

        if (Geoms[geoId1].type == Ellipse) {
            GCS::Ellipse& e1 = Ellipses[Geoms[geoId1].index];

            // constraints
            // 1. start point with ellipse -a
            // 2. end point with ellipse +a
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintInternalAlignmentEllipseMajorDiameter(e1, p1, p2, tag);
            return ConstraintsCounter;
        }
        else {
            GCS::ArcOfEllipse& a1 = ArcsOfEllipse[Geoms[geoId1].index];

            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintInternalAlignmentEllipseMajorDiameter(a1, p1, p2, tag);
            return ConstraintsCounter;
        }
    }
    return -1;
}

int Sketch::addInternalAlignmentEllipseMinorDiameter(int geoId1, int geoId2)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != Ellipse && Geoms[geoId1].type != ArcOfEllipse) {
        return -1;
    }
    if (Geoms[geoId2].type != Line) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);
    int pointId2 = getPointId(geoId2, PointPos::end);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];

        if (Geoms[geoId1].type == Ellipse) {
            GCS::Ellipse& e1 = Ellipses[Geoms[geoId1].index];

            // constraints
            // 1. start point with ellipse -a
            // 2. end point with ellipse +a
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintInternalAlignmentEllipseMinorDiameter(e1, p1, p2, tag);
            return ConstraintsCounter;
        }
        else {
            GCS::ArcOfEllipse& a1 = ArcsOfEllipse[Geoms[geoId1].index];

            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintInternalAlignmentEllipseMinorDiameter(a1, p1, p2, tag);
            return ConstraintsCounter;
        }
    }
    return -1;
}

int Sketch::addInternalAlignmentEllipseFocus1(int geoId1, int geoId2)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != Ellipse && Geoms[geoId1].type != ArcOfEllipse) {
        return -1;
    }
    if (Geoms[geoId2].type != Point) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);

    if (pointId1 >= 0 && pointId1 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];

        if (Geoms[geoId1].type == Ellipse) {
            GCS::Ellipse& e1 = Ellipses[Geoms[geoId1].index];

            // constraints
            // 1. start point with ellipse -a
            // 2. end point with ellipse +a
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintInternalAlignmentEllipseFocus1(e1, p1, tag);
            return ConstraintsCounter;
        }
        else {
            GCS::ArcOfEllipse& a1 = ArcsOfEllipse[Geoms[geoId1].index];

            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintInternalAlignmentEllipseFocus1(a1, p1, tag);
            return ConstraintsCounter;
        }
    }
    return -1;
}


int Sketch::addInternalAlignmentEllipseFocus2(int geoId1, int geoId2)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != Ellipse && Geoms[geoId1].type != ArcOfEllipse) {
        return -1;
    }
    if (Geoms[geoId2].type != Point) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);

    if (pointId1 >= 0 && pointId1 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];

        if (Geoms[geoId1].type == Ellipse) {
            GCS::Ellipse& e1 = Ellipses[Geoms[geoId1].index];

            // constraints
            // 1. start point with ellipse -a
            // 2. end point with ellipse +a
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintInternalAlignmentEllipseFocus2(e1, p1, tag);
            return ConstraintsCounter;
        }
        else {
            GCS::ArcOfEllipse& a1 = ArcsOfEllipse[Geoms[geoId1].index];

            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintInternalAlignmentEllipseFocus2(a1, p1, tag);
            return ConstraintsCounter;
        }
    }
    return -1;
}


int Sketch::addInternalAlignmentHyperbolaMajorDiameter(int geoId1, int geoId2)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != ArcOfHyperbola) {
        return -1;
    }
    if (Geoms[geoId2].type != Line) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);
    int pointId2 = getPointId(geoId2, PointPos::end);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {

        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];

        GCS::ArcOfHyperbola& a1 = ArcsOfHyperbola[Geoms[geoId1].index];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintInternalAlignmentHyperbolaMajorDiameter(a1, p1, p2, tag);
        return ConstraintsCounter;
    }

    return -1;
}

int Sketch::addInternalAlignmentHyperbolaMinorDiameter(int geoId1, int geoId2)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != ArcOfHyperbola) {
        return -1;
    }
    if (Geoms[geoId2].type != Line) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);
    int pointId2 = getPointId(geoId2, PointPos::end);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {

        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];

        GCS::ArcOfHyperbola& a1 = ArcsOfHyperbola[Geoms[geoId1].index];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintInternalAlignmentHyperbolaMinorDiameter(a1, p1, p2, tag);
        return ConstraintsCounter;
    }

    return -1;
}

int Sketch::addInternalAlignmentHyperbolaFocus(int geoId1, int geoId2)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != ArcOfHyperbola) {
        return -1;
    }
    if (Geoms[geoId2].type != Point) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);

    if (pointId1 >= 0 && pointId1 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];

        GCS::ArcOfHyperbola& a1 = ArcsOfHyperbola[Geoms[geoId1].index];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintInternalAlignmentHyperbolaFocus(a1, p1, tag);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addInternalAlignmentParabolaFocus(int geoId1, int geoId2)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != ArcOfParabola) {
        return -1;
    }
    if (Geoms[geoId2].type != Point) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);

    if (pointId1 >= 0 && pointId1 < int(Points.size())) {
        GCS::Point& p1 = Points[pointId1];

        GCS::ArcOfParabola& a1 = ArcsOfParabola[Geoms[geoId1].index];

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintInternalAlignmentParabolaFocus(a1, p1, tag);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addInternalAlignmentParabolaFocalDistance(int geoId1, int geoId2)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != ArcOfParabola) {
        return -1;
    }
    if (Geoms[geoId2].type != Line) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);
    int pointId2 = getPointId(geoId2, PointPos::end);

    if (pointId1 >= 0 && pointId1 < int(Points.size()) && pointId2 >= 0
        && pointId2 < int(Points.size())) {

        GCS::Point& p1 = Points[pointId1];
        GCS::Point& p2 = Points[pointId2];

        GCS::ArcOfParabola& a1 = ArcsOfParabola[Geoms[geoId1].index];

        auto& vertexpoint = a1.vertex;
        auto& focuspoint = a1.focus1;

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2PCoincident(p1, vertexpoint, tag);
        GCSsys.addConstraintP2PCoincident(p2, focuspoint, tag);

        return ConstraintsCounter;
    }

    return -1;
}

int Sketch::addInternalAlignmentBSplineControlPoint(int geoId1, int geoId2, int poleindex)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != BSpline) {
        return -1;
    }
    if (Geoms[geoId2].type != Circle) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::mid);

    if (pointId1 >= 0 && pointId1 < int(Points.size())) {
        GCS::Circle& c = Circles[Geoms[geoId2].index];

        GCS::BSpline& b = BSplines[Geoms[geoId1].index];

        // (FreeCAD asserts this; an index out of range is malformed here)
        if (!(poleindex < static_cast<int>(b.poles.size()) && poleindex >= 0)) {
            return -1;
        }

        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintInternalAlignmentBSplineControlPoint(b, c, poleindex, tag);
        return ConstraintsCounter;
    }
    return -1;
}

int Sketch::addInternalAlignmentKnotPoint(int geoId1, int geoId2, int knotindex)
{
    std::swap(geoId1, geoId2);

    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    if (Geoms[geoId1].type != BSpline) {
        return -1;
    }
    if (Geoms[geoId2].type != Point) {
        return -1;
    }

    int pointId1 = getPointId(geoId2, PointPos::start);

    if (pointId1 >= 0 && pointId1 < int(Points.size())) {
        GCS::Point& p = Points[pointId1];
        GCS::BSpline& b = BSplines[Geoms[geoId1].index];

        // (FreeCAD asserts this; an index out of range is malformed here)
        if (!(knotindex < static_cast<int>(b.knots.size()) && knotindex >= 0)) {
            return -1;
        }

        b.knotpointGeoids[knotindex] = geoId2;
        int tag = ++ConstraintsCounter;
        GCSsys.addConstraintInternalAlignmentKnotPoint(b, p, knotindex, tag);

        return ConstraintsCounter;
    }
    return -1;
}

double Sketch::calculateAngleViaPoint(int geoId1, int geoId2, double px, double py)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    GCS::Point p;
    p.x = &px;
    p.y = &py;

    // check pointers
    GCS::Curve* crv1 = getGCSCurveByGeoId(geoId1);
    GCS::Curve* crv2 = getGCSCurveByGeoId(geoId2);
    if (!crv1 || !crv2) {
        throw std::invalid_argument("calculateAngleViaPoint: getGCSCurveByGeoId returned NULL!");
    }

    return GCSsys.calculateAngleViaPoint(*crv1, *crv2, p);
}

double Sketch::calculateAngleViaParams(int geoId1, int geoId2, double param1, double param2)
{
    geoId1 = checkGeoId(geoId1);
    geoId2 = checkGeoId(geoId2);

    // check pointers
    GCS::Curve* crv1 = getGCSCurveByGeoId(geoId1);
    GCS::Curve* crv2 = getGCSCurveByGeoId(geoId2);
    if (!crv1 || !crv2) {
        throw std::invalid_argument("calculateAngleViaPoint: getGCSCurveByGeoId returned NULL!");
    }
    // FIXME: This should probably not be needed
    auto* crv1AsBSpline = dynamic_cast<GCS::BSpline*>(crv1);
    if (crv1AsBSpline && crv1AsBSpline->flattenedknots.empty()) {
        crv1AsBSpline->setupFlattenedKnots();
    }
    auto* crv2AsBSpline = dynamic_cast<GCS::BSpline*>(crv2);
    if (crv2AsBSpline && crv2AsBSpline->flattenedknots.empty()) {
        crv2AsBSpline->setupFlattenedKnots();
    }

    return GCSsys.calculateAngleViaParams(*crv1, *crv2, &param1, &param2);
}

bool Sketch::updateGeometry()
{
    for (GeoDef& it : Geoms) {
        try {
            updateGeometry(it);
        }
        catch (const GeometryError&) {
            // "Updating geometry: Error build geometry({}): {}"
            return false;
        }
    }
    return true;
}

void Sketch::updateGeometry(GeoDef& it)
{
    if (it.type == Point) {
        updatePoint(it);
    }
    else if (it.type == Line) {
        updateLineSegment(it);
    }
    else if (it.type == Arc) {
        updateArcOfCircle(it);
    }
    else if (it.type == ArcOfEllipse) {
        updateArcOfEllipse(it);
    }
    else if (it.type == Circle) {
        updateCircle(it);
    }
    else if (it.type == Ellipse) {
        updateEllipse(it);
    }
    else if (it.type == ArcOfHyperbola) {
        updateArcOfHyperbola(it);
    }
    else if (it.type == ArcOfParabola) {
        updateArcOfParabola(it);
    }
    else if (it.type == BSpline) {
        updateBSpline(it);
    }
}

void Sketch::updatePoint(GeoDef& def)
{
    def.geo.setPoint(Vec {*Points[def.startPointId].x, *Points[def.startPointId].y});
}

void Sketch::updateLineSegment(GeoDef& def)
{
    def.geo.setPoints(
        Vec {*Lines[def.index].p1.x, *Lines[def.index].p1.y},
        Vec {*Lines[def.index].p2.x, *Lines[def.index].p2.y}
    );
}

void Sketch::updateArcOfCircle(GeoDef& def)
{
    GCS::Arc& myArc = Arcs[def.index];
    def.geo.setCenter(Vec {*Points[def.midPointId].x, *Points[def.midPointId].y});
    def.geo.setRadius(*myArc.rad);
    def.geo.setRange(*myArc.startAngle, *myArc.endAngle /*, emulateCCWXY=true*/);
}

void Sketch::updateCircle(GeoDef& def)
{
    def.geo.setCenter(Vec {*Points[def.midPointId].x, *Points[def.midPointId].y});
    def.geo.setRadius(*Circles[def.index].rad);
}

void Sketch::updateArcOfEllipse(GeoDef& def)
{
    GCS::ArcOfEllipse& myArc = ArcsOfEllipse[def.index];

    Geometry* aoe = &def.geo;

    Vec center {*Points[def.midPointId].x, *Points[def.midPointId].y};
    Vec f1 {*myArc.focus1.x, *myArc.focus1.y};
    double radmin = *myArc.radmin;

    Vec fd {f1.x - center.x, f1.y - center.y};
    double radmaj = sqrt((fd.x * fd.x + fd.y * fd.y + 0.0 * 0.0) + radmin * radmin);

    aoe->setCenter(center);
    // ensure that ellipse's major radius is always larger than minor radius... may
    // still cause problems with degenerates.
    if (radmaj >= aoe->getMinorRadius()) {
        aoe->setMajorRadius(radmaj);
        aoe->setMinorRadius(radmin);
    }
    else {
        aoe->setMinorRadius(radmin);
        aoe->setMajorRadius(radmaj);
    }
    aoe->setMajorAxisDir(fd);
    aoe->setConicRange(*myArc.startAngle, *myArc.endAngle /*, emulateCCWXY=true*/);
}

void Sketch::updateArcOfHyperbola(GeoDef& def)
{
    GCS::ArcOfHyperbola& myArc = ArcsOfHyperbola[def.index];

    Geometry* aoh = &def.geo;

    Vec center {*Points[def.midPointId].x, *Points[def.midPointId].y};
    Vec f1 {*myArc.focus1.x, *myArc.focus1.y};
    double radmin = *myArc.radmin;

    Vec fd {f1.x - center.x, f1.y - center.y};
    double radmaj = sqrt((fd.x * fd.x + fd.y * fd.y + 0.0 * 0.0) - radmin * radmin);

    aoh->setCenter(center);
    if (radmaj >= aoh->getMinorRadius()) {
        aoh->setMajorRadius(radmaj);
        aoh->setMinorRadius(radmin);
    }
    else {
        aoh->setMinorRadius(radmin);
        aoh->setMajorRadius(radmaj);
    }
    aoh->setMajorAxisDir(fd);
    aoh->setConicRange(*myArc.startAngle, *myArc.endAngle /*, emulateCCWXY=true*/);
}

void Sketch::updateArcOfParabola(GeoDef& def)
{
    GCS::ArcOfParabola& myArc = ArcsOfParabola[def.index];

    Geometry* aop = &def.geo;

    Vec vertex {*Points[def.midPointId].x, *Points[def.midPointId].y};
    Vec f1 {*myArc.focus1.x, *myArc.focus1.y};

    Vec fd {f1.x - vertex.x, f1.y - vertex.y};

    aop->setMajorAxisDir(fd);  // GeomArcOfConic::setXAxisDir
    aop->setCenter(vertex);
    aop->setFocal(std::sqrt(fd.x * fd.x + fd.y * fd.y + 0.0 * 0.0));  // fd.Length()
    aop->setConicRange(*myArc.startAngle, *myArc.endAngle /*, emulateCCWXY=true*/);
}

void Sketch::updateEllipse(GeoDef& def)
{
    Geometry* ellipse = &def.geo;

    Vec center {*Points[def.midPointId].x, *Points[def.midPointId].y};
    Vec f1 {*Ellipses[def.index].focus1.x, *Ellipses[def.index].focus1.y};
    double radmin = *Ellipses[def.index].radmin;

    Vec fd {f1.x - center.x, f1.y - center.y};
    double radmaj = sqrt((fd.x * fd.x + fd.y * fd.y + 0.0 * 0.0) + radmin * radmin);

    ellipse->setCenter(center);
    // ensure that ellipse's major radius is always larger than minor radius... may
    // still cause problems with degenerates.
    if (radmaj >= ellipse->getMinorRadius()) {
        ellipse->setMajorRadius(radmaj);
        ellipse->setMinorRadius(radmin);
    }
    else {
        ellipse->setMinorRadius(radmin);
        ellipse->setMajorRadius(radmaj);
    }
    ellipse->setMajorAxisDir(fd);
}

void Sketch::updateBSpline(GeoDef& def)
{
    GCS::BSpline& mybsp = BSplines[def.index];

    std::vector<Vec> poles;
    std::vector<double> weights;

    for (size_t k = 0; k < mybsp.poles.size() && k < mybsp.weights.size(); ++k) {
        poles.push_back(Vec {*mybsp.poles[k].x, *mybsp.poles[k].y});
        weights.push_back(*mybsp.weights[k]);
    }

    def.geo.setPoles(poles, weights);

    // (the knots are not written back, as in FreeCAD: "This is the code that should be here
    // when/if b-spline gets its full implementation in the solver.")
}

bool Sketch::updateNonDrivingConstraints()
{
    for (auto& constrDef : Constrs) {
        if (constrDef.driving) {
            continue;
        }
        if (constrDef.constr->Type == SnellsLaw) {
            double n1 = *(constrDef.value);
            double n2 = *(constrDef.secondvalue);

            constrDef.constr->setValue(n2 / n1);
        }
        else if (constrDef.constr->Type == Angle) {

            constrDef.constr->setValue(std::fmod(*(constrDef.value), 2.0 * std::numbers::pi));
        }
        else {
            constrDef.constr->setValue(*(constrDef.value));
        }
    }

    return true;
}

// solving ==========================================================

GCS::SolveStatus Sketch::solve()
{
    captureGroupStates();

    std::string solvername;

    auto result = internalSolve(solvername);

    if (result == GCS::SolveStatus::Success) {
        applyGroupTransformations();
    }

    return result;
}

// Group functions related -------------------------------------------------

Sketch::GroupLineState Sketch::getGroupLineState(int geoId) const
{
    GroupLineState state;
    state.startPoint = getPoint(geoId, PointPos::start);
    state.endPoint = getPoint(geoId, PointPos::end);
    return state;
}

void Sketch::captureGroupStates()
{
    preSolveGroupStates.clear();

    for (const auto& constrDef : Constrs) {
        const Constraint* c = constrDef.constr;

        if ((c->Type != Group && c->Type != Text) || !c->hasElement(1)) {
            continue;
        }

        // --- Capture Frame State ---
        int frameGeoId = c->getGeoId(0);
        preSolveGroupStates[frameGeoId] = getGroupLineState(frameGeoId);
    }
}

namespace
{
// Base::Matrix4D, as much of it as applyGroupTransformations uses: identity by default, operator*, rotLine
struct Mat4
{
    double d[4][4] = {{1, 0, 0, 0}, {0, 1, 0, 0}, {0, 0, 1, 0}, {0, 0, 0, 1}};
    Mat4 operator*(const Mat4& m) const
    {
        Mat4 r;
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 4; j++) {
                r.d[i][j] = 0;
                for (int e = 0; e < 4; e++) {
                    r.d[i][j] += d[i][e] * m.d[e][j];
                }
            }
        }
        return r;
    }
    // Matrix4D::rotLine(vec, fAngle)
    void rotLine(V3 a, double fAngle)
    {
        double len = std::sqrt(a.x * a.x + a.y * a.y + a.z * a.z);  // Vector3d::Normalize
        if (len != 0.0 && len != 1.0) {
            a.x /= len;
            a.y /= len;
            a.z /= len;
        }
        double fcos = std::cos(fAngle), fsin = std::sin(fAngle);
        double A[3][3] = {{(1 - fcos) * a.x * a.x, (1 - fcos) * a.x * a.y, (1 - fcos) * a.x * a.z},
                          {(1 - fcos) * a.x * a.y, (1 - fcos) * a.y * a.y, (1 - fcos) * a.y * a.z},
                          {(1 - fcos) * a.x * a.z, (1 - fcos) * a.y * a.z, (1 - fcos) * a.z * a.z}};
        double B[3][3] = {{fcos, 0, 0}, {0, fcos, 0}, {0, 0, fcos}};
        double C[3][3] = {{0, -fsin * a.z, fsin * a.y}, {fsin * a.z, 0, -fsin * a.x}, {-fsin * a.y, fsin * a.x, 0}};
        Mat4 rot;
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                rot.d[i][j] = A[i][j] + B[i][j] + C[i][j];
            }
        }
        *this = rot * *this;
    }
};
}  // namespace

void Sketch::applyGroupTransformations()
{
    if (preSolveGroupStates.empty()) {
        return;
    }

    for (const auto& constrDef : Constrs) {
        const Constraint* c = constrDef.constr;
        if ((c->Type != Group && c->Type != Text) || !c->hasElement(1)) {
            continue;
        }

        int frameGeoId = c->getGeoId(0);

        // Get the "before" and "after" states of the frame line
        GroupLineState preSolveFrame = preSolveGroupStates.at(frameGeoId);
        GroupLineState postSolveFrame = getGroupLineState(frameGeoId);

        // --- Calculate the Transformation ---
        V3 preVec {preSolveFrame.endPoint.x - preSolveFrame.startPoint.x,
                   preSolveFrame.endPoint.y - preSolveFrame.startPoint.y, 0.0};
        V3 postVec {postSolveFrame.endPoint.x - postSolveFrame.startPoint.x,
                    postSolveFrame.endPoint.y - postSolveFrame.startPoint.y, 0.0};
        auto length = [](const V3& v) { return std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z); };

        // Handle potential zero-length lines to avoid division by zero
        double preLen = length(preVec);
        double scale = (preLen > 1e-7) ? length(postVec) / preLen : 1.0;  // Precision::Confusion()

        // 1. T1: Matrix to translate the group to the origin (using pre-solve start point)
        Mat4 T1;
        T1.d[0][3] = -preSolveFrame.startPoint.x;
        T1.d[1][3] = -preSolveFrame.startPoint.y;
        T1.d[2][3] = 0;

        // 2. S: Matrix for scaling
        Mat4 S;
        S.d[0][0] = scale;
        S.d[1][1] = scale;
        S.d[2][2] = scale;

        // 3. R: Matrix for rotation
        Mat4 R;
        if (preLen > 1e-7) {
            // We can get the axis and angle from the two vectors and use rotLine (Vector3d::Cross, GetAngle)
            V3 axis {preVec.y * postVec.z - preVec.z * postVec.y, preVec.z * postVec.x - preVec.x * postVec.z,
                     preVec.x * postVec.y - preVec.y * postVec.x};
            double angle;
            double len1 = length(preVec), len2 = length(postVec);
            if (len1 <= DBL_EPSILON || len2 <= DBL_EPSILON) {
                angle = std::numeric_limits<double>::quiet_NaN();
            }
            else {
                double dot = preVec.x * postVec.x + preVec.y * postVec.y + preVec.z * postVec.z;
                dot /= len1;
                dot /= len2;
                angle = dot <= -1.0 ? std::numbers::pi : dot >= 1.0 ? 0.0 : std::acos(dot);
            }
            // Only apply rotation if the vectors are not collinear
            if (length(axis) > 1e-7) {
                R.rotLine(axis, angle);
            }
        }

        // 4. T2: Matrix to translate the group to its new final position
        Mat4 T2;
        T2.d[0][3] = postSolveFrame.startPoint.x;
        T2.d[1][3] = postSolveFrame.startPoint.y;
        T2.d[2][3] = 0;

        // 5. Combine the matrices in the correct order: T_final = T2 * R * S * T1
        Mat4 transform = T2 * R * S * T1;
        double m[3][4];
        for (int i = 0; i < 3; ++i) {
            for (int j = 0; j < 4; ++j) {
                m[i][j] = transform.d[i][j];
            }
        }

        // --- Loop through grouped elements and apply the transform ---
        for (int i = 1; c->hasElement(i); ++i) {
            int groupedGeoId = c->getGeoId(i);
            if (groupedGeoId == GeoEnum::GeoUndef) {
                continue;
            }
            Geoms[checkGeoId(groupedGeoId)].geo.transform(m);
        }
    }

    preSolveGroupStates.clear();
}

GCS::SolveStatus Sketch::internalSolve(std::string& solvername, int level)
{
    if (!isInitMove) {  // make sure we are in single subsystem mode
        clearTemporaryConstraints();
    }

    bool valid_solution;
    int defaultsoltype = -1;
    GCS::SolveStatus status = GCS::SolveStatus::Failed;

    if (isInitMove) {
        solvername = "DogLeg";  // DogLeg is used for dragging (same as before)
        status = GCSsys.solve(GCS::DogLeg);
    }
    else {
        switch (defaultSolver) {
            case GCS::BFGS:
                solvername = "BFGS";
                status = GCSsys.solve(GCS::BFGS);
                defaultsoltype = 2;
                break;
            case GCS::LevenbergMarquardt:
                solvername = "LevenbergMarquardt";
                status = GCSsys.solve(GCS::LevenbergMarquardt);
                defaultsoltype = 1;
                break;
            case GCS::DogLeg:
                solvername = "DogLeg";
                status = GCSsys.solve(GCS::DogLeg);
                defaultsoltype = 0;
                break;
        }
    }

    // if successfully solved try to write the parameters back
    if (status == GCS::SolveStatus::Success) {
        GCSsys.applySolution();
        valid_solution = updateGeometry();
        if (!valid_solution) {
            GCSsys.undoSolution();
            updateGeometry();
            // "Invalid solution from {} solver."
        }
        else {
            updateNonDrivingConstraints();
        }
    }
    else {
        valid_solution = false;
    }

    if (!valid_solution && !isInitMove) {  // Fall back to other solvers
        for (int soltype = 0; soltype < 4; soltype++) {

            if (soltype == defaultsoltype) {
                continue;  // skip default solver
            }

            switch (soltype) {
                case 0:
                    solvername = "DogLeg";
                    status = GCSsys.solve(GCS::DogLeg);
                    break;
                case 1:  // solving with the LevenbergMarquardt solver
                    solvername = "LevenbergMarquardt";
                    status = GCSsys.solve(GCS::LevenbergMarquardt);
                    break;
                case 2:  // solving with the BFGS solver
                    solvername = "BFGS";
                    status = GCSsys.solve(GCS::BFGS);
                    break;
                // last resort: augment the system with a second subsystem and use the SQP solver
                case 3:
                    solvername = "SQP(augmented system)";
                    InitParameters.resize(Parameters.size());
                    int i = 0;
                    for (auto it = Parameters.begin(); it != Parameters.end(); ++it, ++i) {
                        InitParameters[i] = **it;
                        GCSsys.addConstraintEqual(
                            *it,
                            &InitParameters[i],
                            GCS::DefaultTemporaryConstraint
                        );
                    }
                    GCSsys.initSolution();
                    status = GCSsys.solve();
                    break;
            }

            // if successfully solved try to write the parameters back
            if (status == GCS::SolveStatus::Success) {
                GCSsys.applySolution();
                valid_solution = updateGeometry();
                if (!valid_solution) {
                    GCSsys.undoSolution();
                    updateGeometry();
                    status = GCS::SolveStatus::SuccessfulSolutionInvalid;
                }
                else {
                    updateNonDrivingConstraints();
                }
            }
            else {
                valid_solution = false;
            }

            if (soltype == 3) {  // cleanup temporary constraints of the augmented system
                clearTemporaryConstraints();
            }

            if (valid_solution) {
                break;
            }
        }  // soltype
    }

    // For OCCT reliant geometry that needs an extra solve() for example to update non-driving
    // constraints.
    if (resolveAfterGeometryUpdated && status == GCS::SolveStatus::Success && level == 0) {
        return internalSolve(solvername, 1);
    }

    return status;
}

int Sketch::initMove(const std::vector<GeoElementId>& geoEltIds)
{
    if (hasConflicts()) {
        // don't try to move sketches that contain conflicting constraints
        isInitMove = false;
        return -1;
    }

    clearTemporaryConstraints();

    MoveParameters.clear();

    // We need to reserve enough size in the vec or the dynamic resizing
    // (emplace_back in the for loop below) will trigger reallocation.
    // Which will corrupt pointers we're storing.
    size_t reserveSize = 0;
    for (auto& pair : geoEltIds) {
        int geoId = checkGeoId(pair.GeoId);
        PointPos pos = pair.Pos;
        if (Geoms[geoId].type == BSpline && (pos == PointPos::none || pos == PointPos::mid)) {
            GCS::BSpline& bsp = BSplines[Geoms[geoId].index];
            reserveSize += bsp.poles.size() * 2;
        }
        else {
            reserveSize += 6;  // 6 is the max for all other cases.
        }
    }
    MoveParameters.reserve(reserveSize);

    for (auto& pair : geoEltIds) {
        int geoId = checkGeoId(pair.GeoId);
        PointPos pos = pair.Pos;

        if (Geoms[geoId].type == Point) {
            if (pos == PointPos::start) {
                GCS::Point& point = Points[Geoms[geoId].startPointId];
                GCS::Point p0;
                p0.x = &MoveParameters.emplace_back(*point.x);
                p0.y = &MoveParameters.emplace_back(*point.y);
                GCSsys.addConstraintP2PCoincident(p0, point, GCS::DefaultTemporaryConstraint);
            }
        }
        else if (Geoms[geoId].type == Line) {
            if (pos == PointPos::start || pos == PointPos::end) {
                GCS::Point p0;
                GCS::Point& p = pos == PointPos::start ? Points[Geoms[geoId].startPointId]
                                                       : Points[Geoms[geoId].endPointId];
                p0.x = &MoveParameters.emplace_back(*p.x);
                p0.y = &MoveParameters.emplace_back(*p.y);
                GCSsys.addConstraintP2PCoincident(p0, p, GCS::DefaultTemporaryConstraint);
            }
            else if (pos == PointPos::none || pos == PointPos::mid) {
                GCS::Point p1, p2;
                GCS::Line& l = Lines[Geoms[geoId].index];
                p1.x = &MoveParameters.emplace_back(*l.p1.x);
                p1.y = &MoveParameters.emplace_back(*l.p1.y);
                p2.x = &MoveParameters.emplace_back(*l.p2.x);
                p2.y = &MoveParameters.emplace_back(*l.p2.y);
                GCSsys.addConstraintP2PCoincident(p1, l.p1, GCS::DefaultTemporaryConstraint);
                GCSsys.addConstraintP2PCoincident(p2, l.p2, GCS::DefaultTemporaryConstraint);
            }
        }
        else if (Geoms[geoId].type == Circle) {
            GCS::Point& center = Points[Geoms[geoId].midPointId];
            GCS::Point p0, p1;
            if (pos == PointPos::mid) {
                p0.x = &MoveParameters.emplace_back(*center.x);
                p0.y = &MoveParameters.emplace_back(*center.y);
                GCSsys.addConstraintP2PCoincident(p0, center, GCS::DefaultTemporaryConstraint);
            }
            else if (pos == PointPos::none) {
                GCS::Circle& c = Circles[Geoms[geoId].index];
                p0.x = &MoveParameters.emplace_back(*center.x);
                p0.y = &MoveParameters.emplace_back(*center.y + *c.rad);
                GCSsys.addConstraintPointOnCircle(p0, c, GCS::DefaultTemporaryConstraint);
                p1.x = &MoveParameters.emplace_back(*center.x);
                p1.y = &MoveParameters.emplace_back(*center.y);
                int i = GCSsys.addConstraintP2PCoincident(p1, center, GCS::DefaultTemporaryConstraint);
                GCSsys.rescaleConstraint(i - 1, 0.01);
                GCSsys.rescaleConstraint(i, 0.01);
            }
        }
        else if (Geoms[geoId].type == Ellipse) {
            if (pos == PointPos::mid || pos == PointPos::none) {
                GCS::Point& center = Points[Geoms[geoId].midPointId];
                GCS::Point p0;
                p0.x = &MoveParameters.emplace_back(*center.x);
                p0.y = &MoveParameters.emplace_back(*center.y);
                GCSsys.addConstraintP2PCoincident(p0, center, GCS::DefaultTemporaryConstraint);
            }
        }
        else if (Geoms[geoId].type == ArcOfEllipse || Geoms[geoId].type == ArcOfHyperbola
                 || Geoms[geoId].type == ArcOfParabola) {
            // (FreeCAD has one branch per type, all three the same)
            GCS::Point& center = Points[Geoms[geoId].midPointId];
            GCS::Point p0, p1;
            if (pos == PointPos::mid || pos == PointPos::none) {
                p0.x = &MoveParameters.emplace_back(*center.x);
                p0.y = &MoveParameters.emplace_back(*center.y);
                GCSsys.addConstraintP2PCoincident(p0, center, GCS::DefaultTemporaryConstraint);
            }
            else if (pos == PointPos::start || pos == PointPos::end) {
                GCS::Point& p = (pos == PointPos::start) ? Points[Geoms[geoId].startPointId]
                                                         : Points[Geoms[geoId].endPointId];
                p0.x = &MoveParameters.emplace_back(*p.x);
                p0.y = &MoveParameters.emplace_back(*p.y);
                GCSsys.addConstraintP2PCoincident(p0, p, GCS::DefaultTemporaryConstraint);
                p1.x = &MoveParameters.emplace_back(*center.x);
                p1.y = &MoveParameters.emplace_back(*center.y);
                int i = GCSsys.addConstraintP2PCoincident(p1, center, GCS::DefaultTemporaryConstraint);
                GCSsys.rescaleConstraint(i - 1, 0.01);
                GCSsys.rescaleConstraint(i, 0.01);
            }
        }
        else if (Geoms[geoId].type == BSpline) {
            if (pos == PointPos::start || pos == PointPos::end) {
                GCS::Point p0;
                GCS::Point& p = pos == PointPos::start ? Points[Geoms[geoId].startPointId]
                                                       : Points[Geoms[geoId].endPointId];
                p0.x = &MoveParameters.emplace_back(*p.x);
                p0.y = &MoveParameters.emplace_back(*p.y);
                GCSsys.addConstraintP2PCoincident(p0, p, GCS::DefaultTemporaryConstraint);
            }
            else if (pos == PointPos::none || pos == PointPos::mid) {
                GCS::BSpline& bsp = BSplines[Geoms[geoId].index];
                for (auto pole : bsp.poles) {
                    GCS::Point p1;
                    p1.x = &MoveParameters.emplace_back(*pole.x);
                    p1.y = &MoveParameters.emplace_back(*pole.y);
                    GCSsys.addConstraintP2PCoincident(p1, pole, GCS::DefaultTemporaryConstraint);
                }
            }
        }
        else if (Geoms[geoId].type == Arc) {
            GCS::Point& center = Points[Geoms[geoId].midPointId];
            GCS::Point p0, p1;
            if (pos == PointPos::mid) {
                p0.x = &MoveParameters.emplace_back(*center.x);
                p0.y = &MoveParameters.emplace_back(*center.y);
                GCSsys.addConstraintP2PCoincident(p0, center, GCS::DefaultTemporaryConstraint);
            }
            else if (pos == PointPos::none && geoEltIds.size() > 1) {
                // When group dragging, arcs should move without modification.
                GCS::Point p2;
                GCS::Point& sp = Points[Geoms[geoId].startPointId];
                GCS::Point& ep = Points[Geoms[geoId].endPointId];
                p0.x = &MoveParameters.emplace_back(*sp.x);
                p0.y = &MoveParameters.emplace_back(*sp.y);
                GCSsys.addConstraintP2PCoincident(p0, sp, GCS::DefaultTemporaryConstraint);

                p2.x = &MoveParameters.emplace_back(*ep.x);
                p2.y = &MoveParameters.emplace_back(*ep.y);
                GCSsys.addConstraintP2PCoincident(p2, ep, GCS::DefaultTemporaryConstraint);

                p1.x = &MoveParameters.emplace_back(*center.x);
                p1.y = &MoveParameters.emplace_back(*center.y);
                int i = GCSsys.addConstraintP2PCoincident(p1, center, GCS::DefaultTemporaryConstraint);
                GCSsys.rescaleConstraint(i - 2, 0.01);
                GCSsys.rescaleConstraint(i - 1, 0.01);
                GCSsys.rescaleConstraint(i, 0.01);
            }
            else if (pos == PointPos::start || pos == PointPos::end || pos == PointPos::none) {
                if (pos == PointPos::start || pos == PointPos::end) {
                    GCS::Point& p = (pos == PointPos::start) ? Points[Geoms[geoId].startPointId]
                                                             : Points[Geoms[geoId].endPointId];
                    p0.x = &MoveParameters.emplace_back(*p.x);
                    p0.y = &MoveParameters.emplace_back(*p.y);
                    GCSsys.addConstraintP2PCoincident(p0, p, GCS::DefaultTemporaryConstraint);
                }
                else if (pos == PointPos::none) {
                    GCS::Arc& a = Arcs[Geoms[geoId].index];
                    p0.x = &MoveParameters.emplace_back(*center.x);
                    p0.y = &MoveParameters.emplace_back(*center.y + *a.rad);
                    GCSsys.addConstraintPointOnArc(p0, a, GCS::DefaultTemporaryConstraint);
                }

                p1.x = &MoveParameters.emplace_back(*center.x);
                p1.y = &MoveParameters.emplace_back(*center.y);
                int i = GCSsys.addConstraintP2PCoincident(p1, center, GCS::DefaultTemporaryConstraint);
                GCSsys.rescaleConstraint(i - 1, 0.01);
                GCSsys.rescaleConstraint(i, 0.01);
            }
        }
    }

    InitParameters = MoveParameters;

    GCSsys.initSolution();
    isInitMove = true;

    return 0;
}

int Sketch::initMove(int geoId, PointPos pos)
{
    std::vector<GeoElementId> geoEltIds = {GeoElementId {geoId, pos}};
    return initMove(geoEltIds);
}

void Sketch::resetInitMove()
{
    isInitMove = false;
}

static double vecDistance(Vec a, Vec b)
{
    // Base::Vector3d (a - b).Length()
    double dx = a.x - b.x, dy = a.y - b.y, dz = 0.0;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

GCS::SolveStatus Sketch::moveGeometries(const std::vector<GeoElementId>& geoEltIds, Vec toPoint, bool relative)
{
    if (hasConflicts()) {
        // don't try to move sketches that contain conflicting constraints
        return GCS::SolveStatus::Failed;
    }

    if (!isInitMove) {
        initMove(geoEltIds);
        initToPoint = toPoint;
        moveStep = 0;
    }
    else {
        if (!relative && RecalculateInitialSolutionWhileMovingPoint) {
            if (moveStep == 0) {
                moveStep = vecDistance(toPoint, initToPoint);
            }
            else {
                // I am getting too far away from the original solution so reinit the solution
                if (vecDistance(toPoint, initToPoint) > 20 * moveStep) {
                    initMove(geoEltIds);
                    initToPoint = toPoint;
                }
            }
        }
    }

    if (relative) {
        for (size_t i = 0; i < MoveParameters.size() - 1; i += 2) {
            MoveParameters[i] = InitParameters[i] + toPoint.x;
            MoveParameters[i + 1] = InitParameters[i + 1] + toPoint.y;
        }
    }
    else {
        size_t i = 0;
        for (auto& pair : geoEltIds) {
            if (i >= MoveParameters.size()) {
                break;
            }
            int geoId = checkGeoId(pair.GeoId);
            PointPos pos = pair.Pos;

            if (Geoms[geoId].type == Point) {
                if (pos == PointPos::start) {
                    MoveParameters[i] = toPoint.x;
                    MoveParameters[i + 1] = toPoint.y;
                    i += 2;
                }
            }
            else if (Geoms[geoId].type == Line) {
                if (pos == PointPos::start || pos == PointPos::end) {
                    MoveParameters[i] = toPoint.x;
                    MoveParameters[i + 1] = toPoint.y;
                    i += 2;
                }
                else if (pos == PointPos::none || pos == PointPos::mid) {
                    double dx = (InitParameters[i + 2] - InitParameters[i]) * 0.5;
                    double dy = (InitParameters[i + 3] - InitParameters[i + 1]) * 0.5;
                    MoveParameters[i] = toPoint.x - dx;
                    MoveParameters[i + 1] = toPoint.y - dy;
                    MoveParameters[i + 2] = toPoint.x + dx;
                    MoveParameters[i + 3] = toPoint.y + dy;
                    i += 4;
                }
            }
            else if (Geoms[geoId].type == Circle || Geoms[geoId].type == Ellipse) {
                if (pos == PointPos::mid || pos == PointPos::none) {
                    MoveParameters[i] = toPoint.x;
                    MoveParameters[i + 1] = toPoint.y;
                    i += 2;
                }
            }
            else if (
                Geoms[geoId].type == Arc || Geoms[geoId].type == ArcOfEllipse
                || Geoms[geoId].type == ArcOfHyperbola || Geoms[geoId].type == ArcOfParabola
            ) {
                MoveParameters[i] = toPoint.x;
                MoveParameters[i + 1] = toPoint.y;
                i += 2;
            }
            else if (Geoms[geoId].type == BSpline) {
                if (pos == PointPos::start || pos == PointPos::end) {
                    MoveParameters[i] = toPoint.x;
                    MoveParameters[i + 1] = toPoint.y;
                    i += 2;
                }
                else if (pos == PointPos::none || pos == PointPos::mid) {
                    GCS::BSpline& bsp = BSplines[Geoms[geoId].index];

                    double cx = 0, cy = 0;  // geometric center
                    for (size_t j = 0; j < bsp.poles.size() * 2; j += 2) {
                        cx += InitParameters[i + j];
                        cy += InitParameters[i + j + 1];
                        j += 2;
                    }

                    cx /= bsp.poles.size();
                    cy /= bsp.poles.size();

                    for (size_t j = 0; j < bsp.poles.size() * 2; j += 2) {
                        MoveParameters[i + j] = toPoint.x + InitParameters[i + j] - cx;
                        MoveParameters[i + j + 1] = toPoint.y + InitParameters[i + j + 1] - cy;
                        j += 2;
                    }
                    i += bsp.poles.size() * 2;
                }
            }
        }
    }

    return solve();
}

GCS::SolveStatus Sketch::moveGeometry(int geoId, PointPos pos, Vec toPoint, bool relative)
{
    std::vector<GeoElementId> geoEltIds = {GeoElementId {geoId, pos}};
    return moveGeometries(geoEltIds, toPoint, relative);
}

int Sketch::getPointId(int geoId, PointPos pos) const
{
    // do a range check first
    if (geoId < 0 || geoId >= (int)Geoms.size()) {
        return -1;
    }
    switch (pos) {
        case PointPos::start:
            return Geoms[geoId].startPointId;
        case PointPos::end:
            return Geoms[geoId].endPointId;
        case PointPos::mid:
            return Geoms[geoId].midPointId;
        case PointPos::none:
        case PointPos::NumPointPos:
            break;
    }
    return -1;
}

Vec Sketch::getPoint(int geoId, PointPos pos) const
{
    geoId = checkGeoId(geoId);
    int pointId = getPointId(geoId, pos);
    if (pointId != -1) {
        return Vec {*Points[pointId].x, *Points[pointId].y};
    }

    return Vec {};
}

// SketchDoc (from SketchObject*.cpp) ==========================================================

SketchDoc::SketchDoc()
{
    // SketchObject::initExternalGeo
    auto HLine = Sketcher::Geometry::makeLineSegment(Vec {0, 0}, Vec {1, 0});
    auto VLine = Sketcher::Geometry::makeLineSegment(Vec {0, 0}, Vec {0, 1});
    HLine.construction = true;
    VLine.construction = true;
    externalGeo = {HLine, VLine};
}

std::vector<Sketcher::Geometry> SketchDoc::getCompleteGeometry() const
{
    std::vector<Sketcher::Geometry> vals = geometry;
    vals.insert(vals.end(), externalGeo.rbegin(), externalGeo.rend());  // in reverse order
    return vals;
}

const Sketcher::Geometry* SketchDoc::getGeometry(int geoId) const
{
    if (geoId >= 0) {
        if (geoId < int(geometry.size())) {
            return &geometry[geoId];
        }
    }
    else if (-geoId - 1 < int(externalGeo.size())) {
        return &externalGeo[-geoId - 1];
    }
    return nullptr;
}

Vec SketchDoc::getPoint(int geoId, PointPos pos) const
{
    // SketchObject::getPoint(const Part::Geometry*, PointPos)
    const Sketcher::Geometry* geo = getGeometry(geoId);
    if (!geo) {
        throw std::invalid_argument("SketchObject::getPoint. Invalid GeoId was supplied.");
    }
    switch (geo->kind) {
        case Sketcher::Geometry::Point:
            if (pos == PointPos::start || pos == PointPos::mid || pos == PointPos::end) {
                return geo->getPoint();
            }
            break;
        case Sketcher::Geometry::LineSegment:
            if (pos == PointPos::start) {
                return geo->getStartPoint();
            }
            else if (pos == PointPos::end) {
                return geo->getEndPoint();
            }
            break;
        case Sketcher::Geometry::Circle: {
            auto pt = geo->getCenter();
            if (pos != PointPos::mid) {
                pt.x += geo->getRadius();
            }
            return pt;
        }
        case Sketcher::Geometry::ArcOfCircle:
            if (pos == PointPos::start) {
                return geo->getStartPoint();
            }
            else if (pos == PointPos::end) {
                return geo->getEndPoint();
            }
            else if (pos == PointPos::mid) {
                return geo->getCenter();
            }
            break;
        case Sketcher::Geometry::Ellipse: {
            // SketchEllipse::getPoint
            auto pt = geo->getCenter();
            if (pos != PointPos::mid) {
                Vec d = geo->getMajorAxisDir();
                double r = geo->getMajorRadius();
                pt.x += d.x * r;
                pt.y += d.y * r;
            }
            return pt;
        }
        case Sketcher::Geometry::ArcOfEllipse:
        case Sketcher::Geometry::ArcOfHyperbola:
        case Sketcher::Geometry::ArcOfParabola: {
            // SketchArcOfEllipse (emulateCCW) / SketchArcOfHyperbola / SketchArcOfParabola::getPoint
            bool emulateCCW = geo->kind == Sketcher::Geometry::ArcOfEllipse;
            if (pos == PointPos::start) {
                return geo->getStartPoint(emulateCCW);
            }
            else if (pos == PointPos::end) {
                return geo->getEndPoint(emulateCCW);
            }
            else if (pos == PointPos::mid) {
                return geo->getCenter();
            }
            break;
        }
        case Sketcher::Geometry::BSplineCurve:
            // SketchBSplineCurve::getPoint
            if (pos == PointPos::start) {
                return geo->getStartPoint();
            }
            else if (pos == PointPos::end) {
                return geo->getEndPoint();
            }
            break;
    }
    return Vec {};
}

int SketchDoc::addGeometry(const Sketcher::Geometry& geo)
{
    geometry.push_back(geo);
    return geometry.size() - 1;
}

bool SketchDoc::evaluateConstraint(const Constraint& constraint) const
{
    // if requireXXX,  GeoUndef is treated as an error. If not requireXXX,
    // GeoUndef is accepted. Index range checking is done on everything regardless.

    // constraints always require a First!!
    bool requireSecond = false;
    bool requireThird = false;

    switch (constraint.Type) {
        case Tangent:
        case Group:
            requireSecond = true;
            break;
        case Symmetric:
        case SnellsLaw:
            requireSecond = true;
            requireThird = true;
            break;
        default:
            break;
    }

    int intGeoCount = geometry.size();
    int extGeoCount = getExternalGeometryCount();

    // the actual checks
    bool ret = true;
    int geoId;

    // First is always required and GeoId must be within range
    geoId = constraint.First;
    ret = ret && (geoId >= -extGeoCount && geoId < intGeoCount);

    geoId = constraint.Second;
    ret = ret
        && ((geoId == GeoEnum::GeoUndef && !requireSecond)
            || (geoId >= -extGeoCount && geoId < intGeoCount));

    geoId = constraint.Third;
    ret = ret
        && ((geoId == GeoEnum::GeoUndef && !requireThird)
            || (geoId >= -extGeoCount && geoId < intGeoCount));

    return ret;
}

bool SketchDoc::addConstraints(const std::vector<Constraint>& newConstraints)
{
    // SketchObjectPy::addConstraint with a list: every constraint is evaluated first
    for (const auto& c : newConstraints) {
        if (!evaluateConstraint(c)) {
            return false;
        }
    }
    // SketchObject::addConstraints
    for (const auto& c : newConstraints) {
        Constraint cnew = c;

        if (cnew.Type == Tangent || cnew.Type == Perpendicular) {
            AutoLockTangencyAndPerpty(&cnew);
        }

        setOrientation(&cnew);

        // addGeometryState: InternalAlignment gives its geometry its internal type, Block marks
        // its geometry blocked (internal geometry only)
        if (cnew.First >= 0 && cnew.First < int(geometry.size())) {
            if (cnew.Type == InternalAlignment) {
                // getInternalTypeState: the alignment types are numbered as the internal types
                int t = cnew.AlignmentType;
                geometry[cnew.First].internalType = (t > Undef && t < NumInternalAlignmentType)
                    ? static_cast<InternalType::InternalType>(t)
                    : InternalType::None;
            }
            else if (cnew.Type == Block) {
                geometry[cnew.First].blocked = true;
            }
        }

        constraints.push_back(cnew);
    }
    solverNeedsUpdate = true;
    return true;
}

double SketchDoc::calculateAngleViaPoint(int GeoId1, int GeoId2, double px, double py)
{
    // Temporary sketch based calculation. Slow, but guaranteed consistency with constraints.
    Sketch sk;

    const Sketcher::Geometry* p1 = getGeometry(GeoId1);
    const Sketcher::Geometry* p2 = getGeometry(GeoId2);

    if (p1 && p2 && p1->kind != Sketcher::Geometry::Point && p2->kind != Sketcher::Geometry::Point) {
        // TODO: Check if any of these are B-splines
        int i1 = sk.addGeometry(*p1);
        int i2 = sk.addGeometry(*p2);

        if (p1->kind == Sketcher::Geometry::BSplineCurve || p2->kind == Sketcher::Geometry::BSplineCurve) {
            Vec pt {px, py};
            double p1ClosestParam = p1->closestParameter(pt);
            double p2ClosestParam = p2->closestParameter(pt);

            return sk.calculateAngleViaParams(i1, i2, p1ClosestParam, p2ClosestParam);
        }

        return sk.calculateAngleViaPoint(i1, i2, px, py);
    }
    throw std::invalid_argument("Null geometry in calculateAngleViaPoint");
}

bool SketchDoc::AutoLockTangencyAndPerpty(Constraint* cstr)
{
    // AutoLockTangencyAndPerpty(cstr, bForce=false, bLock=true)
    using std::numbers::pi;

    try {
        /*tangency type already set. If not bForce - don't touch.*/
        if (cstr->getValue() != 0.0) {
            return true;
        }
        // decide on tangency type. Write the angle value into the datum field of the
        // constraint.
        int geoId1, geoId2, geoIdPt;
        PointPos posPt;
        geoId1 = cstr->First;
        geoId2 = cstr->Second;
        geoIdPt = cstr->Third;
        posPt = cstr->ThirdPos;
        if (geoIdPt == GeoEnum::GeoUndef) {  // not tangent-via-point, try endpoint-to-endpoint...

            // First check if it is a tangency at knot constraint, if not continue with checking
            // for endpoints. Endpoint constraints make use of the AngleViaPoint framework at
            // solver level, so they need locking angle calculation, tangency at knot constraint
            // does not.
            auto geof = getGeometry(cstr->First);
            if (!geof) {
                return false;
            }
            if (geof->internalType == InternalType::BSplineKnotPoint) {
                // there is point that is a B-Spline knot in a two element constraint
                // this is not implement using AngleViaPoint (TangencyViaPoint)
                return false;
            }
            geoIdPt = cstr->First;
            posPt = cstr->FirstPos;
        }
        if (posPt == PointPos::none) {
            // not endpoint-to-curve and not endpoint-to-endpoint tangent (is simple tangency)
            // no tangency lockdown is implemented for simple tangency. Do nothing.
            return false;
        }

        Vec p = getPoint(geoIdPt, posPt);

        // this piece of code is also present in Sketch.cpp, correct for offset
        // and to do the autodecision for old sketches.
        // the difference between the datum value and the actual angle to apply.
        // (datum=angle+offset)
        double angleOffset = 0.0;
        // the desired angle value (and we are to decide if 180* should be added to it)
        double angleDesire = 0.0;
        if (cstr->Type == Tangent) {
            angleOffset = -pi / 2;
            angleDesire = 0.0;
        }
        if (cstr->Type == Perpendicular) {
            angleOffset = 0;
            angleDesire = pi / 2;
        }

        double angleErr = calculateAngleViaPoint(geoId1, geoId2, p.x, p.y) - angleDesire;

        // bring angleErr to -pi..pi
        if (angleErr > pi) {
            angleErr -= pi * 2;
        }
        if (angleErr < -pi) {
            angleErr += pi * 2;
        }

        // the autodetector
        if (fabs(angleErr) > pi / 2) {
            angleDesire += pi;
        }

        // external tangency. The angle stored is offset by Pi/2 so that a value of 0.0 is
        // invalid and treated as "undecided".
        cstr->setValue(angleDesire + angleOffset);
    }
    catch (const std::exception&) {
        // failure to determine tangency type is not a big deal, so a warning.
        return false;
    }
    return true;
}

namespace
{
int ccw2d(Vec A, Vec B, Vec C)
{
    double signedArea = B.x * C.y - B.y * C.x - A.x * C.y + A.y * C.x + A.x * B.y - A.y * B.x;
    return signedArea > 0.0 ? ConstraintOrientations::CounterClockwise
                            : ConstraintOrientations::Clockwise;
}

// getCircle(): a circle or an arc's circle as (centre, radius)
bool getCircle(const Sketcher::Geometry* geo, Vec& center, double& radius)
{
    if (geo
        && (geo->kind == Sketcher::Geometry::Circle || geo->kind == Sketcher::Geometry::ArcOfCircle)) {
        center = geo->getCenter();
        radius = std::max(geo->getRadius(), 0.0);
        return true;
    }
    return false;
}

// Base::Vector3d::DistanceToLine(base, dir)
double distanceToLine(Vec p, Vec base, Vec dir)
{
    // (dir % (p - base)).Length() / dir.Length()
    Vec d {p.x - base.x, p.y - base.y};
    double cz = dir.x * d.y - dir.y * d.x;
    double cx = dir.y * 0.0 - 0.0 * d.y;
    double cy = 0.0 * d.x - dir.x * 0.0;
    double len = std::sqrt(cx * cx + cy * cy + cz * cz);
    return len / vecLength(dir);
}
}  // namespace

void SketchDoc::setOrientationDistance(Constraint* constr)
{
    // Try to find the orientation of point-line distance
    if (constr->FirstPos != PointPos::none && constr->Second != GeoEnum::GeoUndef) {
        const Sketcher::Geometry* g = getGeometry(constr->Second);
        if (g && g->kind == Sketcher::Geometry::LineSegment) {
            constr->Orientation.i
                = ccw2d(g->getStartPoint(), g->getEndPoint(), getPoint(constr->First, constr->FirstPos));
        }
        return;
    }

    // Try to find the orientation of circle-circle distance or circle-line
    if (constr->FirstPos == PointPos::none && constr->SecondPos == PointPos::none
        && constr->Second != GeoEnum::GeoUndef) {
        const Sketcher::Geometry* firGeo = getGeometry(constr->First);
        const Sketcher::Geometry* secGeo = getGeometry(constr->Second);
        Vec c1, c2;
        double r1, r2;
        bool isC1 = getCircle(firGeo, c1, r1);
        bool isC2 = getCircle(secGeo, c2, r2);

        if (isC1 && isC2) {  // circle-circle distance

            // If one of the circles is completely within the other, we will say that
            // it is internal, if they are not within each other orcompletly intersect we won't
            // make a call

            double centerDistance = pntDistance(c1, c2);

            if (centerDistance + r1 < r2) {
                constr->Orientation.i = ConstraintOrientations::Internal;  // Circ1 is within circ2
            }
            else if (centerDistance + r2 < r1) {
                constr->Orientation.i = ConstraintOrientations::External;  // Circ2 is within circ1
            }
            return;
        }

        if (isC1 && secGeo && secGeo->kind == Sketcher::Geometry::LineSegment) {  // circle-line distance
            Vec s = secGeo->getStartPoint();
            Vec e = secGeo->getEndPoint();
            bool internal = distanceToLine(c1, s, Vec {e.x - s.x, e.y - s.y}) < r1;
            auto ccw = ccw2d(s, e, c1);

            constr->Orientation.i = ccw
                | (internal ? ConstraintOrientations::Internal : ConstraintOrientations::External);
        }
    }
}

void SketchDoc::setOrientationTangent(Constraint* constr)
{
    const Sketcher::Geometry* firGeo = getGeometry(constr->First);
    const Sketcher::Geometry* secGeo = getGeometry(constr->Second);

    auto impl = [&](const Sketcher::Geometry* firGeo, const Sketcher::Geometry* secGeo) -> bool {
        Vec center;
        double radius;
        if (!getCircle(firGeo, center, radius) || !secGeo
            || secGeo->kind != Sketcher::Geometry::LineSegment) {
            return false;
        }

        constr->Orientation.i = ccw2d(secGeo->getStartPoint(), secGeo->getEndPoint(), center);
        return true;
    };

    // Tangent can be defined as line + [circle] or [circle] + line
    // so we test both
    if (impl(firGeo, secGeo)) {
        return;
    }
    if (impl(secGeo, firGeo)) {
        return;
    }
}

void SketchDoc::setOrientation(Constraint* constr)
{
    // setOrientation(constr, reset=false)
    if (!constr->Orientation.testFlag(ConstraintOrientations::None)) {
        return;
    }

    if (constr->Type == Distance) {
        setOrientationDistance(constr);
    }
    else if (constr->Type == Tangent) {
        setOrientationTangent(constr);
    }
}

std::vector<Constraint*> SketchDoc::constraintPointers()
{
    std::vector<Constraint*> out;
    out.reserve(constraints.size());
    for (auto& c : constraints) {
        out.push_back(&c);
    }
    return out;
}

void SketchDoc::retrieveSolverDiagnostics()
{
    lastHasConflict = solvedSketch.hasConflicts();
    lastHasRedundancies = solvedSketch.hasRedundancies();
    lastHasPartialRedundancies = solvedSketch.hasPartialRedundancies();
    lastHasMalformedConstraints = solvedSketch.hasMalformedConstraints();
    lastConflicting = solvedSketch.getConflicting();
    lastRedundant = solvedSketch.getRedundant();
    lastPartiallyRedundant = solvedSketch.getPartiallyRedundant();
    lastMalformedConstraints = solvedSketch.getMalformedConstraints();
}

SketchSolveStatus SketchDoc::solve(bool updateGeoAfterSolving)
{
    // Reset the initial movement in case of a dragging operation was ongoing on the solver.
    solvedSketch.resetInitMove();

    // set up a sketch (including dofs counting and diagnosing of conflicts)
    lastDoF = solvedSketch.setUpSketch(getCompleteGeometry(), constraintPointers(), getExternalGeometryCount());

    solverNeedsUpdate = false;

    retrieveSolverDiagnostics();

    // Failure is default for notifying the user unless otherwise proven
    lastSolverStatus = GCS::SolveStatus::Failed;

    auto status = SketchSolveStatus::Success;

    // redundancy is a lower priority problem than conflict/over-constraint/solver error
    // we set it here because we are indeed going to solve, as we can. However, we still want to
    // provide the right error code.
    if (lastHasRedundancies) {  // redundant constraints
        status = SketchSolveStatus::RedundantConstraints;
    }

    if (lastDoF < 0) {  // over-constrained sketch
        status = SketchSolveStatus::Overconstrained;
    }
    else if (lastHasConflict) {  // conflicting constraints
        // The situation is exactly the same as in the over-constrained situation.
        status = SketchSolveStatus::ConflictingConstraints;
    }
    else if (lastHasMalformedConstraints) {
        status = SketchSolveStatus::MalformedConstraints;
    }
    else {
        lastSolverStatus = solvedSketch.solve();
        if (lastSolverStatus != GCS::SolveStatus::Success) {  // solving
            status = SketchSolveStatus::SolverError;
        }
    }

    // In uncommon situations, the analysis of QR decomposition leads to full rank, but the result
    // does not converge. We avoid marking a sketch as fully constrained when no convergence is
    // achieved.
    if (status == SketchSolveStatus::Success) {
        FullyConstrained = lastDoF == 0;
        if (updateGeoAfterSolving) {
            // set the newly solved geometry
            auto geomlist = solvedSketch.extractGeometry();
            // the blocked state and the internal type live in the geometry (GeometryFacade); keep
            // them as the property's
            for (size_t i = 0; i < geomlist.size() && i < geometry.size(); ++i) {
                geomlist[i].blocked = geometry[i].blocked;
                geomlist[i].internalType = geometry[i].internalType;
            }
            geometry = std::move(geomlist);
        }
    }

    return status;
}

SketchSolveStatus SketchDoc::moveGeometries(const std::vector<GeoElementId>& geoEltIds, Vec toPoint, bool relative)
{
    // if we are moving a point at SketchObject level, we need to start from a solved sketch
    // if we have conflicts we can forget about moving.
    if (solverNeedsUpdate) {
        lastDoF = solvedSketch.setUpSketch(getCompleteGeometry(), constraintPointers(), getExternalGeometryCount());

        retrieveSolverDiagnostics();

        solverNeedsUpdate = false;
    }

    if (lastDoF < 0) {  // over-constrained sketch
        return SketchSolveStatus::SolverError;
    }
    if (lastHasConflict) {  // conflicting constraints
        return SketchSolveStatus::SolverError;
    }

    // move the point and solve
    lastSolverStatus = solvedSketch.moveGeometries(geoEltIds, toPoint, relative);

    // moving the point can not result in a conflict that we did not have
    // or a redundancy that we did not have before, or a change of DoF

    if (lastSolverStatus == GCS::SolveStatus::Success) {
        auto geomlist = solvedSketch.extractGeometry();
        for (size_t i = 0; i < geomlist.size() && i < geometry.size(); ++i) {
            geomlist[i].blocked = geometry[i].blocked;
            geomlist[i].internalType = geometry[i].internalType;
        }
        geometry = std::move(geomlist);
    }

    solvedSketch.resetInitMove();  // reset solver point moving mechanism

    return lastSolverStatus == GCS::SolveStatus::Success ? SketchSolveStatus::Success
                                                         : SketchSolveStatus::SolverError;
}

int SketchDoc::initTemporaryMove(const std::vector<GeoElementId>& geoEltIds)
{
    if (solverNeedsUpdate) {
        solve();
    }

    return solvedSketch.initMove(geoEltIds);
}

GCS::SolveStatus SketchDoc::moveGeometriesTemporary(const std::vector<GeoElementId>& geoEltIds, Vec toPoint, bool relative)
{
    return solvedSketch.moveGeometries(geoEltIds, toPoint, relative);
}
