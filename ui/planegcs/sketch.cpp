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

Vec Geometry::getStartPoint() const
{
    if (kind == LineSegment) {
        // ElCLib::LineValue: U * D + P
        return {u1 * dir.x + p.x, u1 * dir.y + p.y};
    }
    // ElCLib::CircleValue with XDir (1,0,0), YDir (0,1,0)
    double A1 = r * std::cos(u1);
    double A2 = r * std::sin(u1);
    return {A1 * 1.0 + A2 * 0.0 + p.x, A1 * 0.0 + A2 * 1.0 + p.y};
}

Vec Geometry::getEndPoint() const
{
    if (kind == LineSegment) {
        return {u2 * dir.x + p.x, u2 * dir.y + p.y};
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
    resolveAfterGeometryUpdated = false;

    // deleting the doubles allocated with new
    for (auto param : Parameters) {
        delete param;
    }
    Parameters.clear();
    DrivenParameters.clear();
    for (auto fixParam : FixParameters) {
        delete fixParam;
    }
    FixParameters.clear();

    param2geoelement.clear();
    pDependencyGroups.clear();

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

int Sketch::setUpSketch(
    const std::vector<Geometry>& GeoList,
    const std::vector<Constraint*>& ConstraintList,
    int extGeoCount
)
{
    clear();

    // (Group and Text constraints, whose geometry the solver ignores, are not ported.)

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

    addGeometry(intGeoList, onlyBlockedGeometry);
    int extStart = Geoms.size();
    addGeometry(extGeoList, true);
    int extEnd = Geoms.size() - 1;
    for (int i = extStart; i <= extEnd; i++) {
        Geoms[i].external = true;
    }

    // The Geoms list might be empty after an undo/redo
    if (!Geoms.empty()) {
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

int Sketch::addPoint(const Geometry& point, bool fixed)
{
    std::vector<double*>& params = fixed ? FixParameters : Parameters;

    // create the definition struct for that geom
    GeoDef def;
    def.geo = point;
    def.type = Point;

    // set the parameter for the solver
    params.push_back(new double(point.getPoint().x));
    params.push_back(new double(point.getPoint().y));

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

    params.push_back(new double(start.x));
    params.push_back(new double(start.y));
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];

    params.push_back(new double(end.x));
    params.push_back(new double(end.y));
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

    params.push_back(new double(startPnt.x));
    params.push_back(new double(startPnt.y));
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];

    params.push_back(new double(endPnt.x));
    params.push_back(new double(endPnt.y));
    p2.x = params[params.size() - 2];
    p2.y = params[params.size() - 1];

    params.push_back(new double(center.x));
    params.push_back(new double(center.y));
    p3.x = params[params.size() - 2];
    p3.y = params[params.size() - 1];

    def.startPointId = Points.size();
    Points.push_back(p1);
    def.endPointId = Points.size();
    Points.push_back(p2);
    def.midPointId = Points.size();
    Points.push_back(p3);

    params.push_back(new double(radius));
    double* r = params[params.size() - 1];
    params.push_back(new double(startAngle));
    double* a1 = params[params.size() - 1];
    params.push_back(new double(endAngle));
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

    params.push_back(new double(center.x));
    params.push_back(new double(center.y));
    p1.x = params[params.size() - 2];
    p1.y = params[params.size() - 1];

    params.push_back(new double(radius));

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
        c.value = new double(constraint->getValue());
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
            // (the B-spline branch is not ported)
            rtn = addPointOnObjectConstraint(constraint->First, constraint->FirstPos, constraint->Second);
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
            // (the B-spline knot tangency branch is not ported)
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
        // (InternalAlignment, SnellsLaw, Group and Text are not ported: malformed here)
        case InternalAlignment:
        case SnellsLaw:
        case Text:
        case Group:
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
    }
    else if (Geoms[geoId1].type == Circle) {
        GCS::Circle& c = Circles[Geoms[geoId1].index];
        if (Geoms[geoId2].type == Circle) {
            GCS::Circle& c2 = Circles[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(c, c2, tag);
            return ConstraintsCounter;
        }
        else if (Geoms[geoId2].type == Arc) {
            GCS::Arc& a = Arcs[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(c, a, tag);
            return ConstraintsCounter;
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
        else if (Geoms[geoId2].type == Arc) {
            GCS::Arc& a2 = Arcs[Geoms[geoId2].index];
            int tag = ++ConstraintsCounter;
            GCSsys.addConstraintTangent(a, a2, tag);
            return ConstraintsCounter;
        }
    }

    return -1;
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
    // (the B-spline branches are not ported)
    if (e2c) {
        // increases ConstraintsCounter
        tag = Sketch::addPointOnObjectConstraint(geoId1, pos1, geoId2, driving);
        GCSsys.addConstraintAngleViaPoint(*crv1, *crv2, p, angle, tag, driving);
    }
    if (e2e) {
        tag = ++ConstraintsCounter;
        GCSsys.addConstraintP2PCoincident(p, *p2, tag, driving);
        GCSsys.addConstraintAngleViaPoint(*crv1, *crv2, p, angle, tag, driving);
    }
    if (avp) {
        tag = ++ConstraintsCounter;
        GCSsys.addConstraintAngleViaPoint(*crv1, *crv2, p, angle, tag, driving);
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
    else if (it.type == Circle) {
        updateCircle(it);
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
    // (captureGroupStates/applyGroupTransformations act on Group/Text constraints only, which are
    // not ported.)
    std::string solvername;

    auto result = internalSolve(solvername);

    return result;
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
    for (size_t k = 0; k < geoEltIds.size(); ++k) {
        reserveSize += 6;  // 6 is the max for all other cases.
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
            else if (Geoms[geoId].type == Circle) {
                if (pos == PointPos::mid || pos == PointPos::none) {
                    MoveParameters[i] = toPoint.x;
                    MoveParameters[i + 1] = toPoint.y;
                    i += 2;
                }
            }
            else if (Geoms[geoId].type == Arc) {
                MoveParameters[i] = toPoint.x;
                MoveParameters[i + 1] = toPoint.y;
                i += 2;
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

        // addGeometryState: Block marks its geometry blocked (internal geometry only)
        if (cnew.Type == Block && cnew.First >= 0 && cnew.First < int(geometry.size())) {
            geometry[cnew.First].blocked = true;
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
        int i1 = sk.addGeometry(*p1);
        int i2 = sk.addGeometry(*p2);
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
            // (the B-spline knot check is not ported)
            if (!getGeometry(cstr->First)) {
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
            // the blocked state lives in the geometry (GeometryFacade); keep it as the property's
            for (size_t i = 0; i < geomlist.size() && i < geometry.size(); ++i) {
                geomlist[i].blocked = geometry[i].blocked;
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
