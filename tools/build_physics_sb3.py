#!/usr/bin/env python3
"""
Builds physics_2d.sb3: an advanced 2D rigid-body physics sandbox for TurboWarp,
rendered entirely with pen and labelled with the existing pen text engine
(claude_text.sb3).

    python3 tools/build_physics_sb3.py            # writes physics_2d.sb3

Everything lives inside the "Text Engine" sprite (as that engine's README
recommends) so the physics, rendering and text share one warp-speed frame.

Engine overview (all of it compiled to Scratch blocks by sb3dsl.py):
  * bodies     circles + convex polygons stored as parallel lists ("b x", "b vx", ...)
  * broadphase sort-and-sweep on x (persistent order list, insertion sort)
  * narrowphase circle/circle, polygon/circle (Voronoi regions),
               polygon/polygon (SAT + reference/incident face clipping, 2 points)
  * solver     sequential impulses (Box2D-lite style) with accumulated-impulse
               clamping, Coulomb friction, restitution, Baumgarte stabilisation
               and warm starting (contacts matched frame-to-frame by feature key)
  * joints     revolute (point) + distance (rod) constraints, soft springs,
               mouse spring (force based)
  * sleeping   union-find islands each substep; an island sleeps when every body
               in it has been still for 0.5 s
Units: 50 px = 1 m, masses in kg (density 1 kg/m²), so metrics read in SI units.
"""
import contextlib
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sb3dsl import (Project, ListRef, Locals, v, l, If, Else, Repeat, RepeatUntil, Forever,  # noqa: E402
                    setvar, changevar, eq, ne, join, sqrt, abs_, floor, sin, cos, round_, rand,
                    mouse_x, mouse_y, mouse_down, timer, clock_ms, key_pressed, pen_up, pen_down,
                    erase_all, pen_size, pen_color, goto, switch_costume, hide, letter, strlen,
                    Lit, Expr)

REPO = os.path.dirname(HERE)
BASE = os.path.join(REPO, "claude_text.sb3")
OUT = os.path.join(REPO, "physics_2d.sb3")

P = Project(BASE, "Text Engine")
proc = P.proc

# ------------------------------------------------------------------ the base
# Drop the text engine's demo/benchmark (its README says they are safe to
# delete) and the stage script that started the demo.
DEMO_HATS = {("event_whenbroadcastreceived", "TE demo"), ("event_whenkeypressed", "space"),
             ("event_whenkeypressed", "b")}


def _is_demo(B, b):
    op = b["opcode"]
    if op == "procedures_definition":
        code = B[b["inputs"]["custom_block"][1]]["mutation"]["proccode"]
        return code.startswith(("_demo", "_bench"))
    if op == "event_whenflagclicked":
        return True          # replaced by our own green-flag script below
    f = b["fields"]
    key = f.get("BROADCAST_OPTION", f.get("KEY_OPTION", [None]))[0]
    return (op, key) in DEMO_HATS


P.remove_scripts(P.sprite, _is_demo)
P.remove_scripts(P.stage, lambda B, b: True)
for t in (P.sprite, P.stage):
    for vid in [k for k, (n, *_r) in t["variables"].items() if n.startswith(("_demo", "_bench"))]:
        del t["variables"][vid]
    for lid in [k for k, (n, *_r) in t["lists"].items() if n.startswith(("_demo", "_bench")) or n == "TE benchmark results"]:
        del t["lists"][lid]
    t["comments"] = {k: c for k, c in t.get("comments", {}).items()
                     if not c["text"].startswith(("DEMO", "BENCHMARK"))}
P.stage["broadcasts"] = {k: n for k, n in P.stage["broadcasts"].items() if n != "TE demo"}

# text engine API (existing custom blocks)
te_draw = P.external_proc("draw text %s at x: %s y: %s")
te_size = P.external_proc("set text size to %s")
te_align = P.external_proc("set text align %s vertical %s")
te_color = P.external_proc("set text color hue: %s brightness: %s")
te_alpha = P.external_proc("set text transparency to %s")
te_reset = P.external_proc("reset text style")

# ------------------------------------------------------------------- storage


class _Lists:
    def __init__(s, prefix):
        s._p = prefix

    def __getattr__(s, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return ListRef(s._p + n)


B = _Lists("b ")     # bodies
VT = _Lists("v ")    # polygon vertices (local + world)
C = _Lists("c ")     # contacts
CO = _Lists("co ")   # previous step's contacts (warm starting)
J = _Lists("j ")     # joints
G = _Lists("g ")     # graph history

BODY_FIELDS = ["type", "x", "y", "a", "vx", "vy", "w", "im", "ii", "m", "i", "imr", "iir", "rest", "fric",
               "r", "v0", "vn", "col", "static", "awake", "sleep", "group", "minx", "maxx", "miny", "maxy",
               "fx", "fy", "t", "pvx", "pvy", "rfx", "rfy", "efx", "efy", "nc", "par", "imin", "isl"]
VERT_FIELDS = ["lx", "ly", "lnx", "lny", "wx", "wy", "wnx", "wny"]
CONTACT_FIELDS = ["a", "b", "nx", "ny", "px", "py", "pen", "key", "rax", "ray", "rbx", "rby",
                  "mn", "mt", "bias", "pn", "pt", "mu"]
JOINT_FIELDS = ["type", "a", "b", "lax", "lay", "lbx", "lby", "len", "freq", "damp", "r1x", "r1y", "r2x",
                "r2y", "m11", "m12", "m22", "bx", "by", "px", "py", "nx", "ny", "mass", "act", "force", "soft"]

PPM = 50                 # pixels per metre
DEG = 180 / math.pi
SLEEP_TIME = 0.5         # s of stillness before an island sleeps
SLEEP_LIN = 6            # px/s
SLEEP_ANG = 0.08         # rad/s
SLOP = 0.6               # px of allowed penetration
BAUMGARTE = 0.2
MAX_BIAS = 300           # px/s cap on position-correction velocity
REST_THRESHOLD = 40      # px/s: slower impacts don't bounce
GRAPH_N = 120

# body types
CIRCLE, POLY, WORLD, DEAD = 0, 1, 2, -1
# joint types
REVOLUTE, DISTANCE, SPRING = 0, 1, 2


@contextlib.contextmanager
def loop(var, n, start=1):
    """var = start, start+1, ... for n iterations."""
    setvar(var, start)
    with Repeat(n):
        yield
        changevar(var, 1)


def clamp_stmt(var, lo, hi):
    with If(var < lo):
        setvar(var, lo)
    with If(var > hi):
        setvar(var, hi)


# ================================================================ geometry

@proc()
def set_mass(i, m, inertia):
    B.m[i] = m
    B.i[i] = inertia
    with If(eq(B.static[i], 1)):
        B.imr[i] = 0
        B.iir[i] = 0
    with Else():
        B.imr[i] = 1 / m
        B.iir[i] = 1 / inertia
    B.im[i] = B.imr[i]
    B.ii[i] = B.iir[i]


@proc()
def new_body(kind, x, y, angle):
    vals = {"type": kind, "x": x, "y": y, "a": angle, "rest": v.mat_rest, "fric": v.mat_fric,
            "col": v.mat_col, "static": v.mat_static, "awake": 1, "group": v.mat_group}
    for f in BODY_FIELDS:
        ListRef("b " + f).add(vals.get(f, 0))
    v.nb = B.type.length
    B.par[v.nb] = v.nb
    with If(ne(kind, WORLD)):
        l["bp order"].add(v.nb)


@proc()
def update_geom(i):
    """World-space vertices, normals and AABB of body i."""
    g = Locals("geom")
    g.ca = cos(B.a[i])
    g.sa = sin(B.a[i])
    g.x = B.x[i]
    g.y = B.y[i]
    with If(eq(B.type[i], CIRCLE)):
        g.r = B.r[i]
        B.minx[i] = g.x - g.r
        B.maxx[i] = g.x + g.r
        B.miny[i] = g.y - g.r
        B.maxy[i] = g.y + g.r
    with Else():
        g.minx = 1e9
        g.maxx = -1e9
        g.miny = 1e9
        g.maxy = -1e9
        with loop(g.k, B.vn[i], B.v0[i]):
            g.lx = VT.lx[g.k]
            g.ly = VT.ly[g.k]
            g.wx = g.x + g.ca * g.lx - g.sa * g.ly
            g.wy = g.y + g.sa * g.lx + g.ca * g.ly
            VT.wx[g.k] = g.wx
            VT.wy[g.k] = g.wy
            VT.wnx[g.k] = g.ca * VT.lnx[g.k] - g.sa * VT.lny[g.k]
            VT.wny[g.k] = g.sa * VT.lnx[g.k] + g.ca * VT.lny[g.k]
            with If(g.wx < g.minx):
                g.minx = g.wx
            with If(g.wx > g.maxx):
                g.maxx = g.wx
            with If(g.wy < g.miny):
                g.miny = g.wy
            with If(g.wy > g.maxy):
                g.maxy = g.wy
        B.minx[i] = g.minx
        B.maxx[i] = g.maxx
        B.miny[i] = g.miny
        B.maxy[i] = g.maxy


@proc()
def add_circle(x, y, r):
    new_body(CIRCLE, x, y, rand(0, 360))
    g = Locals("addc")
    g.i = v.nb
    B.r[g.i] = r
    g.m = v.mat_density * math.pi * r * r / (PPM * PPM)
    set_mass(g.i, g.m, 0.5 * g.m * r * r)
    update_geom(g.i)


@proc()
def add_poly(x, y, angle):
    """Convex polygon from the CCW vertices in 'tmp vx' / 'tmp vy' (any origin).
    The body is placed with its centroid at (x, y)."""
    g = Locals("addp")
    TX, TY = l.tmp_vx, l.tmp_vy
    g.n = TX.length
    g.area = 0
    g.cx = 0
    g.cy = 0
    g.inert = 0
    with loop(g.k, g.n):
        with If(eq(g.k, g.n)):
            g.k2 = 1
        with Else():
            g.k2 = g.k + 1
        g.x1 = TX[g.k]
        g.y1 = TY[g.k]
        g.x2 = TX[g.k2]
        g.y2 = TY[g.k2]
        g.d = g.x1 * g.y2 - g.y1 * g.x2
        g.area = g.area + 0.5 * g.d
        g.cx = g.cx + g.d * (g.x1 + g.x2) / 6
        g.cy = g.cy + g.d * (g.y1 + g.y2) / 6
        g.inert = g.inert + g.d / 12 * (g.x1 * g.x1 + g.x1 * g.x2 + g.x2 * g.x2 +
                                         g.y1 * g.y1 + g.y1 * g.y2 + g.y2 * g.y2)
    g.cx = g.cx / g.area
    g.cy = g.cy / g.area
    new_body(POLY, x, y, angle)
    g.i = v.nb
    B.v0[g.i] = VT.lx.length + 1
    B.vn[g.i] = g.n
    g.r = 0
    with loop(g.k, g.n):
        g.x1 = TX[g.k] - g.cx
        g.y1 = TY[g.k] - g.cy
        VT.lx.add(g.x1)
        VT.ly.add(g.y1)
        for f in ("lnx", "lny", "wx", "wy", "wnx", "wny"):
            ListRef("v " + f).add(0)
        with If(g.x1 * g.x1 + g.y1 * g.y1 > g.r * g.r):
            g.r = sqrt(g.x1 * g.x1 + g.y1 * g.y1)
    B.r[g.i] = g.r
    # outward normals (CCW winding: normal of edge e is (ey, -ex))
    g.s = B.v0[g.i]
    with loop(g.k, g.n, 0):
        g.p = g.s + g.k
        with If(eq(g.k, g.n - 1)):
            g.q = g.s
        with Else():
            g.q = g.p + 1
        g.ex = VT.lx[g.q] - VT.lx[g.p]
        g.ey = VT.ly[g.q] - VT.ly[g.p]
        g.d = sqrt(g.ex * g.ex + g.ey * g.ey)
        VT.lnx[g.p] = g.ey / g.d
        VT.lny[g.p] = 0 - g.ex / g.d
    g.m = v.mat_density * g.area / (PPM * PPM)
    set_mass(g.i, g.m, v.mat_density * g.inert / (PPM * PPM) - g.m * (g.cx * g.cx + g.cy * g.cy))
    update_geom(g.i)


@proc()
def add_box(x, y, w, h, angle):
    l.tmp_vx.clear()
    l.tmp_vy.clear()
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        l.tmp_vx.add(sx * w / 2)
        l.tmp_vy.add(sy * h / 2)
    add_poly(x, y, angle)


@proc()
def add_ngon(x, y, n, radius, jitter):
    """Random convex polygon: n vertices on a circle at jittered (still increasing) angles."""
    g = Locals("ngon")
    l.tmp_vx.clear()
    l.tmp_vy.clear()
    g.base = rand(0, 360)
    with loop(g.k, n, 0):
        g.ang = g.base + 360 * g.k / n + rand(-100, 100) / 100 * jitter * 180 / n
        l.tmp_vx.add(radius * cos(g.ang))
        l.tmp_vy.add(radius * sin(g.ang))
    add_poly(x, y, 0)


@proc()
def to_local(i, wx, wy):
    """World point -> body-local point (into 'lx', 'ly')."""
    g = Locals("tol")
    g.dx = wx - B.x[i]
    g.dy = wy - B.y[i]
    g.c = cos(B.a[i])
    g.s = sin(B.a[i])
    v.lx = g.c * g.dx + g.s * g.dy
    v.ly = g.c * g.dy - g.s * g.dx


# ================================================================== joints

@proc()
def new_joint(kind, a, b, ax, ay, bx, by):
    vals = {"type": kind, "a": a, "b": b, "act": 1}
    for f in JOINT_FIELDS:
        ListRef("j " + f).add(vals.get(f, 0))
    v.nj = J.type.length
    to_local(a, ax, ay)
    J.lax[v.nj] = v.lx
    J.lay[v.nj] = v.ly
    to_local(b, bx, by)
    J.lbx[v.nj] = v.lx
    J.lby[v.nj] = v.ly
    J.len[v.nj] = sqrt((bx - ax) * (bx - ax) + (by - ay) * (by - ay))


@proc()
def add_revolute(a, b, x, y):
    new_joint(REVOLUTE, a, b, x, y, x, y)


@proc()
def add_distance(a, b, ax, ay, bx, by):
    new_joint(DISTANCE, a, b, ax, ay, bx, by)


@proc()
def add_spring(a, b, ax, ay, bx, by, rest, hz, damping):
    new_joint(SPRING, a, b, ax, ay, bx, by)
    J.len[v.nj] = rest
    J.freq[v.nj] = hz
    J.damp[v.nj] = damping


def joint_arms(g, j):
    """Emit: world lever arms r1/r2 and anchor points p1/p2 of joint j into locals of g."""
    g.a = J.a[j]
    g.b = J.b[j]
    g.c = cos(B.a[g.a])
    g.s = sin(B.a[g.a])
    g.r1x = g.c * J.lax[j] - g.s * J.lay[j]
    g.r1y = g.s * J.lax[j] + g.c * J.lay[j]
    g.c = cos(B.a[g.b])
    g.s = sin(B.a[g.b])
    g.r2x = g.c * J.lbx[j] - g.s * J.lby[j]
    g.r2y = g.s * J.lbx[j] + g.c * J.lby[j]
    g.p1x = B.x[g.a] + g.r1x
    g.p1y = B.y[g.a] + g.r1y
    g.p2x = B.x[g.b] + g.r2x
    g.p2y = B.y[g.b] + g.r2y


# =================================================================== forces

@proc()
def apply_forces():
    """External forces for this substep: mouse spring + soft springs."""
    g = Locals("frc")
    with If(v.drag > 0):
        g.d = v.drag
        g.c = cos(B.a[g.d])
        g.s = sin(B.a[g.d])
        g.rx = g.c * v.drag_lx - g.s * v.drag_ly
        g.ry = g.s * v.drag_lx + g.c * v.drag_ly
        v.drag_ax = B.x[g.d] + g.rx
        v.drag_ay = B.y[g.d] + g.ry
        g.vx = B.vx[g.d] - B.w[g.d] * g.ry
        g.vy = B.vy[g.d] + B.w[g.d] * g.rx
        g.m = B.m[g.d]
        # critically-ish damped spring, scaled by mass so every body feels the same
        g.fx = g.m * (v.drag_k * (mouse_x() - v.drag_ax) - v.drag_c * g.vx)
        g.fy = g.m * (v.drag_k * (mouse_y() - v.drag_ay) - v.drag_c * g.vy)
        g.f = sqrt(g.fx * g.fx + g.fy * g.fy)
        g.fmax = g.m * 30000
        with If(g.f > g.fmax):
            g.fx = g.fx * g.fmax / g.f
            g.fy = g.fy * g.fmax / g.f
        B.fx[g.d] = B.fx[g.d] + g.fx
        B.fy[g.d] = B.fy[g.d] + g.fy
        B.t[g.d] = B.t[g.d] + (g.rx * g.fy - g.ry * g.fx)
        v.drag_fx = g.fx
        v.drag_fy = g.fy
    with loop(g.j, J.type.length):
        with If(eq(J.type[g.j], SPRING)):
            joint_arms(g, g.j)
            g.dx = g.p2x - g.p1x
            g.dy = g.p2y - g.p1y
            g.len = sqrt(g.dx * g.dx + g.dy * g.dy)
            with If(g.len > 0.001):
                g.nx = g.dx / g.len
                g.ny = g.dy / g.len
                g.meff = 1 / (B.imr[g.a] + B.imr[g.b])
                g.om = 2 * math.pi * J.freq[g.j]
                g.vr = ((B.vx[g.b] - B.w[g.b] * g.r2y - B.vx[g.a] + B.w[g.a] * g.r1y) * g.nx +
                        (B.vy[g.b] + B.w[g.b] * g.r2x - B.vy[g.a] - B.w[g.a] * g.r1x) * g.ny)
                g.f = g.meff * (g.om * g.om * (g.len - J.len[g.j]) + 2 * J.damp[g.j] * g.om * g.vr)
                J.force[g.j] = abs_(g.f) / PPM
                g.fx = g.f * g.nx
                g.fy = g.f * g.ny
                B.fx[g.a] = B.fx[g.a] + g.fx
                B.fy[g.a] = B.fy[g.a] + g.fy
                B.t[g.a] = B.t[g.a] + (g.r1x * g.fy - g.r1y * g.fx)
                B.fx[g.b] = B.fx[g.b] - g.fx
                B.fy[g.b] = B.fy[g.b] - g.fy
                B.t[g.b] = B.t[g.b] - (g.r2x * g.fy - g.r2y * g.fx)


@proc()
def integrate_velocities(h):
    g = Locals("iv")
    g.gy = 0 - v.gravity * PPM
    g.ld = 1 / (1 + h * v.lin_damping)
    g.ad = 1 / (1 + h * v.ang_damping)
    with loop(g.i, B.type.length):
        with If(B.im[g.i] > 0):
            g.vx = (B.vx[g.i] + h * B.fx[g.i] * B.imr[g.i]) * g.ld
            g.vy = (B.vy[g.i] + h * (g.gy + B.fy[g.i] * B.imr[g.i])) * g.ld
            B.vx[g.i] = g.vx
            B.vy[g.i] = g.vy
            B.w[g.i] = (B.w[g.i] + h * B.t[g.i] * B.iir[g.i]) * g.ad
            B.pvx[g.i] = g.vx
            B.pvy[g.i] = g.vy
            B.efx[g.i] = B.efx[g.i] + B.fx[g.i] / v.substeps
            B.efy[g.i] = B.efy[g.i] + B.fy[g.i] / v.substeps
        B.fx[g.i] = 0
        B.fy[g.i] = 0
        B.t[g.i] = 0


@proc()
def integrate_positions(h):
    g = Locals("ip")
    g.k = 1 / (h * v.substeps)
    with loop(g.i, B.type.length):
        with If(B.im[g.i] > 0):
            g.vx = B.vx[g.i]
            g.vy = B.vy[g.i]
            g.w = B.w[g.i]
            # contact + joint reaction force (what the solver had to apply), frame average
            B.rfx[g.i] = B.rfx[g.i] + B.m[g.i] * (g.vx - B.pvx[g.i]) * g.k
            B.rfy[g.i] = B.rfy[g.i] + B.m[g.i] * (g.vy - B.pvy[g.i]) * g.k
            B.x[g.i] = B.x[g.i] + g.vx * h
            B.y[g.i] = B.y[g.i] + g.vy * h
            B.a[g.i] = (B.a[g.i] + g.w * h * DEG) % 360
            update_geom(g.i)
            with If(((g.vx * g.vx + g.vy * g.vy) < SLEEP_LIN * SLEEP_LIN) &
                    ((g.w * g.w) < SLEEP_ANG * SLEEP_ANG) & ne(g.i, v.drag)):
                B.sleep[g.i] = B.sleep[g.i] + h
            with Else():
                B.sleep[g.i] = 0


# ============================================================== collisions

@proc()
def find_root(x):
    g = Locals("find")
    g.r = x
    with RepeatUntil(eq(B.par[g.r], g.r)):
        B.par[g.r] = B.par[B.par[g.r]]
        g.r = B.par[g.r]
    v.root = g.r


@proc()
def union(a, b):
    find_root(a)
    v.ra = v.root
    find_root(b)
    with If(ne(v.ra, v.root)):
        B.par[v.ra] = v.root


@proc()
def add_contact(a, b, nx, ny, px, py, pen, feature):
    g = Locals("addk")
    with If(a < b):
        g.key = (a * 4096 + b) * 256 + feature
    with Else():
        g.key = (b * 4096 + a) * 256 + feature
    C.a.add(a)
    C.b.add(b)
    C.nx.add(nx)
    C.ny.add(ny)
    C.px.add(px)
    C.py.add(py)
    C.pen.add(pen)
    C.key.add(g.key)
    g.idx = 0
    with If(eq(v.warm, 1)):
        g.idx = CO.key.index(g.key)
    with If(g.idx > 0):
        C.pn.add(CO.pn[g.idx])
        C.pt.add(CO.pt[g.idx])
        v.warm_hits = v.warm_hits + 1
    with Else():
        C.pn.add(0)
        C.pt.add(0)
    for f in ("rax", "ray", "rbx", "rby", "mn", "mt", "bias", "mu"):
        ListRef("c " + f).add(0)
    B.nc[a] = B.nc[a] + 1
    B.nc[b] = B.nc[b] + 1
    with If(pen > v.max_pen):
        v.max_pen = pen


@proc()
def collide_circles(a, b):
    g = Locals("cc")
    g.dx = B.x[b] - B.x[a]
    g.dy = B.y[b] - B.y[a]
    g.r = B.r[a] + B.r[b]
    g.d2 = g.dx * g.dx + g.dy * g.dy
    with If(g.d2 < g.r * g.r):
        g.d = sqrt(g.d2)
        with If(g.d > 0.0001):
            g.nx = g.dx / g.d
            g.ny = g.dy / g.d
        with Else():
            g.nx = 0
            g.ny = 1
        g.pen = g.r - g.d
        g.k = B.r[a] - g.pen / 2
        add_contact(a, b, g.nx, g.ny, B.x[a] + g.nx * g.k, B.y[a] + g.ny * g.k, g.pen, 0)


@proc()
def collide_poly_circle(a, b):
    """a = polygon, b = circle. Normal points from a to b."""
    g = Locals("pc")
    g.cx = B.x[b]
    g.cy = B.y[b]
    g.rad = B.r[b]
    g.s0 = B.v0[a]
    g.n = B.vn[a]
    g.best = -1e9
    with loop(g.k, g.n, 0):
        g.p = g.s0 + g.k
        g.sep = VT.wnx[g.p] * (g.cx - VT.wx[g.p]) + VT.wny[g.p] * (g.cy - VT.wy[g.p])
        with If(g.sep > g.best):
            g.best = g.sep
            g.face = g.k
    with If(g.best < g.rad):
        g.i1 = g.s0 + g.face
        with If(eq(g.face, g.n - 1)):
            g.i2 = g.s0
        with Else():
            g.i2 = g.i1 + 1
        g.v1x = VT.wx[g.i1]
        g.v1y = VT.wy[g.i1]
        g.v2x = VT.wx[g.i2]
        g.v2y = VT.wy[g.i2]
        g.fnx = VT.wnx[g.i1]
        g.fny = VT.wny[g.i1]
        with If(g.best < 0.0001):
            # centre inside the polygon: push out along the face normal
            g.k = (g.rad + g.best) / 2
            add_contact(a, b, g.fnx, g.fny, g.cx - g.fnx * g.k, g.cy - g.fny * g.k, g.rad - g.best, 0)
        with Else():
            g.dot1 = (g.cx - g.v1x) * (g.v2x - g.v1x) + (g.cy - g.v1y) * (g.v2y - g.v1y)
            g.dot2 = (g.cx - g.v2x) * (g.v1x - g.v2x) + (g.cy - g.v2y) * (g.v1y - g.v2y)
            g.vert = 0
            with If(g.dot1 < 0):
                g.vert = 1
                g.vx = g.v1x
                g.vy = g.v1y
            with Else():
                with If(g.dot2 < 0):
                    g.vert = 1
                    g.vx = g.v2x
                    g.vy = g.v2y
            with If(eq(g.vert, 1)):
                # vertex region
                g.dx = g.cx - g.vx
                g.dy = g.cy - g.vy
                g.d2 = g.dx * g.dx + g.dy * g.dy
                with If(g.d2 < g.rad * g.rad):
                    g.d = sqrt(g.d2)
                    g.nx = g.dx / g.d
                    g.ny = g.dy / g.d
                    add_contact(a, b, g.nx, g.ny, (g.vx + g.cx - g.nx * g.rad) / 2,
                                (g.vy + g.cy - g.ny * g.rad) / 2, g.rad - g.d, 1)
            with Else():
                # face region
                g.k = (g.rad + g.best) / 2
                add_contact(a, b, g.fnx, g.fny, g.cx - g.fnx * g.k, g.cy - g.fny * g.k, g.rad - g.best, 2)


@proc()
def find_axis(a, b):
    """Face of a with the largest separation from b -> axis sep, axis face (0-based)."""
    g = Locals("ax")
    g.sa = B.v0[a]
    g.sb = B.v0[b]
    g.nb = B.vn[b]
    v.axis_sep = -1e9
    with loop(g.i, B.vn[a], 0):
        g.p = g.sa + g.i
        g.nx = VT.wnx[g.p]
        g.ny = VT.wny[g.p]
        g.vx = VT.wx[g.p]
        g.vy = VT.wy[g.p]
        g.min = 1e9
        with loop(g.q, g.nb, g.sb):
            g.d = g.nx * (VT.wx[g.q] - g.vx) + g.ny * (VT.wy[g.q] - g.vy)
            with If(g.d < g.min):
                g.min = g.d
        with If(g.min > v.axis_sep):
            v.axis_sep = g.min
            v.axis_face = g.i


def clip(g, nx, ny, c):
    """Clip segment (i1, i2) against the half-plane n.p <= c *in place*: a clipped
    endpoint is replaced by the intersection, so slot 1 / slot 2 always belong to
    the same incident vertex.  That keeps warm-start impulses on the right corner
    (appending points instead swaps the slots and pumps energy into stacks).
    cnt = number of points left (0 or 2)."""
    g.d1 = nx * g.i1x + ny * g.i1y - c
    g.d2 = nx * g.i2x + ny * g.i2y - c
    g.cnt = 2
    with If((g.d1 > 0) & (g.d2 > 0)):
        g.cnt = 0
    with Else():
        with If(g.d1 * g.d2 < 0):
            g.al = g.d1 / (g.d1 - g.d2)
            g.qx = g.i1x + g.al * (g.i2x - g.i1x)
            g.qy = g.i1y + g.al * (g.i2y - g.i1y)
            with If(g.d1 > 0):
                g.i1x = g.qx
                g.i1y = g.qy
            with Else():
                g.i2x = g.qx
                g.i2y = g.qy


@proc()
def collide_polys(a, b):
    g = Locals("pp")
    find_axis(a, b)
    with If(v.axis_sep < 0):
        g.sepa = v.axis_sep
        g.facea = v.axis_face
        find_axis(b, a)
        with If(v.axis_sep < 0):
            # reference face: keep a unless b is better by an absolute tolerance
            # (a relative bias flip-flops when resting penetrations are tiny)
            with If(~(v.axis_sep > g.sepa + 0.1)):
                g.ref = a
                g.inc = b
                g.rf = g.facea
                g.flip = 0
            with Else():
                g.ref = b
                g.inc = a
                g.rf = v.axis_face
                g.flip = 1
            g.rs = B.v0[g.ref]
            g.rn = B.vn[g.ref]
            g.r1 = g.rs + g.rf
            with If(eq(g.rf, g.rn - 1)):
                g.r2 = g.rs
            with Else():
                g.r2 = g.r1 + 1
            g.nx = VT.wnx[g.r1]
            g.ny = VT.wny[g.r1]
            # incident face: most anti-parallel to the reference normal
            g.incs = B.v0[g.inc]
            g.incn = B.vn[g.inc]
            g.min = 1e9
            with loop(g.k, g.incn, 0):
                g.d = g.nx * VT.wnx[g.incs + g.k] + g.ny * VT.wny[g.incs + g.k]
                with If(g.d < g.min):
                    g.min = g.d
                    g.incf = g.k
            g.p = g.incs + g.incf
            with If(eq(g.incf, g.incn - 1)):
                g.q = g.incs
            with Else():
                g.q = g.p + 1
            g.i1x = VT.wx[g.p]
            g.i1y = VT.wy[g.p]
            g.i2x = VT.wx[g.q]
            g.i2y = VT.wy[g.q]
            g.rv1x = VT.wx[g.r1]
            g.rv1y = VT.wy[g.r1]
            g.rv2x = VT.wx[g.r2]
            g.rv2y = VT.wy[g.r2]
            g.tx = g.rv2x - g.rv1x
            g.ty = g.rv2y - g.rv1y
            g.tl = sqrt(g.tx * g.tx + g.ty * g.ty)
            g.tx = g.tx / g.tl
            g.ty = g.ty / g.tl
            g.refc = g.nx * g.rv1x + g.ny * g.rv1y
            clip(g, 0 - g.tx, 0 - g.ty, 0 - (g.tx * g.rv1x + g.ty * g.rv1y))
            with If(~(g.cnt < 2)):
                clip(g, g.tx, g.ty, g.tx * g.rv2x + g.ty * g.rv2y)
                with If(~(g.cnt < 2)):
                    with If(eq(g.flip, 0)):
                        g.cnx = g.nx
                        g.cny = g.ny
                    with Else():
                        g.cnx = 0 - g.nx
                        g.cny = 0 - g.ny
                    # feature id must not depend on which body the broadphase called "a"
                    with If(a < b):
                        g.fid = (g.rf * 8 + g.incf) * 4 + g.flip * 2
                    with Else():
                        g.fid = (g.rf * 8 + g.incf) * 4 + (1 - g.flip) * 2
                    for slot, (ox, oy) in enumerate(((g.i1x, g.i1y), (g.i2x, g.i2y))):
                        g.sep = g.nx * ox + g.ny * oy - g.refc
                        with If(~(g.sep > 0)):
                            add_contact(a, b, g.cnx, g.cny, ox - g.nx * g.sep / 2, oy - g.ny * g.sep / 2,
                                        0 - g.sep, g.fid + slot)


@proc()
def wake_island(id_):
    """Wake every body of a sleeping island (island ids come from the last step)."""
    g = Locals("wi")
    with loop(g.i, B.type.length):
        with If(eq(B.isl[g.i], id_) & eq(B.static[g.i], 0)):
            wake_body(g.i)


@proc()
def pair_test(a, b):
    g = Locals("pair")
    # A moving body reaching a sleeping island wakes the whole island *before*
    # the contact is solved, so the impact travels through it (Newton's cradle)
    # instead of bouncing off a temporarily static body.
    with If(eq(B.awake[a], 0) & (B.im[b] > 0) & (B.sleep[b] < 0.1)):
        wake_island(B.isl[a])
    with If(eq(B.awake[b], 0) & (B.im[a] > 0) & (B.sleep[a] < 0.1)):
        wake_island(B.isl[b])
    with If((B.im[a] > 0) | (B.im[b] > 0)):
        with If(eq(B.group[a], 0) | ne(B.group[a], B.group[b])):
            v.pairs = v.pairs + 1
            g.n0 = C.a.length
            g.ta = B.type[a]
            g.tb = B.type[b]
            with If(eq(g.ta, CIRCLE)):
                with If(eq(g.tb, CIRCLE)):
                    collide_circles(a, b)
                with Else():
                    collide_poly_circle(b, a)
            with Else():
                with If(eq(g.tb, CIRCLE)):
                    collide_poly_circle(a, b)
                with Else():
                    collide_polys(a, b)
            with If((C.a.length > g.n0) & eq(B.static[a], 0) & eq(B.static[b], 0)):
                union(a, b)
    with Else():
        # two sleeping bodies whose boxes touch belong to the same island
        with If(eq(B.static[a], 0) & eq(B.static[b], 0)):
            union(a, b)


@proc()
def collide():
    g = Locals("col")
    BP = l["bp order"]
    # keep last step's impulses for warm starting
    CO.key.clear()
    CO.pn.clear()
    CO.pt.clear()
    with loop(g.k, C.key.length):
        CO.key.add(C.key[g.k])
        CO.pn.add(C.pn[g.k])
        CO.pt.add(C.pt[g.k])
    for f in CONTACT_FIELDS:
        ListRef("c " + f).clear()
    v.pairs = 0
    v.max_pen = 0
    v.warm_hits = 0
    with loop(g.i, B.type.length):
        B.par[g.i] = g.i
        B.nc[g.i] = 0
    # insertion sort of the sweep order by AABB min x (nearly sorted every step -> ~O(n))
    g.n = BP.length
    with loop(g.i, g.n - 1, 2):
        g.key = BP[g.i]
        g.kx = B.minx[g.key]
        g.j = g.i - 1
        with RepeatUntil((g.j < 1) | ~(B.minx[BP[g.j]] > g.kx)):
            BP[g.j + 1] = BP[g.j]
            g.j = g.j - 1
        BP[g.j + 1] = g.key
    # sweep
    with loop(g.i, g.n):
        g.a = BP[g.i]
        g.amaxx = B.maxx[g.a]
        g.aminy = B.miny[g.a]
        g.amaxy = B.maxy[g.a]
        g.j = g.i + 1
        with RepeatUntil((g.j > g.n) | (B.minx[BP[g.j]] > g.amaxx)):
            g.b = BP[g.j]
            with If(~(B.miny[g.b] > g.amaxy) & ~(B.maxy[g.b] < g.aminy)):
                pair_test(g.a, g.b)
            g.j = g.j + 1


# ================================================================== solver

def load_body(g, side, idx):
    setvar(getattr(g, "im" + side), B.im[idx])
    setvar(getattr(g, "ii" + side), B.ii[idx])
    setvar(getattr(g, "vx" + side), B.vx[idx])
    setvar(getattr(g, "vy" + side), B.vy[idx])
    setvar(getattr(g, "w" + side), B.w[idx])


def store_body(g, side, idx):
    B.vx[idx] = getattr(g, "vx" + side)
    B.vy[idx] = getattr(g, "vy" + side)
    B.w[idx] = getattr(g, "w" + side)


def apply_impulse(g, px, py, rax, ray, rbx, rby):
    """v_a -= P/m_a, w_a -= (r_a x P)/I_a ; v_b += ... (on locals of g)."""
    g.vxa = g.vxa - g.ima * px
    g.vya = g.vya - g.ima * py
    g.wa = g.wa - g.iia * (rax * py - ray * px)
    g.vxb = g.vxb + g.imb * px
    g.vyb = g.vyb + g.imb * py
    g.wb = g.wb + g.iib * (rbx * py - rby * px)


@proc()
def prestep_contacts(inv_h):
    g = Locals("pre")
    with loop(g.k, C.a.length):
        g.a = C.a[g.k]
        g.b = C.b[g.k]
        load_body(g, "a", g.a)
        load_body(g, "b", g.b)
        g.nx = C.nx[g.k]
        g.ny = C.ny[g.k]
        g.rax = C.px[g.k] - B.x[g.a]
        g.ray = C.py[g.k] - B.y[g.a]
        g.rbx = C.px[g.k] - B.x[g.b]
        g.rby = C.py[g.k] - B.y[g.b]
        C.rax[g.k] = g.rax
        C.ray[g.k] = g.ray
        C.rbx[g.k] = g.rbx
        C.rby[g.k] = g.rby
        g.rna = g.rax * g.nx + g.ray * g.ny
        g.rnb = g.rbx * g.nx + g.rby * g.ny
        g.kn = (g.ima + g.imb + g.iia * (g.rax * g.rax + g.ray * g.ray - g.rna * g.rna) +
                g.iib * (g.rbx * g.rbx + g.rby * g.rby - g.rnb * g.rnb))
        C.mn[g.k] = 1 / g.kn
        g.rta = g.rax * g.ny - g.ray * g.nx
        g.rtb = g.rbx * g.ny - g.rby * g.nx
        g.kt = (g.ima + g.imb + g.iia * (g.rax * g.rax + g.ray * g.ray - g.rta * g.rta) +
                g.iib * (g.rbx * g.rbx + g.rby * g.rby - g.rtb * g.rtb))
        C.mt[g.k] = 1 / g.kt
        # Baumgarte position correction + restitution as a velocity bias
        g.bias = 0
        with If(C.pen[g.k] > SLOP):
            g.bias = BAUMGARTE * inv_h * (C.pen[g.k] - SLOP)
            with If(g.bias > MAX_BIAS):
                g.bias = MAX_BIAS
        g.vn = ((g.vxb - g.wb * g.rby - g.vxa + g.wa * g.ray) * g.nx +
                (g.vyb + g.wb * g.rbx - g.vya - g.wa * g.rax) * g.ny)
        with If(g.vn < 0 - REST_THRESHOLD):
            g.e = B.rest[g.a]
            with If(B.rest[g.b] > g.e):
                g.e = B.rest[g.b]
            with If(0 - g.e * g.vn > g.bias):
                g.bias = 0 - g.e * g.vn
        C.bias[g.k] = g.bias
        C.mu[g.k] = sqrt(B.fric[g.a] * B.fric[g.b])
    # Warm start in a second pass: the restitution test above must see the
    # velocities *before* any stored impulse is re-applied, otherwise the impulse
    # from the contact below a box looks like an impact with the box above
    # (and tall stacks bounce themselves apart).
    with loop(g.k, C.a.length):
        g.a = C.a[g.k]
        g.b = C.b[g.k]
        load_body(g, "a", g.a)
        load_body(g, "b", g.b)
        g.nx = C.nx[g.k]
        g.ny = C.ny[g.k]
        g.rax = C.rax[g.k]
        g.ray = C.ray[g.k]
        g.rbx = C.rbx[g.k]
        g.rby = C.rby[g.k]
        g.pn = C.pn[g.k]
        g.pt = C.pt[g.k]
        g.px = g.pn * g.nx + g.pt * g.ny
        g.py = g.pn * g.ny - g.pt * g.nx
        apply_impulse(g, g.px, g.py, g.rax, g.ray, g.rbx, g.rby)
        store_body(g, "a", g.a)
        store_body(g, "b", g.b)


@proc()
def solve_contacts():
    g = Locals("sc")
    with loop(g.k, C.a.length):
        g.a = C.a[g.k]
        g.b = C.b[g.k]
        load_body(g, "a", g.a)
        load_body(g, "b", g.b)
        g.nx = C.nx[g.k]
        g.ny = C.ny[g.k]
        g.rax = C.rax[g.k]
        g.ray = C.ray[g.k]
        g.rbx = C.rbx[g.k]
        g.rby = C.rby[g.k]
        # normal impulse (accumulated, clamped >= 0)
        g.dvx = g.vxb - g.wb * g.rby - g.vxa + g.wa * g.ray
        g.dvy = g.vyb + g.wb * g.rbx - g.vya - g.wa * g.rax
        g.dp = C.mn[g.k] * (C.bias[g.k] - (g.dvx * g.nx + g.dvy * g.ny))
        g.p0 = C.pn[g.k]
        g.pn = g.p0 + g.dp
        with If(g.pn < 0):
            g.pn = 0
        C.pn[g.k] = g.pn
        g.dp = g.pn - g.p0
        apply_impulse(g, g.dp * g.nx, g.dp * g.ny, g.rax, g.ray, g.rbx, g.rby)
        # friction impulse (accumulated, clamped to the Coulomb cone mu * pn)
        g.dvx = g.vxb - g.wb * g.rby - g.vxa + g.wa * g.ray
        g.dvy = g.vyb + g.wb * g.rbx - g.vya - g.wa * g.rax
        g.dp = 0 - C.mt[g.k] * (g.dvx * g.ny - g.dvy * g.nx)
        g.max = C.mu[g.k] * g.pn
        g.p0 = C.pt[g.k]
        g.pt = g.p0 + g.dp
        with If(g.pt > g.max):
            g.pt = g.max
        with If(g.pt < 0 - g.max):
            g.pt = 0 - g.max
        C.pt[g.k] = g.pt
        g.dp = g.pt - g.p0
        apply_impulse(g, g.dp * g.ny, 0 - g.dp * g.nx, g.rax, g.ray, g.rbx, g.rby)
        store_body(g, "a", g.a)
        store_body(g, "b", g.b)


@proc()
def prestep_joints(inv_h):
    g = Locals("pj")
    with loop(g.j, J.type.length):
        g.t = J.type[g.j]
        J.act[g.j] = 0
        with If((g.t > -1) & (g.t < SPRING)):
            joint_arms(g, g.j)
            load_body(g, "a", g.a)
            load_body(g, "b", g.b)
            with If(g.ima + g.imb > 0):
                J.act[g.j] = 1
                J.r1x[g.j] = g.r1x
                J.r1y[g.j] = g.r1y
                J.r2x[g.j] = g.r2x
                J.r2y[g.j] = g.r2y
                with If(eq(g.t, REVOLUTE)):
                    # soft point constraint (Box2D v2 style): a very stiff, critically
                    # damped spring.  gamma softens the mass matrix; the bias replaces
                    # Baumgarte.  Rigid Gauss-Seidel loops (a bridge pinned at both
                    # ends) otherwise pump energy into the chain.
                    g.meff = 1 / (g.ima + g.imb)
                    g.om = 2 * math.pi * v.joint_hz
                    g.kk = g.meff * g.om * g.om
                    g.dd = 2 * g.meff * g.om
                    g.h = 1 / inv_h
                    g.gam = 1 / (g.h * (g.dd + g.h * g.kk))
                    J.soft[g.j] = g.gam
                    g.k11 = g.ima + g.imb + g.iia * g.r1y * g.r1y + g.iib * g.r2y * g.r2y + g.gam
                    g.k12 = 0 - g.iia * g.r1x * g.r1y - g.iib * g.r2x * g.r2y
                    g.k22 = g.ima + g.imb + g.iia * g.r1x * g.r1x + g.iib * g.r2x * g.r2x + g.gam
                    g.det = 1 / (g.k11 * g.k22 - g.k12 * g.k12)
                    J.m11[g.j] = g.k22 * g.det
                    J.m12[g.j] = 0 - g.k12 * g.det
                    J.m22[g.j] = g.k11 * g.det
                    g.beta = g.h * g.kk * g.gam          # 1/s
                    J.bx[g.j] = (0 - g.beta) * (g.p2x - g.p1x)
                    J.by[g.j] = (0 - g.beta) * (g.p2y - g.p1y)
                    g.px = J.px[g.j]
                    g.py = J.py[g.j]
                with Else():
                    g.dx = g.p2x - g.p1x
                    g.dy = g.p2y - g.p1y
                    g.len = sqrt(g.dx * g.dx + g.dy * g.dy)
                    with If(g.len > 0.001):
                        g.nx = g.dx / g.len
                        g.ny = g.dy / g.len
                    with Else():
                        g.nx = 1
                        g.ny = 0
                    J.nx[g.j] = g.nx
                    J.ny[g.j] = g.ny
                    g.rn1 = g.r1x * g.ny - g.r1y * g.nx
                    g.rn2 = g.r2x * g.ny - g.r2y * g.nx
                    J.mass[g.j] = 1 / (g.ima + g.imb + g.iia * g.rn1 * g.rn1 + g.iib * g.rn2 * g.rn2)
                    J.bx[g.j] = (0 - v.joint_beta) * inv_h * (g.len - J.len[g.j])
                    g.px = J.px[g.j] * g.nx
                    g.py = J.px[g.j] * g.ny
                apply_impulse(g, g.px, g.py, g.r1x, g.r1y, g.r2x, g.r2y)
                store_body(g, "a", g.a)
                store_body(g, "b", g.b)


@proc()
def solve_joints():
    g = Locals("sj")
    with loop(g.j, J.type.length):
        with If(eq(J.act[g.j], 1)):
            g.a = J.a[g.j]
            g.b = J.b[g.j]
            load_body(g, "a", g.a)
            load_body(g, "b", g.b)
            g.r1x = J.r1x[g.j]
            g.r1y = J.r1y[g.j]
            g.r2x = J.r2x[g.j]
            g.r2y = J.r2y[g.j]
            g.dvx = g.vxb - g.wb * g.r2y - g.vxa + g.wa * g.r1y
            g.dvy = g.vyb + g.wb * g.r2x - g.vya - g.wa * g.r1x
            with If(eq(J.type[g.j], REVOLUTE)):
                g.ex = J.bx[g.j] - g.dvx - J.soft[g.j] * J.px[g.j]
                g.ey = J.by[g.j] - g.dvy - J.soft[g.j] * J.py[g.j]
                g.px = J.m11[g.j] * g.ex + J.m12[g.j] * g.ey
                g.py = J.m12[g.j] * g.ex + J.m22[g.j] * g.ey
                J.px[g.j] = J.px[g.j] + g.px
                J.py[g.j] = J.py[g.j] + g.py
            with Else():
                g.nx = J.nx[g.j]
                g.ny = J.ny[g.j]
                g.lam = J.mass[g.j] * (J.bx[g.j] - (g.dvx * g.nx + g.dvy * g.ny))
                J.px[g.j] = J.px[g.j] + g.lam
                g.px = g.lam * g.nx
                g.py = g.lam * g.ny
            apply_impulse(g, g.px, g.py, g.r1x, g.r1y, g.r2x, g.r2y)
            store_body(g, "a", g.a)
            store_body(g, "b", g.b)


# ================================================================ sleeping

@proc()
def wake_body(i):
    with If(eq(B.awake[i], 0)):
        B.awake[i] = 1
        B.sleep[i] = 0
        B.im[i] = B.imr[i]
        B.ii[i] = B.iir[i]


@proc()
def sleep_body(i):
    B.awake[i] = 0
    B.vx[i] = 0
    B.vy[i] = 0
    B.w[i] = 0
    B.im[i] = 0
    B.ii[i] = 0


@proc()
def wake_all():
    g = Locals("wa")
    with loop(g.i, B.type.length):
        with If(eq(B.static[g.i], 0)):
            wake_body(g.i)
            B.sleep[g.i] = 0


def is_dynamic(i):
    return eq(B.static[i], 0)


@proc()
def update_islands():
    g = Locals("isl")
    with If(eq(v.sleeping, 0)):
        with loop(g.i, B.type.length):
            with If(is_dynamic(g.i)):
                wake_body(g.i)
    with Else():
        with loop(g.j, J.type.length):
            with If(J.type[g.j] > -1):
                g.a = J.a[g.j]
                g.b = J.b[g.j]
                with If(is_dynamic(g.a) & is_dynamic(g.b)):
                    union(g.a, g.b)
        with loop(g.i, B.type.length):
            B.imin[g.i] = 1e9
        with loop(g.i, B.type.length):
            with If(is_dynamic(g.i)):
                find_root(g.i)
                with If(B.sleep[g.i] < B.imin[v.root]):
                    B.imin[v.root] = B.sleep[g.i]
        with loop(g.i, B.type.length):
            with If(is_dynamic(g.i)):
                find_root(g.i)
                B.isl[g.i] = v.root
                with If(B.imin[v.root] > SLEEP_TIME):
                    with If(eq(B.awake[g.i], 1)):
                        sleep_body(g.i)
                with Else():
                    wake_body(g.i)


# ============================================================ simulation

@proc()
def physics_frame():
    g = Locals("pf")
    g.h = v.time_scale / (60 * v.substeps)
    with loop(g.i, B.type.length):
        B.rfx[g.i] = 0
        B.rfy[g.i] = 0
        B.efx[g.i] = 0
        B.efy[g.i] = 0
    with Repeat(v.substeps):
        apply_forces()
        collide()
        integrate_velocities(g.h)
        prestep_contacts(1 / g.h)
        prestep_joints(1 / g.h)
        with Repeat(v.iterations):
            with Repeat(v.joint_passes):
                solve_joints()
            solve_contacts()
        integrate_positions(g.h)
        update_islands()
    v.sim_time = v.sim_time + g.h * v.substeps
    v.last_h = g.h
    # joint reaction forces for display (N)
    with loop(g.j, J.type.length):
        with If(eq(J.type[g.j], REVOLUTE)):
            J.force[g.j] = sqrt(J.px[g.j] * J.px[g.j] + J.py[g.j] * J.py[g.j]) / (g.h * PPM)
        with If(eq(J.type[g.j], DISTANCE)):
            J.force[g.j] = abs_(J.px[g.j]) / (g.h * PPM)


@proc()
def compute_metrics():
    """Energy / momentum in SI units (50 px = 1 m) + body counts."""
    g = Locals("met")
    g.ke = 0
    g.pe = 0
    g.px = 0
    g.py = 0
    g.am = 0
    v.n_bodies = 0
    v.n_awake = 0
    v.n_asleep = 0
    v.n_static = 0
    v.islands = 0
    with loop(g.i, B.type.length):
        g.t = B.type[g.i]
        with If((g.t > -1) & (g.t < WORLD)):
            v.n_bodies = v.n_bodies + 1
            with If(eq(B.static[g.i], 1)):
                v.n_static = v.n_static + 1
            with Else():
                g.m = B.m[g.i]
                g.vx = B.vx[g.i]
                g.vy = B.vy[g.i]
                g.w = B.w[g.i]
                g.ke = g.ke + g.m * (g.vx * g.vx + g.vy * g.vy) + B.i[g.i] * g.w * g.w
                g.pe = g.pe + g.m * (B.y[g.i] + 180)
                g.px = g.px + g.m * g.vx
                g.py = g.py + g.m * g.vy
                g.am = g.am + B.i[g.i] * g.w + g.m * (B.x[g.i] * g.vy - B.y[g.i] * g.vx)
                with If(eq(B.awake[g.i], 1)):
                    v.n_awake = v.n_awake + 1
                with Else():
                    v.n_asleep = v.n_asleep + 1
                with If(eq(B.par[g.i], g.i)):
                    v.islands = v.islands + 1
    v.ke = g.ke / (2 * PPM * PPM)
    v.pe = g.pe * v.gravity / PPM
    v.energy = v.ke + v.pe
    v.mom_x = g.px / PPM
    v.mom_y = g.py / PPM
    v.mom = sqrt(v.mom_x * v.mom_x + v.mom_y * v.mom_y)
    v.ang_mom = g.am / (PPM * PPM)
    v.n_contacts = C.a.length
    v.n_joints = 0
    with loop(g.j, J.type.length):
        with If(J.type[g.j] > -1):
            v.n_joints = v.n_joints + 1
    with If(eq(v.paused, 0)):
        G.ke.add(v.ke)
        G.pe.add(v.pe)
        G.e.add(v.energy)
        G.p.add(v.mom)
        with If(G.ke.length > GRAPH_N):
            for lst in (G.ke, G.pe, G.e, G.p):
                lst.delete(1)


exec(open(os.path.join(HERE, "physics_view.py")).read())
