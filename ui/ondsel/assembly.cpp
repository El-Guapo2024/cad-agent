// SPDX-License-Identifier: LGPL-2.1-or-later
//
// Port of FreeCAD 3160daf1e2b6's src/Mod/Assembly/App/AssemblyObject.cpp and AssemblyUtils.cpp
// (Copyright (c) 2023 Ondsel <development@ondsel.com>) and of src/Base/Rotation.cpp, Placement.cpp and
// Vector3D.cpp (Copyright (c) 2005 Jürgen Riegel, Werner Mayer), over the OndselSolver they drive
// (ui/ondsel/upstream, unchanged). assembly.h says what is in and what is out. Each function keeps
// FreeCAD's name and order of operations, so the ASMT system built here is the one FreeCAD builds:
// the same parts, markers and joints, added in the same order, with the same numbers.

#include "assembly.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <limits>
#include <numbers>
#include <sstream>
#include <unordered_set>
#if !defined(__EMSCRIPTEN__)
#include <unistd.h>
#endif

#include <OndselSolver/CREATE.h>
#include <OndselSolver/ASMTAssembly.h>
#include <OndselSolver/ASMTMarker.h>
#include <OndselSolver/ASMTPart.h>
#include <OndselSolver/ASMTPrincipalMassMarker.h>
#include <OndselSolver/ASMTJoint.h>
#include <OndselSolver/ASMTAngleJoint.h>
#include <OndselSolver/ASMTFixedJoint.h>
#include <OndselSolver/ASMTGearJoint.h>
#include <OndselSolver/ASMTRevoluteJoint.h>
#include <OndselSolver/ASMTCylindricalJoint.h>
#include <OndselSolver/ASMTTranslationalJoint.h>
#include <OndselSolver/ASMTSphericalJoint.h>
#include <OndselSolver/ASMTParallelAxesJoint.h>
#include <OndselSolver/ASMTPerpendicularJoint.h>
#include <OndselSolver/ASMTPointInPlaneJoint.h>
#include <OndselSolver/ASMTPointInLineJoint.h>
#include <OndselSolver/ASMTLineInPlaneJoint.h>
#include <OndselSolver/ASMTPlanarJoint.h>
#include <OndselSolver/ASMTRevCylJoint.h>
#include <OndselSolver/ASMTCylSphJoint.h>
#include <OndselSolver/ASMTRackPinionJoint.h>
#include <OndselSolver/ASMTRotationLimit.h>
#include <OndselSolver/ASMTTranslationLimit.h>
#include <OndselSolver/ASMTScrewJoint.h>
#include <OndselSolver/ASMTSphSphJoint.h>
#include <OndselSolver/ExternalSystem.h>
#include <OndselSolver/System.h>
#include <OndselSolver/Joint.h>
#include <OndselSolver/Constraint.h>
#include <OndselSolver/FullColumn.h>

using namespace MbD;

namespace Asm
{

namespace
{
// OCCT's Precision::Confusion(), which AssemblyObject.cpp uses
constexpr double Confusion = 1.e-7;
constexpr double VecEpsilon = std::numeric_limits<double>::epsilon();

double toRadians(double d)
{
    return d / 180.0 * std::numbers::pi;
}
double toDegrees(double r)
{
    return r / std::numbers::pi * 180.0;
}
}  // namespace

// ── Base::Vector3d ──────────────────────────────────────────────────────────────────────────────

double Vec::length() const
{
    return std::sqrt(x * x + y * y + z * z);
}

Vec& Vec::normalize()
{
    double fLen = length();
    if (fLen != 0.0 && fLen != 1.0) {
        x /= fLen;
        y /= fLen;
        z /= fLen;
    }
    return *this;
}

double Vec::getAngle(const Vec& o) const
{
    double len1 = length();
    double len2 = o.length();
    if (len1 <= VecEpsilon || len2 <= VecEpsilon) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    double dot = (*this) * o;
    dot /= len1;
    dot /= len2;
    if (dot <= -1.0) {
        return std::numbers::pi;
    }
    if (dot >= 1.0) {
        return 0.0;
    }
    return std::acos(dot);
}

bool Vec::isEqual(const Vec& o, double tol) const
{
    return (*this - o).length() <= tol;
}

// ── Base::Rotation ──────────────────────────────────────────────────────────────────────────────

Rotation::Rotation(double q0, double q1, double q2, double q3)
{
    setValue(q0, q1, q2, q3);
}

Rotation::Rotation(const Vec& ax, double fAngle)
{
    axis = Vec {0.0, 0.0, 1.0};
    setValue(ax, fAngle);
}

void Rotation::evaluateVector()
{
    if ((quat[3] > -1.0) && (quat[3] < 1.0)) {
        double rfAngle = std::acos(quat[3]) * 2.0;
        double scale = std::sin(rfAngle / 2.0);
        double l = axis.length();
        if (l < VecEpsilon) {
            l = 1;
        }
        axis.x = quat[0] * l / scale;
        axis.y = quat[1] * l / scale;
        axis.z = quat[2] * l / scale;
        angle = rfAngle;
    }
    else {
        axis = Vec {0.0, 0.0, 1.0};
        angle = 0.0;
    }
}

void Rotation::setValue(double q0, double q1, double q2, double q3)
{
    quat[0] = q0;
    quat[1] = q1;
    quat[2] = q2;
    quat[3] = q3;
    normalize();
    evaluateVector();
}

void Rotation::setValue(const Vec& ax, double fAngle)
{
    using std::numbers::pi;
    angle = fAngle;
    double theAngle = fAngle - std::floor(fAngle / (2.0 * pi)) * (2.0 * pi);
    quat[3] = std::cos(theAngle / 2.0);

    Vec norm = ax;
    norm.normalize();
    double l = norm.length();
    if (l > 0.5) {
        axis = ax;
    }
    else {
        norm = axis;
        norm.normalize();
    }
    double scale = std::sin(theAngle / 2.0);
    quat[0] = norm.x * scale;
    quat[1] = norm.y * scale;
    quat[2] = norm.z * scale;
}

void Rotation::normalize()
{
    double len = std::sqrt(quat[0] * quat[0] + quat[1] * quat[1] + quat[2] * quat[2] + quat[3] * quat[3]);
    if (len > 0.0) {
        quat[0] /= len;
        quat[1] /= len;
        quat[2] /= len;
        quat[3] /= len;
    }
}

Rotation Rotation::inverse() const
{
    Rotation rot;
    rot.quat[0] = -quat[0];
    rot.quat[1] = -quat[1];
    rot.quat[2] = -quat[2];
    rot.quat[3] = quat[3];
    rot.axis = -axis;
    rot.angle = angle;
    return rot;
}

Rotation& Rotation::multRight(const Rotation& q)
{
    double x0 = quat[0], y0 = quat[1], z0 = quat[2], w0 = quat[3];
    double x1 = q.quat[0], y1 = q.quat[1], z1 = q.quat[2], w1 = q.quat[3];
    setValue(
        w0 * x1 + x0 * w1 + y0 * z1 - z0 * y1,
        w0 * y1 - x0 * z1 + y0 * w1 + z0 * x1,
        w0 * z1 + x0 * y1 - y0 * x1 + z0 * w1,
        w0 * w1 - x0 * x1 - y0 * y1 - z0 * z1
    );
    return *this;
}

Rotation Rotation::operator*(const Rotation& q) const
{
    Rotation r(*this);
    r.multRight(q);
    return r;
}

Vec Rotation::multVec(const Vec& src) const
{
    double x = quat[0], y = quat[1], z = quat[2], w = quat[3];
    double x2 = x * x, y2 = y * y, z2 = z * z, w2 = w * w;
    double dx = (x2 + w2 - y2 - z2) * src.x + 2.0 * (x * y - z * w) * src.y + 2.0 * (x * z + y * w) * src.z;
    double dy = 2.0 * (x * y + z * w) * src.x + (w2 - x2 + y2 - z2) * src.y + 2.0 * (y * z - x * w) * src.z;
    double dz = 2.0 * (x * z - y * w) * src.x + 2.0 * (x * w + y * z) * src.y + (w2 - x2 - y2 + z2) * src.z;
    return {dx, dy, dz};
}

void Rotation::getMatrix(double m[3][3]) const
{
    const double l = std::sqrt(quat[0] * quat[0] + quat[1] * quat[1] + quat[2] * quat[2] + quat[3] * quat[3]);
    const double x = quat[0] / l;
    const double y = quat[1] / l;
    const double z = quat[2] / l;
    const double w = quat[3] / l;
    m[0][0] = 1.0 - 2.0 * (y * y + z * z);
    m[0][1] = 2.0 * (x * y - z * w);
    m[0][2] = 2.0 * (x * z + y * w);
    m[1][0] = 2.0 * (x * y + z * w);
    m[1][1] = 1.0 - 2.0 * (x * x + z * z);
    m[1][2] = 2.0 * (y * z - x * w);
    m[2][0] = 2.0 * (x * z - y * w);
    m[2][1] = 2.0 * (y * z + x * w);
    m[2][2] = 1.0 - 2.0 * (x * x + y * y);
}

void Rotation::getYawPitchRoll(double& y, double& p, double& r) const
{
    using std::numbers::pi;
    double q00 = quat[0] * quat[0];
    double q11 = quat[1] * quat[1];
    double q22 = quat[2] * quat[2];
    double q33 = quat[3] * quat[3];
    double q01 = quat[0] * quat[1];
    double q02 = quat[0] * quat[2];
    double q03 = quat[0] * quat[3];
    double q12 = quat[1] * quat[2];
    double q13 = quat[1] * quat[3];
    double q23 = quat[2] * quat[3];
    double qd2 = 2.0 * (q13 - q02);
    constexpr double tolerance = 16 * std::numeric_limits<double>::epsilon();
    if (std::fabs(qd2 - 1.0) <= tolerance) {
        y = 0.0;
        p = pi / 2.0;
        r = 2.0 * std::atan2(quat[0], quat[3]);
    }
    else if (std::fabs(qd2 + 1.0) <= tolerance) {
        y = 0.0;
        p = -pi / 2.0;
        r = 2.0 * std::atan2(quat[0], quat[3]);
    }
    else {
        y = std::atan2(2.0 * (q01 + q23), (q00 + q33) - (q11 + q22));
        p = qd2 > 1.0 ? pi / 2.0 : (qd2 < -1.0 ? -pi / 2.0 : std::asin(qd2));
        r = std::atan2(2.0 * (q12 + q03), (q22 + q33) - (q00 + q11));
    }
    y = toDegrees(y);
    p = toDegrees(p);
    r = toDegrees(r);
}

bool Rotation::isSame(const Rotation& q) const
{
    return (quat[0] == q.quat[0] && quat[1] == q.quat[1] && quat[2] == q.quat[2] && quat[3] == q.quat[3])
        || (quat[0] == -q.quat[0] && quat[1] == -q.quat[1] && quat[2] == -q.quat[2]
            && quat[3] == -q.quat[3]);
}

bool Rotation::isSame(const Rotation& q, double tol) const
{
    double dot = q.quat[0] * quat[0] + q.quat[1] * quat[1] + q.quat[2] * quat[2] + q.quat[3] * quat[3];
    return std::fabs(dot) >= 1.0 - tol / 2;
}

bool Rotation::isIdentity() const
{
    return (quat[0] == 0.0 && quat[1] == 0.0 && quat[2] == 0.0) && (quat[3] == 1.0 || quat[3] == -1.0);
}

// ── Base::Placement ─────────────────────────────────────────────────────────────────────────────

Placement Placement::inverse() const
{
    Placement p(*this);
    p.rot = p.rot.inverse();
    p.pos = p.rot.multVec(p.pos);
    p.pos = -p.pos;
    return p;
}

Placement Placement::operator*(const Placement& p) const
{
    Placement plm(*this);
    Vec tmp = plm.rot.multVec(p.pos);
    plm.pos = plm.pos + tmp;
    plm.rot.multRight(p.rot);
    return plm;
}

bool Placement::isIdentity() const
{
    return pos.x == 0 && pos.y == 0 && pos.z == 0 && rot.isIdentity();
}

bool Placement::isSame(const Placement& p) const
{
    return rot.isSame(p.rot) && pos.isEqual(p.pos, 0);
}

bool Placement::isSame(const Placement& p, double tol) const
{
    return rot.isSame(p.rot, tol) && pos.isEqual(p.pos, tol);
}

// ── names ───────────────────────────────────────────────────────────────────────────────────────

namespace
{
const char* const jointTypeNames[] = {"Fixed", "Revolute", "Cylindrical", "Slider", "Ball",
                                      "Distance", "Parallel", "Perpendicular", "Angle", "RackPinion",
                                      "Screw", "Gears", "Belt"};
}

const char* jointTypeName(JointType t)
{
    return jointTypeNames[int(t)];
}

bool jointTypeFromName(const std::string& s, JointType& t)
{
    for (int i = 0; i < 13; ++i) {
        if (s == jointTypeNames[i]) {
            t = JointType(i);
            return true;
        }
    }
    return false;
}

std::string Ref::elementType() const
{
    std::string out;
    for (char ch : element()) {
        if (std::isalpha(static_cast<unsigned char>(ch))) {
            out += ch;
        }
    }
    return out;
}

Component* Document::part(const std::string& n)
{
    for (auto& p : parts) {
        if (p.name == n) {
            return &p;
        }
    }
    return nullptr;
}

Joint* Document::joint(const std::string& n)
{
    for (auto& j : joints) {
        if (j.name == n) {
            return &j;
        }
    }
    return nullptr;
}

// ── AssemblyUtils.cpp ───────────────────────────────────────────────────────────────────────────

namespace
{
bool getJointActivated(const Joint* joint)
{
    return joint && !joint->suppressed;
}

void setJointActivated(Joint* joint, bool val)
{
    if (joint) {
        joint->suppressed = !val;
    }
}

// isEdgeType / isFaceType: the reference's element is of that BRepAdaptor type
bool isGeom(const Ref& r, const char* type)
{
    return r.geom == type;
}
}  // namespace

void AssemblyObject::swapJCS(Joint* joint)
{
    if (!joint) {
        return;
    }
    std::swap(joint->plc1, joint->plc2);
    std::swap(joint->ref1, joint->ref2);
    if (std::find(swapped.begin(), swapped.end(), joint->name) == swapped.end()) {
        swapped.push_back(joint->name);
    }
    else {
        // swapped twice is not swapped
        swapped.erase(std::find(swapped.begin(), swapped.end(), joint->name));
    }
}

DistanceType AssemblyObject::getDistanceType(Joint* joint)
{
    if (!joint) {
        return DistanceType::Other;
    }
    const std::string type1 = joint->ref1.elementType();
    const std::string type2 = joint->ref2.elementType();
    // obj1/elt1 and obj2/elt2 follow the references through each swap
    auto r1 = [&]() -> const Ref& { return joint->ref1; };
    auto r2 = [&]() -> const Ref& { return joint->ref2; };

    if (type1 == "Vertex" && type2 == "Vertex") {
        return DistanceType::PointPoint;
    }
    else if (type1 == "Edge" && type2 == "Edge") {
        if (isGeom(r1(), "Line") || isGeom(r2(), "Line")) {
            if (!isGeom(r1(), "Line")) {
                swapJCS(joint);  // make sure that line is first if not 2 lines.
            }
            if (isGeom(r2(), "Line")) {
                return DistanceType::LineLine;
            }
            else if (isGeom(r2(), "Circle")) {
                return DistanceType::LineCircle;
            }
        }
        else if (isGeom(r1(), "Circle") || isGeom(r2(), "Circle")) {
            if (!isGeom(r1(), "Circle")) {
                swapJCS(joint);
            }
            if (isGeom(r2(), "Circle")) {
                return DistanceType::CircleCircle;
            }
        }
    }
    else if (type1 == "Face" && type2 == "Face") {
        if (isGeom(r1(), "Plane") || isGeom(r2(), "Plane")) {
            if (!isGeom(r1(), "Plane")) {
                swapJCS(joint);
            }
            if (isGeom(r2(), "Plane")) {
                return DistanceType::PlanePlane;
            }
            else if (isGeom(r2(), "Cylinder")) {
                return DistanceType::PlaneCylinder;
            }
            else if (isGeom(r2(), "Sphere")) {
                return DistanceType::PlaneSphere;
            }
            else if (isGeom(r2(), "Cone")) {
                return DistanceType::PlaneCone;
            }
            else if (isGeom(r2(), "Torus")) {
                return DistanceType::PlaneTorus;
            }
        }
        else if (isGeom(r1(), "Cylinder") || isGeom(r2(), "Cylinder")) {
            if (!isGeom(r1(), "Cylinder")) {
                swapJCS(joint);
            }
            if (isGeom(r2(), "Cylinder")) {
                return DistanceType::CylinderCylinder;
            }
            else if (isGeom(r2(), "Sphere")) {
                return DistanceType::CylinderSphere;
            }
            else if (isGeom(r2(), "Cone")) {
                return DistanceType::CylinderCone;
            }
            else if (isGeom(r2(), "Torus")) {
                return DistanceType::CylinderTorus;
            }
        }
        else if (isGeom(r1(), "Cone") || isGeom(r2(), "Cone")) {
            if (!isGeom(r1(), "Cone")) {
                swapJCS(joint);
            }
            if (isGeom(r2(), "Cone")) {
                return DistanceType::ConeCone;
            }
            else if (isGeom(r2(), "Torus")) {
                return DistanceType::ConeTorus;
            }
            else if (isGeom(r2(), "Sphere")) {
                return DistanceType::ConeSphere;
            }
        }
        else if (isGeom(r1(), "Torus") || isGeom(r2(), "Torus")) {
            if (!isGeom(r1(), "Torus")) {
                swapJCS(joint);
            }
            if (isGeom(r2(), "Torus")) {
                return DistanceType::TorusTorus;
            }
            else if (isGeom(r2(), "Sphere")) {
                return DistanceType::TorusSphere;
            }
        }
        else if (isGeom(r1(), "Sphere") || isGeom(r2(), "Sphere")) {
            if (!isGeom(r1(), "Sphere")) {
                swapJCS(joint);
            }
            if (isGeom(r2(), "Sphere")) {
                return DistanceType::SphereSphere;
            }
        }
    }
    else if ((type1 == "Vertex" && type2 == "Face") || (type1 == "Face" && type2 == "Vertex")) {
        if (type1 == "Vertex") {  // Make sure face is the first.
            swapJCS(joint);
        }
        if (isGeom(r1(), "Plane")) {
            return DistanceType::PointPlane;
        }
        else if (isGeom(r1(), "Cylinder")) {
            return DistanceType::PointCylinder;
        }
        else if (isGeom(r1(), "Sphere")) {
            return DistanceType::PointSphere;
        }
        else if (isGeom(r1(), "Cone")) {
            return DistanceType::PointCone;
        }
        else if (isGeom(r1(), "Torus")) {
            return DistanceType::PointTorus;
        }
    }
    else if ((type1 == "Edge" && type2 == "Face") || (type1 == "Face" && type2 == "Edge")) {
        if (type1 == "Edge") {  // Make sure face is the first.
            swapJCS(joint);
        }
        if (isGeom(r2(), "Line")) {
            if (isGeom(r1(), "Plane")) {
                return DistanceType::LinePlane;
            }
            else if (isGeom(r1(), "Cylinder")) {
                return DistanceType::LineCylinder;
            }
            else if (isGeom(r1(), "Sphere")) {
                return DistanceType::LineSphere;
            }
            else if (isGeom(r1(), "Cone")) {
                return DistanceType::LineCone;
            }
            else if (isGeom(r1(), "Torus")) {
                return DistanceType::LineTorus;
            }
        }
        else {
            if (isGeom(r1(), "Plane")) {
                return DistanceType::CurvePlane;
            }
            else if (isGeom(r1(), "Cylinder")) {
                return DistanceType::CurveCylinder;
            }
            else if (isGeom(r1(), "Sphere")) {
                return DistanceType::CurveSphere;
            }
            else if (isGeom(r1(), "Cone")) {
                return DistanceType::CurveCone;
            }
            else if (isGeom(r1(), "Torus")) {
                return DistanceType::CurveTorus;
            }
        }
    }
    else if ((type1 == "Vertex" && type2 == "Edge") || (type1 == "Edge" && type2 == "Vertex")) {
        if (type1 == "Vertex") {  // Make sure edge is the first.
            swapJCS(joint);
        }
        if (isGeom(r1(), "Line")) {
            return DistanceType::PointLine;
        }
        else {
            return DistanceType::PointCurve;
        }
    }
    return DistanceType::Other;
}

// ── AssemblyObject ──────────────────────────────────────────────────────────────────────────────

AssemblyObject::AssemblyObject(Document d)
    : doc(std::move(d))
{
    lastDoF = int(doc.parts.size()) * 6;
}

AssemblyObject::~AssemblyObject() = default;

Placement AssemblyObject::placementOf(const std::string& obj)
{
    // getPlacementFromProp(obj, "Placement"); the Origin and an unknown object sit at the identity
    if (auto* p = doc.part(obj)) {
        return p->plc;
    }
    return Placement();
}

std::shared_ptr<ASMTAssembly> AssemblyObject::makeMbdAssembly()
{
    auto assembly = CREATE<ASMTAssembly>::With();
    assembly->setName("OndselAssembly");
    assembly->setDebug(doc.logDebug);
    return assembly;
}

int AssemblyObject::solve(bool enableRedo)
{
    solveInProgress = true;
    struct Unlock
    {
        bool& b;
        ~Unlock()
        {
            b = false;
        }
    } unlock {solveInProgress};

    // ensureIdentityPlacements() and syncGroundedJoints(): a component here is never a link group,
    // and its grounded flag is its GroundedJoint.

    mbdAssembly = makeMbdAssembly();
    objectPartMap.clear();
    objectPartOrder.clear();

    auto groundedObjs = fixGroundedParts();
    if (groundedObjs.empty()) {
        // If no part fixed we can't solve.
        return -6;
    }

    std::vector<Joint*> joints = getJoints();

    removeUnconnectedJoints(joints, groundedObjs);

    jointParts(joints);

    if (enableRedo) {
        savePlacementsForUndo();
    }

    try {
        mbdAssembly->runPreDrag();
        lastSolverStatus = 0;
    }
    catch (const std::exception& e) {
        errors.push_back(std::string("Solve failed: ") + e.what());
        lastSolverStatus = -1;
        updateSolveStatus();
        return -1;
    }
    catch (...) {
        errors.push_back("Solve failed: unhandled exception");
        lastSolverStatus = -1;
        updateSolveStatus();
        return -1;
    }

    setNewPlacements();

    updateSolveStatus();

    return 0;
}

void AssemblyObject::updateSolveStatus()
{
    lastRedundantJoints.clear();
    lastHasRedundancies = false;

    int numberOfSolverBodies = int(doc.parts.size());
    if (!objectPartMap.empty()) {
        std::unordered_set<MbD::ASMTPart*> uniqueParts;
        for (const auto& entry : objectPartMap) {
            if (entry.second.part) {
                uniqueParts.insert(entry.second.part.get());
            }
        }
        const int bundledParts = static_cast<int>(objectPartMap.size() - uniqueParts.size());
        numberOfSolverBodies -= bundledParts;
    }

    // +1 because the assembly origin is also represented by a solver body.
    lastDoF = (1 + numberOfSolverBodies) * 6;

    if (!solveInProgress && (!mbdAssembly || !mbdAssembly->mbdSystem)) {
        solve();
    }

    if (!mbdAssembly || !mbdAssembly->mbdSystem) {
        return;
    }

    auto cleanJointName = [](const std::string& rawName) -> std::string {
        size_t hashPos = rawName.find_last_of('#');
        if (hashPos != std::string::npos) {
            return rawName.substr(hashPos + 1);
        }
        return rawName;
    };

    mbdAssembly->mbdSystem->jointsMotionsDo([&](std::shared_ptr<MbD::Joint> jm) {
        if (!jm) {
            return;
        }
        bool isJointRedundant = false;

        jm->constraintsDo([&](std::shared_ptr<MbD::Constraint> con) {
            if (!con) {
                return;
            }
            std::string spec = con->constraintSpec();
            if (spec.rfind("Redundant", 0) == 0) {
                isJointRedundant = true;
            }
            --lastDoF;
        });

        const std::string fullName = cleanJointName(jm->name);
        // We only care about objects that are actual joints in the FreeCAD document.
        Joint* docObj = doc.joint(fullName);
        if (!docObj) {
            return;
        }
        if (isJointRedundant) {
            if (std::find(lastRedundantJoints.begin(), lastRedundantJoints.end(), docObj->name)
                == lastRedundantJoints.end()) {
                lastRedundantJoints.push_back(docObj->name);
            }
        }
    });

    if (!lastRedundantJoints.empty()) {
        lastHasRedundancies = true;
    }
}

void AssemblyObject::preDrag(const std::vector<std::string>& dragParts)
{
    bundleFixed = true;
    bool hasUnconnectedDragPart = std::any_of(dragParts.begin(), dragParts.end(), [this](const std::string& part) {
        return !part.empty() && !isPartConnected(part);
    });

    if (hasUnconnectedDragPart) {
        prepareMbdForIslandDrag(dragParts);
    }
    else {
        solve();
    }
    bundleFixed = false;

    draggedParts.clear();

    for (const auto& part : dragParts) {
        // make sure no duplicate
        if (std::find(draggedParts.begin(), draggedParts.end(), part) != draggedParts.end()) {
            continue;
        }

        // Free-floating parts are ignored by the solver. (FreeCAD keeps an unconnected part that an
        // island drag seeded only when it belongs to a rigid cluster; there are none here.)
        if (!isPartConnected(part)) {
            continue;
        }

        Placement plc;
        if (auto it = objectPartMap.find(part); it != objectPartMap.end()) {
            plc = it->second.offsetPlc;
        }
        if (!plc.isIdentity()) {
            // a bundled object
            continue;
        }

        draggedParts.push_back(part);
    }
}

void AssemblyObject::prepareMbdForIslandDrag(const std::vector<std::string>& dragParts)
{
    mbdAssembly = makeMbdAssembly();
    objectPartMap.clear();
    objectPartOrder.clear();

    auto seededParts = fixGroundedParts();
    for (const auto& part : dragParts) {
        if (!part.empty() && std::find(seededParts.begin(), seededParts.end(), part) == seededParts.end()) {
            seededParts.push_back(part);
        }
    }

    std::vector<Joint*> joints = getJoints();
    removeUnconnectedJoints(joints, seededParts);
    if (joints.empty()) {
        objectPartMap.clear();
        objectPartOrder.clear();
        mbdAssembly.reset();
        return;
    }

    jointParts(joints);

    try {
        mbdAssembly->runPreDrag();
    }
    catch (const std::exception& e) {
        errors.push_back(std::string("Drag setup failed: ") + e.what());
        objectPartMap.clear();
        objectPartOrder.clear();
        mbdAssembly.reset();
    }
    catch (...) {
        errors.push_back("Drag setup failed: unhandled exception");
        objectPartMap.clear();
        objectPartOrder.clear();
        mbdAssembly.reset();
    }
}

void AssemblyObject::doDragStep()
{
    dragFailed = false;
    if (!mbdAssembly || draggedParts.empty()) {
        return;
    }

    try {
        std::vector<std::shared_ptr<MbD::ASMTPart>> dragMbdParts;
        std::unordered_set<ASMTPart*> seenMbdParts;

        for (auto& part : draggedParts) {
            auto mbdPart = getMbDPart(part);
            if (!mbdPart) {
                continue;
            }
            if (!seenMbdParts.insert(mbdPart.get()).second) {
                continue;
            }
            dragMbdParts.push_back(mbdPart);

            Placement plc = placementOf(part);
            if (auto it = objectPartMap.find(part);
                it != objectPartMap.end() && !it->second.offsetPlc.isIdentity()) {
                plc = plc * it->second.offsetPlc.inverse();
            }
            Vec pos = plc.pos;
            mbdPart->updateMbDFromPosition3D(std::make_shared<FullColumn<double>>(ListD {pos.x, pos.y, pos.z}));

            double m[3][3];
            plc.rot.getMatrix(m);
            mbdPart->updateMbDFromRotationMatrix(m[0][0], m[0][1], m[0][2], m[1][0], m[1][1], m[1][2],
                                                 m[2][0], m[2][1], m[2][2]);
        }

        auto dragPartsVec = std::make_shared<std::vector<std::shared_ptr<ASMTPart>>>(dragMbdParts);
        mbdAssembly->runDragStep(dragPartsVec);

        if (validateNewPlacements()) {
            setNewPlacements();
        }
        else {
            dragFailed = true;
        }
    }
    catch (...) {
        // We do nothing if a solve step fails.
        dragFailed = true;
    }
}

Placement AssemblyObject::getMbdPlacement(const std::shared_ptr<ASMTPart>& mbdPart)
{
    if (!mbdPart) {
        return Placement();
    }
    double x, y, z;
    mbdPart->getPosition3D(x, y, z);
    Vec pos {x, y, z};

    double q0, q1, q2, q3;
    mbdPart->getQuarternions(q3, q0, q1, q2);
    Rotation rot(q0, q1, q2, q3);

    return Placement(pos, rot);
}

bool AssemblyObject::validateNewPlacements()
{
    auto groundedParts = getGroundedParts();
    for (const auto& obj : groundedParts) {
        if (!doc.part(obj)) {
            continue;  // the Origin has no Placement property
        }
        Placement oldPlc = placementOf(obj);
        auto it = objectPartMap.find(obj);
        if (it != objectPartMap.end()) {
            Placement newPlacement = getMbdPlacement(it->second.part);
            if (!it->second.offsetPlc.isIdentity()) {
                newPlacement = newPlacement * it->second.offsetPlc;
            }
            if (!oldPlc.isSame(newPlacement, Confusion)) {
                auto* p = doc.part(obj);
                warnings.push_back("Assembly : Ignoring bad solve, a grounded object (" + doc.name + "#"
                                   + (p->label.empty() ? p->name : p->label) + ") moved.");
                return false;
            }
        }
    }
    return true;
}

void AssemblyObject::postDrag()
{
    if (!mbdAssembly) {
        return;
    }
    mbdAssembly->runPostDrag();  // Do this after last drag
}

void AssemblyObject::savePlacementsForUndo()
{
    previousPositions.clear();
    for (const auto& name : objectPartOrder) {
        if (auto* p = doc.part(name)) {
            previousPositions.emplace_back(name, p->plc);
        }
    }
}

void AssemblyObject::undoSolve()
{
    if (previousPositions.empty()) {
        return;
    }
    for (auto& pair : previousPositions) {
        if (auto* p = doc.part(pair.first)) {
            p->plc = pair.second;
        }
    }
    previousPositions.clear();
}

std::string AssemblyObject::exportAsASMT()
{
    mbdAssembly = makeMbdAssembly();
    objectPartMap.clear();
    objectPartOrder.clear();
    fixGroundedParts();

    std::vector<Joint*> joints = getJoints();

    jointParts(joints);

    char path[] = "/tmp/ondsel-asmt-XXXXXX";
    std::string file;
#if defined(__EMSCRIPTEN__)
    file = "/tmp/ondsel.asmt";
#else
    int fd = mkstemp(path);
    if (fd >= 0) {
        close(fd);
    }
    file = path;
#endif
    mbdAssembly->outputFile(file);
    std::ifstream in(file);
    std::stringstream ss;
    ss << in.rdbuf();
    in.close();
    std::remove(file.c_str());
    return ss.str();
}

namespace
{
bool isFinitePlacement(const Placement& plc)
{
    return std::isfinite(plc.pos.x) && std::isfinite(plc.pos.y) && std::isfinite(plc.pos.z)
        && std::isfinite(plc.rot.quat[0]) && std::isfinite(plc.rot.quat[1])
        && std::isfinite(plc.rot.quat[2]) && std::isfinite(plc.rot.quat[3]);
}
}  // namespace

void AssemblyObject::setNewPlacements()
{
    for (const auto& name : objectPartOrder) {
        auto& data = objectPartMap[name];
        auto* obj = doc.part(name);
        if (!obj || !data.part) {
            continue;  // the Origin has no Placement property
        }
        Placement newPlacement = getMbdPlacement(data.part);
        if (!data.offsetPlc.isIdentity()) {
            newPlacement = newPlacement * data.offsetPlc;
        }
        if (!isFinitePlacement(newPlacement)) {
            warnings.push_back("Assembly: solver returned a non-finite placement for '" + doc.fullName(name)
                               + "'; keeping its previous position.");
            continue;
        }
        if (!obj->plc.isSame(newPlacement)) {
            obj->plc = newPlacement;
        }
    }
}

// getGroundedParts: FreeCAD fills an unordered_set<DocumentObject*>, the grounded components in the
// Group's order and then the Origin. For a handful of pointers libstdc++ walks such a set in reverse
// order of insertion, which is the order FreeCAD then fixes them in; that order is used here.
std::vector<std::string> AssemblyObject::getGroundedParts()
{
    std::vector<std::string> inserted;
    for (const auto& p : doc.parts) {
        if (p.grounded) {
            inserted.push_back(p.name);
        }
    }
    inserted.push_back(doc.origin);
    std::reverse(inserted.begin(), inserted.end());
    return inserted;
}

std::vector<std::string> AssemblyObject::fixGroundedParts()
{
    auto groundedParts = getGroundedParts();
    for (const auto& obj : groundedParts) {
        Placement plc = placementOf(obj);
        std::string str = doc.fullName(obj);
        fixGroundedPart(obj, plc, str);
    }
    return groundedParts;
}

void AssemblyObject::fixGroundedPart(const std::string& obj, Placement plc, const std::string& name)
{
    std::string markerName1 = "marker-" + doc.fullName(obj);
    auto mbdMarker1 = makeMbdMarker(markerName1, plc);
    mbdAssembly->addMarker(mbdMarker1);

    std::shared_ptr<ASMTPart> mbdPart = getMbDPart(obj);

    std::string markerName2 = "FixingMarker";
    Placement basePlc;
    auto mbdMarker2 = makeMbdMarker(markerName2, basePlc);
    mbdPart->addMarker(mbdMarker2);

    markerName1 = "/OndselAssembly/" + mbdMarker1->name;
    markerName2 = "/OndselAssembly/" + mbdPart->name + "/" + mbdMarker2->name;

    auto mbdJoint = CREATE<ASMTFixedJoint>::With();
    mbdJoint->setName(name);
    mbdJoint->setMarkerI(markerName1);
    mbdJoint->setMarkerJ(markerName2);

    mbdAssembly->addJoint(mbdJoint);
}

bool AssemblyObject::isJointConnectingPartToGround(const std::string& jointName, const char* propname)
{
    Joint* joint = doc.joint(jointName);
    if (!joint || !isJointTypeConnecting(joint)) {
        return false;
    }
    const std::string part = std::string(propname) == "Reference1" ? joint->ref1.part : joint->ref2.part;
    if (part.empty()) {
        return false;
    }
    if (isPartGrounded(part)) {
        return false;
    }
    if (!isPartConnected(part)) {
        return false;
    }

    // to know if a joint is connecting to ground we disable all the other joints
    std::vector<Joint*> jointsOfPart = getJointsOfPart(part);
    std::vector<bool> activatedStates;
    for (auto* jointi : jointsOfPart) {
        if (jointi->name == joint->name) {
            continue;
        }
        activatedStates.push_back(getJointActivated(jointi));
        setJointActivated(jointi, false);
    }

    bool isConnected = isPartConnected(part);

    for (auto* jointi : jointsOfPart) {
        if (jointi->name == joint->name || activatedStates.empty()) {
            continue;
        }
        setJointActivated(jointi, activatedStates[0]);
        activatedStates.erase(activatedStates.begin());
    }
    return isConnected;
}

bool AssemblyObject::isJointTypeConnecting(const Joint* joint)
{
    if (!joint) {
        return false;
    }
    JointType jointType = joint->type;
    return jointType != JointType::RackPinion && jointType != JointType::Screw
        && jointType != JointType::Gears && jointType != JointType::Belt;
}

std::vector<Joint*> AssemblyObject::getJoints()
{
    std::vector<Joint*> joints;
    for (auto& joint : doc.joints) {
        if (joint.isError || joint.suppressed) {
            continue;
        }
        const std::string& part1 = joint.ref1.part;
        const std::string& part2 = joint.ref2.part;
        if (part1.empty() || part2.empty() || part1 == part2) {
            continue;
        }
        joints.push_back(&joint);
    }
    return joints;
}

std::vector<Joint*> AssemblyObject::getJointsOfPart(const std::string& part)
{
    std::vector<Joint*> jointsOf;
    for (auto* joint : getJoints()) {
        if (part == joint->ref1.part || part == joint->ref2.part) {
            jointsOf.push_back(joint);
        }
    }
    return jointsOf;
}

void AssemblyObject::removeUnconnectedJoints(std::vector<Joint*>& joints, const std::vector<std::string>& grounded)
{
    std::vector<std::string> connectedParts(grounded.begin(), grounded.end());
    for (const auto& g : grounded) {
        traverseAndMarkConnectedParts(g, connectedParts, joints);
    }
    auto has = [&](const std::string& o) {
        return std::find(connectedParts.begin(), connectedParts.end(), o) != connectedParts.end();
    };
    joints.erase(std::remove_if(joints.begin(), joints.end(),
                                [&](Joint* joint) { return !has(joint->ref1.part) || !has(joint->ref2.part); }),
                 joints.end());
}

void AssemblyObject::traverseAndMarkConnectedParts(const std::string& current, std::vector<std::string>& connected,
                                                   const std::vector<Joint*>& joints)
{
    for (auto& next : getConnectedParts(current, joints)) {
        if (std::find(connected.begin(), connected.end(), next) == connected.end()) {
            connected.push_back(next);
            traverseAndMarkConnectedParts(next, connected, joints);
        }
    }
}

std::vector<std::string> AssemblyObject::getConnectedParts(const std::string& part, const std::vector<Joint*>& joints)
{
    std::vector<std::string> connectedParts;
    for (auto* joint : joints) {
        if (!isJointTypeConnecting(joint)) {
            continue;
        }
        const std::string& obj1 = joint->ref1.part;
        const std::string& obj2 = joint->ref2.part;
        if (obj1.empty() || obj2.empty()) {
            continue;
        }
        if (obj1 == part) {
            connectedParts.push_back(obj2);
        }
        else if (obj2 == part) {
            connectedParts.push_back(obj1);
        }
    }
    return connectedParts;
}

bool AssemblyObject::isPartGrounded(const std::string& obj)
{
    auto g = getGroundedParts();
    return std::find(g.begin(), g.end(), obj) != g.end();
}

bool AssemblyObject::isPartConnected(const std::string& obj)
{
    auto groundedObjs = getGroundedParts();
    std::vector<Joint*> joints = getJoints();
    std::vector<std::string> connectedParts(groundedObjs.begin(), groundedObjs.end());
    for (const auto& g : groundedObjs) {
        traverseAndMarkConnectedParts(g, connectedParts, joints);
    }
    return std::find(connectedParts.begin(), connectedParts.end(), obj) != connectedParts.end();
}

std::vector<std::string> AssemblyObject::getDownstreamParts(const std::string& part, const std::string& jointName)
{
    Joint* joint = doc.joint(jointName);
    bool state = false;
    if (joint) {
        state = getJointActivated(joint);
        setJointActivated(joint, false);
    }

    std::vector<Joint*> joints = getJoints();
    std::vector<std::string> connectedParts = {part};
    traverseAndMarkConnectedParts(part, connectedParts, joints);

    std::vector<std::string> downstreamParts;
    for (auto& parti : connectedParts) {
        if (!isPartConnected(parti) && parti != part) {
            downstreamParts.push_back(parti);
        }
    }

    if (joint) {
        setJointActivated(joint, state);
    }
    return downstreamParts;
}

void AssemblyObject::jointParts(const std::vector<Joint*>& joints)
{
    for (auto* joint : joints) {
        for (auto& mbdJoint : makeMbdJoint(joint)) {
            mbdAssembly->addJoint(mbdJoint);
        }
    }
}

std::shared_ptr<ASMTJoint> AssemblyObject::makeMbdJointOfType(Joint* joint, JointType type)
{
    switch (type) {
        case JointType::Fixed:
            if (bundleFixed) {
                return nullptr;
            }
            return CREATE<ASMTFixedJoint>::With();

        case JointType::Revolute:
            return CREATE<ASMTRevoluteJoint>::With();

        case JointType::Cylindrical:
            return CREATE<ASMTCylindricalJoint>::With();

        case JointType::Slider:
            return CREATE<ASMTTranslationalJoint>::With();

        case JointType::Ball:
            return CREATE<ASMTSphericalJoint>::With();

        case JointType::Distance:
            return makeMbdJointDistance(joint);

        case JointType::Parallel:
            return CREATE<ASMTParallelAxesJoint>::With();

        case JointType::Perpendicular:
            return CREATE<ASMTPerpendicularJoint>::With();

        case JointType::Angle: {
            double angle = std::fabs(toRadians(joint->angle));
            if (std::fmod(angle, 2 * std::numbers::pi) < Confusion) {
                return CREATE<ASMTParallelAxesJoint>::With();
            }
            auto mbdJoint = CREATE<ASMTAngleJoint>::With();
            mbdJoint->theIzJz = angle;
            return mbdJoint;
        }

        case JointType::RackPinion: {
            auto mbdJoint = CREATE<ASMTRackPinionJoint>::With();
            mbdJoint->pitchRadius = joint->distance;
            return mbdJoint;
        }

        case JointType::Screw: {
            int slidingIndex = slidingPartIndex(joint);
            if (slidingIndex == 0) {  // invalid this joint needs a slider
                return nullptr;
            }
            if (slidingIndex != 1) {
                swapJCS(joint);  // make sure that sliding is first.
            }
            auto mbdJoint = CREATE<ASMTScrewJoint>::With();
            mbdJoint->pitch = joint->distance;
            return mbdJoint;
        }

        case JointType::Gears: {
            auto mbdJoint = CREATE<ASMTGearJoint>::With();
            mbdJoint->radiusI = joint->distance;
            mbdJoint->radiusJ = joint->distance2;
            return mbdJoint;
        }

        case JointType::Belt: {
            auto mbdJoint = CREATE<ASMTGearJoint>::With();
            mbdJoint->radiusI = joint->distance;
            mbdJoint->radiusJ = -joint->distance2;
            return mbdJoint;
        }

        default:
            return nullptr;
    }
}

std::shared_ptr<ASMTJoint> AssemblyObject::makeMbdJointDistance(Joint* joint)
{
    DistanceType type = getDistanceType(joint);
    // elt1/obj1 and elt2/obj2 are read after the swap getDistanceType may have made
    const double r1 = joint->ref1.radius;
    const double r2 = joint->ref2.radius;
    auto edgeRadius = [](const Ref& r) { return r.geom == "Circle" ? r.radius : 0.0; };
    auto faceRadius = [](const Ref& r) {
        return (r.geom == "Cylinder" || r.geom == "Sphere") ? r.radius : 0.0;
    };
    (void)r1;
    (void)r2;

    switch (type) {
        case DistanceType::PointPoint: {
            double distance = joint->distance;
            if (distance < Confusion) {
                return CREATE<ASMTSphericalJoint>::With();
            }
            auto mbdJoint = CREATE<ASMTSphSphJoint>::With();
            mbdJoint->distanceIJ = distance;
            return mbdJoint;
        }
        case DistanceType::LineLine: {
            auto mbdJoint = CREATE<ASMTRevCylJoint>::With();
            mbdJoint->distanceIJ = joint->distance;
            return mbdJoint;
        }
        case DistanceType::LineCircle: {
            auto mbdJoint = CREATE<ASMTRevCylJoint>::With();
            mbdJoint->distanceIJ = joint->distance + edgeRadius(joint->ref2);
            return mbdJoint;
        }
        case DistanceType::CircleCircle: {
            auto mbdJoint = CREATE<ASMTRevCylJoint>::With();
            mbdJoint->distanceIJ = joint->distance + edgeRadius(joint->ref1) + edgeRadius(joint->ref2);
            return mbdJoint;
        }
        case DistanceType::PlanePlane: {
            auto mbdJoint = CREATE<ASMTPlanarJoint>::With();
            mbdJoint->offset = joint->distance;
            return mbdJoint;
        }
        case DistanceType::PlaneCylinder: {
            auto mbdJoint = CREATE<ASMTLineInPlaneJoint>::With();
            mbdJoint->offset = joint->distance + faceRadius(joint->ref2);
            return mbdJoint;
        }
        case DistanceType::PlaneSphere: {
            auto mbdJoint = CREATE<ASMTPointInPlaneJoint>::With();
            mbdJoint->offset = joint->distance + faceRadius(joint->ref2);
            return mbdJoint;
        }
        case DistanceType::PlaneTorus: {
            auto mbdJoint = CREATE<ASMTPlanarJoint>::With();
            mbdJoint->offset = joint->distance;
            return mbdJoint;
        }
        case DistanceType::CylinderCylinder: {
            auto mbdJoint = CREATE<ASMTRevCylJoint>::With();
            mbdJoint->distanceIJ = joint->distance + faceRadius(joint->ref1) + faceRadius(joint->ref2);
            return mbdJoint;
        }
        case DistanceType::CylinderSphere: {
            auto mbdJoint = CREATE<ASMTCylSphJoint>::With();
            mbdJoint->distanceIJ = joint->distance + faceRadius(joint->ref1) + faceRadius(joint->ref2);
            return mbdJoint;
        }
        case DistanceType::CylinderTorus: {
            auto mbdJoint = CREATE<ASMTRevCylJoint>::With();
            mbdJoint->distanceIJ = joint->distance + faceRadius(joint->ref1) + faceRadius(joint->ref2);
            return mbdJoint;
        }
        case DistanceType::TorusTorus: {
            auto mbdJoint = CREATE<ASMTPlanarJoint>::With();
            mbdJoint->offset = joint->distance;
            return mbdJoint;
        }
        case DistanceType::TorusSphere: {
            auto mbdJoint = CREATE<ASMTCylSphJoint>::With();
            mbdJoint->distanceIJ = joint->distance + faceRadius(joint->ref1) + faceRadius(joint->ref2);
            return mbdJoint;
        }
        case DistanceType::SphereSphere: {
            auto mbdJoint = CREATE<ASMTSphSphJoint>::With();
            mbdJoint->distanceIJ = joint->distance + faceRadius(joint->ref1) + faceRadius(joint->ref2);
            return mbdJoint;
        }
        case DistanceType::PointPlane: {
            auto mbdJoint = CREATE<ASMTPointInPlaneJoint>::With();
            mbdJoint->offset = joint->distance;
            return mbdJoint;
        }
        case DistanceType::PointCylinder: {
            auto mbdJoint = CREATE<ASMTCylSphJoint>::With();
            mbdJoint->distanceIJ = joint->distance + faceRadius(joint->ref1);
            return mbdJoint;
        }
        case DistanceType::PointSphere: {
            auto mbdJoint = CREATE<ASMTSphSphJoint>::With();
            mbdJoint->distanceIJ = joint->distance + faceRadius(joint->ref1);
            return mbdJoint;
        }
        case DistanceType::LinePlane: {
            auto mbdJoint = CREATE<ASMTLineInPlaneJoint>::With();
            mbdJoint->offset = joint->distance;
            return mbdJoint;
        }
        case DistanceType::PointLine: {
            auto mbdJoint = CREATE<ASMTCylSphJoint>::With();
            mbdJoint->distanceIJ = joint->distance;
            return mbdJoint;
        }
        case DistanceType::PointCurve: {
            auto mbdJoint = CREATE<ASMTPointInPlaneJoint>::With();
            mbdJoint->offset = joint->distance;
            return mbdJoint;
        }
        default: {
            auto mbdJoint = CREATE<ASMTPlanarJoint>::With();
            mbdJoint->offset = joint->distance;
            return mbdJoint;
        }
    }
}

namespace
{
bool axesAreCoaxial(const Placement& plc1, const Placement& plc2)
{
    Vec axis1 = plc1.rot.multVec(Vec {0, 0, 1});
    Vec axis2 = plc2.rot.multVec(Vec {0, 0, 1});
    if (axis1.length() <= Confusion || axis2.length() <= Confusion) {
        return false;
    }
    axis1.normalize();
    axis2.normalize();
    if (1.0 - std::abs(axis1 * axis2) > Confusion) {
        return false;
    }
    const Vec delta = plc2.pos - plc1.pos;
    return delta.cross(axis1).length() <= Confusion;
}

bool isRotationCarrierJoint(JointType type)
{
    return type == JointType::Revolute || type == JointType::Cylindrical;
}
}  // namespace

bool AssemblyObject::findRotationCarrierForGearSide(Joint* gearJoint, int gearSide, Joint*& carrier, int& carrierSide)
{
    const Ref& gearRef = gearSide == 1 ? gearJoint->ref1 : gearJoint->ref2;
    if (gearRef.part.empty()) {
        return false;
    }
    // getJointSideGlobalPlacement: getGlobalPlacement(ref) * Placement
    const Placement gearPlc = placementOf(gearRef.part) * (gearSide == 1 ? gearJoint->plc1 : gearJoint->plc2);
    bool foundCarrier = false;
    bool ambiguousCarrier = false;

    for (auto* joint : getJoints()) {
        if (joint == gearJoint || !getJointActivated(joint)) {
            continue;
        }
        if (!isRotationCarrierJoint(joint->type)) {
            continue;
        }
        auto matchesSide = [&](int movingSide, int otherSide) {
            const Ref& movingRef = movingSide == 1 ? joint->ref1 : joint->ref2;
            if (movingRef.part != gearRef.part) {
                return false;
            }
            const Placement rotationPlc = placementOf(movingRef.part) * (movingSide == 1 ? joint->plc1 : joint->plc2);
            if (!axesAreCoaxial(gearPlc, rotationPlc)) {
                return false;
            }
            if (foundCarrier) {
                ambiguousCarrier = true;
                return false;
            }
            foundCarrier = true;
            carrier = joint;
            carrierSide = otherSide;
            return true;
        };
        matchesSide(1, 2);
        matchesSide(2, 1);
    }
    return foundCarrier && !ambiguousCarrier;
}

void AssemblyObject::setGearJointCarrierMarkerIfAvailable(Joint* joint, const std::shared_ptr<ASMTJoint>& mbdJoint)
{
    auto gearJoint = std::dynamic_pointer_cast<ASMTGearJoint>(mbdJoint);
    if (!gearJoint) {
        return;
    }
    Joint *side1 = nullptr, *side2 = nullptr;
    int carrierSide1 = 0, carrierSide2 = 0;
    const bool hasCarrier1 = findRotationCarrierForGearSide(joint, 1, side1, carrierSide1);
    const bool hasCarrier2 = findRotationCarrierForGearSide(joint, 2, side2, carrierSide2);
    if (!hasCarrier1 || !hasCarrier2) {
        return;
    }
    const std::string& carrierPart1 = carrierSide1 == 1 ? side1->ref1.part : side1->ref2.part;
    const std::string& carrierPart2 = carrierSide2 == 1 ? side2->ref1.part : side2->ref2.part;
    if (carrierPart1.empty() || carrierPart2.empty()) {
        return;
    }
    auto carrierMbd1 = getMbDPart(carrierPart1);
    auto carrierMbd2 = getMbDPart(carrierPart2);
    if (carrierMbd1 != carrierMbd2) {
        return;
    }
    const std::string carrierMarkerName = doc.fullName(joint->name) + "-Carrier";
    std::string fullMarkerNameK = handleOneSideOfJoint(side1, carrierSide1, carrierMarkerName);
    if (!fullMarkerNameK.empty()) {
        gearJoint->setMarkerK(fullMarkerNameK);
    }
}

namespace
{
// Gears/Belt need a carrier marker when both sides' axes coincide (gearJointNeedsCarrierMarker)
}

std::vector<std::shared_ptr<MbD::ASMTJoint>> AssemblyObject::makeMbdJoint(Joint* joint)
{
    if (!joint) {
        return {};
    }
    JointType jointType = joint->type;

    std::shared_ptr<ASMTJoint> mbdJoint = makeMbdJointOfType(joint, jointType);
    if (!mbdJoint || !isMbDJointValid(joint)) {
        return {};
    }
    if (jointType == JointType::Gears || jointType == JointType::Belt) {
        const Placement plc1 = placementOf(joint->ref1.part) * joint->plc1;
        const Placement plc2 = placementOf(joint->ref2.part) * joint->plc2;
        if (axesAreCoaxial(plc1, plc2)) {
            setGearJointCarrierMarkerIfAvailable(joint, mbdJoint);
        }
    }

    std::string fullMarkerNameI, fullMarkerNameJ;
    if (jointType == JointType::RackPinion) {
        getRackPinionMarkers(joint, fullMarkerNameI, fullMarkerNameJ);
    }
    else {
        fullMarkerNameI = handleOneSideOfJoint(joint, 1);
        fullMarkerNameJ = handleOneSideOfJoint(joint, 2);
    }
    if (fullMarkerNameI.empty() || fullMarkerNameJ.empty()) {
        return {};
    }

    const std::string fullName = doc.fullName(joint->name);
    mbdJoint->setName(fullName);
    mbdJoint->setMarkerI(fullMarkerNameI);
    mbdJoint->setMarkerJ(fullMarkerNameJ);

    // Add limits if needed (no simulation motions here).
    if (jointType == JointType::Slider || jointType == JointType::Cylindrical) {
        bool minEnabled = joint->enableLengthMin;
        bool maxEnabled = joint->enableLengthMax;
        double minLength = joint->lengthMin;
        double maxLength = joint->lengthMax;
        if ((minLength > maxLength) && minEnabled && maxEnabled) {
            joint->lengthMin = maxLength;
            joint->lengthMax = minLength;
            minLength = maxLength;
            maxLength = joint->lengthMax;
            joint->enableLengthMin = maxEnabled;
            joint->enableLengthMax = minEnabled;
            minEnabled = maxEnabled;
            maxEnabled = joint->enableLengthMax;
        }
        if (minEnabled) {
            auto limit = ASMTTranslationLimit::With();
            limit->setName(fullName + "-LimitLenMin");
            limit->setMarkerI(fullMarkerNameI);
            limit->setMarkerJ(fullMarkerNameJ);
            limit->settype("=>");
            limit->setlimit(std::to_string(minLength));
            limit->settol("1.0e-9");
            mbdAssembly->addLimit(limit);
        }
        if (maxEnabled) {
            auto limit2 = ASMTTranslationLimit::With();
            limit2->setName(fullName + "-LimitLenMax");
            limit2->setMarkerI(fullMarkerNameI);
            limit2->setMarkerJ(fullMarkerNameJ);
            limit2->settype("=<");
            limit2->setlimit(std::to_string(maxLength));
            limit2->settol("1.0e-9");
            mbdAssembly->addLimit(limit2);
        }
    }
    if (jointType == JointType::Revolute || jointType == JointType::Cylindrical) {
        bool minEnabled = joint->enableAngleMin;
        bool maxEnabled = joint->enableAngleMax;
        double minAngle = joint->angleMin;
        double maxAngle = joint->angleMax;
        if ((minAngle > maxAngle) && minEnabled && maxEnabled) {
            joint->angleMin = maxAngle;
            joint->angleMax = minAngle;
            minAngle = maxAngle;
            maxAngle = joint->angleMax;
            joint->enableAngleMin = maxEnabled;
            joint->enableAngleMax = minEnabled;
            minEnabled = maxEnabled;
            maxEnabled = joint->enableAngleMax;
        }
        if (minEnabled) {
            auto limit = ASMTRotationLimit::With();
            limit->setName(fullName + "-LimitRotMin");
            limit->setMarkerI(fullMarkerNameI);
            limit->setMarkerJ(fullMarkerNameJ);
            limit->settype("=>");
            limit->setlimit(std::to_string(minAngle) + "*pi/180.0");
            limit->settol("1.0e-9");
            mbdAssembly->addLimit(limit);
        }
        if (maxEnabled) {
            auto limit2 = ASMTRotationLimit::With();
            limit2->setName(fullName + "-LimitRotMax");
            limit2->setMarkerI(fullMarkerNameI);
            limit2->setMarkerJ(fullMarkerNameJ);
            limit2->settype("=<");
            limit2->setlimit(std::to_string(maxAngle) + "*pi/180.0");
            limit2->settol("1.0e-9");
            mbdAssembly->addLimit(limit2);
        }
    }
    return {mbdJoint};
}

std::string AssemblyObject::handleOneSideOfJoint(Joint* joint, int side, const std::string& markerName)
{
    const Ref& ref = side == 1 ? joint->ref1 : joint->ref2;
    const std::string& part = ref.part;
    if (part.empty()) {
        warnings.push_back(std::string("The property ") + (side == 1 ? "Reference1" : "Reference2")
                           + " of Joint " + doc.fullName(joint->name) + " is bad.");
        return "";
    }

    MbDPartData data = getMbDData(part);
    std::shared_ptr<ASMTPart> mbdPart = data.part;
    Placement plc = side == 1 ? joint->plc1 : joint->plc2;
    // The JCS placement is relative to the Object, not to the containing Part: a component is its
    // own object here, so its global placement is applied and taken off again, as FreeCAD does.
    Placement obj_global_plc = placementOf(part);
    plc = obj_global_plc * plc;
    Placement part_global_plc = placementOf(part);
    plc = part_global_plc.inverse() * plc;

    if (!data.offsetPlc.isIdentity()) {
        plc = data.offsetPlc * plc;
    }

    std::string markerNameCopy = markerName.empty() ? doc.fullName(joint->name) : markerName;
    auto mbdMarker = makeMbdMarker(markerNameCopy, plc);
    mbdPart->addMarker(mbdMarker);

    return "/OndselAssembly/" + mbdPart->name + "/" + markerNameCopy;
}

void AssemblyObject::getRackPinionMarkers(Joint* joint, std::string& markerNameI, std::string& markerNameJ)
{
    int slidingIndex = slidingPartIndex(joint);
    if (slidingIndex == 0) {
        return;
    }
    if (slidingIndex != 1) {
        swapJCS(joint);  // make sure that rack is first.
    }

    const std::string part1 = joint->ref1.part;
    Placement plc1 = joint->plc1;
    const std::string obj2 = joint->ref2.part;
    Placement plc2 = joint->plc2;

    if (part1.empty()) {
        warnings.push_back("Reference1 of Joint " + doc.fullName(joint->name) + " is bad.");
        return;
    }

    // For the pinion nothing special needed :
    markerNameJ = handleOneSideOfJoint(joint, 2);

    // For the rack we need to change the placement :
    // make the pinion plc relative to the rack placement.
    Placement pinion_global_plc = placementOf(obj2);
    plc2 = pinion_global_plc * plc2;
    Placement rack_global_plc = placementOf(part1);
    plc2 = rack_global_plc.inverse() * plc2;

    // The rot of the rack placement should be the same as the pinion, but with X axis along the
    // slider axis.
    Rotation rot = plc2.rot;
    Vec currentZAxis = rot.multVec(Vec {0, 0, 1});
    Vec currentXAxis = rot.multVec(Vec {1, 0, 0});
    Vec targetXAxis = plc1.rot.multVec(Vec {0, 0, 1});

    double yawAdjustment = currentXAxis.getAngle(targetXAxis);
    Vec crossProd = currentXAxis.cross(targetXAxis);
    if (currentZAxis * crossProd < 0) {
        yawAdjustment = -yawAdjustment;
    }
    Rotation yawRotation(currentZAxis, yawAdjustment);
    Rotation adjustedRotation = rot * yawRotation;
    plc1.rot = adjustedRotation;

    MbDPartData data1 = getMbDData(part1);
    std::shared_ptr<ASMTPart> mbdPart = data1.part;
    // obj1 is part1 here, so the obj != part adjustment does not apply
    if (!data1.offsetPlc.isIdentity()) {
        plc1 = data1.offsetPlc * plc1;
    }

    std::string markerName = doc.fullName(joint->name);
    auto mbdMarker = makeMbdMarker(markerName, plc1);
    mbdPart->addMarker(mbdMarker);

    markerNameI = "/OndselAssembly/" + mbdPart->name + "/" + markerName;
}

int AssemblyObject::slidingPartIndex(Joint* joint)
{
    const std::string part1 = joint->ref1.part;
    const Placement plc1 = joint->plc1;
    const std::string part2 = joint->ref2.part;
    const Placement plc2 = joint->plc2;

    int slidingFound = 0;
    for (auto* jt : getJoints()) {
        if (jt->type == JointType::Slider) {
            const std::string& jpart1 = jt->ref1.part;
            const std::string& jpart2 = jt->ref2.part;
            int found = 0;
            Placement plcjt, plci;
            if (jpart1 == part1 || jpart1 == part2) {
                found = (jpart1 == part1) ? 1 : 2;
                plci = (jpart1 == part1) ? plc1 : plc2;
                plcjt = jt->plc1;
            }
            else if (jpart2 == part1 || jpart2 == part2) {
                found = (jpart2 == part1) ? 1 : 2;
                plci = (jpart2 == part1) ? plc1 : plc2;
                plcjt = jt->plc2;
            }

            if (found != 0) {
                double y1, p1, r1, y2, p2, r2;
                plcjt.rot.getYawPitchRoll(y1, p1, r1);
                plci.rot.getYawPitchRoll(y2, p2, r2);
                if (std::fabs(p1 - p2) < Confusion && std::fabs(r1 - r2) < Confusion) {
                    slidingFound = found;
                }
            }
        }
    }
    return slidingFound;
}

bool AssemblyObject::isMbDJointValid(Joint* joint)
{
    const std::string& part1 = joint->ref1.part;
    const std::string& part2 = joint->ref2.part;
    if (part1.empty() || part2.empty()) {
        return false;
    }
    // FreeCAD writes getMbDPart(part1) == getMbDPart(part2), whose operands C++ may evaluate in either order;
    // each call can create its part, and FreeCAD's build (as its exportAsASMT shows) creates part1's first.
    auto mbdPart1 = getMbDPart(part1);
    auto mbdPart2 = getMbDPart(part2);
    if (mbdPart1 == mbdPart2) {
        warnings.push_back("Assembly: Ignoring joint (" + doc.name + "#"
                           + (joint->label.empty() ? joint->name : joint->label)
                           + ") because its parts are connected by a fixed joint bundle. This joint is a "
                             "conflicting or redundant constraint.");
        return false;
    }
    return true;
}

MbDPartData AssemblyObject::getMbDData(const std::string& part)
{
    auto it = objectPartMap.find(part);
    if (it != objectPartMap.end()) {
        return it->second;
    }

    std::string str = doc.fullName(part);
    Placement plc = placementOf(part);
    std::shared_ptr<ASMTPart> mbdPart = makeMbdPart(str, plc);
    mbdAssembly->addPart(mbdPart);
    MbDPartData data = {mbdPart, Placement()};
    objectPartMap[part] = data;
    objectPartOrder.push_back(part);

    // Associate other objects connected with fixed joints
    if (bundleFixed) {
        std::function<void(const std::string&)> addConnectedFixedParts = [&](const std::string& currentPart) {
            for (auto* joint : getJointsOfPart(currentPart)) {
                if (joint->type == JointType::Fixed) {
                    const std::string& part1 = joint->ref1.part;
                    const std::string& part2 = joint->ref2.part;
                    const std::string partToAdd = currentPart == part1 ? part2 : part1;
                    if (objectPartMap.find(partToAdd) != objectPartMap.end()) {
                        continue;
                    }
                    Placement plci = placementOf(partToAdd);
                    MbDPartData partData = {mbdPart, plc.inverse() * plci};
                    objectPartMap[partToAdd] = partData;
                    objectPartOrder.push_back(partToAdd);
                    addConnectedFixedParts(partToAdd);
                }
            }
        };
        addConnectedFixedParts(part);
    }
    return data;
}

std::shared_ptr<ASMTPart> AssemblyObject::getMbDPart(const std::string& part)
{
    if (part.empty()) {
        return nullptr;
    }
    return getMbDData(part).part;
}

std::shared_ptr<ASMTPart> AssemblyObject::makeMbdPart(const std::string& name, Placement plc, double mass)
{
    auto mbdPart = CREATE<ASMTPart>::With();
    mbdPart->setName(name);

    auto massMarker = CREATE<ASMTPrincipalMassMarker>::With();
    massMarker->setMass(mass);
    massMarker->setDensity(1.0);
    massMarker->setMomentOfInertias(1.0, 1.0, 1.0);
    mbdPart->setPrincipalMassMarker(massMarker);

    Vec pos = plc.pos;
    mbdPart->setPosition3D(pos.x, pos.y, pos.z);

    double m[3][3];
    plc.rot.getMatrix(m);
    mbdPart->setRotationMatrix(m[0][0], m[0][1], m[0][2], m[1][0], m[1][1], m[1][2], m[2][0], m[2][1], m[2][2]);
    return mbdPart;
}

std::shared_ptr<ASMTMarker> AssemblyObject::makeMbdMarker(const std::string& name, const Placement& plc)
{
    auto mbdMarker = CREATE<ASMTMarker>::With();
    mbdMarker->setName(name);

    Vec pos = plc.pos;
    mbdMarker->setPosition3D(pos.x, pos.y, pos.z);

    double m[3][3];
    plc.rot.getMatrix(m);
    mbdMarker->setRotationMatrix(m[0][0], m[0][1], m[0][2], m[1][0], m[1][1], m[1][2], m[2][0], m[2][1], m[2][2]);
    return mbdMarker;
}

}  // namespace Asm
