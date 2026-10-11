"""Demo circuits. Each is built with a tiny API and serialised to the same
"LS1;..." code format the project uses for Save / Load."""
from parts import TYPE, pins


class Circuit:
    def __init__(self):
        self.parts = []   # [type, x, y, state, param, label]
        self.wires = []   # (dst, dstpin, src, srcpin, mid)

    def add(self, tname, x, y, label='', state=None, param=None):
        from parts import PARTS
        p = PARTS[TYPE[tname] - 1]
        self.parts.append([TYPE[tname], x, y, p[8] if state is None else state,
                           p[9] if param is None else param, label])
        return len(self.parts)

    def text(self, x, y, s, size=12):
        return self.add('Text', x, y, label=s, param=size)

    def wire(self, src, dst, srcpin=0, dstpin=0, mid=''):
        if mid is None:
            mid = ''
        """Connect output `srcpin` of part `src` to input `dstpin` of part `dst`."""
        from parts import PARTS
        ins = PARTS[self.parts[dst - 1][0] - 1][3]
        outs = PARTS[self.parts[src - 1][0] - 1][4]
        assert dstpin < len(ins) and srcpin < len(outs), (src, dst, srcpin, dstpin)
        for w in self.wires:
            assert not (w[0] == dst and w[1] == dstpin), 'input already connected'
        self.wires.append((dst, dstpin, src, srcpin, mid))

    def pin_in(self, part, i):
        t, x, y = self.parts[part - 1][:3]
        from parts import PARTS
        dx, dy = PARTS[t - 1][3][i]
        return x + dx, y + dy

    def pin_out(self, part, i):
        t, x, y = self.parts[part - 1][:3]
        from parts import PARTS
        dx, dy = PARTS[t - 1][4][i]
        return x + dx, y + dy

    def code(self):
        out = ['LS1']
        for t, x, y, st, pa, lab in self.parts:
            assert ',' not in lab and ';' not in lab
            out.append('P,%d,%d,%d,%s,%s,%s' % (t, x, y, st, pa, lab))
        for d, dp, s, sp, mid in self.wires:
            out.append('W,%d,%d,%d,%d,%s' % (d, dp, s, sp, '' if mid is None else mid))
        return ';'.join(out)


DEMOS = []


def demo(name, desc, speed=4, info=1):
    def deco(fn):
        c = Circuit()
        fn(c)
        DEMOS.append({'name': name, 'desc': desc, 'code': c.code(), 'speed': speed, 'info': info})
        return fn
    return deco


# ------------------------------------------------------------------ gates
def gate_block(c, g, y, x=0):
    """Two switches -> gate -> LED, plus a truth-table probe below-right."""
    one = g in ('NOT', 'Buffer')
    if one:
        a = c.add('Switch', x - 130, y, 'A')
    else:
        a = c.add('Switch', x - 130, y + 10, 'A')
        b = c.add('Switch', x - 130, y - 10, 'B')
    gate = c.add(g, x - 50, y, g)
    led = c.add('LED', x + 30, y)
    tab = c.add('Truth table', x + 120, y - 40)
    c.wire(a, gate, 0, 0)
    c.wire(a, tab, 0, 0, mid=x - 90)
    if not one:
        c.wire(b, gate, 0, 1)
        c.wire(b, tab, 0, 1, mid=x - 100)
    c.wire(gate, led)
    c.wire(gate, tab, 0, 2, mid=x)
    return gate


@demo('AND and OR',
      'Click the switches to set inputs A and B. An AND gate outputs 1 only when A and B are both 1; '
      'an OR gate outputs 1 when at least one of them is 1. The truth-table probes fill in a row each time '
      'you try a new combination - try all four!')
def d_and_or(c):
    gate_block(c, 'AND', 60)
    gate_block(c, 'OR', -60)


@demo('NOT and XOR',
      'NOT (an inverter) flips its input: 0 becomes 1 and 1 becomes 0. XOR, "exclusive or", outputs 1 when '
      'its inputs are different - it is the heart of binary addition (see the adder demos).')
def d_not_xor(c):
    gate_block(c, 'NOT', 60)
    gate_block(c, 'XOR', -60)


@demo('NAND, NOR and XNOR',
      'The little circle (a "bubble") on a gate\'s output means NOT. NAND = NOT AND, NOR = NOT OR and '
      'XNOR = NOT XOR, so each truth table is the exact opposite of AND, OR and XOR.')
def d_inverted(c):
    gate_block(c, 'NAND', 115)
    gate_block(c, 'NOR', 0)
    gate_block(c, 'XNOR', -115)


# ------------------------------------------------------------------ adders
def full_adder(c, oy, a, b, cin, ox=0, cin_mid=None):
    """Gate-level full adder (130 units tall). a, b, cin are (part, pin) sources.
    Returns (xor2, orgate)."""
    x1 = c.add('XOR', ox - 110, oy - 20)
    x2 = c.add('XOR', ox - 10, oy - 30)
    n2 = c.add('AND', ox - 10, oy - 80)
    n1 = c.add('AND', ox - 110, oy - 110)
    o = c.add('OR', ox + 80, oy - 90)
    c.wire(a[0], x1, a[1], 0, mid=ox - 170)
    c.wire(b[0], x1, b[1], 1, mid=ox - 160)
    c.wire(a[0], n1, a[1], 0, mid=ox - 170)
    c.wire(b[0], n1, b[1], 1, mid=ox - 160)
    c.wire(x1, x2, 0, 0)
    c.wire(x1, n2, 0, 0, mid=ox - 60)
    c.wire(cin[0], x2, cin[1], 1, mid=ox - 50 if cin_mid is None else cin_mid)
    c.wire(cin[0], n2, cin[1], 1, mid=ox - 50 if cin_mid is None else cin_mid)
    c.wire(n2, o, 0, 0)
    c.wire(n1, o, 0, 1, mid=ox + 40)
    return x2, o


@demo('Half and full adders',
      'Adding two bits: the half adder\'s XOR gives the sum bit S and its AND gives the carry C (1 + 1 = 10 in binary). '
      'A full adder also adds a carry-in, so full adders can be chained to add bigger numbers.')
def d_adders(c):
    c.text(-110, 175, 'Half adder', 12)
    a = c.add('Switch', -210, 100, 'A')
    b = c.add('Switch', -210, 80, 'B')
    x = c.add('XOR', -110, 130)
    n = c.add('AND', -110, 60)
    c.wire(a, x, 0, 0, mid=-170)
    c.wire(b, x, 0, 1, mid=-160)
    c.wire(a, n, 0, 0, mid=-170)
    c.wire(b, n, 0, 1, mid=-160)
    s = c.add('LED', 10, 130, 'S')
    k = c.add('LED', 10, 60, 'C')
    c.wire(x, s)
    c.wire(n, k)
    c.text(-110, 25, 'Full adder', 12)
    a = c.add('Switch', -210, -10, 'A')
    b = c.add('Switch', -210, -40, 'B')
    ci = c.add('Switch', -210, -70, 'Cin')
    x2, o = full_adder(c, 0, (a, 0), (b, 0), (ci, 0))
    s = c.add('LED', 170, -30, 'S')
    k = c.add('LED', 170, -90, 'Cout')
    c.wire(x2, s)
    c.wire(o, k)


@demo('4-bit ripple-carry adder',
      'Four full adders chained: each carry-out feeds the next carry-in. Set A and B with the switches (bit 0 is at the '
      'top, worth 1; bit 3 is worth 8). The sum appears in binary on the LEDs and in decimal on the right. '
      'Slow the simulation down and watch the carry ripple through.', speed=3, info=0)
def d_adder4(c):
    pitch = 150
    prev = None
    sums = []
    for i in range(4):
        oy = 210 - i * pitch
        a = c.add('Switch', -210, oy - 10, 'A%d' % i)
        b = c.add('Switch', -210, oy - 40, 'B%d' % i)
        if prev is None:
            x2, o = full_adder(c, oy, (a, 0), (b, 0), (c.add('Constant', -210, oy - 70, 'carry in', state=0), 0))
        else:
            x2, o = full_adder(c, oy, (a, 0), (b, 0), (prev, 0), cin_mid=oy + 10)
        prev = o
        sums.append(x2)
        led = c.add('LED', 170, oy - 50, 'S%d' % i)
        c.wire(x2, led, mid=140)
    cout = c.add('LED', 170, 210 - 3 * pitch - 110, 'Cout')
    c.wire(prev, cout)
    num = c.add('Number', 330, -50, 'A + B')
    for i, x2 in enumerate(sums):
        c.wire(x2, num, 0, i, mid=230 + 10 * i)
    c.wire(prev, num, 0, 4, mid=270)
    c.text(-80, 245, 'Click the switches: A = A3 A2 A1 A0 and B = B3 B2 B1 B0 in binary', 11)


# ------------------------------------------------------------------ memory
@demo('SR latch (memory!)',
      'Two NOR gates feeding each other remember one bit. Press Set (hold the button) and Q turns on - and stays on '
      'after you let go. Reset turns it off. This feedback loop is the basis of all computer memory.')
def d_sr(c):
    r = c.add('Button', -120, 50, 'Reset')
    s = c.add('Button', -120, -50, 'Set')
    n1 = c.add('NOR', 0, 40, state=0)
    n2 = c.add('NOR', 10, -40, state=1)
    c.wire(r, n1, 0, 0)
    c.wire(s, n2, 0, 1)
    c.wire(n1, n2, 0, 0, mid=10)
    c.wire(n2, n1, 0, 1, mid=-10)
    q = c.add('LED', 130, 40, 'Q')
    nq = c.add('LED', 130, -40, 'not Q')
    c.wire(n1, q)
    c.wire(n2, nq)


def d_latch(c, ox, oy, dsrc, esrc, dmid, emid, qstate=0, label=True):
    """Gated D latch from 4 NANDs + NOT. Returns (q_gate, nq_gate)."""
    n1 = c.add('NAND', ox - 90, oy + 50, state=1)
    inv = c.add('NOT', ox - 130, oy - 80, state=1)
    n2 = c.add('NAND', ox - 50, oy - 50, state=1)
    n3 = c.add('NAND', ox + 40, oy + 40, state=qstate)
    n4 = c.add('NAND', ox + 50, oy - 40, state=1 - qstate)
    c.wire(dsrc[0], n1, dsrc[1], 0, mid=dmid)
    c.wire(dsrc[0], inv, dsrc[1], 0, mid=ox - 175)
    c.wire(esrc[0], n1, esrc[1], 1, mid=emid)
    c.wire(esrc[0], n2, esrc[1], 0, mid=emid)
    c.wire(inv, n2, 0, 1, mid=ox - 90)
    c.wire(n1, n3, 0, 0)
    c.wire(n2, n4, 0, 1)
    c.wire(n3, n4, 0, 0, mid=oy + 10)
    c.wire(n4, n3, 0, 1, mid=oy - 10)
    return n3, n4


@demo('Gated D latch',
      'A latch with a "door": while Enable is on, Q copies D. Switch Enable off and Q freezes, remembering the last '
      'value of D no matter what D does next. Built from four NAND gates and a NOT.')
def d_dlatch(c):
    d = c.add('Switch', -210, 60, 'D')
    e = c.add('Switch', -210, 0, 'Enable')
    n3, n4 = d_latch(c, 0, 0, (d, 0), (e, 0), None, -165)
    # D goes straight into the first NAND; fix its route (no bend needed)
    c.wires = [(w[0], w[1], w[2], w[3], '' if w[4] is None else w[4]) for w in c.wires]
    q = c.add('LED', 150, 40, 'Q')
    nq = c.add('LED', 150, -40, 'not Q')
    c.wire(n3, q)
    c.wire(n4, nq)


@demo('D flip-flop from gates',
      'Two D latches in a row (master and slave) make an edge-triggered flip-flop: Q only changes at the moment the '
      'clock goes from 0 to 1. Set D, then press Clock. Below, the built-in D flip-flop part does exactly the same.')
def d_dff(c):
    d = c.add('Switch', -230, 60, 'D')
    clk = c.add('Button', -230, -150, 'Clock')
    inv = c.add('NOT', -150, -150)
    mq, _ = d_latch(c, 0, 0, (d, 0), (inv, 0), None, -100)
    sq, snq = d_latch(c, 330, 0, (mq, 0), (clk, 0), 215, 260)
    c.wires = [(w[0], w[1], w[2], w[3], '' if w[4] is None else w[4]) for w in c.wires]
    c.wire(clk, inv)
    q = c.add('LED', 480, 40, 'Q')
    nq = c.add('LED', 480, -40, 'not Q')
    c.wire(sq, q)
    c.wire(snq, nq)
    c.text(-20, 135, 'master latch', 11)
    c.text(310, 135, 'slave latch', 11)
    ff = c.add('D flip-flop', 330, -230, 'built-in part')
    c.wire(d, ff, 0, 0, mid=-180)
    c.wire(clk, ff, 0, 1, mid=-190)
    q2 = c.add('LED', 480, -220, 'Q')
    c.wire(ff, q2, 0, 0)


@demo('4-bit counter',
      'Each D flip-flop feeds its inverted output back into D, so it flips every time its clock rises. Chaining them '
      '(each one clocked by the previous one) counts in binary: 0, 1, 2 ... 15. The decoder turns the count into '
      'segment signals for the 7-segment display. Click the clock to change its speed.', speed=6)
def d_counter(c):
    clk = c.add('Clock', -270, 70, 'Clock', param=16)
    prev = (clk, 0)
    qs = []
    for i in range(4):
        x = -170 + 100 * i
        ff = c.add('D flip-flop', x, 80, 'bit %d' % i)
        c.wire(prev[0], ff, prev[1], 1)
        c.wire(ff, ff, 1, 0, mid=120)
        prev = (ff, 1)
        qs.append(ff)
    dec = c.add('Decoder', 280, -40, 'decoder')
    seg = c.add('7-segment', 400, -40, 'display')
    for i in range(7):
        c.wire(dec, seg, i, i)
    for i, ff in enumerate(qs):
        x = -170 + 100 * i
        led = c.add('LED', x + 80, 20, str(2 ** i))
        c.wire(ff, led, 0, 0, mid=x + 50)
        c.wire(ff, dec, 0, i, mid=x + 50)
    num = c.add('Number', 280, -160, 'count')
    for i, ff in enumerate(qs):
        c.wire(ff, num, 0, i, mid=-170 + 100 * i + 50)


@demo('7-segment decoder',
      'A 7-segment display has one input per segment (a-g). The decoder converts a 4-bit binary number into the right '
      'pattern of segments. Flip the switches (worth 8, 4, 2 and 1) to show any hex digit 0-F.')
def d_seg(c):
    sw = []
    for i, w in enumerate([1, 2, 4, 8]):
        sw.append(c.add('Switch', -130, 30 - 20 * i, str(w)))
    dec = c.add('Decoder', 0, 0, 'decoder')
    seg = c.add('7-segment', 120, 0, 'display')
    for i, s in enumerate(sw):
        c.wire(s, dec, 0, i)
    for i in range(7):
        c.wire(dec, seg, i, i)
    num = c.add('Number', 120, -130, 'value')
    for i, s in enumerate(sw):
        c.wire(s, num, 0, i, mid=-80 - 10 * i)


@demo('Ring oscillator',
      'An odd number of inverting gates in a loop can never settle: the signal chases its own tail. Turn on Enable and '
      'watch the wave travel round. Each gate takes one tick, so the loop of 5 gates flips every 5 ticks.', speed=2)
def d_ring(c):
    en = c.add('Switch', -230, 10, 'Enable')
    nand = c.add('NAND', -130, 0, 'NAND', state=1)
    c.wire(en, nand, 0, 0)
    prev = nand
    xs = [-130]
    for i in range(4):
        x = -50 + 80 * i
        g = c.add('NOT', x, 0, state=i % 2)
        c.wire(prev, g)
        xs.append(x)
        prev = g
    c.wire(prev, nand, 0, 1, mid=-50)
    gates = list(range(nand, prev + 1))
    for i, x in enumerate(xs):
        led = c.add('LED', x + 60, 50)
        c.wire(nand + i, led, mid=x + 35)


@demo('Traffic light',
      'A clock drives a 2-bit counter (two D flip-flops). Two gates decode the count: 00 = green, 01 = amber, '
      '10 and 11 = red (so red stays on twice as long). Real controllers work the same way, just with more states.', speed=5)
def d_traffic(c):
    clk = c.add('Clock', -260, 40, 'Clock', param=16)
    f0 = c.add('D flip-flop', -150, 50, 'Q0')
    f1 = c.add('D flip-flop', -50, 50, 'Q1')
    c.wire(clk, f0, 0, 1)
    c.wire(f0, f0, 1, 0, mid=90)
    c.wire(f0, f1, 1, 1)
    c.wire(f1, f1, 1, 0, mid=90)
    amber = c.add('AND', 80, 0)
    green = c.add('NOR', 80, -60)
    c.wire(f1, amber, 1, 0, mid=20)
    c.wire(f0, amber, 0, 1, mid=-100)
    c.wire(f1, green, 0, 0, mid=10)
    c.wire(f0, green, 0, 1, mid=-100)
    r = c.add('LED', 200, 60, 'red', param=1)
    y = c.add('LED', 200, 0, 'amber', param=3)
    g = c.add('LED', 200, -60, 'green', param=2)
    c.wire(f1, r, 0, 0)
    c.wire(amber, y)
    c.wire(green, g)


@demo('NAND makes everything',
      'NAND is "universal": any logic circuit can be built from NAND gates alone. Here NOT, AND, OR and XOR are each '
      'made only from NANDs - compare them with the real gates in the earlier demos.')
def d_nand(c):
    # NOT
    c.text(-150, 175, 'NOT', 12)
    a = c.add('Switch', -230, 130, 'A')
    n = c.add('NAND', -140, 130)
    c.wire(a, n, 0, 0, mid=-190)
    c.wire(a, n, 0, 1, mid=-190)
    c.wire(n, c.add('LED', -60, 130))
    # AND
    c.text(140, 175, 'AND', 12)
    a = c.add('Switch', 40, 140, 'A')
    b = c.add('Switch', 40, 120, 'B')
    n1 = c.add('NAND', 120, 130)
    n2 = c.add('NAND', 200, 130)
    c.wire(a, n1, 0, 0)
    c.wire(b, n1, 0, 1)
    c.wire(n1, n2, 0, 0, mid=160)
    c.wire(n1, n2, 0, 1, mid=160)
    c.wire(n2, c.add('LED', 280, 130))
    # OR
    c.text(-150, 55, 'OR', 12)
    a = c.add('Switch', -230, 0, 'A')
    b = c.add('Switch', -230, -40, 'B')
    na = c.add('NAND', -150, 10)
    nb = c.add('NAND', -150, -50)
    no = c.add('NAND', -70, -20)
    c.wire(a, na, 0, 0, mid=-200)
    c.wire(a, na, 0, 1, mid=-200)
    c.wire(b, nb, 0, 0, mid=-200)
    c.wire(b, nb, 0, 1, mid=-200)
    c.wire(na, no, 0, 0)
    c.wire(nb, no, 0, 1)
    c.wire(no, c.add('LED', 10, -20))
    # XOR
    c.text(140, 55, 'XOR', 12)
    a = c.add('Switch', 40, 0, 'A')
    b = c.add('Switch', 40, -40, 'B')
    m = c.add('NAND', 110, -20, state=1)
    p = c.add('NAND', 190, 10, state=1)
    q = c.add('NAND', 190, -50, state=1)
    x = c.add('NAND', 270, -20)
    c.wire(a, m, 0, 0, mid=70)
    c.wire(b, m, 0, 1, mid=70)
    c.wire(a, p, 0, 0, mid=80)
    c.wire(m, p, 0, 1)
    c.wire(m, q, 0, 0)
    c.wire(b, q, 0, 1, mid=70)
    c.wire(p, x, 0, 0)
    c.wire(q, x, 0, 1)
    c.wire(x, c.add('LED', 350, -20))
