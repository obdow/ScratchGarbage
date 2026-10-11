"""Part definitions: pins, drawing ops (lines + colour classes) and texts.

Coordinates are world units relative to the part centre (grid = 10).
Drawing op kinds (see drawops / setcls in logic_sim.sl):
  (1, x1, y1, x2, y2, width)          line (a dot when both ends match)
  (2, cls, index, colour1, colour2)   colour class
     1 body fill / 2 outline (colour2 = hovered), 3 input value, 4 output value,
     5 visible if state=1, 6 visible if state=0, 7 state ? c1 : c2,
     8 LED body, 9 LED glow, 10 segment lit ? c1 : c2, 11 segment glow,
     12 constant colour, 13 visible when input is 1
"""
import math

FILL, FILLH = 0x1a2330, 0x24324a
LINE, LINEH = 0x8fa3b8, 0xeef4fb
HIGH, LOW = 0x3dff8a, 0x3a4b5c
PINLOW = 0x54687c
SW_ON, SW_OFF = 0x3dff8a, 0x5a6878
BTN_ON, BTN_OFF = 0xff5a5a, 0x6a2e33
SEG_ON, SEG_OFF, SEG_GLOW = 0xff6a3d, 0x2c1f1c, 0x55ff6a3d
DECO = 0x5c6b7d

# 7-segment patterns (a b c d e f g) for 0-F
SEGTAB = ['1111110', '0110000', '1101101', '1111001', '0110011', '1011011', '1011111', '1110000',
          '1111111', '1111011', '1110111', '0011111', '1001110', '0111101', '1001111', '1000111']


def rnd(v):
    v = round(v, 2)
    return int(v) if float(v).is_integer() else v


class Shape:
    def __init__(self):
        self.ops = []
        self.texts = []

    def cls(self, c, idx=0, c1=0, c2=0):
        self.ops.append((2, c, idx, c1, c2, 0))

    def line(self, x1, y1, x2, y2, w):
        self.ops.append((1, rnd(x1), rnd(y1), rnd(x2), rnd(y2), w))

    def dot(self, x, y, w):
        self.line(x, y, x, y, w)

    def poly(self, pts, w, closed=False):
        if closed:
            pts = list(pts) + [pts[0]]
        for a, b in zip(pts, pts[1:]):
            self.line(a[0], a[1], b[0], b[1], w)

    def text(self, s, x, y, size, align=1):
        self.texts.append((s, x, y, size, align))

    def fill_rows(self, extent, y0, y1, step=5):
        """Fill a shape whose row extent at height y is extent(y) -> (xl, xr)."""
        n = max(1, int(math.ceil((y1 - y0) / step)))
        st = (y1 - y0) / n
        for i in range(n):
            ya, yb = y0 + i * st, y0 + (i + 1) * st
            # average of the edge and middle extents: round caps then hug curved edges
            xl = (max(extent(ya)[0], extent(yb)[0]) + extent((ya + yb) / 2)[0]) / 2
            xr = (min(extent(ya)[1], extent(yb)[1]) + extent((ya + yb) / 2)[1]) / 2
            # extend slightly so neighbouring rows overlap without gaps
            w = st + 0.8
            if xr - xl <= w:
                self.dot((xl + xr) / 2, (ya + yb) / 2, max(1, xr - xl))
            else:
                self.line(xl + w / 2, (ya + yb) / 2, xr - w / 2, (ya + yb) / 2, w)

    def fill_rect(self, x1, y1, x2, y2):
        self.fill_rows(lambda y: (x1, x2), y1, y2, 8)


def arc(cx, cy, r, a0, a1, n):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def rect_pts(x1, y1, x2, y2):
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def pill_pts(x1, x2, r):
    """Outline of a horizontal stadium from x1..x2 (centres of the end caps) radius r."""
    return arc(x2, 0, r, -90, 90, 8) + arc(x1, 0, r, 90, 270, 8)


def in_stub(s, idx, px, py, x_edge):
    s.cls(3, idx, HIGH, PINLOW)
    s.line(px, py, x_edge, py, 2)
    s.dot(px, py, 4.5)


def out_stub(s, idx, px, py, x_edge):
    s.cls(4, idx, HIGH, PINLOW)
    s.line(x_edge, py, px, py, 2)
    s.dot(px, py, 4.5)


def bubble(s, cx):
    s.cls(1, 0, FILL, FILLH)
    s.dot(cx, 0, 8)
    s.cls(2, 0, LINE, LINEH)
    s.poly(arc(cx, 0, 4, 0, 360, 12), 2)


# ---------------------------------------------------------------- gates
def or_back(y):
    return -20 + 7 * (1 - (y / 20) ** 2)


def or_front(y):
    y = min(abs(y), 20)
    return -12 + 32 * math.sqrt(max(0, 1 - y / 20))


def gate(kind):
    s = Shape()
    inv = kind in ('NAND', 'NOR', 'XNOR', 'NOT')
    if kind in ('NOT', 'BUF'):
        s.cls(1, 0, FILL, FILLH)
        s.fill_rows(lambda y: (-20, -20 + 34 * (1 - abs(y) / 16)), -16, 16, 4)
        s.cls(2, 0, LINE, LINEH)
        s.poly([(-20, 16), (14, 0), (-20, -16)], 2, closed=True)
        if inv:
            bubble(s, 18)
        in_stub(s, 0, -30, 0, -20)
        out_stub(s, 0, 30, 0, 22 if inv else 14)
        return s
    base = kind.replace('N', '', 1) if kind in ('NAND', 'NOR') else ('XOR' if kind == 'XNOR' else kind)
    s.cls(1, 0, FILL, FILLH)
    if base == 'AND':
        s.fill_rows(lambda y: (-20, math.sqrt(max(0, 400 - y * y))), -20, 20, 4)
        s.cls(2, 0, LINE, LINEH)
        s.poly([(-20, 20), (0, 20)] + arc(0, 0, 20, 90, -90, 14)[1:-1] + [(0, -20), (-20, -20)], 2, closed=True)
        edge = [-20, -20]
    else:
        s.fill_rows(lambda y: (or_back(y), or_front(y)), -20, 20, 4)
        s.cls(2, 0, LINE, LINEH)
        back = [(or_back(y), y) for y in [20 - 40 * i / 10 for i in range(11)]]
        front_top = [(or_front(y), y) for y in [20 - 20 * i / 10 for i in range(11)]]
        front_bot = [(x, -y) for x, y in reversed(front_top)]
        s.poly([(-20, 20)] + front_top + front_bot[1:] + [(-20, -20)], 2)
        s.poly(back, 2)
        edge = [or_back(10), or_back(-10)]
        if base == 'XOR':
            s.poly([(x - 6, y) for x, y in back], 2)
            edge = [e - 6 for e in edge]
    if inv:
        bubble(s, 24)
    in_stub(s, 0, -30, 10, edge[0])
    in_stub(s, 1, -30, -10, edge[1])
    out_stub(s, 0, 30, 0, 28 if inv else 20)
    return s


# ---------------------------------------------------------------- inputs / outputs
def switch():
    s = Shape()
    s.cls(1, 0, FILL, FILLH)
    s.line(-3, 0, 3, 0, 22)
    s.cls(2, 0, LINE, LINEH)
    s.poly(pill_pts(-3, 3, 11), 2, closed=True)
    s.cls(5, 0, SW_ON)
    s.dot(5, 0, 14)
    s.cls(6, 0, SW_OFF)
    s.dot(-5, 0, 14)
    out_stub(s, 0, 20, 0, 14)
    return s


def button():
    s = Shape()
    s.cls(1, 0, FILL, FILLH)
    s.dot(0, 0, 24)
    s.cls(2, 0, LINE, LINEH)
    s.poly(arc(0, 0, 12, 0, 360, 16), 2)
    s.cls(7, 0, BTN_ON, BTN_OFF)
    s.dot(0, 0, 14)
    out_stub(s, 0, 20, 0, 12)
    return s


def clock():
    s = Shape()
    s.cls(1, 0, FILL, FILLH)
    s.line(-4, 0, 4, 0, 28)
    s.cls(2, 0, LINE, LINEH)
    s.poly(pill_pts(-4, 4, 14), 2, closed=True)
    s.cls(4, 0, HIGH, PINLOW)
    s.poly([(-11, -5), (-6, -5), (-6, 5), (0, 5), (0, -5), (6, -5), (6, 5), (11, 5)], 2)
    out_stub(s, 0, 30, 0, 18)
    return s


def const():
    s = Shape()
    s.cls(1, 0, FILL, FILLH)
    s.line(-1, 0, 1, 0, 20)
    s.cls(2, 0, LINE, LINEH)
    s.poly([(-10, 10), (10, 10), (10, -10), (-10, -10)], 2, closed=True)
    s.cls(5, 0, HIGH)
    s.poly([(-3, 3), (1, 6), (1, -6)], 2.2)
    s.cls(6, 0, LINE)
    s.poly([(x * 0.7, y) for x, y in arc(0, 0, 6, 0, 360, 12)], 2.2)
    out_stub(s, 0, 20, 0, 10)
    return s


def led():
    s = Shape()
    s.cls(9)
    s.dot(0, 0, 36)
    s.cls(8)
    s.dot(0, 0, 24)
    s.cls(12, 0, 0x60ffffff)
    s.dot(-4, 4, 5)
    s.cls(2, 0, LINE, LINEH)
    s.poly(arc(0, 0, 12, 0, 360, 16), 2)
    in_stub(s, 0, -20, 0, -12)
    return s


def seg_digit(s, cx, cy, sel_cls=10):
    w, h = 10, 22
    segs = [((-w + 3, h), (w - 3, h)),          # a
            ((w, h - 3), (w, 3)),               # b
            ((w, -3), (w, -h + 3)),             # c
            ((-w + 3, -h), (w - 3, -h)),        # d
            ((-w, -3), (-w, -h + 3)),           # e
            ((-w, h - 3), (-w, 3)),             # f
            ((-w + 3, 0), (w - 3, 0))]          # g
    for i, ((x1, y1), (x2, y2)) in enumerate(segs):
        s.cls(11, i, SEG_GLOW)
        s.line(cx + x1, cy + y1, cx + x2, cy + y2, 9)
    for i, ((x1, y1), (x2, y2)) in enumerate(segs):
        s.cls(10, i, SEG_ON, SEG_OFF)
        s.line(cx + x1, cy + y1, cx + x2, cy + y2, 4.5)


def box(s, x1, y1, x2, y2):
    s.cls(1, 0, FILL, FILLH)
    s.fill_rect(x1, y1, x2, y2)
    s.cls(2, 0, LINE, LINEH)
    s.poly(rect_pts(x1, y1, x2, y2), 2, closed=True)


def hexdisp():
    s = Shape()
    box(s, -28, -40, 28, 40)
    seg_digit(s, 6, 0)
    for i, lab in enumerate(['1', '2', '4', '8']):
        y = 30 - 20 * i
        in_stub(s, i, -40, y, -28)
        s.text(lab, -22, y, 7, 1)
    return s


def seg7():
    s = Shape()
    box(s, -28, -40, 28, 40)
    seg_digit(s, 6, 0)
    for i, lab in enumerate('abcdefg'):
        y = 30 - 10 * i
        in_stub(s, i, -40, y, -28)
        s.text(lab, -22, y, 7, 1)
    return s


def dff():
    s = Shape()
    box(s, -20, -24, 20, 24)
    s.cls(2, 0, LINE, LINEH)
    s.poly([(-20, -4), (-12, -10), (-20, -16)], 1.5)
    s.line(5, -3.5, 13, -3.5, 1.2)
    in_stub(s, 0, -30, 10, -20)
    in_stub(s, 1, -30, -10, -20)
    out_stub(s, 0, 30, 10, 20)
    out_stub(s, 1, 30, -10, 20)
    s.text('D', -15, 10, 9, 0)
    s.text('Q', 15, 10, 9, 2)
    s.text('Q', 15, -10, 9, 2)
    return s


def dec7():
    s = Shape()
    box(s, -28, -40, 28, 40)
    for i, lab in enumerate(['1', '2', '4', '8']):
        y = 30 - 20 * i
        in_stub(s, i, -40, y, -28)
        s.text(lab, -22, y, 7, 1)
    for i, lab in enumerate('abcdefg'):
        y = 30 - 10 * i
        out_stub(s, i, 40, y, 28)
        s.text(lab, 22, y, 7, 1)
    s.text('DEC', 0, 0, 8, 1)
    return s


def table():
    s = Shape()
    box(s, -40, -30, 40, 30)
    s.cls(12, 0, 0x34404e)
    s.line(-28, 29, -28, -29, 1)
    s.line(-26, 15, 39, 15, 1)
    s.line(14, 27, 14, -29, 1)
    for i, lab in enumerate('ABY'):
        y = 10 - 10 * i
        in_stub(s, i, -50, y, -40)
        s.text(lab, -34, y, 7, 1)
    return s


def numdisp():
    s = Shape()
    box(s, -30, -46, 30, 36)
    for i in range(8):
        y = 30 - 10 * i
        in_stub(s, i, -40, y, -30)
        s.text(str(2 ** i), -26, y, 6, 0)
    return s


def label():
    return Shape()


# ---------------------------------------------------------------- part list
# name, desc (palette tooltip), hint (status bar), inputs, outputs, shape fn,
# half-width, half-height, default state, default param, label position (1 left, 2 right, 3 above)
G_HINT = ' gate  |  drag to move  |  X deletes  |  L adds a label'
PARTS = [
    ('AND', 'Output is 1 only when both inputs are 1.', 'AND' + G_HINT,
     [(-30, 10), (-30, -10)], [(30, 0)], lambda: gate('AND'), 20, 20, 0, 0, 3),
    ('OR', 'Output is 1 when either input (or both) is 1.', 'OR' + G_HINT,
     [(-30, 10), (-30, -10)], [(30, 0)], lambda: gate('OR'), 20, 20, 0, 0, 3),
    ('NOT', 'Inverter: the output is the opposite of the input.', 'NOT' + G_HINT,
     [(-30, 0)], [(30, 0)], lambda: gate('NOT'), 20, 16, 0, 0, 3),
    ('NAND', 'NOT-AND: output is 0 only when both inputs are 1. Every other gate can be built from NANDs.',
     'NAND' + G_HINT, [(-30, 10), (-30, -10)], [(30, 0)], lambda: gate('NAND'), 20, 20, 0, 0, 3),
    ('NOR', 'NOT-OR: output is 1 only when both inputs are 0.', 'NOR' + G_HINT,
     [(-30, 10), (-30, -10)], [(30, 0)], lambda: gate('NOR'), 20, 20, 0, 0, 3),
    ('XOR', 'Exclusive OR: output is 1 when the inputs are different.', 'XOR' + G_HINT,
     [(-30, 10), (-30, -10)], [(30, 0)], lambda: gate('XOR'), 20, 20, 0, 0, 3),
    ('XNOR', 'Equality gate: output is 1 when both inputs are the same.', 'XNOR' + G_HINT,
     [(-30, 10), (-30, -10)], [(30, 0)], lambda: gate('XNOR'), 20, 20, 0, 0, 3),
    ('Buffer', 'Passes its input straight through (after one tick of delay).', 'Buffer  |  drag to move  |  X deletes',
     [(-30, 0)], [(30, 0)], lambda: gate('BUF'), 20, 16, 0, 0, 3),
    ('Switch', 'Toggle switch: click it to flip its output between 0 and 1.',
     'Switch  |  click to flip  |  drag to move  |  L adds a label', [], [(20, 0)], switch, 14, 11, 0, 0, 1),
    ('Button', 'Push button: outputs 1 only while you hold the mouse down on it.',
     'Button  |  hold the mouse on it  |  drag to move', [], [(20, 0)], button, 12, 12, 0, 0, 1),
    ('Clock', 'Flips between 0 and 1 by itself. T is the period in ticks; click it to change T.',
     'Clock  |  click to change the period  |  drag to move', [], [(30, 0)], clock, 18, 14, 0, 8, 3),
    ('Constant', 'A fixed 1 (click it to make it a fixed 0).', 'Constant  |  click to flip  |  drag to move',
     [], [(20, 0)], const, 10, 10, 1, 0, 1),
    ('LED', 'Lights up when its input is 1. Click it to change its colour.',
     'LED  |  click to change colour  |  L adds a label', [(-20, 0)], [], led, 12, 12, 0, 1, 2),
    ('Hex display', 'Shows the 4-bit number on its inputs (worth 1, 2, 4 and 8) as a digit 0-F.',
     'Hex display  |  inputs are worth 1, 2, 4, 8', [(-40, 30), (-40, 10), (-40, -10), (-40, -30)], [],
     hexdisp, 28, 40, 0, 0, 3),
    ('7-segment', 'Each input a-g lights one segment of the display directly.',
     '7-segment display  |  inputs a-g drive one segment each',
     [(-40, 30 - 10 * i) for i in range(7)], [], seg7, 28, 40, 0, 0, 3),
    ('D flip-flop', 'On the rising edge of the clock (input 2 going 0 to 1) it copies D to Q. Q-bar is the opposite of Q.',
     'D flip-flop  |  copies D to Q when the clock rises', [(-30, 10), (-30, -10)], [(30, 10), (30, -10)],
     dff, 20, 24, 0, 0, 3),
    ('Decoder', 'Turns a 4-bit number (inputs worth 1, 2, 4, 8) into the a-g signals for a 7-segment display.',
     '7-segment decoder  |  4-bit number in, segments a-g out',
     [(-40, 30), (-40, 10), (-40, -10), (-40, -30)], [(40, 30 - 10 * i) for i in range(7)],
     dec7, 28, 40, 0, 0, 3),
    ('Text', 'A text note for the board. Click it to edit the text.', 'Text  |  click to edit  |  drag to move',
     [], [], label, 10, 10, 0, 12, 3),
    ('Truth table', 'Wire inputs A and B and output Y of a circuit to it: it fills in the table as you try each combination. Click to clear.',
     'Truth table  |  wire A, B and Y  |  click to clear', [(-50, 10), (-50, 0), (-50, -10)], [],
     table, 40, 30, '????', 0, 3),
    ('Number', 'Shows the 8-bit number on its inputs (worth 1, 2, 4 ... 128) in decimal.',
     'Number display  |  inputs are worth 1, 2, 4 ... 128', [(-40, 30 - 10 * i) for i in range(8)], [],
     numdisp, 30, 46, 0, 0, 3),
]
TYPE = {p[0]: i + 1 for i, p in enumerate(PARTS)}


def pins(tname):
    p = PARTS[TYPE[tname] - 1]
    return p[3], p[4]


def part_tables():
    d = {k: [] for k in ['tp_name', 'tp_desc', 'tp_hint', 'tp_nin', 'tp_nout', 'tp_pin0', 'pin_dx', 'pin_dy',
                         'tp_hw', 'tp_hh', 'tp_op0', 'tp_opn', 'op_k', 'op_a', 'op_b', 'op_c', 'op_d', 'op_e',
                         'tp_tx0', 'tp_txn', 'tx_s', 'tx_x', 'tx_y', 'tx_sz', 'tx_al',
                         'tp_ics', 'tp_icx', 'tp_icy', 'tp_lpos', 'tp_defstate', 'tp_defparam']}
    for (name, desc, hint, ins, outs, fn, hw, hh, dstate, dparam, lpos) in PARTS:
        s = fn()
        d['tp_name'].append(name)
        d['tp_desc'].append(desc)
        d['tp_hint'].append(hint)
        d['tp_nin'].append(len(ins))
        d['tp_nout'].append(len(outs))
        d['tp_pin0'].append(len(d['pin_dx']) + 1)
        for x, y in ins + outs:
            d['pin_dx'].append(x)
            d['pin_dy'].append(y)
        d['tp_hw'].append(hw)
        d['tp_hh'].append(hh)
        d['tp_op0'].append(len(d['op_k']) + 1)
        d['tp_opn'].append(len(s.ops))
        for op in s.ops:
            for key, v in zip(['op_k', 'op_a', 'op_b', 'op_c', 'op_d', 'op_e'], op):
                d[key].append(v)
        d['tp_tx0'].append(len(d['tx_s']) + 1)
        d['tp_txn'].append(len(s.texts))
        for t in s.texts:
            for key, v in zip(['tx_s', 'tx_x', 'tx_y', 'tx_sz', 'tx_al'], t):
                d[key].append(v)
        # palette icon: fit the line ops into a 22 x 22 cell
        xs = [v for op in s.ops if op[0] == 1 for v in (op[1], op[3])] or [0]
        ys = [v for op in s.ops if op[0] == 1 for v in (op[2], op[4])] or [0]
        w = max(xs) - min(xs) + 4
        h = max(ys) - min(ys) + 4
        sc = min(23 / w, 23 / h, 0.7)
        d['tp_ics'].append(rnd(sc))
        d['tp_icx'].append(rnd((max(xs) + min(xs)) / 2))
        d['tp_icy'].append(rnd((max(ys) + min(ys)) / 2))
        d['tp_lpos'].append(lpos)
        d['tp_defstate'].append(dstate)
        d['tp_defparam'].append(dparam)
    return d
