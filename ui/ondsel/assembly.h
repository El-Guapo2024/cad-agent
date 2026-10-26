// SPDX-License-Identifier: LGPL-2.1-or-later
//
// The Assembly workbench's solver side, ported from FreeCAD 3160daf1e2b6:
//   src/Mod/Assembly/App/AssemblyObject.cpp (Copyright (c) 2023 Ondsel <development@ondsel.com>):
//     solve(), updateSolveStatus(), preDrag()/doDragStep()/postDrag(), the grounding, the connectivity
//     walk, makeMbdJoint*/handleOneSideOfJoint/getRackPinionMarkers/slidingPartIndex, getMbDData with
//     the fixed-joint bundles of a drag, makeMbdPart/makeMbdMarker;
//   src/Mod/Assembly/App/AssemblyUtils.cpp (Copyright (c) 2023 Ondsel): swapJCS, getDistanceType;
//   src/Base/Rotation.cpp, Placement.cpp, Vector3D.cpp (Copyright (c) 2005 Jürgen Riegel, Werner Mayer):
//     the quaternion arithmetic those use, operation for operation.
// What FreeCAD reads from its document (a component's Placement and whether it is grounded, a joint's
// properties, the type of the element a reference names, its radius) comes in as a Document; what the
// solve writes back (placements, the joints whose references it swapped, the solver's status) goes out.
// RigidGroup joints, simulations (motions) and sub-assemblies (AssemblyLink) are not ported.
#pragma once

#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

namespace MbD
{
class ASMTAssembly;
class ASMTPart;
class ASMTMarker;
class ASMTJoint;
}  // namespace MbD

namespace Asm
{

// ── Base::Vector3d, Base::Rotation, Base::Placement (the parts AssemblyObject.cpp uses) ──

struct Vec
{
    double x = 0, y = 0, z = 0;
    Vec operator+(const Vec& o) const
    {
        return {x + o.x, y + o.y, z + o.z};
    }
    Vec operator-(const Vec& o) const
    {
        return {x - o.x, y - o.y, z - o.z};
    }
    Vec operator-() const
    {
        return {-x, -y, -z};
    }
    double operator*(const Vec& o) const  // Dot
    {
        return x * o.x + y * o.y + z * o.z;
    }
    Vec cross(const Vec& o) const
    {
        return {y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x};
    }
    double length() const;
    Vec& normalize();
    double getAngle(const Vec& o) const;
    bool isEqual(const Vec& o, double tol) const;
};

struct Rotation
{
    double quat[4] = {0, 0, 0, 1};  // x, y, z, w
    Vec axis {0, 0, 1};             // Base::Rotation's _axis, kept for setValue(axis, angle)'s fallback
    double angle = 0;

    Rotation() = default;
    Rotation(double q0, double q1, double q2, double q3);
    Rotation(const Vec& ax, double fAngle);
    void setValue(double q0, double q1, double q2, double q3);
    void setValue(const Vec& ax, double fAngle);
    void normalize();
    void evaluateVector();
    Rotation inverse() const;
    Rotation& multRight(const Rotation& q);
    Rotation operator*(const Rotation& q) const;
    Vec multVec(const Vec& src) const;
    void getMatrix(double m[3][3]) const;  // getValue(Matrix4D&), its 3x3 part
    void getYawPitchRoll(double& y, double& p, double& r) const;
    bool isSame(const Rotation& q) const;
    bool isSame(const Rotation& q, double tol) const;
    bool isIdentity() const;
};

struct Placement
{
    Vec pos;
    Rotation rot;
    Placement() = default;
    Placement(const Vec& p, const Rotation& r)
        : pos(p)
        , rot(r)
    {}
    Placement inverse() const;
    Placement operator*(const Placement& p) const;
    bool isIdentity() const;
    bool isSame(const Placement& p) const;
    bool isSame(const Placement& p, double tol) const;
};

// ── what the document holds ──

enum class JointType
{
    Fixed,
    Revolute,
    Cylindrical,
    Slider,
    Ball,
    Distance,
    Parallel,
    Perpendicular,
    Angle,
    RackPinion,
    Screw,
    Gears,
    Belt,
};

enum class DistanceType
{
    PointPoint,
    LineLine,
    LineCircle,
    CircleCircle,
    PlanePlane,
    PlaneCylinder,
    PlaneSphere,
    PlaneCone,
    PlaneTorus,
    CylinderCylinder,
    CylinderSphere,
    CylinderCone,
    CylinderTorus,
    ConeCone,
    ConeTorus,
    ConeSphere,
    TorusTorus,
    TorusSphere,
    SphereSphere,
    PointPlane,
    PointCylinder,
    PointSphere,
    PointCone,
    PointTorus,
    LinePlane,
    LineCylinder,
    LineSphere,
    LineCone,
    LineTorus,
    CurvePlane,
    CurveCylinder,
    CurveSphere,
    CurveCone,
    CurveTorus,
    PointLine,
    PointCurve,
    Other,
};

// A joint's Reference1/2 (PropertyXLinkSub): the component it moves, the element and vertex names,
// and what FreeCAD's AssemblyUtils reads from the element's shape (BRepAdaptor's GetType, the radius).
struct Ref
{
    std::string part;              // the component (getMovingPartFromRef), "" when unset
    std::vector<std::string> subs; // ["Face6", "Vertex8"]
    std::string geom;              // "Plane", "Cylinder", "Sphere", "Cone", "Torus", "Line", "Circle", ...
    double radius = 0;             // getFaceRadius / getEdgeRadius
    std::string element() const    // getElementFromProp: the first sub's last name
    {
        return subs.empty() ? std::string() : subs[0];
    }
    std::string elementType() const;  // getElementTypeFromProp: "Face", "Edge", "Vertex", ""
};

struct Joint
{
    std::string name;
    std::string label;
    JointType type = JointType::Fixed;
    bool suppressed = false;
    bool isError = false;
    Ref ref1, ref2;
    Placement plc1, plc2;
    double distance = 0, distance2 = 0, angle = 0;  // Angle in degrees, as the property
    bool enableLengthMin = false, enableLengthMax = false, enableAngleMin = false,
         enableAngleMax = false;
    double lengthMin = 0, lengthMax = 0, angleMin = 0, angleMax = 0;
};

struct Component
{
    std::string name;
    std::string label;
    Placement plc;
    bool grounded = false;  // its Placement is read-only (a GroundedJoint holds it)
};

struct Document
{
    std::string name = "Unnamed";   // the FreeCAD document's Name: getFullName() is "Doc#Obj"
    std::string origin = "Origin";  // the Assembly's App::Origin
    std::vector<Component> parts;   // getAssemblyComponents, in the Assembly's Group order
    std::vector<Joint> joints;      // the JointGroup's joints (GroundedJoints are the parts' flags)
    bool logDebug = false;

    Component* part(const std::string& n);
    Joint* joint(const std::string& n);
    std::string fullName(const std::string& n) const
    {
        return name + "#" + n;
    }
};

struct MbDPartData
{
    std::shared_ptr<MbD::ASMTPart> part;
    Placement offsetPlc;
};

// AssemblyObject's solver state for one Document. A Document's parts and joints are what the
// FreeCAD document's objects are; solve() and the drag write into them as FreeCAD does.
class AssemblyObject
{
public:
    explicit AssemblyObject(Document d);
    ~AssemblyObject();

    Document doc;

    int solve(bool enableRedo = false);
    void updateSolveStatus();
    void preDrag(const std::vector<std::string>& dragParts);
    void doDragStep();  // the dragged parts' placements are set in doc first, as the view provider does
    void postDrag();
    void undoSolve();
    std::string exportAsASMT();  // exportAsASMT(fileName), the file's text

    // the queries JointObject.py asks the assembly (AssemblyObjectPy)
    bool isPartGrounded(const std::string& obj);
    bool isPartConnected(const std::string& obj);
    bool isJointConnectingPartToGround(const std::string& joint, const char* propname);
    std::vector<std::string> getDownstreamParts(const std::string& part, const std::string& joint);

    // last solve
    int lastDoF = 0;
    bool lastHasRedundancies = false;
    int lastSolverStatus = 0;
    std::vector<std::string> lastRedundantJoints;
    std::vector<std::string> swapped;   // joints whose Reference1/2 a solve swapped (swapJCS)
    std::vector<std::string> warnings;  // Base::Console().warning(...)
    std::vector<std::string> errors;    // FC_ERR
    std::vector<std::string> draggedParts;
    bool dragFailed = false;

private:
    std::shared_ptr<MbD::ASMTAssembly> mbdAssembly;
    std::map<std::string, MbDPartData> objectPartMap;
    std::vector<std::string> objectPartOrder;  // objectPartMap's keys in the order they were added
    std::vector<std::pair<std::string, Placement>> previousPositions;
    bool bundleFixed = false;
    bool solveInProgress = false;

    std::shared_ptr<MbD::ASMTAssembly> makeMbdAssembly();
    void setNewPlacements();
    bool validateNewPlacements();
    Placement getMbdPlacement(const std::shared_ptr<MbD::ASMTPart>& mbdPart);
    void savePlacementsForUndo();
    void prepareMbdForIslandDrag(const std::vector<std::string>& dragParts);

    std::vector<std::string> getGroundedParts();
    std::vector<std::string> fixGroundedParts();
    void fixGroundedPart(const std::string& obj, Placement plc, const std::string& name);
    std::vector<Joint*> getJoints();
    std::vector<Joint*> getJointsOfPart(const std::string& part);
    bool isJointTypeConnecting(const Joint* joint);
    void removeUnconnectedJoints(std::vector<Joint*>& joints, const std::vector<std::string>& grounded);
    void traverseAndMarkConnectedParts(const std::string& current, std::vector<std::string>& connected,
                                       const std::vector<Joint*>& joints);
    std::vector<std::string> getConnectedParts(const std::string& part, const std::vector<Joint*>& joints);
    void jointParts(const std::vector<Joint*>& joints);

    std::shared_ptr<MbD::ASMTJoint> makeMbdJointOfType(Joint* joint, JointType type);
    std::shared_ptr<MbD::ASMTJoint> makeMbdJointDistance(Joint* joint);
    std::vector<std::shared_ptr<MbD::ASMTJoint>> makeMbdJoint(Joint* joint);
    std::string handleOneSideOfJoint(Joint* joint, int side, const std::string& markerName = "");
    void getRackPinionMarkers(Joint* joint, std::string& markerNameI, std::string& markerNameJ);
    int slidingPartIndex(Joint* joint);
    bool isMbDJointValid(Joint* joint);
    void setGearJointCarrierMarkerIfAvailable(Joint* joint, const std::shared_ptr<MbD::ASMTJoint>& mbdJoint);
    bool findRotationCarrierForGearSide(Joint* gearJoint, int gearSide, Joint*& carrier, int& carrierSide);

    MbDPartData getMbDData(const std::string& part);
    std::shared_ptr<MbD::ASMTPart> getMbDPart(const std::string& part);
    std::shared_ptr<MbD::ASMTPart> makeMbdPart(const std::string& name, Placement plc, double mass = 1.0);
    std::shared_ptr<MbD::ASMTMarker> makeMbdMarker(const std::string& name, const Placement& plc);

    Placement placementOf(const std::string& obj);
    void swapJCS(Joint* joint);
    DistanceType getDistanceType(Joint* joint);
};

const char* jointTypeName(JointType t);
bool jointTypeFromName(const std::string& s, JointType& t);

}  // namespace Asm
