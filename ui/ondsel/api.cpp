// SPDX-License-Identifier: LGPL-2.1-or-later
//
// Flat C API over the Assembly solver port (assembly.h), for ctypes (cad_agent/ondsel.py) and for
// WebAssembly (ui/src/ondsel.ts). Documents come in and results go out as JSON strings.
//
// A document is
//   {"document": "Unnamed" (the FreeCAD document's Name), "origin": "Origin" (the Assembly's Origin),
//    "parts": [{"name", "label", "placement": P, "grounded": bool}, ...]     (the components, in order)
//    "joints": [{"name", "label", "type": "Fixed"|"Revolute"|...|"Belt", "suppressed": bool,
//                "reference1": R, "reference2": R, "placement1": P, "placement2": P,
//                "distance", "distance2", "angle" (degrees),
//                "enable_length_min", "enable_length_max", "enable_angle_min", "enable_angle_max",
//                "length_min", "length_max", "angle_min", "angle_max"}, ...],  (the JointGroup's joints)
//    "rigid_groups": [{"name", "suppressed": bool, "members": [part, ...]}, ...]   (its RigidGroupJoints)
//    "rigid_cache": [[part, P], ...]}  (AssemblyObject::rigidPlacementCache, as the last solve left it)
//   P = {"base": [x, y, z], "rotation": [x, y, z, w]} (FreeCAD's Placement: Base and Rotation.Q)
//   R = {"part": name, "subs": ["Face6", "Vertex8"], "geom": "Plane"|"Cylinder"|"Sphere"|"Cone"|"Torus"|
//        "Line"|"Circle"|..., "radius": r, "obj": P}  or null: the component it moves, its element and vertex
//        names, the element's type and radius as AssemblyUtils reads them from the shape, and where the object
//        the element belongs to sits in the component (a child of a rigid sub-assembly, a datum; default identity).
// A result is
//   {"status": solve()'s return (0 solved, -1 failed, -6 nothing grounded), "solver_status",
//    "dof", "redundant": [joint names], "placements": {part: P} (every component),
//    "joints": [the joints as the solve left them: a swap moves Reference1/2 and Placement1/2],
//    "swapped": [joint names], "rigid_cache": [[part, P], ...], "rigid_groups": {group: [members]} (the groups
//    getRigidGroups cleaned), "warnings": [...], "errors": [...], "log": the solver's own output}
//   or {"error": "..."}.
//
// Stateless: ondsel_solve(doc), ondsel_query(doc, op, args) (isPartConnected, isPartGrounded,
// isJointConnectingPartToGround, getDownstreamParts, requiresRigidSolveForMove, getRigidMembers, ...),
// ondsel_export(doc) (exportAsASMT's file).
// For a drag: ondsel_new(doc) -> handle, ondsel_pre_drag(h, ["part", ...]), ondsel_drag_step(h,
// {part: P}) (the view provider's new placements for the dragged parts), ondsel_post_drag(h),
// ondsel_free(h). Returned strings belong to the library and stay valid until the next call.

#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <string>

#include "assembly.h"
#include "json.h"

using namespace Asm;
using AsmJson::Json;
using AsmJson::Parser;
using AsmJson::Writer;

namespace
{

const Json* need(const Json& j, const char* key)
{
    const Json* v = j.get(key);
    if (!v) {
        throw std::invalid_argument(std::string("missing \"") + key + "\"");
    }
    return v;
}

double num(const Json& j, const char* key, double dflt = 0)
{
    const Json* v = j.get(key);
    return v && v->kind != Json::Null ? v->asDouble() : dflt;
}

bool flag(const Json& j, const char* key)
{
    const Json* v = j.get(key);
    return v && v->kind == Json::Bool && v->b;
}

std::string str(const Json& j, const char* key, const std::string& dflt = "")
{
    const Json* v = j.get(key);
    return v && v->kind == Json::String ? v->str : dflt;
}

Placement toPlacement(const Json* j)
{
    Placement p;
    if (!j || j->kind == Json::Null) {
        return p;
    }
    if (const Json* b = j->get("base")) {
        if (b->kind != Json::Array || b->items.size() != 3) {
            throw std::invalid_argument("a placement's base is [x, y, z]");
        }
        p.pos = Vec {b->items[0].asDouble(), b->items[1].asDouble(), b->items[2].asDouble()};
    }
    if (const Json* r = j->get("rotation")) {
        if (r->kind != Json::Array || r->items.size() != 4) {
            throw std::invalid_argument("a placement's rotation is the quaternion [x, y, z, w]");
        }
        p.rot = Rotation(r->items[0].asDouble(), r->items[1].asDouble(), r->items[2].asDouble(),
                         r->items[3].asDouble());
    }
    return p;
}

Ref toRef(const Json* j)
{
    Ref r;
    if (!j || j->kind == Json::Null) {
        return r;
    }
    r.part = str(*j, "part");
    if (const Json* s = j->get("subs")) {
        for (auto& it : s->items) {
            r.subs.push_back(it.str);
        }
    }
    r.geom = str(*j, "geom");
    r.radius = num(*j, "radius");
    r.jcs = toPlacement(j->get("jcs"));
    r.objPlc = toPlacement(j->get("obj"));
    return r;
}

Document toDocument(const Json& j)
{
    Document d;
    d.name = str(j, "document", "Unnamed");
    d.origin = str(j, "origin", "Origin");
    d.logDebug = flag(j, "debug");
    if (const Json* ps = j.get("parts")) {
        for (auto& pj : ps->items) {
            Component c;
            c.name = str(pj, "name");
            c.label = str(pj, "label", c.name);
            c.plc = toPlacement(pj.get("placement"));
            c.grounded = flag(pj, "grounded");
            d.parts.push_back(c);
        }
    }
    if (const Json* js = j.get("joints")) {
        for (auto& jj : js->items) {
            Joint jt;
            jt.name = str(jj, "name");
            jt.label = str(jj, "label", jt.name);
            if (!jointTypeFromName(str(jj, "type", "Fixed"), jt.type)) {
                throw std::invalid_argument(jt.name + ": " + str(jj, "type") + " is not a JointType");
            }
            jt.suppressed = flag(jj, "suppressed");
            jt.isError = flag(jj, "error");
            jt.ref1 = toRef(jj.get("reference1"));
            jt.ref2 = toRef(jj.get("reference2"));
            jt.plc1 = toPlacement(jj.get("placement1"));
            jt.plc2 = toPlacement(jj.get("placement2"));
            jt.offset1 = toPlacement(jj.get("offset1"));
            jt.offset2 = toPlacement(jj.get("offset2"));
            jt.detach1 = flag(jj, "detach1");
            jt.detach2 = flag(jj, "detach2");
            jt.distance = num(jj, "distance");
            jt.distance2 = num(jj, "distance2");
            jt.angle = num(jj, "angle");
            jt.enableLengthMin = flag(jj, "enable_length_min");
            jt.enableLengthMax = flag(jj, "enable_length_max");
            jt.enableAngleMin = flag(jj, "enable_angle_min");
            jt.enableAngleMax = flag(jj, "enable_angle_max");
            jt.lengthMin = num(jj, "length_min");
            jt.lengthMax = num(jj, "length_max");
            jt.angleMin = num(jj, "angle_min");
            jt.angleMax = num(jj, "angle_max");
            d.joints.push_back(jt);
        }
    }
    if (const Json* gs = j.get("rigid_groups")) {
        for (auto& gj : gs->items) {
            RigidGroup g;
            g.name = str(gj, "name");
            g.suppressed = flag(gj, "suppressed");
            g.isError = flag(gj, "error");
            if (const Json* ms = gj.get("members")) {
                for (auto& m : ms->items) {
                    g.members.push_back(m.str);
                }
            }
            d.rigidGroups.push_back(g);
        }
    }
    if (const Json* cs = j.get("rigid_cache")) {
        for (auto& c : cs->items) {
            if (c.kind != Json::Array || c.items.size() != 2) {
                throw std::invalid_argument("a rigid_cache entry is [part, placement]");
            }
            d.rigidPlacementCache.emplace_back(c.items[0].str, toPlacement(&c.items[1]));
        }
    }
    return d;
}

void writePlacement(Writer& w, const Placement& p)
{
    w.out += "{\"base\":[";
    w.num(p.pos.x);
    w.out += ',';
    w.num(p.pos.y);
    w.out += ',';
    w.num(p.pos.z);
    w.out += "],\"rotation\":[";
    for (int k = 0; k < 4; ++k) {
        if (k) {
            w.out += ',';
        }
        w.num(p.rot.quat[k]);
    }
    w.out += "]}";
}

void writeStrings(Writer& w, const std::vector<std::string>& v)
{
    w.out += '[';
    for (size_t k = 0; k < v.size(); ++k) {
        if (k) {
            w.out += ',';
        }
        w.str(v[k]);
    }
    w.out += ']';
}

void writeRef(Writer& w, const Ref& r)
{
    if (r.part.empty() && r.subs.empty()) {
        w.out += "null";
        return;
    }
    w.out += '{';
    w.key("part");
    w.str(r.part);
    w.key("subs");
    writeStrings(w, r.subs);
    w.key("geom");
    w.str(r.geom);
    w.key("radius");
    w.num(r.radius);
    w.out += '}';
}

std::string result(AssemblyObject& a, int status, const std::string& log)
{
    Writer w;
    w.out += '{';
    w.key("status");
    w.integer(status);
    w.key("solver_status");
    w.integer(a.lastSolverStatus);
    w.key("dof");
    w.integer(a.lastDoF);
    w.key("redundant");
    writeStrings(w, a.lastRedundantJoints);
    w.key("placements");
    w.out += '{';
    for (auto& p : a.doc.parts) {
        w.key(p.name.c_str());
        writePlacement(w, p.plc);
    }
    w.out += '}';
    w.key("joints");
    w.out += '[';
    bool first = true;
    for (auto& j : a.doc.joints) {
        if (!first) {
            w.out += ',';
        }
        first = false;
        w.out += '{';
        w.key("name");
        w.str(j.name);
        w.key("reference1");
        writeRef(w, j.ref1);
        w.key("reference2");
        writeRef(w, j.ref2);
        w.key("placement1");
        writePlacement(w, j.plc1);
        w.key("placement2");
        writePlacement(w, j.plc2);
        w.key("enable_length_min");
        w.out += j.enableLengthMin ? "true" : "false";
        w.key("enable_length_max");
        w.out += j.enableLengthMax ? "true" : "false";
        w.key("enable_angle_min");
        w.out += j.enableAngleMin ? "true" : "false";
        w.key("enable_angle_max");
        w.out += j.enableAngleMax ? "true" : "false";
        w.key("length_min");
        w.num(j.lengthMin);
        w.key("length_max");
        w.num(j.lengthMax);
        w.key("angle_min");
        w.num(j.angleMin);
        w.key("angle_max");
        w.num(j.angleMax);
        w.out += '}';
    }
    w.out += ']';
    w.key("swapped");
    writeStrings(w, a.swapped);
    w.key("rigid_cache");
    w.out += '[';
    for (size_t k = 0; k < a.doc.rigidPlacementCache.size(); ++k) {
        if (k) {
            w.out += ',';
        }
        w.out += '[';
        w.str(a.doc.rigidPlacementCache[k].first);
        w.out += ',';
        writePlacement(w, a.doc.rigidPlacementCache[k].second);
        w.out += ']';
    }
    w.out += ']';
    w.key("rigid_groups");
    w.out += '{';
    for (size_t k = 0; k < a.cleanedRigidGroups.size(); ++k) {
        if (k) {
            w.out += ',';
        }
        w.key(a.cleanedRigidGroups[k].first.c_str());
        writeStrings(w, a.cleanedRigidGroups[k].second);
    }
    w.out += '}';
    w.key("dragged");
    writeStrings(w, a.draggedParts);
    w.key("drag_failed");
    w.out += a.dragFailed ? "true" : "false";
    w.key("warnings");
    writeStrings(w, a.warnings);
    w.key("errors");
    writeStrings(w, a.errors);
    w.key("log");
    w.str(log);
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
    static std::string b;
    return b;
}

const char* give(std::string s)
{
    buffer() = std::move(s);
    return buffer().c_str();
}

// The solver writes its progress to std::cout ("MbD: Assembling system. ", "MbD: Convergence = ..."),
// as FreeCAD's report view shows it; it is caught here and returned as "log".
struct Capture
{
    std::ostringstream ss;
    std::streambuf* old;
    Capture()
        : old(std::cout.rdbuf(ss.rdbuf()))
    {}
    ~Capture()
    {
        std::cout.rdbuf(old);
    }
};

template<class F>
const char* guarded(F&& f)
{
    try {
        return give(f());
    }
    catch (const std::exception& e) {
        return give(errorJson(e.what()));
    }
    catch (...) {
        return give(errorJson("unknown error"));
    }
}

std::map<int, std::unique_ptr<AssemblyObject>>& handles()
{
    static std::map<int, std::unique_ptr<AssemblyObject>> h;
    return h;
}

AssemblyObject& handle(int h)
{
    auto it = handles().find(h);
    if (it == handles().end()) {
        throw std::invalid_argument("no such assembly handle");
    }
    return *it->second;
}

void clearMessages(AssemblyObject& a)
{
    a.warnings.clear();
    a.errors.clear();
    a.swapped.clear();
}

}  // namespace

extern "C" {

const char* ondsel_version()
{
    return "OndselSolver 4be80eef02a3 (FreeCAD 3160daf1e2b6)";
}

const char* ondsel_solve(const char* json)
{
    return guarded([&] {
        Json j = Parser(json).parse();
        AssemblyObject a(toDocument(j));
        Capture cap;
        int status = a.solve(flag(j, "enable_redo"));
        return result(a, status, cap.ss.str());
    });
}

const char* ondsel_export(const char* json)
{
    return guarded([&] {
        Json j = Parser(json).parse();
        AssemblyObject a(toDocument(j));
        Capture cap;
        std::string text = a.exportAsASMT();
        (void)cap;
        Writer w;
        w.out += '{';
        w.key("asmt");
        w.str(text);
        w.key("swapped");
        writeStrings(w, a.swapped);
        w.key("warnings");
        writeStrings(w, a.warnings);
        w.out += '}';
        return w.out;
    });
}

const char* ondsel_query(const char* json, const char* op, const char* args)
{
    return guarded([&] {
        Json j = Parser(json).parse();
        Json as = Parser(args).parse();
        AssemblyObject a(toDocument(j));
        std::string o(op);
        auto arg = [&](size_t k) {
            if (as.kind != Json::Array || as.items.size() <= k || as.items[k].kind != Json::String) {
                throw std::invalid_argument(o + ": argument " + std::to_string(k) + " is a name");
            }
            return as.items[k].str;
        };
        Writer w;
        w.out += "{\"value\":";
        if (o == "isPartConnected") {
            w.out += a.isPartConnected(arg(0)) ? "true" : "false";
        }
        else if (o == "isPartGrounded") {
            w.out += a.isPartGrounded(arg(0)) ? "true" : "false";
        }
        else if (o == "isJointConnectingPartToGround") {
            w.out += a.isJointConnectingPartToGround(arg(0), arg(1).c_str()) ? "true" : "false";
        }
        else if (o == "getJointOfPartConnectingToGround" || o == "getJointOfPartForUngroundedDrag") {
            std::string name;
            std::string j = o == "getJointOfPartForUngroundedDrag" ? a.getJointOfPartForUngroundedDrag(arg(0), name)
                                                                    : a.getJointOfPartConnectingToGround(arg(0), name);
            writeStrings(w, {j, name});
        }
        else if (o == "getUpstreamMovingPart") {
            std::string joint = as.items.size() > 1 ? arg(1) : std::string();
            std::string name;
            std::string part = a.getUpstreamMovingPart(arg(0), joint, name);
            writeStrings(w, {part, joint, name});
        }
        else if (o == "getDistanceType") {
            w.str(a.distanceTypeName(arg(0)));
        }
        else if (o == "getDownstreamParts") {
            writeStrings(w, a.getDownstreamParts(arg(0), as.items.size() > 1 ? arg(1) : std::string()));
        }
        else if (o == "requiresRigidSolveForMove") {
            std::vector<std::string> parts;
            for (auto& it : as.items) {
                parts.push_back(it.str);
            }
            w.out += a.requiresRigidSolveForMove(parts) ? "true" : "false";
        }
        else if (o == "getRigidMembers") {
            writeStrings(w, a.getRigidMembersOf(arg(0)));
        }
        else {
            throw std::invalid_argument(o + " is not a query");
        }
        w.out += '}';
        return w.out;
    });
}

static std::string lastError;

int ondsel_new(const char* json)
{
    try {
        Json j = Parser(json).parse();
        static int next = 1;
        int h = next++;
        handles()[h] = std::make_unique<AssemblyObject>(toDocument(j));
        return h;
    }
    catch (const std::exception& e) {
        lastError = e.what();
        return 0;
    }
}

const char* ondsel_last_error()
{
    return lastError.c_str();
}

void ondsel_free(int h)
{
    handles().erase(h);
}

const char* ondsel_handle_solve(int h)
{
    return guarded([&] {
        auto& a = handle(h);
        clearMessages(a);
        Capture cap;
        int status = a.solve();
        return result(a, status, cap.ss.str());
    });
}

const char* ondsel_pre_drag(int h, const char* parts)
{
    return guarded([&] {
        auto& a = handle(h);
        clearMessages(a);
        Json ps = Parser(parts).parse();
        std::vector<std::string> names;
        for (auto& it : ps.items) {
            names.push_back(it.str);
        }
        Capture cap;
        a.preDrag(names);
        return result(a, 0, cap.ss.str());
    });
}

const char* ondsel_drag_step(int h, const char* placements)
{
    return guarded([&] {
        auto& a = handle(h);
        clearMessages(a);
        Json ps = Parser(placements).parse();
        for (size_t k = 0; k < ps.keys.size(); ++k) {
            if (auto* p = a.doc.part(ps.keys[k])) {
                p->plc = toPlacement(&ps.values[k]);
            }
        }
        Capture cap;
        a.doDragStep();
        return result(a, 0, cap.ss.str());
    });
}

// ViewProviderAssembly::tryMouseMove with forceSolveOnMoveForRigid: the dragged parts' new placements, then a full
// solve() (its syncActiveRigidGroupPlacements drags each moved member's group along) instead of doDragStep.
const char* ondsel_rigid_step(int h, const char* placements)
{
    return guarded([&] {
        auto& a = handle(h);
        clearMessages(a);
        Json ps = Parser(placements).parse();
        for (size_t k = 0; k < ps.keys.size(); ++k) {
            if (auto* p = a.doc.part(ps.keys[k])) {
                p->plc = toPlacement(&ps.values[k]);
            }
        }
        Capture cap;
        int status = a.solve();
        return result(a, status, cap.ss.str());
    });
}

const char* ondsel_post_drag(int h)
{
    return guarded([&] {
        auto& a = handle(h);
        clearMessages(a);
        Capture cap;
        a.postDrag();
        return result(a, 0, cap.ss.str());
    });
}

}  // extern "C"
