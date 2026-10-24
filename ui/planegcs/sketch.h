// SPDX-License-Identifier: LGPL-2.1-or-later
//
// The Sketcher's link between sketch geometry/constraints and PlaneGCS, ported from FreeCAD's
// src/Mod/Sketcher/App/Sketch.cpp/.h at FreeCAD commit 3160daf1e2b6 (weekly-2026.09.30),
// (c) 2010 Juergen Riegel and FreeCAD's contributors, LGPL-2.1-or-later. The few parts of
// SketchObject*.cpp that drive it (solve(), moveGeometries(), AutoLockTangencyAndPerpty(),
// setOrientation(), the Block geometry state) are ported into SketchDoc below.
//
// What changes from FreeCAD: Part::Geometry (OpenCascade) is replaced by Sketcher::Geometry, which
// keeps the same numbers OpenCascade would (a line segment is a point, a unit direction and a
// trim range; an arc's trim range is normalised as Geom_TrimmedCurve::SetTrim does), and
// Base::Console logging is dropped. Scope: Point, LineSegment, Circle, ArcOfCircle, Ellipse,
// ArcOfEllipse, ArcOfHyperbola, ArcOfParabola and BSplineCurve (OpenCascade's numbers for the
// conics: gp_Ax2's directions, ElCLib's values, Geom_TrimmedCurve's trims and reversal; for the
// B-spline: Geom_BSplineCurve's poles, weights (rational only while they differ), knots and
// multiplicities); constraints Coincident, Horizontal, Vertical, Parallel, Perpendicular, Tangent
// (with B-spline knot tangency), Distance, DistanceX, DistanceY, Radius, Diameter, Weight, Angle,
// Equal, PointOnObject (B-splines too), Symmetric, SnellsLaw, InternalAlignment (every alignment
// type), Block, driving or not. Groups and text are not ported.
#pragma once

#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "freecad/Sketcher/App/planegcs/GCS.h"

namespace Sketcher
{

// GeoEnum.h
enum class PointPos : int
{
    none = 0,
    start = 1,
    end = 2,
    mid = 3,
    NumPointPos
};

namespace GeoEnum
{
constexpr int RtPnt = -1;
constexpr int HAxis = -1;
constexpr int VAxis = -2;
constexpr int RefExt = -3;
constexpr int GeoUndef = -2000;
}  // namespace GeoEnum

struct GeoElementId
{
    int GeoId = GeoEnum::GeoUndef;
    PointPos Pos = PointPos::none;
};

// Constraint.h
enum ConstraintType : int
{
    None = 0,
    Coincident = 1,
    Horizontal = 2,
    Vertical = 3,
    Parallel = 4,
    Tangent = 5,
    Distance = 6,
    DistanceX = 7,
    DistanceY = 8,
    Angle = 9,
    Perpendicular = 10,
    Radius = 11,
    Equal = 12,
    PointOnObject = 13,
    Symmetric = 14,
    InternalAlignment = 15,
    SnellsLaw = 16,
    Block = 17,
    Diameter = 18,
    Weight = 19,
    Group = 20,
    Text = 21,
    NumConstraintTypes
};

// ConstraintOrientations, as Base::Flags: testFlag(None) is true only for no flag at all.
namespace ConstraintOrientations
{
constexpr int None = 0;
constexpr int CounterClockwise = 1;
constexpr int Clockwise = 2;
constexpr int Internal = 4;
constexpr int External = 8;
}  // namespace ConstraintOrientations

struct ConstraintOrientation
{
    int i = ConstraintOrientations::None;
    bool testFlag(int f) const
    {
        return (i & f) == f && (f != 0 || i == f);
    }
};

// Constraint.h
enum InternalAlignmentType : int
{
    Undef = 0,
    EllipseMajorDiameter = 1,
    EllipseMinorDiameter = 2,
    EllipseFocus1 = 3,
    EllipseFocus2 = 4,
    HyperbolaMajor = 5,
    HyperbolaMinor = 6,
    HyperbolaFocus = 7,
    ParabolaFocus = 8,
    BSplineControlPoint = 9,
    BSplineKnotPoint = 10,
    ParabolaFocalAxis = 11,
    NumInternalAlignmentType  // must be the last item!
};

// SketchGeometryExtension.h: the internal type a geometry gets from its InternalAlignment
// constraint (SketchObject::addGeometryState), with the same numbers as InternalAlignmentType.
namespace InternalType
{
enum InternalType : int
{
    None = 0,
    EllipseMajorDiameter = 1,
    EllipseMinorDiameter = 2,
    EllipseFocus1 = 3,
    EllipseFocus2 = 4,
    HyperbolaMajor = 5,
    HyperbolaMinor = 6,
    HyperbolaFocus = 7,
    ParabolaFocus = 8,
    BSplineControlPoint = 9,
    BSplineKnotPoint = 10,
    ParabolaFocalAxis = 11,
    NumInternalGeometryType  // Must be the last
};
}  // namespace InternalType

struct Constraint
{
    ConstraintType Type = None;
    ConstraintOrientation Orientation;
    std::string Name;
    double Value = 0.0;
    int First = GeoEnum::GeoUndef;
    PointPos FirstPos = PointPos::none;
    int Second = GeoEnum::GeoUndef;
    PointPos SecondPos = PointPos::none;
    int Third = GeoEnum::GeoUndef;
    PointPos ThirdPos = PointPos::none;
    bool isDriving = true;
    bool isActive = true;
    InternalAlignmentType AlignmentType = Undef;
    int InternalAlignmentIndex = -1;

    void setValue(double v)
    {
        Value = v;
    }
    double getValue() const
    {
        return Value;
    }
    bool isDimensional() const
    {
        return Type == Distance || Type == DistanceX || Type == DistanceY || Type == Radius
            || Type == Diameter || Type == Angle || Type == SnellsLaw || Type == Weight;
    }
};

// Raised where OpenCascade would raise while setting up a curve from solver values; updateGeometry
// then reports an invalid solution, as FreeCAD does.
struct GeometryError: std::runtime_error
{
    using std::runtime_error::runtime_error;
};

// Stand-in for Part::GeomPoint / GeomLineSegment / GeomCircle / GeomArcOfCircle / GeomEllipse /
// GeomArcOfEllipse / GeomArcOfHyperbola / GeomArcOfParabola / GeomBSplineCurve in the sketch's XY
// plane, with the arithmetic OpenCascade uses for them (gp_Lin, gp_Circ, gp_Elips, gp_Hypr,
// gp_Parab, gp_Ax2, ElCLib, Geom_TrimmedCurve, Geom_BSplineCurve).
struct Vec
{
    double x = 0.0, y = 0.0;
};

// gp_XYZ, for gp_Dir and gp_Ax2: the conics' in-plane directions come from cross products with
// their normal, as OpenCascade computes them.
struct V3
{
    double x = 0.0, y = 0.0, z = 0.0;
};

// gp_Ax2: location, main direction (the normal) and X and Y directions, as gp_Ax2() makes them.
struct Ax2
{
    V3 loc;
    V3 n {0.0, 0.0, 1.0};
    V3 vx {1.0, 0.0, 0.0};
    V3 vy {0.0, 1.0, 0.0};
    void setXDirection(const V3& dir);  // gp_Ax2::SetXDirection (dir is a gp_Dir)
    void setDirection(const V3& dir);   // gp_Ax2::SetDirection (dir is a gp_Dir)
};

// gp_Dir(x, y, z): the vector normalised; GeometryError where OpenCascade raises
// Standard_ConstructionError (a null vector).
V3 makeDir(double x, double y, double z);

// The B-spline's data as Geom_BSplineCurve keeps it: weights is empty while the curve is not
// rational (Weights() then reads 1.0 for every pole).
struct BSplineData
{
    std::vector<Vec> poles;
    std::vector<double> weights;
    std::vector<double> knots;
    std::vector<int> mults;
    int degree = 0;
    bool periodic = false;
};

class Geometry
{
public:
    enum Kind
    {
        Point,
        LineSegment,
        Circle,
        ArcOfCircle,
        Ellipse,
        ArcOfEllipse,
        ArcOfHyperbola,
        ArcOfParabola,
        BSplineCurve
    };

    static Geometry makePoint(Vec p);
    // GC_MakeSegment(p1, p2): a line through p1 along (p2 - p1) normalised, trimmed to [0, |p2-p1|].
    static Geometry makeLineSegment(Vec p1, Vec p2);
    static Geometry makeCircle(Vec center, double radius);
    // Geom_TrimmedCurve(circle, u1, u2): the range is normalised as SetTrim does.
    static Geometry makeArcOfCircle(Vec center, double radius, double u1, double u2);
    // Part.Ellipse(center, major, minor) (gp_Ax2(center, +Z)), then .XAxis = xaxis
    static Geometry makeEllipse(Vec center, double major, double minor, Vec xaxis);
    // Part.ArcOfEllipse(that ellipse, u1, u2)
    static Geometry makeArcOfEllipse(Vec center, double major, double minor, Vec xaxis, double u1, double u2);
    // Part.Hyperbola() with .Center, .MajorRadius, .MinorRadius, .XAxis set in that order, then
    // Part.ArcOfHyperbola(it, u1, u2)
    static Geometry makeArcOfHyperbola(Vec center, double major, double minor, Vec xaxis, double u1, double u2);
    // Part.Parabola() with .Center (its vertex), .Focal, .XAxis, then Part.ArcOfParabola(it, u1, u2)
    static Geometry makeArcOfParabola(Vec vertex, double focal, Vec xaxis, double u1, double u2);
    // Part.BSplineCurve(poles, mults, knots, periodic, degree, weights) (Geom_BSplineCurve's checks)
    static Geometry makeBSpline(BSplineData data);

    Kind kind = Point;
    bool construction = false;
    bool blocked = false;  // GeometryFacade::getBlocked (set by a Block constraint)
    InternalType::InternalType internalType = InternalType::None;  // GeometryFacade::getInternalType

    bool isConic() const
    {
        return kind == Ellipse || kind == ArcOfEllipse || kind == ArcOfHyperbola || kind == ArcOfParabola;
    }
    bool isTrimmedConic() const
    {
        return kind == ArcOfEllipse || kind == ArcOfHyperbola || kind == ArcOfParabola;
    }

    // Point
    Vec getPoint() const
    {
        return p;
    }
    void setPoint(Vec v)
    {
        p = v;
    }
    // LineSegment / the arcs / BSplineCurve (GeomBoundedCurve::getStartPoint); emulateCCWXY as
    // GeomArcOfConic's (the arc's normal is +Z here unless OpenCascade reversed it)
    Vec getStartPoint(bool emulateCCWXY = false) const;
    Vec getEndPoint(bool emulateCCWXY = false) const;
    void setPoints(Vec start, Vec end);  // GeomLineSegment::setPoints
    // Circle / ArcOfCircle; for the conics their location (GeomConic::getCenter, a parabola's vertex)
    Vec getCenter() const
    {
        if (isConic()) {
            return {pos.loc.x, pos.loc.y};
        }
        return p;
    }
    void setCenter(Vec c)
    {
        if (isConic()) {
            pos.loc = V3 {c.x, c.y, 0.0};  // Geom_Conic::SetLocation
            return;
        }
        p = c;
    }
    double getRadius() const
    {
        return r;
    }
    void setRadius(double radius)
    {
        // gp_Circ::SetRadius
        if (radius < 0.0) {
            throw GeometryError("gp_Circ::SetRadius() - radius should be positive number");
        }
        r = radius;
    }
    // ArcOfCircle, as GeomArcOfCircle::getRange/setRange with emulateCCWXY on a +Z circle.
    void getRange(double& u, double& v) const;
    // The trim range as stored (Geom_TrimmedCurve's First/LastParameter, what Python reads)
    double getFirstParameter() const
    {
        return u1;
    }
    double getLastParameter() const
    {
        return u2;
    }
    void setRange(double u, double v);

    // Ellipse / ArcOfEllipse / ArcOfHyperbola
    double getMajorRadius() const
    {
        return majR;
    }
    double getMinorRadius() const
    {
        return minR;
    }
    void setMajorRadius(double radius);  // gp_Elips / gp_Hypr::SetMajorRadius
    void setMinorRadius(double radius);  // gp_Elips / gp_Hypr::SetMinorRadius
    // the X direction (major axis, or towards a parabola's focus)
    Vec getMajorAxisDir() const
    {
        return {pos.vx.x, pos.vx.y};
    }
    const Ax2& getPosition() const
    {
        return pos;
    }
    // GeomEllipse::setMajorAxisDir / GeomArcOfConic::setXAxisDir (a null vector keeps the axis)
    void setMajorAxisDir(Vec dir);
    // ArcOfParabola
    double getFocal() const
    {
        return focal;
    }
    void setFocal(double f);  // gp_Parab::SetFocal
    Vec getFocus() const;     // Geom_Parabola::Focus
    // the conic arcs' getRange/setRange(u, v, emulateCCWXY=true); for a hyperbola or a parabola
    // these may reverse the basis curve, as GeomArcOfHyperbola/Parabola's do
    void getConicRange(double& u, double& v);
    void setConicRange(double u, double v);
    bool isReversed() const
    {
        return pos.n.z < 0;
    }
    // ElCLib's value of the basis conic at u
    Vec conicValue(double u) const;

    // BSplineCurve
    const BSplineData& bspline() const
    {
        return bsp;
    }
    std::vector<double> getWeights() const;  // Geom_BSplineCurve::Weights
    // GeomBSplineCurve::setPoles(poles, weights), workAroundOCCTBug included
    void setPoles(const std::vector<Vec>& poles, const std::vector<double>& weights);
    Vec bsplineValue(double u) const;
    void bsplineD1(double u, Vec& value, Vec& tangent) const;
    double bsplineFirstParameter() const;
    double bsplineLastParameter() const;
    // GeomCurve::closestParameter (GeomAPI_ProjectPointOnCurve's lowest-distance parameter)
    double closestParameter(Vec point) const;

private:
    Vec p;         // point, line location, circle centre
    Vec dir;       // line direction (unit)
    double r = 0;  // radius
    double u1 = 0, u2 = 0;  // trim parameters of a line or arc
    Ax2 pos;                // a conic's position
    double majR = 0, minR = 0, focal = 0;
    BSplineData bsp;

    void setWeight(int index, double w);  // Geom_BSplineCurve::SetWeight (index from 0)
    void setTrimConic(double U1, double U2, bool sense, bool adjustPeriodic);  // Geom_TrimmedCurve::SetTrim
    void reverseTrimmed();  // Geom_TrimmedCurve::Reverse
    void reverseBasis();    // Geom_Conic::Reverse
};

class Sketch
{
public:
    Sketch();
    ~Sketch();
    Sketch(const Sketch&) = delete;
    Sketch& operator=(const Sketch&) = delete;

    GCS::SolveStatus solve();
    int resetSolver();
    void clear();

    // set the sketch up with geoms and constraints; returns the degrees of freedom (see Sketch.h)
    int setUpSketch(
        const std::vector<Geometry>& GeoList,
        const std::vector<Constraint*>& ConstraintList,
        int extGeoCount = 0
    );

    int addGeometry(const Geometry& geo, bool fixed = false);
    int addGeometry(const std::vector<Geometry>& geos, bool fixed = false);
    int addGeometry(const std::vector<Geometry>& geos, const std::vector<bool>& blockedGeometry);

    std::vector<Geometry> extractGeometry(
        bool withConstructionElements = true,
        bool withExternalElements = false
    ) const;

    int getPointId(int geoId, PointPos pos) const;
    Vec getPoint(int geoId, PointPos pos) const;

    bool hasConflicts() const
    {
        return !Conflicting.empty();
    }
    const std::vector<int>& getConflicting() const
    {
        return Conflicting;
    }
    bool hasRedundancies() const
    {
        return !Redundant.empty();
    }
    const std::vector<int>& getRedundant() const
    {
        return Redundant;
    }
    bool hasPartialRedundancies() const
    {
        return !PartiallyRedundant.empty();
    }
    const std::vector<int>& getPartiallyRedundant() const
    {
        return PartiallyRedundant;
    }
    bool hasMalformedConstraints() const
    {
        return !MalformedConstraints.empty();
    }
    const std::vector<int>& getMalformedConstraints() const
    {
        return MalformedConstraints;
    }

    std::set<std::pair<int, PointPos>> getDependencyGroup(int geoId, PointPos pos) const;
    const std::vector<std::set<std::pair<int, PointPos>>>& getDependencyGroups() const
    {
        return pDependencyGroups;
    }
    // (geoId, pos, index) of every parameter the solver reports as dependent (not fixed by the
    // constraints): pos none for a radius (index 0) or arc angles (1, 2), else x (0) / y (1).
    std::vector<std::tuple<int, PointPos, int>> getDependentParameterElements() const;
    bool isEmptyDiagnoseMatrix() const
    {
        return GCSsys.isEmptyDiagnoseMatrix();
    }

    // dragging
    int initMove(const std::vector<GeoElementId>& geoEltIds);
    int initMove(int geoId, PointPos pos);
    void resetInitMove();
    GCS::SolveStatus moveGeometries(
        const std::vector<GeoElementId>& geoEltIds,
        Vec toPoint,
        bool relative = false
    );
    GCS::SolveStatus moveGeometry(int geoId, PointPos pos, Vec toPoint, bool relative = false);
    bool getRecalculateInitialSolutionWhileMovingPoint() const
    {
        return RecalculateInitialSolutionWhileMovingPoint;
    }
    void setRecalculateInitialSolutionWhileMovingPoint(bool on)
    {
        RecalculateInitialSolutionWhileMovingPoint = on;
    }

    int addConstraints(
        const std::vector<Constraint*>& ConstraintList,
        const std::vector<bool>& unenforceableConstraints
    );
    int addConstraint(const Constraint* constraint);

    int addCoordinateXConstraint(int geoId, PointPos pos, double* value, bool driving = true);
    int addCoordinateYConstraint(int geoId, PointPos pos, double* value, bool driving = true);
    int addDistanceXConstraint(int geoId, double* value, bool driving = true);
    int addDistanceXConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, double* value, bool driving = true);
    int addDistanceYConstraint(int geoId, double* value, bool driving = true);
    int addDistanceYConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, double* value, bool driving = true);
    int addHorizontalConstraint(int geoId);
    int addHorizontalConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2);
    int addVerticalConstraint(int geoId);
    int addVerticalConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2);
    int addPointCoincidentConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2);
    int addDistanceConstraint(int geoId1, double* value, bool driving = true);
    int addDistanceConstraint(int geoId1, PointPos pos1, int geoId2, double* value, ConstraintOrientation orientation, bool driving = true);
    int addDistanceConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, double* value, bool driving = true);
    int addDistanceConstraint(int geoId1, int geoId2, double* value, ConstraintOrientation orientation, bool driving = true);
    int addParallelConstraint(int geoId1, int geoId2);
    int addPerpendicularConstraint(int geoId1, int geoId2);
    int addPerpendicularConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, int geoId3);
    int addTangentConstraint(int geoId1, int geoId2, ConstraintOrientation orientation);
    int addAngleAtPointConstraint(
        int geoId1,
        PointPos pos1,
        int geoId2,
        PointPos pos2,
        int geoId3,
        PointPos pos3,
        double* value,
        ConstraintType cTyp,
        bool driving = true
    );
    int addRadiusConstraint(int geoId, double* value, bool driving = true);
    int addDiameterConstraint(int geoId, double* value, bool driving = true);
    int addAngleConstraint(int geoId, double* value, bool driving = true);
    int addAngleConstraint(int geoId1, int geoId2, double* value, bool driving = true);
    int addAngleConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, double* value, bool driving = true);
    int addEqualConstraint(int geoId1, int geoId2);
    int addPointOnObjectConstraint(int geoId1, PointPos pos1, int geoId2, bool driving = true);
    int addSymmetricConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, int geoId3);
    int addSymmetricConstraint(int geoId1, PointPos pos1, int geoId2, PointPos pos2, int geoId3, PointPos pos3);
    int addPointOnObjectConstraint(int geoId1, PointPos pos1, int geoId2, double* pointparam, bool driving = true);
    int addTangentLineAtBSplineKnotConstraint(int checkedlinegeoId, int checkedbsplinegeoId, int checkedknotgeoid);
    int addTangentLineEndpointAtBSplineKnotConstraint(
        int checkedlinegeoId,
        PointPos endpointPos,
        int checkedbsplinegeoId,
        int checkedknotgeoid
    );
    int addSnellsLawConstraint(
        int geoIdRay1,
        PointPos posRay1,
        int geoIdRay2,
        PointPos posRay2,
        int geoIdBnd,
        double* value,
        double* second,
        bool driving = true
    );
    int addInternalAlignmentEllipseMajorDiameter(int geoId1, int geoId2);
    int addInternalAlignmentEllipseMinorDiameter(int geoId1, int geoId2);
    int addInternalAlignmentEllipseFocus1(int geoId1, int geoId2);
    int addInternalAlignmentEllipseFocus2(int geoId1, int geoId2);
    int addInternalAlignmentHyperbolaMajorDiameter(int geoId1, int geoId2);
    int addInternalAlignmentHyperbolaMinorDiameter(int geoId1, int geoId2);
    int addInternalAlignmentHyperbolaFocus(int geoId1, int geoId2);
    int addInternalAlignmentParabolaFocus(int geoId1, int geoId2);
    int addInternalAlignmentParabolaFocalDistance(int geoId1, int geoId2);
    int addInternalAlignmentBSplineControlPoint(int geoId1, int geoId2, int poleindex);
    int addInternalAlignmentKnotPoint(int geoId1, int geoId2, int knotindex);

    double calculateAngleViaPoint(int geoId1, int geoId2, double px, double py);
    double calculateAngleViaParams(int geoId1, int geoId2, double param1, double param2);

    int getGeometrySize() const
    {
        return Geoms.size();
    }

    enum GeoType
    {
        None = 0,
        Point = 1,    // 1 Point(start), 2 Parameters(x,y)
        Line = 2,     // 2 Points(start,end), 4 Parameters(x1,y1,x2,y2)
        Arc = 3,      // 3 Points(start,end,mid), (4)+5 Parameters((x1,y1,x2,y2),x,y,r,a1,a2)
        Circle = 4,   // 1 Point(mid), 3 Parameters(x,y,r)
        Ellipse = 5,  // 1 Point(mid), 5 Parameters(x,y,r1,r2,phi)
                      // phi=angle xaxis of ellipse with respect of sketch xaxis
        ArcOfEllipse = 6,
        ArcOfHyperbola = 7,
        ArcOfParabola = 8,
        BSpline = 9
    };

    GCS::Algorithm defaultSolver;
    GCS::Algorithm defaultSolverRedundant;

    // read access to the constraint values after a solve (non-driving ones are updated)
    struct ConstrDef
    {
        Constraint* constr {};
        bool driving = true;
        double* value {};
        double* secondvalue {};
    };
    const std::vector<ConstrDef>& getConstrDefs() const
    {
        return Constrs;
    }

private:
    bool RecalculateInitialSolutionWhileMovingPoint;
    bool resolveAfterGeometryUpdated;

    struct GeoDef
    {
        Geometry geo {};
        GeoType type = None;
        bool external = false;
        int index = -1;
        int startPointId = -1;
        int midPointId = -1;
        int endPointId = -1;
    };

    std::vector<GeoDef> Geoms;
    std::vector<ConstrDef> Constrs;
    GCS::System GCSsys;
    int ConstraintsCounter;
    std::vector<int> Conflicting;
    std::vector<int> Redundant;
    std::vector<int> PartiallyRedundant;
    std::vector<int> MalformedConstraints;
    std::vector<double*> pDependentParametersList;
    std::vector<std::set<std::pair<int, PointPos>>> pDependencyGroups;
    std::map<double*, std::tuple<int, PointPos, int>> param2geoelement;

    // PlaneGCS orders a subsystem's unknowns by their addresses (std::set<double*> in
    // SubSystem::initialize), and with FullPivLU's Gauss step an under-constrained sketch's
    // solution depends on that order. FreeCAD allocates each parameter with new, so its order is
    // whatever the heap gives; on a fresh heap that is the order of creation. Here the parameters
    // are taken from one block in the order they are made, so the order is always that one.
    std::vector<std::unique_ptr<double[]>> paramPool;
    size_t paramPoolUsed = 0, paramPoolSize = 0;
    double* newParam(double value);
    void reserveParams(size_t count);

    std::vector<double*> Parameters;        // with memory allocation
    std::vector<double*> DrivenParameters;  // with memory allocation
    std::vector<double*> FixParameters;     // with memory allocation

    std::vector<double> MoveParameters, InitParameters;

    std::vector<GCS::Point> Points;
    std::vector<GCS::Line> Lines;
    std::vector<GCS::Arc> Arcs;
    std::vector<GCS::Circle> Circles;
    std::vector<GCS::Ellipse> Ellipses;
    std::vector<GCS::ArcOfEllipse> ArcsOfEllipse;
    std::vector<GCS::ArcOfHyperbola> ArcsOfHyperbola;
    std::vector<GCS::ArcOfParabola> ArcsOfParabola;
    std::vector<GCS::BSpline> BSplines;

    // InternalAlignment constraints: the aligned geometry's geoId -> its parent's geoId
    std::map<int, int> internalAlignmentGeometryMap;
    void buildInternalAlignmentGeometryMap(const std::vector<Constraint*>& constraintList);

    bool isInitMove;
    Vec initToPoint;
    double moveStep;

    GCS::DebugMode debugMode;

    bool updateGeometry();
    void updateGeometry(GeoDef&);
    void updatePoint(GeoDef&);
    void updateLineSegment(GeoDef&);
    void updateArcOfCircle(GeoDef&);
    void updateCircle(GeoDef&);
    void updateArcOfEllipse(GeoDef&);
    void updateArcOfHyperbola(GeoDef&);
    void updateArcOfParabola(GeoDef&);
    void updateEllipse(GeoDef&);
    void updateBSpline(GeoDef&);
    bool updateNonDrivingConstraints();
    void calculateDependentParametersElements();
    void clearTemporaryConstraints();
    GCS::SolveStatus internalSolve(std::string& solvername, int level = 0);

    int checkGeoId(int geoId) const;
    GCS::Curve* getGCSCurveByGeoId(int geoId);

    int addPoint(const Geometry& point, bool fixed = false);
    int addLineSegment(const Geometry& lineSegment, bool fixed = false);
    int addArc(const Geometry& circleSegment, bool fixed = false);
    int addCircle(const Geometry& circle, bool fixed = false);
    int addEllipse(const Geometry& ellipse, bool fixed = false);
    int addArcOfEllipse(const Geometry& ellipseSegment, bool fixed = false);
    int addArcOfHyperbola(const Geometry& hyperbolaSegment, bool fixed = false);
    int addArcOfParabola(const Geometry& parabolaSegment, bool fixed = false);
    int addBSpline(const Geometry& spline, bool fixed = false);

    bool analyseBlockedGeometry(
        const std::vector<Geometry>& internalGeoList,
        const std::vector<Constraint*>& constraintList,
        std::vector<bool>& onlyblockedGeometry,
        std::vector<int>& blockedGeoIds
    ) const;
    bool analyseBlockedConstraintDependentParameters(
        std::vector<int>& blockedGeoIds,
        std::vector<double*>& params_to_block
    ) const;
    void fixParametersAndDiagnose(std::vector<double*>& params_to_block);
};

// FreeCAD's SketchSolveStatus (SketchAnalysis.h): what SketchObject.solve() returns.
enum class SketchSolveStatus : int
{
    Success = 0,
    Overconstrained = -4,
    ConflictingConstraints = -3,
    MalformedConstraints = -5,
    SolverError = -1,
    RedundantConstraints = -2,
    InvalidGeometry = -6,
};

// The part of SketchObject that holds a sketch's Geometry and Constraints properties and drives
// the solver, as SketchObject::solve() and SketchObject::moveGeometries() do. The axes are its
// external geometry: geoId -1 is the H axis (0,0)-(1,0), -2 the V axis (0,0)-(0,1); the root point
// is (-1, start).
class SketchDoc
{
public:
    SketchDoc();

    // SketchObject::addGeometry (the construction flag is in the geometry)
    int addGeometry(const Geometry& geo);
    // SketchObject::addConstraints: AutoLockTangencyAndPerpty, setOrientation and the Block state
    // are applied to each new constraint against the current geometry. Returns false (and adds
    // nothing) if a constraint has invalid indices (SketchObject::evaluateConstraint).
    bool addConstraints(const std::vector<Constraint>& constraints);

    SketchSolveStatus solve(bool updateGeoAfterSolving = true);
    SketchSolveStatus moveGeometries(const std::vector<GeoElementId>& geoEltIds, Vec toPoint, bool relative = false);

    // Temporary moves, as the Sketcher's view provider drags (initTemporaryMove /
    // moveGeometriesTemporary): the Geometry property is not updated.
    int initTemporaryMove(const std::vector<GeoElementId>& geoEltIds);
    GCS::SolveStatus moveGeometriesTemporary(const std::vector<GeoElementId>& geoEltIds, Vec toPoint, bool relative = false);

    std::vector<Sketcher::Geometry> geometry;     // the Geometry property (internal geometry)
    std::vector<Sketcher::Geometry> externalGeo;  // the ExternalGeo property: [H axis, V axis, ...]
    std::vector<Constraint> constraints;          // the Constraints property

    Sketch solvedSketch;
    int lastDoF = 0;
    bool lastHasConflict = false;
    bool lastHasRedundancies = false;
    bool lastHasPartialRedundancies = false;
    bool lastHasMalformedConstraints = false;
    GCS::SolveStatus lastSolverStatus = GCS::SolveStatus::Failed;
    std::vector<int> lastConflicting;
    std::vector<int> lastRedundant;
    std::vector<int> lastPartiallyRedundant;
    std::vector<int> lastMalformedConstraints;
    bool solverNeedsUpdate = true;
    bool FullyConstrained = false;

    std::vector<Sketcher::Geometry> getCompleteGeometry() const;
    const Sketcher::Geometry* getGeometry(int geoId) const;
    Vec getPoint(int geoId, PointPos pos) const;
    int getExternalGeometryCount() const
    {
        return externalGeo.size();
    }

private:
    std::vector<Constraint*> constraintPointers();
    void retrieveSolverDiagnostics();
    bool evaluateConstraint(const Constraint& c) const;
    bool AutoLockTangencyAndPerpty(Constraint* cstr);
    void setOrientation(Constraint* constr);
    void setOrientationDistance(Constraint* constr);
    void setOrientationTangent(Constraint* constr);
    double calculateAngleViaPoint(int geoId1, int geoId2, double px, double py);
};

}  // namespace Sketcher
