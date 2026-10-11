"""sbc - a tiny indentation-based language that compiles to Scratch 3 blocks.

Used to build pen_daw.sb3.  See README.md in this folder for the language.

Top level:
    global a, b              stage variables      (global x = "Scratch name" aliases)
    var a, b                 sprite variables     (var x = "Scratch name")
    list a / glist a         sprite / stage lists (same alias form)
    const NAME = expr        compile-time constant
    macro f(a, b) = expr     expression macro (inlined)
    extern f(a, b) = "proccode %s %s"   call an existing custom block
    proc name(a, b):         custom block, run without screen refresh
    proc nowarp name(a):     custom block that yields normally
    when flag: / when clone: / when key "x": / when receive "msg":

Statements: x = e, x += e, x -= e, L[i] = e, L.add(e), L.insert(i, e),
L.delete(i), L.clear(), if/elif/else, while, until, repeat n, forever,
for i = a to b, return, builtin(...), proc_name(...).
"""
import json
import re
import sys

# ----------------------------------------------------------------------------- lexer

TOKEN_RE = re.compile(r'''
    (?P<ws>[ \t]+)
  | (?P<comment>\#.*)
  | (?P<num>\d+\.\d*|\.\d+|\d+)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<name>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<op>==|!=|<=|>=|\+=|-=|[-+*/%<>=(),:\[\].~])
''', re.X)


class CompileError(Exception):
    pass


def unescape(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            out.append({'n': '\n', 't': '\t', '"': '"', '\\': '\\'}.get(n, n))
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def tokenize_line(text, lineno, fname):
    toks = []
    pos = 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise CompileError(f'{fname}:{lineno}: bad character {text[pos]!r}')
        pos = m.end()
        kind = m.lastgroup
        if kind in ('ws', 'comment'):
            continue
        val = m.group(kind)
        if kind == 'num':
            val = float(val)
            if val == int(val):
                val = int(val)
        elif kind == 'str':
            val = unescape(val[1:-1])
        toks.append((kind, val))
    return toks


class Line:
    def __init__(self, indent, toks, lineno, fname):
        self.indent = indent
        self.toks = toks
        self.lineno = lineno
        self.fname = fname

    def where(self):
        return f'{self.fname}:{self.lineno}'


def read_lines(src, fname):
    lines = []
    raw = src.split('\n')
    i = 0
    while i < len(raw):
        text = raw[i]
        lineno = i + 1
        stripped = text.lstrip(' ')
        if '\t' in text[:len(text) - len(stripped)]:
            raise CompileError(f'{fname}:{lineno}: tabs not allowed')
        indent = len(text) - len(stripped)
        toks = tokenize_line(stripped, lineno, fname)
        # join continuation lines while brackets are open
        depth = sum(1 for k, v in toks if k == 'op' and v in '([') - \
            sum(1 for k, v in toks if k == 'op' and v in ')]')
        while depth > 0 and i + 1 < len(raw):
            i += 1
            more = tokenize_line(raw[i].strip(), i + 1, fname)
            toks += more
            depth += sum(1 for k, v in more if k == 'op' and v in '([') - \
                sum(1 for k, v in more if k == 'op' and v in ')]')
        if toks:
            lines.append(Line(indent, toks, lineno, fname))
        i += 1
    return lines

# ----------------------------------------------------------------------------- parser


class TokStream:
    def __init__(self, line):
        self.t = line.toks
        self.i = 0
        self.line = line

    def peek(self, off=0):
        j = self.i + off
        return self.t[j] if j < len(self.t) else (None, None)

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def accept(self, kind, val=None):
        k, v = self.peek()
        if k == kind and (val is None or v == val):
            self.i += 1
            return v if v is not None else True
        return None

    def expect(self, kind, val=None):
        r = self.accept(kind, val)
        if r is None:
            raise CompileError(f'{self.line.where()}: expected {val or kind}, got {self.peek()[1]!r}')
        return r

    def done(self):
        return self.i >= len(self.t)


BINOPS = [
    ('or',),
    ('and',),
    ('==', '!=', '<', '>', '<=', '>='),
    ('~',),
    ('+', '-'),
    ('*', '/', '%'),
]


def parse_expr(ts, level=0):
    if level == len(BINOPS):
        return parse_unary(ts)
    if level == 2:  # 'not' binds looser than comparison
        if ts.accept('name', 'not'):
            return ('not', parse_expr(ts, level))
    left = parse_expr(ts, level + 1)
    while True:
        k, v = ts.peek()
        ops = BINOPS[level]
        if (k == 'op' and v in ops) or (k == 'name' and v in ops):
            ts.next()
            right = parse_expr(ts, level + 1)
            left = ('bin', v, left, right)
        else:
            return left


def parse_unary(ts):
    if ts.accept('op', '-'):
        e = parse_unary(ts)
        if e[0] == 'num':
            return ('num', -e[1])
        return ('bin', '-', ('num', 0), e)
    if ts.accept('op', '+'):
        return parse_unary(ts)
    return parse_postfix(ts)


def parse_args(ts):
    args = []
    if ts.accept('op', ')'):
        return args
    while True:
        args.append(parse_expr(ts))
        if ts.accept('op', ')'):
            return args
        ts.expect('op', ',')


def parse_postfix(ts):
    k, v = ts.next()
    if k == 'num':
        return ('num', v)
    if k == 'str':
        return ('str', v)
    if k == 'op' and v == '(':
        e = parse_expr(ts)
        ts.expect('op', ')')
        return e
    if k == 'name':
        if ts.accept('op', '('):
            return ('call', v, parse_args(ts))
        if ts.accept('op', '['):
            idx = parse_expr(ts)
            ts.expect('op', ']')
            return ('index', v, idx)
        if ts.peek() == ('op', '.'):
            ts.next()
            meth = ts.expect('name')
            if ts.accept('op', '('):
                return ('meth', v, meth, parse_args(ts))
            return ('meth', v, meth, [])
        return ('name', v)
    raise CompileError(f'{ts.line.where()}: unexpected {v!r}')


def parse_block(lines, i, indent):
    """Parse statements at exactly `indent`, return (stmts, next_i)."""
    stmts = []
    while i < len(lines):
        ln = lines[i]
        if ln.indent < indent:
            break
        if ln.indent > indent:
            raise CompileError(f'{ln.where()}: unexpected indent')
        stmt, i = parse_stmt(lines, i)
        if stmt is not None:
            stmts.append(stmt)
    return stmts, i


def parse_body(lines, i, parent):
    if i >= len(lines) or lines[i].indent <= parent.indent:
        raise CompileError(f'{parent.where()}: expected an indented block')
    return parse_block(lines, i, lines[i].indent)


def parse_stmt(lines, i):
    ln = lines[i]
    ts = TokStream(ln)
    k, v = ts.peek()
    w = ln.where()

    def colon():
        ts.expect('op', ':')
        if not ts.done():
            raise CompileError(f'{w}: junk after ":"')

    if k == 'name' and v in ('if', 'while', 'until'):
        ts.next()
        cond = parse_expr(ts)
        colon()
        body, j = parse_body(lines, i + 1, ln)
        if v != 'if':
            return (v, cond, body, w), j
        node = ['if', cond, body, None, w]
        tail = node
        while j < len(lines) and lines[j].indent == ln.indent:
            ts2 = TokStream(lines[j])
            if ts2.accept('name', 'elif'):
                c2 = parse_expr(ts2)
                ts2.expect('op', ':')
                b2, j2 = parse_body(lines, j + 1, lines[j])
                new = ['if', c2, b2, None, lines[j].where()]
                tail[3] = [new]
                tail = new
                j = j2
            elif ts2.accept('name', 'else'):
                ts2.expect('op', ':')
                b2, j2 = parse_body(lines, j + 1, lines[j])
                tail[3] = b2
                j = j2
                break
            else:
                break

        def freeze(n):
            els = n[3]
            if els is not None and len(els) == 1 and isinstance(els[0], list):
                els = [freeze(els[0])]
            return ('if', n[1], n[2], els, n[4])
        return freeze(node), j
    if k == 'name' and v == 'repeat':
        ts.next()
        n = parse_expr(ts)
        colon()
        body, j = parse_body(lines, i + 1, ln)
        return ('repeat', n, body, w), j
    if k == 'name' and v == 'forever':
        ts.next()
        colon()
        body, j = parse_body(lines, i + 1, ln)
        return ('forever', body, w), j
    if k == 'name' and v == 'for':
        ts.next()
        var = ts.expect('name')
        ts.expect('op', '=')
        a = parse_expr(ts)
        ts.expect('name', 'to')
        b = parse_expr(ts)
        colon()
        body, j = parse_body(lines, i + 1, ln)
        return ('for', var, a, b, body, w), j
    if k == 'name' and v == 'return':
        return ('return', w), i + 1
    if k == 'name' and v == 'pass':
        return None, i + 1
    # assignment / call
    target = parse_postfix(ts)
    if ts.done():
        if target[0] not in ('call', 'meth'):
            raise CompileError(f'{w}: expression statement must be a call')
        return ('exec', target, w), i + 1
    op = ts.next()
    if op[0] != 'op' or op[1] not in ('=', '+=', '-='):
        raise CompileError(f'{w}: expected assignment')
    val = parse_expr(ts)
    if not ts.done():
        raise CompileError(f'{w}: junk at end of line')
    return ('assign', target, op[1], val, w), i + 1


def parse_name_list(ts):
    """a, b = "x", c   ->  [(a, None), (b, 'x'), (c, None)]"""
    out = []
    while True:
        n = ts.expect('name')
        alias = None
        if ts.accept('op', '='):
            alias = ts.expect('str')
        out.append((n, alias))
        if not ts.accept('op', ','):
            return out


def parse_program(src, fname):
    lines = read_lines(src, fname)
    prog = {'globals': [], 'vars': [], 'lists': [], 'glists': [], 'consts': [],
            'macros': [], 'externs': [], 'procs': [], 'hats': []}
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.indent != 0:
            raise CompileError(f'{ln.where()}: unexpected indent at top level')
        ts = TokStream(ln)
        kw = ts.expect('name')
        w = ln.where()
        if kw in ('global', 'var', 'list', 'glist'):
            key = {'global': 'globals', 'var': 'vars', 'list': 'lists', 'glist': 'glists'}[kw]
            prog[key] += parse_name_list(ts)
            i += 1
        elif kw == 'const':
            n = ts.expect('name')
            ts.expect('op', '=')
            prog['consts'].append((n, parse_expr(ts), w))
            i += 1
        elif kw == 'macro':
            n = ts.expect('name')
            ts.expect('op', '(')
            params = []
            if not ts.accept('op', ')'):
                while True:
                    params.append(ts.expect('name'))
                    if ts.accept('op', ')'):
                        break
                    ts.expect('op', ',')
            ts.expect('op', '=')
            prog['macros'].append((n, params, parse_expr(ts), w))
            i += 1
        elif kw == 'extern':
            n = ts.expect('name')
            ts.expect('op', '(')
            params = []
            if not ts.accept('op', ')'):
                while True:
                    params.append(ts.expect('name'))
                    if ts.accept('op', ')'):
                        break
                    ts.expect('op', ',')
            ts.expect('op', '=')
            prog['externs'].append((n, params, ts.expect('str'), w))
            i += 1
        elif kw == 'proc':
            warp = True
            if ts.accept('name', 'nowarp'):
                warp = False
            n = ts.expect('name')
            ts.expect('op', '(')
            params = []
            if not ts.accept('op', ')'):
                while True:
                    params.append(ts.expect('name'))
                    if ts.accept('op', ')'):
                        break
                    ts.expect('op', ',')
            ts.expect('op', ':')
            body, i = parse_body(lines, i + 1, ln)
            prog['procs'].append((n, params, warp, body, w))
        elif kw == 'when':
            k, v = ts.next()
            arg = None
            if v in ('key', 'receive'):
                arg = ts.expect('str')
            elif v not in ('flag', 'clone'):
                raise CompileError(f'{w}: unknown hat {v}')
            ts.expect('op', ':')
            body, i = parse_body(lines, i + 1, ln)
            prog['hats'].append((v, arg, body, w))
        else:
            raise CompileError(f'{w}: unknown top-level statement {kw}')
    return prog

# ----------------------------------------------------------------------------- codegen

BOOL_OPS = {'operator_gt', 'operator_lt', 'operator_equals', 'operator_and', 'operator_or',
            'operator_not', 'operator_contains', 'sensing_keypressed', 'sensing_mousedown',
            'data_listcontainsitem'}

MATHOPS = {'abs', 'floor', 'ceiling', 'sqrt', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan',
           'ln', 'log', 'e ^', '10 ^'}
MATH_ALIASES = {'ceil': 'ceiling', 'exp': 'e ^', 'pow10': '10 ^'}
for _m in list(MATHOPS):
    MATH_ALIASES.setdefault(_m, _m)

BARE_REPORTERS = {
    'mouse_x': ('sensing_mousex', {}),
    'mouse_y': ('sensing_mousey', {}),
    'mouse_down': ('sensing_mousedown', {}),
    'timer': ('sensing_timer', {}),
    'answer': ('sensing_answer', {}),
    'days2000': ('sensing_dayssince2000', {}),
    'costume_number': ('looks_costumenumbername', {'NUMBER_NAME': ['number', None]}),
    'costume_name': ('looks_costumenumbername', {'NUMBER_NAME': ['name', None]}),
}


def fmt_num(v):
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
        return int(v)
    return v


class Compiler:
    def __init__(self, sprite_name, stage_vars, stage_lists, broadcasts,
                 existing_procs=None, id_prefix='x'):
        self.sprite = sprite_name
        self.blocks = {}
        self.n = 0
        self.prefix = id_prefix
        self.stage_vars = stage_vars      # name -> id   (shared across sprites)
        self.stage_lists = stage_lists
        self.broadcasts = broadcasts      # name -> id
        self.local_vars = {}              # scratch name -> id
        self.local_lists = {}
        self.alias = {}                   # source name -> ('var'|'list', scratch name, scope)
        self.consts = {}
        self.macros = {}
        self.procs = {}                   # source name -> dict(proccode, argids, argnames, warp)
        self.existing_procs = existing_procs or {}
        self.cur_args = None
        self.hat_y = 0

    # -- ids
    def nid(self):
        self.n += 1
        return f'{self.prefix}{self.n}'

    def add(self, opcode, parent=None, inputs=None, fields=None, shadow=False, top=False, mutation=None):
        bid = self.nid()
        b = {'opcode': opcode, 'next': None, 'parent': parent, 'inputs': inputs or {},
             'fields': fields or {}, 'shadow': shadow, 'topLevel': top}
        if mutation is not None:
            b['mutation'] = mutation
        if top:
            b['x'] = 0
            b['y'] = self.hat_y
            self.hat_y += 400
        self.blocks[bid] = b
        return bid

    # -- declarations
    def declare(self, prog):
        for n, alias in prog['globals']:
            sname = alias or n
            if sname not in self.stage_vars:
                self.stage_vars[sname] = 'g_' + re.sub(r'\W', '_', sname)
            self.alias[n] = ('var', sname, 'stage')
        for n, alias in prog['vars']:
            sname = alias or n
            if sname not in self.local_vars:
                self.local_vars[sname] = f'l_{self.prefix}_' + re.sub(r'\W', '_', sname)
            self.alias[n] = ('var', sname, 'local')
        for n, alias in prog['glists']:
            sname = alias or n
            if sname not in self.stage_lists:
                self.stage_lists[sname] = 'gl_' + re.sub(r'\W', '_', sname)
            self.alias[n] = ('list', sname, 'stage')
        for n, alias in prog['lists']:
            sname = alias or n
            if sname not in self.local_lists:
                self.local_lists[sname] = f'll_{self.prefix}_' + re.sub(r'\W', '_', sname)
            self.alias[n] = ('list', sname, 'local')
        for n, e, w in prog['consts']:
            self.consts[n] = self.fold(self.subst(e, {}), w)
        for n, params, e, w in prog['macros']:
            self.macros[n] = (params, e)
        for n, params, proccode, w in prog['externs']:
            if proccode not in self.existing_procs:
                raise CompileError(f'{w}: no existing custom block "{proccode}"')
            info = self.existing_procs[proccode]
            if len(info['argids']) != len(params):
                raise CompileError(f'{w}: {proccode} takes {len(info["argids"])} args')
            self.procs[n] = info
        for n, params, warp, body, w in prog['procs']:
            if n in self.procs:
                raise CompileError(f'{w}: duplicate proc {n}')
            proccode = n.replace('_', ' ') + ''.join(' %s' for _ in params)
            argids = [f'{self.prefix}a_{n}_{p}' for p in params]
            self.procs[n] = {'proccode': proccode, 'argids': argids, 'argnames': params,
                             'warp': warp}

    # -- expressions
    def subst(self, e, env):
        """Replace macro params / consts and expand macros (pure AST rewrite)."""
        t = e[0]
        if t == 'name':
            if e[1] in env:
                return env[e[1]]
            if e[1] in self.consts and (self.cur_args is None or e[1] not in self.cur_args):
                return self.consts[e[1]]
            return e
        if t in ('num', 'str'):
            return e
        if t == 'bin':
            return ('bin', e[1], self.subst(e[2], env), self.subst(e[3], env))
        if t == 'not':
            return ('not', self.subst(e[1], env))
        if t == 'index':
            return ('index', e[1], self.subst(e[2], env))
        if t == 'meth':
            return ('meth', e[1], e[2], [self.subst(a, env) for a in e[3]])
        if t == 'call':
            args = [self.subst(a, env) for a in e[2]]
            if e[1] in self.macros:
                params, body = self.macros[e[1]]
                if len(params) != len(args):
                    raise CompileError(f'macro {e[1]} expects {len(params)} args')
                return self.subst(body, dict(zip(params, args)))
            return ('call', e[1], args)
        raise CompileError(f'bad expr {e}')

    def fold(self, e, w=''):
        if e[0] == 'bin':
            a = self.fold(e[2], w)
            b = self.fold(e[3], w)
            if a[0] == 'num' and b[0] == 'num':
                op = e[1]
                x, y = a[1], b[1]
                if op == '+':
                    return ('num', fmt_num(x + y))
                if op == '-':
                    return ('num', fmt_num(x - y))
                if op == '*':
                    return ('num', fmt_num(x * y))
                if op == '/' and y != 0:
                    return ('num', fmt_num(x / y))
            if e[1] == '~' and a[0] in ('num', 'str') and b[0] in ('num', 'str'):
                return ('str', str(fmt_num(a[1])) + str(fmt_num(b[1])))
            return ('bin', e[1], a, b)
        if e[0] == 'not':
            return ('not', self.fold(e[1], w))
        if e[0] == 'call':
            return ('call', e[1], [self.fold(a, w) for a in e[2]])
        if e[0] == 'meth':
            return ('meth', e[1], e[2], [self.fold(a, w) for a in e[3]])
        if e[0] == 'index':
            return ('index', e[1], self.fold(e[2], w))
        return e

    def lookup_var(self, name, w):
        if name in self.alias and self.alias[name][0] == 'var':
            _, sname, scope = self.alias[name]
            vid = self.stage_vars[sname] if scope == 'stage' else self.local_vars[sname]
            return sname, vid
        raise CompileError(f'{w}: unknown variable {name}')

    def lookup_list(self, name, w):
        if name in self.alias and self.alias[name][0] == 'list':
            _, sname, scope = self.alias[name]
            lid = self.stage_lists[sname] if scope == 'stage' else self.local_lists[sname]
            return [sname, lid]
        raise CompileError(f'{w}: unknown list {name}')

    def expr(self, e, parent, w):
        """Compile expression. Returns ('lit', v) | ('block', id, isbool) | ('var', name, id)."""
        e = self.fold(self.subst(e, {}), w)
        return self._expr(e, parent, w)

    def _expr(self, e, parent, w):
        t = e[0]
        if t == 'num':
            return ('lit', fmt_num(e[1]))
        if t == 'str':
            return ('lit', e[1])
        if t == 'name':
            n = e[1]
            if self.cur_args is not None and n in self.cur_args:
                bid = self.add('argument_reporter_string_number', parent,
                               fields={'VALUE': [n, None]})
                return ('block', bid, False)
            if n in BARE_REPORTERS:
                op, fields = BARE_REPORTERS[n]
                bid = self.add(op, parent, fields=dict(fields))
                return ('block', bid, op in BOOL_OPS)
            sname, vid = self.lookup_var(n, w)
            return ('var', sname, vid)
        if t == 'bin':
            op = e[1]
            if op in ('and', 'or'):
                bid = self.add('operator_' + op, parent)
                self.set_bool(bid, 'OPERAND1', e[2], w)
                self.set_bool(bid, 'OPERAND2', e[3], w)
                return ('block', bid, True)
            if op in ('==', '<', '>'):
                opc = {'==': 'operator_equals', '<': 'operator_lt', '>': 'operator_gt'}[op]
                bid = self.add(opc, parent)
                self.set_input(bid, 'OPERAND1', e[2], 10, w)
                self.set_input(bid, 'OPERAND2', e[3], 10, w)
                return ('block', bid, True)
            if op in ('!=', '<=', '>='):
                inner = {'!=': '==', '<=': '>', '>=': '<'}[op]
                return self._expr(('not', ('bin', inner, e[2], e[3])), parent, w)
            if op == '~':
                bid = self.add('operator_join', parent)
                self.set_input(bid, 'STRING1', e[2], 10, w)
                self.set_input(bid, 'STRING2', e[3], 10, w)
                return ('block', bid, False)
            opc = {'+': 'operator_add', '-': 'operator_subtract', '*': 'operator_multiply',
                   '/': 'operator_divide', '%': 'operator_mod'}[op]
            bid = self.add(opc, parent)
            self.set_input(bid, 'NUM1', e[2], 4, w)
            self.set_input(bid, 'NUM2', e[3], 4, w)
            return ('block', bid, False)
        if t == 'not':
            bid = self.add('operator_not', parent)
            self.set_bool(bid, 'OPERAND', e[1], w)
            return ('block', bid, True)
        if t == 'index':
            bid = self.add('data_itemoflist', parent, fields={'LIST': self.lookup_list(e[1], w)})
            self.set_input(bid, 'INDEX', e[2], 7, w)
            return ('block', bid, False)
        if t == 'meth':
            lst, m, args = e[1], e[2], e[3]
            L = self.lookup_list(lst, w)
            if m == 'len' and not args:
                return ('block', self.add('data_lengthoflist', parent, fields={'LIST': L}), False)
            if m == 'index' and len(args) == 1:
                bid = self.add('data_itemnumoflist', parent, fields={'LIST': L})
                self.set_input(bid, 'ITEM', args[0], 10, w)
                return ('block', bid, False)
            if m == 'has' and len(args) == 1:
                bid = self.add('data_listcontainsitem', parent, fields={'LIST': L})
                self.set_input(bid, 'ITEM', args[0], 10, w)
                return ('block', bid, True)
            raise CompileError(f'{w}: unknown list reporter .{m}')
        if t == 'call':
            n, args = e[1], e[2]

            def need(k):
                if len(args) != k:
                    raise CompileError(f'{w}: {n}() takes {k} args')
            if n in MATH_ALIASES:
                need(1)
                bid = self.add('operator_mathop', parent, fields={'OPERATOR': [MATH_ALIASES[n], None]})
                self.set_input(bid, 'NUM', args[0], 4, w)
                return ('block', bid, False)
            if n == 'round':
                need(1)
                bid = self.add('operator_round', parent)
                self.set_input(bid, 'NUM', args[0], 4, w)
                return ('block', bid, False)
            if n == 'join':
                need(2)
                return self._expr(('bin', '~', args[0], args[1]), parent, w)
            if n == 'letter':
                need(2)
                bid = self.add('operator_letter_of', parent)
                self.set_input(bid, 'LETTER', args[0], 6, w)
                self.set_input(bid, 'STRING', args[1], 10, w)
                return ('block', bid, False)
            if n == 'strlen':
                need(1)
                bid = self.add('operator_length', parent)
                self.set_input(bid, 'STRING', args[0], 10, w)
                return ('block', bid, False)
            if n == 'contains':
                need(2)
                bid = self.add('operator_contains', parent)
                self.set_input(bid, 'STRING1', args[0], 10, w)
                self.set_input(bid, 'STRING2', args[1], 10, w)
                return ('block', bid, True)
            if n == 'random':
                need(2)
                bid = self.add('operator_random', parent)
                self.set_input(bid, 'FROM', args[0], 4, w)
                self.set_input(bid, 'TO', args[1], 4, w)
                return ('block', bid, False)
            if n == 'key':
                need(1)
                bid = self.add('sensing_keypressed', parent)
                self.set_menu(bid, 'KEY_OPTION', args[0], 'sensing_keyoptions', 'KEY_OPTION', w)
                return ('block', bid, True)
            if n == 'min' or n == 'max':
                need(2)
                a, b = args
                s = -1 if n == 'min' else 1
                ex = ('bin', '/', ('bin', '+' if s > 0 else '-', ('bin', '+', a, b),
                                   ('call', 'abs', [('bin', '-', a, b)])), ('num', 2))
                return self._expr(self.fold(ex), parent, w)
            if n == 'num':
                need(1)
                return self._expr(('bin', '+', args[0], ('num', 0)), parent, w)
            raise CompileError(f'{w}: unknown function {n}()')
        raise CompileError(f'{w}: cannot compile expression {e}')

    def input_value(self, r, shadow_type):
        if r[0] == 'lit':
            v = r[1]
            if shadow_type in (4, 5, 6, 7, 8) and isinstance(v, str):
                return [1, [10, v]]
            return [1, [shadow_type, v if isinstance(v, str) else fmt_num(v)]]
        if r[0] == 'var':
            return [3, [12, r[1], r[2]], [shadow_type, '']]
        return [3, r[1], [shadow_type, '']]

    def set_input(self, bid, name, e, shadow_type, w):
        r = self._expr(e, bid, w) if e[0] not in ('raw',) else e[1]
        self.blocks[bid]['inputs'][name] = self.input_value(r, shadow_type)

    def set_input_compiled(self, bid, name, r, shadow_type):
        self.blocks[bid]['inputs'][name] = self.input_value(r, shadow_type)

    def set_bool(self, bid, name, e, w):
        r = self._expr(e, bid, w)
        if r[0] != 'block' or not r[2]:
            raise CompileError(f'{w}: expected a condition, got {e}')
        self.blocks[bid]['inputs'][name] = [2, r[1]]

    def set_menu(self, bid, name, e, menu_op, field, w, default=None):
        e = self.fold(self.subst(e, {}), w)
        if e[0] in ('num', 'str'):
            sid = self.add(menu_op, bid, fields={field: [str(fmt_num(e[1])), None]}, shadow=True)
            self.blocks[bid]['inputs'][name] = [1, sid]
        else:
            sid = self.add(menu_op, bid, fields={field: [default or '', None]}, shadow=True)
            r = self._expr(e, bid, w)
            if r[0] == 'var':
                self.blocks[bid]['inputs'][name] = [3, [12, r[1], r[2]], sid]
            else:
                self.blocks[bid]['inputs'][name] = [3, r[1], sid]

    # -- statements
    def stmts(self, body, parent):
        """Compile a list of statements; returns id of first block (or None)."""
        first = None
        prev = None
        for s in body:
            ids = self.stmt(s, prev if prev else parent)
            if not ids:
                continue
            head, tail = ids
            if prev is None:
                first = head
            else:
                self.blocks[prev]['next'] = head
                self.blocks[head]['parent'] = prev
            prev = tail
        return first

    def substack(self, bid, name, body):
        first = self.stmts(body, bid)
        if first:
            self.blocks[bid]['inputs'][name] = [2, first]
            self.blocks[first]['parent'] = bid

    def stmt(self, s, parent):
        kind = s[0]
        w = s[-1]
        if kind == 'if':
            cond, body, els = s[1], s[2], s[3]
            op = 'control_if_else' if els is not None else 'control_if'
            bid = self.add(op, parent)
            self.set_bool(bid, 'CONDITION', self.fold(self.subst(cond, {})), w)
            self.substack(bid, 'SUBSTACK', body)
            if els is not None:
                self.substack(bid, 'SUBSTACK2', els)
            return bid, bid
        if kind in ('while', 'until'):
            cond = self.fold(self.subst(s[1], {}))
            if kind == 'while':
                cond = ('not', cond)
            bid = self.add('control_repeat_until', parent)
            self.set_bool(bid, 'CONDITION', cond, w)
            self.substack(bid, 'SUBSTACK', s[2])
            return bid, bid
        if kind == 'repeat':
            bid = self.add('control_repeat', parent)
            self.set_input(bid, 'TIMES', self.fold(self.subst(s[1], {})), 6, w)
            self.substack(bid, 'SUBSTACK', s[2])
            return bid, bid
        if kind == 'forever':
            bid = self.add('control_forever', parent)
            self.substack(bid, 'SUBSTACK', s[1])
            return bid, bid
        if kind == 'for':
            var, a, b, body = s[1], s[2], s[3], s[4]
            # v = a; repeat (b - a + 1): body; v += 1
            st = [('assign', ('name', var), '=', a, w),
                  ('repeat', ('bin', '+', ('bin', '-', b, a), ('num', 1)),
                   body + [('assign', ('name', var), '+=', ('num', 1), w)], w)]
            first = self.stmts(st, parent)
            last = first
            while self.blocks[last]['next']:
                last = self.blocks[last]['next']
            return first, last
        if kind == 'return':
            bid = self.add('control_stop', parent, fields={'STOP_OPTION': ['this script', None]},
                           mutation={'tagName': 'mutation', 'children': [], 'hasnext': 'false'})
            return bid, bid
        if kind == 'assign':
            target, op, val = s[1], s[2], s[3]
            if target[0] == 'name':
                if self.cur_args and target[1] in self.cur_args:
                    raise CompileError(f'{w}: cannot assign to argument {target[1]}')
                sname, vid = self.lookup_var(target[1], w)
                if op == '=':
                    bid = self.add('data_setvariableto', parent, fields={'VARIABLE': [sname, vid]})
                    self.set_input(bid, 'VALUE', self.fold(self.subst(val, {})), 10, w)
                else:
                    v = self.fold(self.subst(val, {}))
                    if op == '-=':
                        v = self.fold(('bin', '-', ('num', 0), v)) if v[0] != 'num' else ('num', -v[1])
                    bid = self.add('data_changevariableby', parent, fields={'VARIABLE': [sname, vid]})
                    self.set_input(bid, 'VALUE', v, 4, w)
                return bid, bid
            if target[0] == 'index':
                L = self.lookup_list(target[1], w)
                v = self.fold(self.subst(val, {}))
                if op != '=':
                    v = ('bin', '+' if op == '+=' else '-', target, v)
                bid = self.add('data_replaceitemoflist', parent, fields={'LIST': L})
                self.set_input(bid, 'INDEX', self.fold(self.subst(target[2], {})), 7, w)
                self.set_input(bid, 'ITEM', self.fold(self.subst(v, {})), 10, w)
                return bid, bid
            raise CompileError(f'{w}: bad assignment target')
        if kind == 'exec':
            return self.exec_call(s[1], parent, w)
        raise CompileError(f'{w}: unknown statement {kind}')

    def exec_call(self, c, parent, w):
        if c[0] == 'meth':
            lst, m, args = c[1], c[2], [self.fold(self.subst(a, {})) for a in c[3]]
            L = self.lookup_list(lst, w)
            if m == 'add':
                bid = self.add('data_addtolist', parent, fields={'LIST': L})
                self.set_input(bid, 'ITEM', args[0], 10, w)
            elif m == 'insert':
                bid = self.add('data_insertatlist', parent, fields={'LIST': L})
                self.set_input(bid, 'INDEX', args[0], 7, w)
                self.set_input(bid, 'ITEM', args[1], 10, w)
            elif m == 'delete':
                bid = self.add('data_deleteoflist', parent, fields={'LIST': L})
                self.set_input(bid, 'INDEX', args[0], 7, w)
            elif m == 'clear':
                bid = self.add('data_deletealloflist', parent, fields={'LIST': L})
            elif m == 'show':
                bid = self.add('data_showlist', parent, fields={'LIST': L})
            elif m == 'hide':
                bid = self.add('data_hidelist', parent, fields={'LIST': L})
            else:
                raise CompileError(f'{w}: unknown list command .{m}')
            return bid, bid
        n = c[1]
        args = [self.fold(self.subst(a, {})) for a in c[2]]

        def need(k):
            if len(args) != k:
                raise CompileError(f'{w}: {n}() takes {k} args')

        def simple(opcode, spec, fields=None):
            need(len(spec))
            bid = self.add(opcode, parent, fields=fields or {})
            for (iname, st), a in zip(spec, args):
                self.set_input(bid, iname, a, st, w)
            return bid, bid

        if n in self.procs:
            info = self.procs[n]
            if len(args) != len(info['argids']):
                raise CompileError(f'{w}: {n}() takes {len(info["argids"])} args')
            mut = {'tagName': 'mutation', 'children': [], 'proccode': info['proccode'],
                   'argumentids': json.dumps(info['argids']),
                   'warp': 'true' if info['warp'] else 'false'}
            bid = self.add('procedures_call', parent, mutation=mut)
            for aid, a in zip(info['argids'], args):
                self.set_input(bid, aid, a, 10, w)
            return bid, bid
        table = {
            'goto': ('motion_gotoxy', [('X', 4), ('Y', 4)]),
            'setx': ('motion_setx', [('X', 4)]),
            'sety': ('motion_sety', [('Y', 4)]),
            'point': ('motion_pointindirection', [('DIRECTION', 8)]),
            'setsize': ('looks_setsizeto', [('SIZE', 4)]),
            'clear': ('pen_clear', []),
            'stamp': ('pen_stamp', []),
            'pendown': ('pen_penDown', []),
            'penup': ('pen_penUp', []),
            'pencolor': ('pen_setPenColorToColor', [('COLOR', 9)]),
            'pensize': ('pen_setPenSizeTo', [('SIZE', 4)]),
            'hide': ('looks_hide', []),
            'show': ('looks_show', []),
            'cleareffects': ('looks_cleargraphiceffects', []),
            'setvolume': ('sound_setvolumeto', [('VOLUME', 4)]),
            'stopallsounds': ('sound_stopallsounds', []),
            'deleteclone': ('control_delete_this_clone', []),
            'ask': ('sensing_askandwait', [('QUESTION', 10)]),
            'resettimer': ('sensing_resettimer', []),
            'wait': ('control_wait', [('DURATION', 5)]),
        }
        if n in table:
            op, spec = table[n]
            return simple(op, spec)
        if n == 'setpitch' or n == 'setpan':
            need(1)
            bid = self.add('sound_seteffectto', parent,
                           fields={'EFFECT': ['PITCH' if n == 'setpitch' else 'PAN', None]})
            self.set_input(bid, 'VALUE', args[0], 4, w)
            return bid, bid
        if n == 'seteffect':
            need(2)
            if args[0][0] != 'str':
                raise CompileError(f'{w}: effect name must be a literal')
            bid = self.add('looks_seteffectto', parent, fields={'EFFECT': [args[0][1].upper(), None]})
            self.set_input(bid, 'VALUE', args[1], 4, w)
            return bid, bid
        if n == 'pentransp':
            need(1)
            bid = self.add('pen_setPenColorParamTo', parent)
            sid = self.add('pen_menu_colorParam', bid, fields={'colorParam': ['transparency', None]},
                           shadow=True)
            self.blocks[bid]['inputs']['COLOR_PARAM'] = [1, sid]
            self.set_input(bid, 'VALUE', args[0], 4, w)
            return bid, bid
        if n == 'costume':
            need(1)
            bid = self.add('looks_switchcostumeto', parent)
            self.set_menu(bid, 'COSTUME', args[0], 'looks_costume', 'COSTUME', w)
            return bid, bid
        if n == 'playsound':
            need(1)
            bid = self.add('sound_play', parent)
            self.set_menu(bid, 'SOUND_MENU', args[0], 'sound_sounds_menu', 'SOUND_MENU', w)
            return bid, bid
        if n == 'clone':
            need(0)
            bid = self.add('control_create_clone_of', parent)
            sid = self.add('control_create_clone_of_menu', bid,
                           fields={'CLONE_OPTION': ['_myself_', None]}, shadow=True)
            self.blocks[bid]['inputs']['CLONE_OPTION'] = [1, sid]
            return bid, bid
        if n == 'waituntil':
            need(1)
            bid = self.add('control_wait_until', parent)
            self.set_bool(bid, 'CONDITION', args[0], w)
            return bid, bid
        if n in ('broadcast', 'broadcastwait'):
            need(1)
            if args[0][0] != 'str':
                raise CompileError(f'{w}: broadcast name must be a literal')
            name = args[0][1]
            bcid = self.broadcasts.setdefault(name, 'bc_' + re.sub(r'\W', '_', name))
            bid = self.add('event_broadcast' if n == 'broadcast' else 'event_broadcastandwait', parent)
            self.blocks[bid]['inputs']['BROADCAST_INPUT'] = [1, [11, name, bcid]]
            return bid, bid
        if n == 'stopall' or n == 'stopother':
            need(0)
            opt = 'all' if n == 'stopall' else 'other scripts in sprite'
            bid = self.add('control_stop', parent, fields={'STOP_OPTION': [opt, None]},
                           mutation={'tagName': 'mutation', 'children': [],
                                     'hasnext': 'false' if n == 'stopall' else 'true'})
            return bid, bid
        raise CompileError(f'{w}: unknown command {n}()')

    # -- top level
    def compile(self, prog):
        self.declare(prog)
        for n, params, warp, body, w in prog['procs']:
            info = self.procs[n]
            did = self.add('procedures_definition', None, top=True)
            pid = self.add('procedures_prototype', did, shadow=True, mutation={
                'tagName': 'mutation', 'children': [], 'proccode': info['proccode'],
                'argumentids': json.dumps(info['argids']),
                'argumentnames': json.dumps(params),
                'argumentdefaults': json.dumps(['' for _ in params]),
                'warp': 'true' if warp else 'false'})
            self.blocks[did]['inputs']['custom_block'] = [1, pid]
            for aid, p in zip(info['argids'], params):
                rid = self.add('argument_reporter_string_number', pid, shadow=True,
                               fields={'VALUE': [p, None]})
                self.blocks[pid]['inputs'][aid] = [1, rid]
            self.cur_args = set(params)
            first = self.stmts(body, did)
            self.cur_args = None
            if first:
                self.blocks[did]['next'] = first
                self.blocks[first]['parent'] = did
        for kind, arg, body, w in prog['hats']:
            if kind == 'flag':
                hid = self.add('event_whenflagclicked', None, top=True)
            elif kind == 'clone':
                hid = self.add('control_start_as_clone', None, top=True)
            elif kind == 'key':
                hid = self.add('event_whenkeypressed', None, top=True,
                               fields={'KEY_OPTION': [arg, None]})
            else:
                bcid = self.broadcasts.setdefault(arg, 'bc_' + re.sub(r'\W', '_', arg))
                hid = self.add('event_whenbroadcastreceived', None, top=True,
                               fields={'BROADCAST_OPTION': [arg, bcid]})
            first = self.stmts(body, hid)
            if first:
                self.blocks[hid]['next'] = first
                self.blocks[first]['parent'] = hid
        return self.blocks


def compile_files(paths, **kw):
    src = []
    for p in paths:
        with open(p) as f:
            src.append((f.read(), p))
    progs = [parse_program(s, p) for s, p in src]
    merged = {k: [] for k in progs[0]}
    for pr in progs:
        for k in merged:
            merged[k] += pr[k]
    c = Compiler(**kw)
    c.compile(merged)
    return c


if __name__ == '__main__':
    c = compile_files(sys.argv[1:], sprite_name='test', stage_vars={}, stage_lists={},
                      broadcasts={})
    print(json.dumps(c.blocks, indent=1)[:3000])
    print(len(c.blocks), 'blocks')
