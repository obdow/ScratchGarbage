# Rendering, HUD, input, scenes and the main loop for physics_2d.sb3.
# Executed by build_physics_sb3.py in its namespace (shares P, proc, B, C, J, ...).

# ------------------------------------------------------------- static data
# palette index 1 = static bodies, 2..7 = dynamic colours  (stroke, fill)
PALETTE = [(0x5b7bb5, 0x152139), (0x4fd1ff, 0x0f3550), (0xffb04f, 0x45300f), (0x6dff9c, 0x113f27),
           (0xff6fb1, 0x46152f), (0xa98bff, 0x2a2253), (0xffe066, 0x443d12)]


def _dim(c, k):
    r, g_, b = c >> 16, (c >> 8) & 255, c & 255
    grey = (r + g_ + b) / 3
    mix = lambda ch: int(ch * (1 - k) + grey * k * 0.8)
    return (mix(r) << 16) | (mix(g_) << 8) | mix(b)


P.set_list_contents("pal stroke", [s for s, f in PALETTE])
P.set_list_contents("pal fill", [f for s, f in PALETTE])
P.set_list_contents("pal dim", [s if i == 0 else _dim(s, 0.65) for i, (s, f) in enumerate(PALETTE)])
P.set_list_contents("pal dimfill", [f if i == 0 else _dim(f, 0.55) for i, (s, f) in enumerate(PALETTE)])
P.set_list_contents("pow10", [1, 10, 100, 1000, 10000])

KEYS = ["space", "n", "r", "1", "2", "3", "4", "5", "6", "7", "c", "b", "p", "x", "e", "v", "f", "k", "a",
        "g", "i", "h", "o", "m", "s", "t", "up arrow", "down arrow", "left arrow", "right arrow"]
P.set_list_contents("key queue", [])


def _key_hat(key):
    @P.script("event_whenkeypressed", {"KEY_OPTION": [key, None]})
    def _hat():
        with If(l.key_queue.length < 8):
            l.key_queue.add(key)


for _k in KEYS:
    _key_hat(_k)

SCENES = ["Pyramid stack", "Playground", "Newton's cradle", "Rope bridge", "Dominoes",
          "Friction ramps", "Joints & springs"]
P.set_list_contents("scene names", SCENES)

HELP = [
    ("CONTROLS", 1),
    ("mouse     drag a body (spring force)   ·   click empty space to spawn", 0),
    ("C B P     spawn tool: circle / box / polygon", 0),
    ("X         delete body under mouse     E   blast at mouse", 0),
    ("1 - 7     scenes                      R   reset scene", 0),
    ("space     pause / resume              N   single step", 0),
    ("", 0),
    ("OVERLAYS", 1),
    ("V   velocity + angular velocity       F   forces (weight, reaction, net)", 0),
    ("K   contact points, normal + friction forces", 0),
    ("A   AABBs (broadphase)    G   graphs    I   stats    H   this help", 0),
    ("", 0),
    ("TUNING", 1),
    ("up / down      gravity  ±1 m/s²", 0),
    ("left / right   solver iterations  ±1", 0),
    ("S   substeps 1/2/4/8      T   time scale 1 / 0.5 / 0.25 / 0.1", 0),
    ("O   warm starting on/off  M   sleeping on/off", 0),
    ("", 0),
    ("units: 50 px = 1 m · density 1 kg/m² · forces in newtons", 2),
]
P.set_list_contents("help text", [t for t, k in HELP])
P.set_list_contents("help kind", [k for t, k in HELP])

FONT = 8.5          # HUD text size
LH = 10.5           # HUD line height
FORCE_SCALE = 2.0   # px per newton for force arrows
VEL_SCALE = 0.12    # px per (px/s) for velocity arrows

# text colours as (hue, brightness) for the text engine
WHITE = (0, 100)
CYAN = (50, 55)
ORANGE = (9, 35)
BLUE = (58, 45)
GREEN = (36, 45)
YELLOW = (16, 40)
RED = (0, 40)
PINK = (90, 45)


# ------------------------------------------------------------- text helpers

class F:
    """A number formatted with d decimals inside text()."""

    def __init__(s, e, d=2):
        s.e, s.d = e, d


def style(size=FONT, colour=WHITE, alpha=0, align="left", valign="top"):
    te_size(size)
    te_color(colour[0], colour[1])
    te_alpha(alpha)
    te_align(align, valign)


def text(x, y, *parts):
    if all(isinstance(p, str) for p in parts):
        te_draw("".join(parts), x, y)
        return
    v.line = ""
    buf = ""
    for p in parts:
        if isinstance(p, str):
            buf += p
            continue
        if buf:
            v.line = join(v.line, buf)
            buf = ""
        if isinstance(p, F):
            fmt(p.e, p.d)
            v.line = join(v.line, v.f)
        else:
            v.line = join(v.line, p)
    if buf:
        v.line = join(v.line, buf)
    te_draw(v.line, x, y)


@proc()
def fmt(x, d):
    """Fixed-decimal number -> variable 'f'."""
    g = Locals("fmt")
    with If(eq(d, 0)):
        v.f = round_(x)
    with Else():
        g.m = l.pow10[d + 1]
        g.n = round_(abs_(x) * g.m)
        g.s = g.m + g.n % g.m
        g.frac = ""
        with loop(g.k, d, 2):
            g.frac = join(g.frac, letter(g.k, g.s))
        with If((x < 0) & (g.n > 0)):
            v.f = join("-", join(floor(g.n / g.m), join(".", g.frac)))
        with Else():
            v.f = join(floor(g.n / g.m), join(".", g.frac))


# -------------------------------------------------------------- pen helpers

@proc()
def pen_mode():
    pen_up()
    switch_costume("_fence")


@proc()
def line(x1, y1, x2, y2):
    goto(x1, y1)
    pen_down()
    goto(x2, y2)
    pen_up()


@proc()
def dot(x, y):
    goto(x, y)
    pen_down()
    pen_up()


@proc()
def arrow(x, y, dx, dy):
    g = Locals("arr")
    g.len = sqrt(dx * dx + dy * dy)
    with If(g.len > 1.5):
        g.ex = x + dx
        g.ey = y + dy
        g.hs = g.len * 0.45
        with If(g.hs > 7):
            g.hs = 7
        g.ux = dx / g.len * g.hs
        g.uy = dy / g.len * g.hs
        goto(x, y)
        pen_down()
        goto(g.ex, g.ey)
        goto(g.ex - g.ux + g.uy * 0.5, g.ey - g.uy - g.ux * 0.5)
        goto(g.ex, g.ey)
        goto(g.ex - g.ux - g.uy * 0.5, g.ey - g.uy + g.ux * 0.5)
        pen_up()


@proc()
def clamped_arrow(x, y, dx, dy, maxlen):
    g = Locals("carr")
    g.len = sqrt(dx * dx + dy * dy)
    with If(g.len > maxlen):
        arrow(x, y, dx * maxlen / g.len, dy * maxlen / g.len)
    with Else():
        arrow(x, y, dx, dy)


@proc()
def arc(x, y, r, a0, sweep):
    g = Locals("arc")
    goto(x + r * cos(a0), y + r * sin(a0))
    pen_down()
    with loop(g.k, 10):
        g.ang = a0 + sweep * g.k / 10
        goto(x + r * cos(g.ang), y + r * sin(g.ang))
    pen_up()
    g.ex = x + r * cos(g.ang)
    g.ey = y + r * sin(g.ang)
    g.sg = sweep / abs_(sweep) * 5
    g.dx = 0 - sin(g.ang) * g.sg
    g.dy = cos(g.ang) * g.sg
    g.ox = cos(g.ang) * 2.5
    g.oy = sin(g.ang) * 2.5
    line(g.ex - g.dx + g.ox, g.ey - g.dy + g.oy, g.ex, g.ey)
    line(g.ex - g.dx - g.ox, g.ey - g.dy - g.oy, g.ex, g.ey)


@proc()
def panel(x1, y1, x2, y2):
    """Opaque HUD panel, (x1, y1) = top left."""
    g = Locals("pnl")
    pen_mode()
    pen_color(0x0c1426)
    pen_size(4)
    g.y = y1 - 2
    goto(x1 + 2, g.y)
    pen_down()
    with RepeatUntil(g.y < y2 + 2):
        goto(x2 - 2, g.y)
        g.y = g.y - 3
        with If(g.y < y2 + 2):
            g.y = y2 + 2
        goto(x2 - 2, g.y)
        goto(x1 + 2, g.y)
        with If(eq(g.y, y2 + 2)):
            g.y = g.y - 1
        with Else():
            g.y = g.y - 3
            with If(g.y < y2 + 2):
                g.y = y2 + 2
            goto(x1 + 2, g.y)
    pen_up()
    pen_color(0x2a3f6a)
    pen_size(1)
    goto(x1, y1)
    pen_down()
    goto(x2, y1)
    goto(x2, y2)
    goto(x1, y2)
    goto(x1, y1)
    pen_up()


@proc()
def draw_background():
    """Blueprint grid. Each colour is one zig-zag path whose turns happen off-stage."""
    g = Locals("bg")
    pen_color(0x0a1020)
    pen_size(1200)
    dot(0, 0)
    pen_size(1)
    for colour, major in ((0x0f1a30, 0), (0x172645, 1)):
        pen_color(colour)
        g.e = -190
        goto(-260, -190)
        pen_down()
        with loop(g.k, 25, 0):
            g.x = g.k * 20 - 240
            with If(eq(eq(g.x % 100, 0), major)):
                goto(g.x, g.e)
                g.e = 0 - g.e
                goto(g.x, g.e)
        g.e = -250
        goto(250, 190)
        with loop(g.k, 19, 0):
            g.y = g.k * 20 - 180
            with If(eq(eq((g.y + 200) % 100, 0), major)):
                goto(g.e, g.y)
                g.e = 0 - g.e
                goto(g.e, g.y)
        pen_up()


# ----------------------------------------------------------------- bodies

@proc()
def outline_poly(i):
    g = Locals("op")
    g.s = B.v0[i]
    goto(VT.wx[g.s], VT.wy[g.s])
    pen_down()
    with loop(g.k, B.vn[i] - 1, g.s + 1):
        goto(VT.wx[g.k], VT.wy[g.k])
    goto(VT.wx[g.s], VT.wy[g.s])
    pen_up()


@proc()
def fill_poly(i):
    """Fill a convex polygon with 2 px rows, scanning parallel to its longest edge
    (a 10x380 wall takes 5 rows, not 190) as ONE zig-zag pen path: every pen-down
    also stamps a dot, so separate lines would double the draw calls.  The
    connecting zig-zag segments stay inside the polygon because it is convex."""
    g = Locals("fp")
    U, N = l.fp_u, l.fp_n
    g.s = B.v0[i]
    g.n = B.vn[i]
    g.best = 0
    with loop(g.k, g.n, 0):
        g.p = g.s + g.k
        with If(eq(g.k, g.n - 1)):
            g.q = g.s
        with Else():
            g.q = g.p + 1
        g.ex = VT.wx[g.q] - VT.wx[g.p]
        g.ey = VT.wy[g.q] - VT.wy[g.p]
        with If(g.ex * g.ex + g.ey * g.ey > g.best):
            g.best = g.ex * g.ex + g.ey * g.ey
            g.ux = g.ex
            g.uy = g.ey
    g.d = sqrt(g.best)
    g.ux = g.ux / g.d
    g.uy = g.uy / g.d
    U.clear()
    N.clear()
    g.tmin = 1e9
    g.tmax = -1e9
    with loop(g.k, g.n, g.s):
        U.add(VT.wx[g.k] * g.ux + VT.wy[g.k] * g.uy)
        g.t = VT.wy[g.k] * g.ux - VT.wx[g.k] * g.uy
        N.add(g.t)
        with If(g.t < g.tmin):
            g.tmin = g.t
        with If(g.t > g.tmax):
            g.tmax = g.t
    g.t = g.tmin + 1
    g.tmax = g.tmax - 0.5
    g.dir = 0
    g.first = 1
    with RepeatUntil(g.t > g.tmax):
        g.ul = 1e9
        g.ur = -1e9
        with loop(g.k, g.n):
            with If(eq(g.k, g.n)):
                g.q = 1
            with Else():
                g.q = g.k + 1
            g.n1 = N[g.k]
            g.n2 = N[g.q]
            with If((~(g.n1 > g.t) & (g.n2 > g.t)) | (~(g.n2 > g.t) & (g.n1 > g.t))):
                g.u = U[g.k] + (g.t - g.n1) * (U[g.q] - U[g.k]) / (g.n2 - g.n1)
                with If(g.u < g.ul):
                    g.ul = g.u
                with If(g.u > g.ur):
                    g.ur = g.u
        with If(g.ur > g.ul):
            with If(g.ur > g.ul + 2):
                g.ul = g.ul + 1
                g.ur = g.ur - 1
            with Else():
                g.ul = (g.ul + g.ur) / 2
                g.ur = g.ul
            with If(eq(g.dir, 1)):
                g.u = g.ul
                g.ul = g.ur
                g.ur = g.u
            # point (u, t) in the (along-edge, normal) frame -> world
            goto(g.ul * g.ux - g.t * g.uy, g.ul * g.uy + g.t * g.ux)
            with If(eq(g.first, 1)):
                pen_down()
                g.first = 0
            goto(g.ur * g.ux - g.t * g.uy, g.ur * g.uy + g.t * g.ux)
            g.dir = 1 - g.dir
        g.t = g.t + 2
    pen_up()


@proc()
def draw_body(i):
    g = Locals("db")
    g.c = B.col[i]
    with If(eq(B.awake[i], 1)):
        g.stroke = l.pal_stroke[g.c]
        g.fill = l.pal_fill[g.c]
    with Else():
        g.stroke = l.pal_dim[g.c]
        g.fill = l.pal_dimfill[g.c]
    g.x = B.x[i]
    g.y = B.y[i]
    with If(eq(B.type[i], CIRCLE)):
        g.r = B.r[i]
        with If(eq(i, v.hover)):
            pen_color(0xffffff)
            pen_size(g.r * 2 + 5)
            dot(g.x, g.y)
        pen_color(g.stroke)
        pen_size(g.r * 2)
        dot(g.x, g.y)
        pen_color(g.fill)
        pen_size(g.r * 2 - 3)
        dot(g.x, g.y)
        pen_color(g.stroke)
        pen_size(1.5)
        line(g.x + cos(B.a[i]) * g.r * 0.35, g.y + sin(B.a[i]) * g.r * 0.35,
             g.x + cos(B.a[i]) * (g.r - 1.5), g.y + sin(B.a[i]) * (g.r - 1.5))
    with Else():
        with If(eq(i, v.hover)):
            pen_color(0xffffff)
            pen_size(5)
            outline_poly(i)
        pen_color(g.fill)
        pen_size(2.6)
        fill_poly(i)
        pen_color(g.stroke)
        pen_size(1.6)
        outline_poly(i)
    with If(eq(B.static[i], 0)):
        # centre of mass
        pen_color(g.stroke)
        pen_size(2.5)
        dot(g.x, g.y)


@proc()
def draw_joints():
    g = Locals("dj")
    with loop(g.j, J.type.length):
        g.t = J.type[g.j]
        with If(g.t > -1):
            joint_arms(g, g.j)
            with If(eq(g.t, REVOLUTE)):
                pen_color(0x8ea6d8)
                pen_size(1)
                with If(ne(B.type[g.a], WORLD)):
                    line(B.x[g.a], B.y[g.a], g.p1x, g.p1y)
                with If(ne(B.type[g.b], WORLD)):
                    line(B.x[g.b], B.y[g.b], g.p2x, g.p2y)
                pen_color(0xe8eeff)
                pen_size(6)
                dot(g.p1x, g.p1y)
                pen_color(0x0a1020)
                pen_size(2.5)
                dot(g.p1x, g.p1y)
            with If(eq(g.t, DISTANCE)):
                # brighter when under more tension
                g.f = J.force[g.j]
                with If(g.f > 20):
                    g.f = 20
                pen_color(0x8090b0 + floor(g.f * 3) * 65793)
                pen_size(1.5)
                line(g.p1x, g.p1y, g.p2x, g.p2y)
                pen_color(0xe8eeff)
                pen_size(4)
                dot(g.p1x, g.p1y)
                dot(g.p2x, g.p2y)
            with If(eq(g.t, SPRING)):
                g.dx = g.p2x - g.p1x
                g.dy = g.p2y - g.p1y
                g.len = sqrt(g.dx * g.dx + g.dy * g.dy) + 0.0001
                g.ox = 0 - g.dy / g.len * 5
                g.oy = g.dx / g.len * 5
                pen_color(0x7dffb0)
                pen_size(1.3)
                goto(g.p1x, g.p1y)
                pen_down()
                with loop(g.k, 13):
                    g.u = g.k / 14
                    g.sg = (g.k % 2) * 2 - 1
                    goto(g.p1x + g.dx * g.u + g.ox * g.sg, g.p1y + g.dy * g.u + g.oy * g.sg)
                goto(g.p2x, g.p2y)
                pen_up()
                pen_size(4)
                dot(g.p1x, g.p1y)
                dot(g.p2x, g.p2y)


@proc()
def draw_overlays():
    g = Locals("ov")
    with loop(g.i, B.type.length):
        g.t = B.type[g.i]
        with If((g.t > -1) & (g.t < WORLD)):
            g.x = B.x[g.i]
            g.y = B.y[g.i]
            with If(eq(v.show_aabb, 1)):
                with If(B.nc[g.i] > 0):
                    pen_color(0x8a3a5a)
                with Else():
                    pen_color(0x2d4a7a)
                pen_size(1)
                goto(B.minx[g.i], B.miny[g.i])
                pen_down()
                goto(B.maxx[g.i], B.miny[g.i])
                goto(B.maxx[g.i], B.maxy[g.i])
                goto(B.minx[g.i], B.maxy[g.i])
                goto(B.minx[g.i], B.miny[g.i])
                pen_up()
            with If(eq(B.static[g.i], 0)):
                with If(eq(v.show_vel, 1) & eq(B.awake[g.i], 1)):
                    pen_color(0x4dff88)
                    pen_size(2)
                    clamped_arrow(g.x, g.y, B.vx[g.i] * VEL_SCALE, B.vy[g.i] * VEL_SCALE, 110)
                    g.w = B.w[g.i]
                    with If(abs_(g.w) > 0.15):
                        g.sw = g.w * 25
                        clamp_stmt(g.sw, -300, 300)
                        pen_color(0x5ce1ff)
                        pen_size(1.5)
                        arc(g.x, g.y, B.r[g.i] * 0.6 + 4, B.a[g.i], g.sw)
                with If(eq(v.show_forces, 1)):
                    g.wn = B.m[g.i] * v.gravity
                    with If(eq(B.awake[g.i], 1)):
                        g.rx = B.rfx[g.i] / PPM
                        g.ry = B.rfy[g.i] / PPM
                    with Else():
                        g.rx = 0
                        g.ry = g.wn
                    g.ex = B.efx[g.i] / PPM
                    g.ey = B.efy[g.i] / PPM
                    pen_size(2)
                    pen_color(0xff5a5a)
                    clamped_arrow(g.x, g.y, 0, 0 - g.wn * FORCE_SCALE, 70)
                    pen_color(0x5aa8ff)
                    clamped_arrow(g.x, g.y, g.rx * FORCE_SCALE, g.ry * FORCE_SCALE, 70)
                    g.nx = g.rx + g.ex
                    g.ny = g.ry + g.ey - g.wn
                    with If(g.nx * g.nx + g.ny * g.ny > 0.04):
                        pen_color(0xffdd33)
                        pen_size(2.5)
                        clamped_arrow(g.x, g.y, g.nx * FORCE_SCALE, g.ny * FORCE_SCALE, 70)
    with If(eq(v.show_contacts, 1)):
        g.ih = 1 / (v.last_h * PPM)
        with loop(g.k, C.a.length):
            g.x = C.px[g.k]
            g.y = C.py[g.k]
            g.fn = C.pn[g.k] * g.ih
            g.ft = C.pt[g.k] * g.ih
            pen_size(1.5)
            pen_color(0xff7a3d)
            clamped_arrow(g.x, g.y, C.nx[g.k] * g.fn * FORCE_SCALE, C.ny[g.k] * g.fn * FORCE_SCALE, 45)
            with If(abs_(g.ft) > 0.05):
                pen_color(0x3dffd0)
                clamped_arrow(g.x, g.y, C.ny[g.k] * g.ft * FORCE_SCALE, 0 - C.nx[g.k] * g.ft * FORCE_SCALE, 30)
            pen_color(0xff3d7a)
            pen_size(4)
            dot(g.x, g.y)


@proc()
def draw_drag():
    with If(v.drag > 0):
        pen_color(0xffee55)
        pen_size(1.5)
        line(v.drag_ax, v.drag_ay, mouse_x(), mouse_y())
        pen_size(5)
        dot(v.drag_ax, v.drag_ay)
        pen_size(2)
        dot(mouse_x(), mouse_y())


# -------------------------------------------------------------------- HUD

@proc()
def draw_world_text():
    g = Locals("wt")
    style(FONT, WHITE, 45, "center", "middle")
    with loop(g.k, l.lbl_text.length):
        te_draw(l.lbl_text[g.k], l.lbl_x[g.k], l.lbl_y[g.k])
    with If(eq(v.show_contacts, 1) & (C.a.length < 13)):
        style(7.5, ORANGE, 0, "left", "bottom")
        g.ih = 1 / (v.last_h * PPM)
        with loop(g.k, C.a.length):
            text(C.px[g.k] + 4, C.py[g.k] + 3, F(C.pn[g.k] * g.ih, 1), " N")
    with If(eq(v.show_forces, 1) & (J.type.length < 30)):
        # joint reaction / spring forces
        style(7, GREEN, 0, "left", "bottom")
        with loop(g.j, J.type.length):
            with If(J.type[g.j] > -1):
                joint_arms(g, g.j)
                text(g.p1x + 4, g.p1y + 2, F(J.force[g.j], 1), " N")
    with If(v.drag > 0):
        style(8, YELLOW, 0, "left", "bottom")
        text(mouse_x() + 6, mouse_y() + 4, F(sqrt(v.drag_fx * v.drag_fx + v.drag_fy * v.drag_fy) / PPM, 1), " N")


@proc()
def draw_stats():
    g = Locals("st")
    x0 = -232
    panel(-236, 177, -18, 177 - 11 * LH - 6)
    style(FONT, CYAN)
    g.y = 174
    text(x0, g.y, "FPS ", F(v.fps, 0), "    physics ", F(v.phys_ms, 1), " ms    draw ", F(v.draw_ms, 1), " ms")
    style(FONT, WHITE)
    rows = [
        ("bodies ", F(v.n_bodies, 0), "   awake ", F(v.n_awake, 0), " · asleep ", F(v.n_asleep, 0),
         " · static ", F(v.n_static, 0)),
        ("islands ", F(v.islands, 0), "   joints ", F(v.n_joints, 0), "   contacts ", F(v.n_contacts, 0),
         " (", F(v.warm_hits, 0), " warm)"),
        ("broadphase pairs ", F(v.pairs, 0), " of ", F(v.n_bodies * (v.n_bodies - 1) / 2, 0),
         "  (sweep & prune)"),
        ("solver ", F(v.iterations, 0), " it × ", F(v.substeps, 0), " substeps · warm start ", v.warm_txt),
        ("gravity ", F(v.gravity, 2), " m/s²   time ×", F(v.time_scale, 2), "   sleep ", v.sleep_txt),
    ]
    for r in rows:
        g.y = g.y - LH
        text(x0, g.y, *r)
    g.y = g.y - LH
    style(FONT, ORANGE)
    text(x0, g.y, "kinetic ", F(v.ke, 2), " J")
    style(FONT, BLUE)
    text(x0 + 78, g.y, "potential ", F(v.pe, 2), " J")
    style(FONT, WHITE)
    text(x0 + 162, g.y, "E ", F(v.energy, 1), " J")
    g.y = g.y - LH
    style(FONT, GREEN)
    text(x0, g.y, "momentum |p| ", F(v.mom, 2), " kg·m/s  (", F(v.mom_x, 2), ", ", F(v.mom_y, 2), ")")
    style(FONT, WHITE)
    g.y = g.y - LH
    text(x0, g.y, "angular momentum ", F(v.ang_mom, 3), " kg·m²/s")
    g.y = g.y - LH
    text(x0, g.y, "max penetration ", F(v.max_pen, 2), " px   sim time ", F(v.sim_time, 1), " s")
    g.y = g.y - LH
    style(FONT, WHITE, 45)
    text(x0, g.y, "H help · V F K A overlays · drag / click to interact")


@proc()
def draw_title():
    style(13, WHITE, 0, "right", "top")
    text(234, 176, F(v.scene, 0), " · ", l.scene_names[v.scene])
    style(FONT, CYAN, 0, "right", "top")
    text(234, 160, "spawn tool: ", v.tool, "   [C B P]")
    with If(eq(v.paused, 1)):
        style(10, RED, 0, "right", "top")
        te_draw("PAUSED  (N = step)", 234, 148)
    with Else():
        with If(v.time_scale < 1):
            style(10, YELLOW, 0, "right", "top")
            text(234, 148, "slow motion ×", F(v.time_scale, 2))


@proc()
def draw_graphs():
    g = Locals("gr")
    gx1, gy1, gx2, gy2 = 92, 136, 236, 72
    panel(gx1, gy1, gx2, gy2)
    # scales: energies share one, momentum has its own
    g.emax = 0.001
    g.pmax = 0.001
    g.n = G.e.length
    with loop(g.k, g.n):
        with If(G.e[g.k] > g.emax):
            g.emax = G.e[g.k]
        with If(G.ke[g.k] > g.emax):
            g.emax = G.ke[g.k]
        with If(G.pe[g.k] > g.emax):
            g.emax = G.pe[g.k]
        with If(G.p[g.k] > g.pmax):
            g.pmax = G.p[g.k]
    g.sx = (gx2 - gx1 - 8) / (GRAPH_N - 1)
    g.x0 = gx1 + 4 + (GRAPH_N - g.n) * g.sx
    g.ey = (gy1 - gy2 - 22) / g.emax
    g.py = (gy1 - gy2 - 22) / g.pmax
    g.base = gy2 + 4
    pen_size(1.3)
    for lst, colour, scale in ((G.pe, 0x40a0ff, g.ey), (G.ke, 0xffa040, g.ey), (G.e, 0xe8eeff, g.ey),
                               (G.p, 0x60ff90, g.py)):
        pen_color(colour)
        with If(g.n > 1):
            goto(g.x0, g.base + lst[1] * scale)
            pen_down()
            with loop(g.k, g.n - 1, 2):
                goto(g.x0 + (g.k - 1) * g.sx, g.base + lst[g.k] * scale)
            pen_up()
    style(7.5, ORANGE)
    te_draw("KE", gx1 + 5, gy1 - 3)
    style(7.5, BLUE)
    te_draw("PE", gx1 + 22, gy1 - 3)
    style(7.5, WHITE)
    te_draw("E total", gx1 + 39, gy1 - 3)
    style(7.5, GREEN)
    te_draw("|p|", gx1 + 72, gy1 - 3)
    style(7.5, WHITE, 45, "right", "top")
    text(gx2 - 4, gy1 - 3, "max ", F(g.emax, 1), " J")


@proc()
def draw_inspector():
    g = Locals("ins")
    g.i = v.drag
    with If(eq(g.i, 0)):
        g.i = v.hover
    with If(g.i > 0):
        g.w = 176
        g.h = 7 * LH + 8
        g.x = mouse_x() + 14
        with If(g.x + g.w > 236):
            g.x = mouse_x() - 14 - g.w
        g.y = mouse_y() - 10
        with If(g.y - g.h < -176):
            g.y = -176 + g.h
        with If(g.y > 176):
            g.y = 176
        panel(g.x, g.y, g.x + g.w, g.y - g.h)
        g.tx = g.x + 5
        g.ty = g.y - 3
        with If(eq(B.type[g.i], CIRCLE)):
            g.kind = "circle"
        with Else():
            with If(eq(B.vn[g.i], 4)):
                g.kind = "box"
            with Else():
                g.kind = join(B.vn[g.i], "-gon")
        with If(eq(B.awake[g.i], 1)):
            g.state = "awake"
        with Else():
            g.state = "asleep"
        style(FONT, CYAN)
        text(g.tx, g.ty, "body #", g.i, " · ", g.kind, " · ", g.state)
        style(FONT, WHITE)
        g.vx = B.vx[g.i] / PPM
        g.vy = B.vy[g.i] / PPM
        g.m = B.m[g.i]
        g.sp = sqrt(g.vx * g.vx + g.vy * g.vy)
        text(g.tx, g.ty - LH, "mass ", F(g.m, 3), " kg   I ", F(B.i[g.i] / (PPM * PPM), 4), " kg·m²")
        text(g.tx, g.ty - 2 * LH, "pos ", F(B.x[g.i] / PPM, 2), ", ", F((B.y[g.i] + 180) / PPM, 2),
             " m   angle ", F(B.a[g.i], 0), "°")
        text(g.tx, g.ty - 3 * LH, "v ", F(g.sp, 2), " m/s  (", F(g.vx, 2), ", ", F(g.vy, 2), ")")
        text(g.tx, g.ty - 4 * LH, "w ", F(B.w[g.i], 2), " rad/s   contacts ", B.nc[g.i])
        style(FONT, ORANGE)
        text(g.tx, g.ty - 5 * LH, "KE ", F(0.5 * g.m * g.sp * g.sp + 0.5 * B.i[g.i] / (PPM * PPM) * B.w[g.i] * B.w[g.i], 3),
             " J   p ", F(g.m * g.sp, 3), " kg·m/s")
        style(FONT, WHITE, 30)
        text(g.tx, g.ty - 6 * LH, "µ ", F(B.fric[g.i], 2), "   e ", F(B.rest[g.i], 2), "   weight ",
             F(g.m * v.gravity, 2), " N")


@proc()
def draw_help():
    g = Locals("hlp")
    panel(-200, 112, 200, 112 - len(HELP) * 11 - 10)
    g.y = 107
    with loop(g.k, l.help_text.length):
        g.kd = l.help_kind[g.k]
        with If(eq(g.kd, 1)):
            style(9, CYAN)
        with Else():
            with If(eq(g.kd, 2)):
                style(FONT, WHITE, 45)
            with Else():
                style(FONT, WHITE)
        te_draw(l.help_text[g.k], -190, g.y)
        g.y = g.y - 11


@proc()
def render():
    g = Locals("rn")
    pen_mode()
    erase_all()
    draw_background()
    with loop(g.i, B.type.length):
        g.t = B.type[g.i]
        with If((g.t > -1) & (g.t < WORLD)):
            draw_body(g.i)
    draw_joints()
    draw_overlays()
    draw_drag()
    draw_world_text()
    with If(eq(v.show_stats, 1)):
        draw_stats()
    draw_title()
    with If(eq(v.show_graphs, 1)):
        draw_graphs()
    with If(eq(v.show_help, 1)):
        draw_help()
    with Else():
        draw_inspector()
    style(7.5, WHITE, 40, "center", "middle")
    te_draw("H help   ·   1-7 scenes   ·   drag bodies   ·   click to spawn   ·   E blast", 0, -170)


# ------------------------------------------------------------------ input

@proc()
def pick(x, y):
    """Top-most dynamic body under (x, y) -> 'picked' (0 = none)."""
    g = Locals("pk")
    v.picked = 0
    with loop(g.i, B.type.length):
        with If(eq(B.static[g.i], 0) & ~(x < B.minx[g.i]) & ~(x > B.maxx[g.i]) &
                ~(y < B.miny[g.i]) & ~(y > B.maxy[g.i])):
            with If(eq(B.type[g.i], CIRCLE)):
                with If((x - B.x[g.i]) * (x - B.x[g.i]) + (y - B.y[g.i]) * (y - B.y[g.i]) <
                        B.r[g.i] * B.r[g.i]):
                    v.picked = g.i
            with Else():
                g.in_ = 1
                with loop(g.k, B.vn[g.i], B.v0[g.i]):
                    with If((x - VT.wx[g.k]) * VT.wnx[g.k] + (y - VT.wy[g.k]) * VT.wny[g.k] > 0):
                        g.in_ = 0
                with If(eq(g.in_, 1)):
                    v.picked = g.i


@proc()
def random_material():
    v.mat_static = 0
    v.mat_density = 1
    v.mat_fric = 0.5
    v.mat_rest = 0.2
    v.mat_group = 0
    v.mat_col = rand(2, 7)


@proc()
def spawn(x, y):
    random_material()
    with If(eq(v.tool, "circle")):
        add_circle(x, y, rand(8, 20))
    with If(eq(v.tool, "box")):
        add_box(x, y, rand(14, 40), rand(14, 40), rand(0, 360))
    with If(eq(v.tool, "polygon")):
        add_ngon(x, y, rand(3, 7), rand(12, 22), 0.6)


@proc()
def delete_body(i):
    g = Locals("del")
    B.type[i] = DEAD
    B.static[i] = 1
    for f in ("im", "ii", "imr", "iir", "vx", "vy", "w"):
        ListRef("b " + f)[i] = 0
    l["bp order"].delete(l["bp order"].index(i))
    with loop(g.j, J.type.length):
        with If(eq(J.a[g.j], i) | eq(J.b[g.j], i)):
            J.type[g.j] = -1
    with If(eq(v.drag, i)):
        v.drag = 0
    wake_all()


@proc()
def blast(x, y):
    g = Locals("bl")
    with loop(g.i, B.type.length):
        with If(eq(B.static[g.i], 0)):
            g.dx = B.x[g.i] - x
            g.dy = B.y[g.i] - y
            g.d = sqrt(g.dx * g.dx + g.dy * g.dy)
            with If((g.d < 170) & (g.d > 1)):
                wake_body(g.i)
                g.k = 700 * (1 - g.d / 170) / g.d
                B.vx[g.i] = B.vx[g.i] + g.dx * g.k
                B.vy[g.i] = B.vy[g.i] + g.dy * g.k
                B.w[g.i] = B.w[g.i] + rand(-40, 40) / 10
    wake_all()


@proc()
def on_key(k):
    with If(eq(k, "space")):
        v.paused = 1 - v.paused
    with If(eq(k, "n")):
        v.paused = 1
        v.step_once = 1
    with If(eq(k, "r")):
        load_scene(v.scene)
    with If(~(k < 1) & ~(k > 7)):
        load_scene(k)
    for key, tool in (("c", "circle"), ("b", "box"), ("p", "polygon")):
        with If(eq(k, key)):
            v.tool = tool
    with If(eq(k, "x")):
        pick(mouse_x(), mouse_y())
        with If(v.picked > 0):
            delete_body(v.picked)
    with If(eq(k, "e")):
        blast(mouse_x(), mouse_y())
    for key, var in (("v", "show vel"), ("f", "show forces"), ("k", "show contacts"), ("a", "show aabb"),
                     ("g", "show graphs"), ("i", "show stats"), ("h", "show help")):
        with If(eq(k, key)):
            v[var] = 1 - v[var]
    with If(eq(k, "o")):
        v.warm = 1 - v.warm
    with If(eq(k, "m")):
        v.sleeping = 1 - v.sleeping
    with If(eq(k, "s")):
        v.substeps = v.substeps * 2
        with If(v.substeps > 8):
            v.substeps = 1
    with If(eq(k, "t")):
        with If(eq(v.time_scale, 1)):
            v.time_scale = 0.5
        with Else():
            with If(eq(v.time_scale, 0.5)):
                v.time_scale = 0.25
            with Else():
                with If(eq(v.time_scale, 0.25)):
                    v.time_scale = 0.1
                with Else():
                    v.time_scale = 1
    with If(eq(k, "up arrow")):
        v.gravity = v.gravity + 1
    with If(eq(k, "down arrow")):
        v.gravity = v.gravity - 1
    with If(eq(k, "left arrow") & (v.iterations > 1)):
        v.iterations = v.iterations - 1
    with If(eq(k, "right arrow") & (v.iterations < 40)):
        v.iterations = v.iterations + 1
    with If(eq(k, "up arrow") | eq(k, "down arrow")):
        v.gravity = round_(v.gravity * 100) / 100
        wake_all()
    with If(eq(v.warm, 1)):
        v.warm_txt = "on"
    with Else():
        v.warm_txt = "off"
    with If(eq(v.sleeping, 1)):
        v.sleep_txt = "on"
    with Else():
        v.sleep_txt = "off"


@proc()
def handle_input():
    g = Locals("in")
    # keys arrive through the 'when key pressed' hats below (event driven, so a
    # tap shorter than a frame is never missed); handle them in order here
    with RepeatUntil(eq(l.key_queue.length, 0)):
        g.key = l.key_queue[1]
        l.key_queue.delete(1)
        on_key(g.key)
    g.md = 0
    with If(mouse_down()):
        g.md = 1
    with If(eq(g.md, 1) & eq(v.mouse_prev, 0)):
        with If(eq(v.show_help, 1)):
            v.show_help = 0
        with Else():
            pick(mouse_x(), mouse_y())
            with If(v.picked > 0):
                v.drag = v.picked
                to_local(v.drag, mouse_x(), mouse_y())
                v.drag_lx = v.lx
                v.drag_ly = v.ly
                v.drag_fx = 0
                v.drag_fy = 0
                wake_all()
            with Else():
                spawn(mouse_x(), mouse_y())
    with If(eq(g.md, 0)):
        v.drag = 0
    v.mouse_prev = g.md
    with If(eq(v.drag, 0)):
        pick(mouse_x(), mouse_y())
        v.hover = v.picked
    with Else():
        v.hover = v.drag


# ----------------------------------------------------------------- scenes

def label(x, y, s):
    l.lbl_x.add(x)
    l.lbl_y.add(y)
    l.lbl_text.add(s)


def material(fric=0.5, rest=0.2, col=None, group=0, static=0, density=1):
    v.mat_fric = fric
    v.mat_rest = rest
    v.mat_group = group
    v.mat_static = static
    v.mat_density = density
    if col is not None:
        v.mat_col = col


@proc()
def reset_world():
    for f in BODY_FIELDS:
        ListRef("b " + f).clear()
    for f in VERT_FIELDS:
        ListRef("v " + f).clear()
    for f in CONTACT_FIELDS:
        ListRef("c " + f).clear()
    for f in JOINT_FIELDS:
        ListRef("j " + f).clear()
    for lst in (CO.key, CO.pn, CO.pt, l["bp order"], l.lbl_x, l.lbl_y, l.lbl_text, G.ke, G.pe, G.e, G.p):
        lst.clear()
    v.drag = 0
    v.hover = 0
    v.sim_time = 0
    # body 1: the static "world" that joints can pin to
    material(static=1, col=1, fric=0.6, rest=0.1)
    new_body(WORLD, 0, 0, 0)
    set_mass(1, 0, 0)
    # floor and walls
    add_box(0, -170, 470, 20, 0)
    add_box(-235, 0, 10, 380, 0)
    add_box(235, 0, 10, 380, 0)
    random_material()


@proc()
def scene_pyramid():
    g = Locals("s1")
    s = 20
    rows = 12
    with loop(g.r, rows, 0):
        material(col=g.r % 6 + 2)
        g.n = rows - g.r
        with loop(g.c, g.n, 0):
            add_box((g.c - (g.n - 1) / 2) * s, -160 + s / 2 + g.r * s, s, s, 0)
    label(150, -40, "12-row pyramid · 78 boxes")
    label(150, -52, "warm starting keeps it standing (O)")
    label(150, -64, "settled islands sleep (dim) · E to blast")


@proc()
def scene_playground():
    g = Locals("s2")
    material(static=1, col=1, fric=0.6, rest=0.1)
    add_box(-110, 10, 170, 10, -12)
    add_box(110, -70, 170, 10, 14)
    add_box(-60, -110, 60, 10, 0)
    with loop(g.r, 4, 0):
        with loop(g.c, 8, 0):
            random_material()
            g.x = -175 + g.c * 50 + rand(-6, 6)
            g.y = 50 + g.r * 32
            g.k = (g.r * 8 + g.c) % 3
            with If(eq(g.k, 0)):
                add_circle(g.x, g.y, rand(8, 14))
            with If(eq(g.k, 1)):
                add_box(g.x, g.y, rand(14, 26), rand(14, 26), rand(0, 90))
            with If(eq(g.k, 2)):
                add_ngon(g.x, g.y, rand(3, 7), rand(10, 15), 0.6)


@proc()
def scene_cradle():
    g = Locals("s3")
    material(static=1, col=1)
    add_box(0, 116, 230, 8, 0)
    length = 130
    top = 112
    with loop(g.k, 5, 0):
        material(fric=0, rest=1, col=2 + g.k)
        g.x = (g.k - 2) * 32.2
        with If(eq(g.k, 0)):
            add_circle(g.x - length * math.sin(math.radians(55)), top - length * math.cos(math.radians(55)), 16)
        with Else():
            add_circle(g.x, top - length, 16)
        add_distance(1, v.nb, g.x, top, B.x[v.nb], B.y[v.nb])
    label(0, -100, "restitution e = 1 · friction 0 · distance joints")
    label(0, -112, "sequential impulses pass momentum along the row")


@proc()
def scene_bridge():
    g = Locals("s4")
    material(static=1, col=1, fric=0.7)
    add_box(-205, -105, 50, 122, 0)
    add_box(205, -105, 50, 122, 0)
    # planks hang along a parabola: a dead-straight chain between the anchors
    # has no slack and would need infinite tension to sag
    n, x0, x1, y, sag = 15, -175, 175, -40, 28
    pts = [(x0 + (x1 - x0) * k / n, y - sag * 4 * (k / n) * (1 - k / n)) for k in range(n + 1)]
    g.prev = 1
    for k in range(n):
        (ax, ay), (bx, by) = pts[k], pts[k + 1]
        length = math.hypot(bx - ax, by - ay)
        material(fric=0.7, col=3, group=1, density=2)
        add_box(round((ax + bx) / 2, 3), round((ay + by) / 2, 3), round(length - 1, 3), 7,
                round(math.degrees(math.atan2(by - ay, bx - ax)), 3))
        add_revolute(g.prev, v.nb, round(ax, 3), round(ay, 3))
        g.prev = v.nb
    add_revolute(g.prev, 1, x1, y)
    with loop(g.k, 6, 0):
        random_material()
        with If(eq(g.k % 2, 0)):
            add_box(-120 + g.k * 48, 40 + g.k * 12, 26, 26, rand(0, 45))
        with Else():
            add_circle(-120 + g.k * 48, 40 + g.k * 12, 13)
    label(0, -95, "15 planks · 16 revolute joints")


@proc()
def scene_dominoes():
    g = Locals("s5")
    material(static=1, col=1, fric=0.4)
    add_box(-190, -60, 110, 8, -35)
    with loop(g.k, 16, 0):
        material(fric=0.4, rest=0.05, col=g.k % 6 + 2)
        add_box(-110 + g.k * 20, -160 + 24, 7, 48, 0)
    material(fric=0.4, rest=0.1, col=3, density=3)
    add_circle(-218, -6, 11)
    label(40, -40, "a heavy ball rolls down the ramp...")


@proc()
def scene_ramps():
    g = Locals("s6")
    ang = -25
    th = math.radians(ang)
    dx, dy = math.cos(th), math.sin(th)
    nx, ny = -math.sin(th), math.cos(th)
    for idx, (cy, mu) in enumerate(((105, 0.05), (25, 0.30), (-55, 0.80))):
        cx = -95
        material(static=1, col=1, fric=1)
        add_box(cx, cy, 190, 10, ang)
        material(fric=mu * mu, rest=0, col=2 + idx * 2)
        bx = cx - 70 * dx + nx * 17.5
        by = cy - 70 * dy + ny * 17.5
        add_box(round(bx, 2), round(by, 2), 24, 24, ang)
        label(cx + 120, cy + 8, "µ = %.2f" % mu)
        label(cx + 120, cy - 4, ["slides fast", "slides slowly", "sticks: µ > tan 25° = 0.47"][idx])
    v.show_forces = 1


@proc()
def scene_joints():
    g = Locals("s7")
    # double pendulum
    material(col=5, group=2)
    add_box(-125, 110, 70, 8, 0)
    add_revolute(1, v.nb, -160, 110)
    g.a = v.nb
    material(col=6, group=2)
    add_box(-90, 75, 70, 8, 90)
    add_revolute(g.a, v.nb, -90, 110)
    label(-150, 135, "double pendulum")
    # chain with a weight
    g.prev = 1
    with loop(g.k, 10, 0):
        material(col=2, group=3)
        add_box(26 + g.k * 12 + 6, 140, 13, 5, 0)
        add_revolute(g.prev, v.nb, 26 + g.k * 12, 140)
        g.prev = v.nb
    material(col=3, group=3, density=3)
    add_circle(26 + 120 + 10, 140, 10)
    add_revolute(g.prev, v.nb, 26 + 120, 140)
    label(60, 158, "chain · 11 revolute joints")
    # spring-hung box
    material(col=4)
    add_box(195, -20, 26, 26, 0)
    add_spring(1, v.nb, 195, 60, 195, -7, 45, 1.2, 0.05)
    label(195, 66, "spring 1.2 Hz")
    # two-body oscillator on the floor
    material(col=7, fric=0.1)
    add_box(-60, -148, 24, 24, 0)
    g.a = v.nb
    material(col=7, fric=0.1)
    add_box(40, -148, 24, 24, 0)
    add_spring(g.a, v.nb, -48, -148, 28, -148, 50, 2, 0.02)
    label(-10, -125, "spring oscillator (momentum conserved)")


@proc()
def load_scene(n):
    reset_world()
    v.scene = n
    v.show_forces = 0
    v.show_contacts = 0
    v.show_vel = 0
    for k, sc in enumerate((scene_pyramid, scene_playground, scene_cradle, scene_bridge, scene_dominoes,
                            scene_ramps, scene_joints), start=1):
        with If(eq(n, k)):
            sc()
    # the cradle's middle balls sit still between hits; keep them awake there
    with If(eq(n, 3)):
        v.sleeping = 0
        v.sleep_txt = "off"
    with Else():
        v.sleeping = 1
        v.sleep_txt = "on"
    with If(eq(n, 1)):
        v.show_contacts = 1
    with If(eq(n, 3) | eq(n, 5)):
        v.show_vel = 1


# --------------------------------------------------------------- main loop

@proc()
def init_settings():
    v.gravity = 9.81
    v.iterations = 10
    v.substeps = 2
    v.time_scale = 1
    v.warm = 1
    v.warm_txt = "on"
    v.sleeping = 1
    v.sleep_txt = "on"
    v.lin_damping = 0
    v.joint_beta = 0.2      # distance joints (Baumgarte)
    v.joint_hz = 30         # revolute joint stiffness (soft constraint frequency)
    v.joint_passes = 1
    v.ang_damping = 0.05
    v.drag_k = 160          # (2π·2 Hz)²
    v.drag_c = 18           # 2·0.7·(2π·2 Hz)
    v.paused = 0
    v.step_once = 0
    v.tool = "box"
    v.show_stats = 1
    v.show_graphs = 1
    v.show_help = 0
    v.show_aabb = 0
    v.debug_no_render = 0
    v.mouse_prev = 0
    v.fps = 60
    v.frames = 0
    v.fps_t = timer()
    v.phys_ms = 0
    v.draw_ms = 0
    v.last_h = 1 / 120
    v.max_pen = 0
    v.pairs = 0
    v.warm_hits = 0
    l.key_queue.clear()


@proc()
def frame():
    g = Locals("frm")
    g.t0 = clock_ms()
    handle_input()
    with If(eq(v.paused, 0) | eq(v.step_once, 1)):
        physics_frame()
        v.step_once = 0
    g.t1 = clock_ms()
    compute_metrics()
    with If(eq(v.debug_no_render, 0)):
        render()
    g.t2 = clock_ms()
    # 'timer' only advances between frames, so time the work with the real clock
    v.phys_ms = v.phys_ms * 0.9 + (g.t1 - g.t0) * 0.1
    v.draw_ms = v.draw_ms * 0.9 + (g.t2 - g.t1) * 0.1
    g.t2 = timer()
    v.frames = v.frames + 1
    with If(g.t2 - v.fps_t > 1):
        v.fps = v.frames / (g.t2 - v.fps_t)
        v.frames = 0
        v.fps_t = g.t2


@P.script("event_whenflagclicked")
def main():
    hide()
    v["TE newline"] = "\n"
    te_reset()
    init_settings()
    load_scene(1)
    with Forever():
        frame()


# ------------------------------------------------------------------ output

README = """2D RIGID-BODY PHYSICS  (pen-rendered, built for TurboWarp)

Everything is drawn with pen; labels use the pen text engine in this sprite.
Run in TurboWarp (60 FPS, high-quality pen, no fencing are stored in the project).

ENGINE
 • circles + convex polygons, SAT / clipping contact manifolds (2 points)
 • sort-and-sweep broadphase (insertion-sorted list, ~O(n) per step)
 • sequential-impulse solver: accumulated impulses, Coulomb friction,
   restitution, Baumgarte stabilisation, warm starting by contact feature key
 • joints: revolute, distance, soft springs, mouse spring
 • union-find islands + sleeping
 • units: 50 px = 1 m, density 1 kg/m², so every metric reads in SI units

DATA (parallel lists)
 b … per body   v … polygon vertices   c … contacts   j … joints   g … graphs

KEYS   H shows the full list in the project.

This project is generated by tools/build_physics_sb3.py in the repository;
edit that script and rebuild rather than editing blocks by hand if you want to
keep the two in sync."""
P.add_comment(P.sprite, README, 2000, 0, 560, 520)

TWCONFIG = ('Configuration for https://turbowarp.org/\nYou can move, resize, and minimize this comment, but '
            'don\'t edit it by hand. This comment can be deleted to remove the stored settings.\n'
            '{"framerate":60,"runtimeOptions":{"maxClones":300,"miscLimits":true,"fencing":false},'
            '"interpolation":false,"turbo":false,"hq":true,"width":480,"height":360} // _twconfig_')
P.add_comment(P.stage, TWCONFIG, 0, 0, 350, 170)
P.pj["meta"]["agent"] = "physics-2d-builder (sb3dsl)"

if os.environ.get("PHYS_NO_SAVE"):
    raise SystemExit(0)
P.build()
digest = P.save(OUT)
nblocks = sum(1 for b in P.blocks.values() if isinstance(b, dict))
print(f"wrote {OUT}: {nblocks} blocks in sprite, {len(P.procs)} new custom blocks, project.json md5 {digest}")
