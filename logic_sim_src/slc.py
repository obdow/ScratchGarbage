"""slc - a tiny compiler from a readable script language to Scratch 3 blocks.

The language (one statement per line, blocks closed with `end`):

    const NAME = 12            # compile-time constant (number or "string")
    var a, b, c                # sprite-local variables
    list L1, L2                # sprite-local lists
    global `TE width`          # reference an existing stage variable / list
    extern drawtext = "draw text %s at x: %s y: %s"   # existing custom block

    def name(p1, p2) [nowarp]  # custom block ("run without screen refresh" by default)
      x = p1 + 1               # set      ;  x += 1  /  x -= 1  (change)
      L[i] = x                 # replace item
      L.add(x)  L.clear()  L.del(i)  L.insert(i, x)
      if a > 1 and not (b == 2)
      elif ...
      else
      end
      while cond / until cond / repeat n / forever / for i = a to b   ... end
      return                   # stop this script
      name(1, 2)               # call a custom block, or a builtin statement
    end

    when flag | when key "space" | when broadcast "msg"
      ...
    end

Expressions: numbers, "strings" (\\n escapes), names, `quoted names`, L[i],
+ - * / %, == != < > <= >=, and / or / not, and builtin functions (see
EXPR_FUNCS / STMT_FUNCS below).
"""
import json
import re

TOKEN_RE = re.compile(r'''
    (?P<ws>[ \t]+)
  | (?P<num>0x[0-9a-fA-F]+|\d+\.\d*|\.\d+|\d+)
  | (?P<str>"(?:\\.|[^"\\])*")
  | (?P<bq>`[^`]*`)
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>==|!=|<=|>=|\+=|-=|[-+*/%()\[\],.=<>:])
''', re.X)


class CompileError(Exception):
    pass


def tokenize(line, lineno):
    pos = 0
    toks = []
    while pos < len(line):
        m = TOKEN_RE.match(line, pos)
        if not m:
            raise CompileError('line %d: bad character %r' % (lineno, line[pos]))
        pos = m.end()
        kind = m.lastgroup
        text = m.group(kind)
        if kind == 'ws':
            continue
        if kind == 'num':
            v = int(text, 16) if text.startswith('0x') else (float(text) if '.' in text else int(text))
            toks.append(('num', v))
        elif kind == 'str':
            toks.append(('str', json.loads(text)))
        elif kind == 'bq':
            toks.append(('id', text[1:-1]))
        elif kind == 'id':
            toks.append(('id', text))
        else:
            toks.append(('op', text))
    return toks


def strip_comment(line):
    out = []
    inq = False
    i = 0
    while i < len(line):
        ch = line[i]
        if inq:
            out.append(ch)
            if ch == '\\' and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == '"':
                inq = False
        else:
            if ch == '#':
                break
            if ch == '"':
                inq = True
            out.append(ch)
        i += 1
    return ''.join(out).strip()


def fmt_num(v):
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        v = int(v)
    return str(v)


# --------------------------------------------------------------------------
# Expression parsing (Pratt)

class Parser:
    def __init__(self, toks, lineno, consts):
        self.t = toks
        self.i = 0
        self.ln = lineno
        self.consts = consts

    def err(self, msg):
        raise CompileError('line %d: %s' % (self.ln, msg))

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else ('eof', None)

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def accept(self, kind, val=None):
        tok = self.peek()
        if tok[0] == kind and (val is None or tok[1] == val):
            self.i += 1
            return tok
        return None

    def expect(self, kind, val=None):
        tok = self.accept(kind, val)
        if not tok:
            self.err('expected %s %s, got %r' % (kind, val or '', self.peek()))
        return tok

    def at_end(self):
        return self.i >= len(self.t)

    PREC = {'or': 1, 'and': 2, '==': 4, '!=': 4, '<': 4, '>': 4, '<=': 4, '>=': 4,
            '+': 5, '-': 5, '*': 6, '/': 6, '%': 6}

    def binop_of(self, tok):
        if tok[0] == 'op' and tok[1] in self.PREC:
            return tok[1]
        if tok[0] == 'id' and tok[1] in ('and', 'or'):
            return tok[1]
        return None

    def expr(self, minp=0):
        left = self.unary()
        while True:
            op = self.binop_of(self.peek())
            if op is None or self.PREC[op] < minp:
                return left
            self.next()
            right = self.expr(self.PREC[op] + 1)
            left = fold(('bin', op, left, right))

    def unary(self):
        tok = self.peek()
        if tok == ('id', 'not'):
            self.next()
            return ('not', self.expr(3))
        if tok == ('op', '-'):
            self.next()
            e = self.unary()
            if e[0] == 'num':
                return ('num', -e[1])
            return ('bin', '-', ('num', 0), e)
        return self.postfix(self.primary())

    def primary(self):
        tok = self.next()
        if tok[0] == 'num':
            return ('num', tok[1])
        if tok[0] == 'str':
            return ('str', tok[1])
        if tok == ('op', '('):
            e = self.expr()
            self.expect('op', ')')
            return e
        if tok[0] == 'id':
            name = tok[1]
            if name in self.consts:
                return self.consts[name]
            if self.accept('op', '('):
                args = []
                if not self.accept('op', ')'):
                    while True:
                        args.append(self.expr())
                        if self.accept('op', ')'):
                            break
                        self.expect('op', ',')
                return ('call', name, args)
            return ('name', name)
        self.err('unexpected %r' % (tok,))

    def postfix(self, e):
        while True:
            if self.peek() == ('op', '['):
                self.next()
                idx = self.expr()
                self.expect('op', ']')
                if e[0] != 'name':
                    self.err('only lists can be indexed')
                e = ('item', e[1], idx)
            elif self.peek() == ('op', '.') and self.peek(1)[0] == 'id' and self.peek(2) == ('op', '('):
                self.next()
                meth = self.next()[1]
                self.next()
                args = []
                if not self.accept('op', ')'):
                    while True:
                        args.append(self.expr())
                        if self.accept('op', ')'):
                            break
                        self.expect('op', ',')
                if e[0] != 'name':
                    self.err('methods only on lists')
                e = ('method', e[1], meth, args)
            else:
                return e


def fold(e):
    if e[0] == 'bin' and e[2][0] == 'num' and e[3][0] == 'num':
        a, b = e[2][1], e[3][1]
        op = e[1]
        if op == '+': return ('num', a + b)
        if op == '-': return ('num', a - b)
        if op == '*': return ('num', a * b)
        if op == '/' and b != 0:
            r = a / b
            return ('num', int(r) if float(r).is_integer() else r)
    return e


MATHOPS = {'abs': 'abs', 'floor': 'floor', 'ceil': 'ceiling', 'sqrt': 'sqrt', 'sin': 'sin',
           'cos': 'cos', 'tan': 'tan', 'asin': 'asin', 'acos': 'acos', 'atan': 'atan',
           'ln': 'ln', 'log': 'log', 'exp': 'e ^', 'pow10': '10 ^'}


# --------------------------------------------------------------------------
# Statement parsing into an AST

class Program:
    def __init__(self):
        self.consts = {}
        self.vars = []
        self.lists = []
        self.globals = []
        self.externs = {}     # name -> proccode
        self.procs = []       # (name, params, warp, body, lineno)
        self.hats = []        # (kind, arg, body, lineno)
        self.comments = []    # (text) workspace comments placed near the next definition


def parse_program(src, lnmap=None):
    prog = Program()
    lines = src.split('\n')
    stack = []  # stack of (kind, node)
    pending_comment = []
    i = 0

    def parse_expr_tokens(toks, ln):
        p = Parser(toks, ln, prog.consts)
        e = p.expr()
        if not p.at_end():
            p.err('trailing tokens %r' % (p.t[p.i:],))
        return e

    cur_body = None
    body_stack = []

    def push_body(node_list):
        nonlocal cur_body
        body_stack.append(cur_body)
        cur_body = node_list

    def pop_body():
        nonlocal cur_body
        cur_body = body_stack.pop()

    open_blocks = []   # (kind, node, lineno)

    for ln0, raw in enumerate(lines):
        ln = lnmap[ln0] if lnmap else ln0 + 1
        if raw.strip().startswith('##'):
            # doc comment for the next definition (workspace comment)
            pending_comment.append(raw.strip()[2:].strip())
            continue
        line = strip_comment(raw)
        if not line:
            continue
        toks = tokenize(line, ln)
        head = toks[0]
        P = Parser(toks, ln, prog.consts)

        if not open_blocks:
            # top level
            if head == ('id', 'const'):
                P.next()
                name = P.expect('id')[1]
                P.expect('op', '=')
                e = P.expr()
                if e[0] not in ('num', 'str'):
                    P.err('const must be a literal')
                prog.consts[name] = e
                continue
            if head[1] in ('var', 'list', 'global'):
                P.next()
                names = []
                while not P.at_end():
                    names.append(P.expect('id')[1])
                    P.accept('op', ',')
                {'var': prog.vars, 'list': prog.lists, 'global': prog.globals}[head[1]].extend(names)
                continue
            if head == ('id', 'extern'):
                P.next()
                name = P.expect('id')[1]
                P.expect('op', '=')
                prog.externs[name] = P.expect('str')[1]
                continue
            if head == ('id', 'def'):
                P.next()
                name = P.expect('id')[1]
                params = []
                P.expect('op', '(')
                if not P.accept('op', ')'):
                    while True:
                        params.append(P.expect('id')[1])
                        if P.accept('op', ')'):
                            break
                        P.expect('op', ',')
                warp = True
                if P.accept('id', 'nowarp'):
                    warp = False
                body = []
                node = ('proc', name, params, warp, body, ln, pending_comment)
                pending_comment = []
                prog.procs.append(node)
                open_blocks.append(('def', node, ln))
                push_body(body)
                continue
            if head == ('id', 'when'):
                P.next()
                kind = P.expect('id')[1]
                arg = None
                if kind in ('key', 'broadcast'):
                    arg = P.expect('str')[1]
                body = []
                node = ('hat', kind, arg, body, ln, pending_comment)
                pending_comment = []
                prog.hats.append(node)
                open_blocks.append(('hat', node, ln))
                push_body(body)
                continue
            raise CompileError('line %d: unexpected top-level statement' % ln)

        # inside a body
        kw = head[1] if head[0] == 'id' else None
        if kw == 'end' and len(toks) == 1:
            kind, node, _ = open_blocks.pop()
            pop_body()
            if kind == 'if':
                # pop the extra body pushed for else/elif chain
                pass
            continue
        if kw == 'if':
            P.next()
            cond = P.expr()
            body = []
            node = ['if', cond, body, None, ln]
            cur_body.append(node)
            open_blocks.append(('if', node, ln))
            push_body(body)
            continue
        if kw in ('elif', 'else'):
            if not open_blocks or open_blocks[-1][0] != 'if':
                raise CompileError('line %d: %s without if' % (ln, kw))
            kind, node, _ = open_blocks.pop()
            pop_body()
            els = []
            node[3] = els
            if kw == 'elif':
                P.next()
                cond = P.expr()
                body = []
                nnode = ['if', cond, body, None, ln]
                els.append(nnode)
                # the elif chain shares the outer if's `end`
                push_body(els)   # dummy level so that `end` pops correctly
                open_blocks.append(('elifwrap', None, ln))
                open_blocks.append(('if', nnode, ln))
                push_body(body)
            else:
                open_blocks.append(('else', node, ln))
                push_body(els)
            continue
        if kw in ('while', 'until', 'repeat'):
            P.next()
            e = P.expr()
            body = []
            cur_body.append([kw, e, body, ln])
            open_blocks.append((kw, None, ln))
            push_body(body)
            continue
        if kw == 'forever':
            body = []
            cur_body.append(['forever', body, ln])
            open_blocks.append(('forever', None, ln))
            push_body(body)
            continue
        if kw == 'for':
            P.next()
            var = P.expect('id')[1]
            P.expect('op', '=')
            a = P.expr()
            P.expect('id', 'to')
            b = P.expr()
            body = []
            cur_body.append(['for', var, a, b, body, ln])
            open_blocks.append(('for', None, ln))
            push_body(body)
            continue
        if kw == 'return' and len(toks) == 1:
            cur_body.append(['return', ln])
            continue
        # assignment forms
        if head[0] == 'id' and len(toks) > 1 and toks[1][0] == 'op' and toks[1][1] in ('=', '+=', '-='):
            name = head[1]
            e = parse_expr_tokens(toks[2:], ln)
            cur_body.append(['set' if toks[1][1] == '=' else 'change', name,
                             e if toks[1][1] != '-=' else fold(('bin', '-', ('num', 0), e)), ln])
            continue
        # list replace: L[i] = e
        if head[0] == 'id' and len(toks) > 1 and toks[1] == ('op', '['):
            # find the matching ] followed by =
            depth = 0
            for j in range(1, len(toks)):
                if toks[j] == ('op', '['):
                    depth += 1
                elif toks[j] == ('op', ']'):
                    depth -= 1
                    if depth == 0:
                        break
            if j + 1 < len(toks) and toks[j + 1] == ('op', '='):
                idx = parse_expr_tokens(toks[2:j], ln)
                val = parse_expr_tokens(toks[j + 2:], ln)
                cur_body.append(['replace', head[1], idx, val, ln])
                continue
        # expression statement (call / method)
        e = parse_expr_tokens(toks, ln)
        if e[0] not in ('call', 'method'):
            raise CompileError('line %d: not a statement' % ln)
        cur_body.append(['expr', e, ln])
        # handle elifwrap: when an `end` closes an if that was opened by elif,
        # the wrapper must close too (done below)
    # fix-up: elif wrappers are closed implicitly; we emulate this by a
    # post-pass in the `end` handling. (see close loop below)
    if open_blocks:
        raise CompileError('unclosed block opened at line %d' % open_blocks[-1][2])
    return prog


# The `elif` handling above pushes an extra wrapper level which a single `end`
# must also close. Implement by patching the end handler: simplest is to
# re-implement parse with that rule. We wrap parse_program to post-process.
_orig_parse = parse_program


def parse_program(src):  # noqa: F811
    # Rewrite: insert the extra `end`s needed for elif wrappers by counting.
    lines = src.split('\n')
    out = []
    lnmap = []
    stack = []
    for rawno, raw in enumerate(lines):
        s = strip_comment(raw) if not raw.strip().startswith('##') else ''
        word = s.split(None, 1)[0] if s else ''
        if word in ('def', 'when', 'if', 'while', 'until', 'repeat', 'forever', 'for'):
            if not (word == 'def' and False):
                stack.append(0)
            out.append(raw)
        elif word == 'elif':
            stack[-1] += 1
            out.append(raw)
        elif s == 'end':
            n = stack.pop()
            out.append(raw)
            lnmap.append(rawno + 1)
            for _ in range(n):
                out.append('end')
                lnmap.append(rawno + 1)
            continue
        else:
            out.append(raw)
        lnmap.append(rawno + 1)
    return _orig_parse('\n'.join(out), lnmap)


# --------------------------------------------------------------------------
# Code generation

class Gen:
    def __init__(self, sprite, stage, prefix='z'):
        self.sprite = sprite
        self.stage = stage
        self.blocks = sprite['blocks']
        self.n = 0
        self.prefix = prefix
        self.vars = {}
        self.lists = {}
        for vid, (name, _v, *rest) in [(k, v) for k, v in sprite['variables'].items()]:
            self.vars[name] = vid
        for lid, (name, _v) in sprite['lists'].items():
            self.lists[name] = lid
        self.gvars = {v[0]: k for k, v in stage['variables'].items()}
        self.glists = {v[0]: k for k, v in stage['lists'].items()}
        self.broadcasts = {v: k for k, v in stage.get('broadcasts', {}).items()}
        self.procs = {}
        # existing procedures in the sprite
        for bid, b in self.blocks.items():
            if isinstance(b, dict) and b['opcode'] == 'procedures_prototype':
                m = b['mutation']
                self.procs[m['proccode']] = {
                    'proccode': m['proccode'], 'argids': json.loads(m['argumentids']),
                    'warp': m.get('warp', 'false')}
        self.callable = {}   # short name -> proc info
        self.cur_params = []
        self.ln = 0
        self.script_heights = []

    def nid(self):
        self.n += 1
        return '%s%05d' % (self.prefix, self.n)

    def err(self, msg):
        raise CompileError('line %d: %s' % (self.ln, msg))

    def block(self, opcode, inputs=None, fields=None, shadow=False, top=False, mutation=None):
        bid = self.nid()
        b = {'opcode': opcode, 'next': None, 'parent': None, 'inputs': inputs or {},
             'fields': fields or {}, 'shadow': shadow, 'topLevel': top}
        if mutation is not None:
            b['mutation'] = mutation
        self.blocks[bid] = b
        # set parents of child blocks
        for v in b['inputs'].values():
            for x in v[1:]:
                if isinstance(x, str) and x in self.blocks:
                    self.blocks[x]['parent'] = bid
        return bid

    # ---- variable lookup
    def var_ref(self, name):
        if name in self.vars:
            return [12, name, self.vars[name]]
        if name in self.gvars:
            return [12, name, self.gvars[name]]
        self.err('unknown variable %r' % name)

    def var_field(self, name):
        if name in self.vars:
            return [name, self.vars[name]]
        if name in self.gvars:
            return [name, self.gvars[name]]
        self.err('unknown variable %r' % name)

    def list_field(self, name):
        if name in self.lists:
            return [name, self.lists[name]]
        if name in self.glists:
            return [name, self.glists[name]]
        self.err('unknown list %r' % name)

    # ---- expressions: return ('lit', text) | ('blk', id) | ('ref', [12..]) ; bool flag
    def is_bool(self, e):
        if e[0] == 'bin' and e[1] in ('==', '!=', '<', '>', '<=', '>=', 'and', 'or'):
            return True
        if e[0] == 'not':
            return True
        if e[0] == 'call' and e[1] in ('mousedown', 'key', 'contains', 'has'):
            return True
        return False

    def value(self, e):
        """Compile a value expression; returns an 'input source'."""
        if self.is_bool(e):
            self.err('boolean used as a value: %r' % (e,))
        k = e[0]
        if k == 'num':
            return ('lit', fmt_num(e[1]))
        if k == 'str':
            return ('lit', e[1])
        if k == 'name':
            if e[1] in self.cur_params:
                return ('blk', self.block('argument_reporter_string_number', fields={'VALUE': [e[1], None]}))
            return ('ref', self.var_ref(e[1]))
        if k == 'item':
            return ('blk', self.block('data_itemoflist', {'INDEX': self.inp(e[2], 7)},
                                      {'LIST': self.list_field(e[1])}))
        if k == 'bin':
            op = e[1]
            opc = {'+': 'operator_add', '-': 'operator_subtract', '*': 'operator_multiply',
                   '/': 'operator_divide', '%': 'operator_mod'}[op]
            return ('blk', self.block(opc, {'NUM1': self.inp(e[2], 4), 'NUM2': self.inp(e[3], 4)}))
        if k == 'call':
            return self.call_value(e[1], e[2])
        if k == 'method':
            self.err('list method %s used as value' % e[2])
        self.err('bad expression %r' % (e,))

    def inp(self, e, typ):
        """Input array for a value slot of primitive type typ (4 num, 6 posint, 7 int, 10 text, 9 color)."""
        if typ == 9 and e[0] == 'num' and e[1] > 0xFFFFFF:
            # colours with alpha can't be written as '#rrggbb' literals; pass the number via a reporter
            e = ('call', 'join', [e, ('str', '')])
        src = self.value(e)
        default = '' if typ == 10 else ('#000000' if typ == 9 else '')
        if src[0] == 'lit':
            if typ == 9:
                v = src[1]
                try:
                    v = '#%06x' % int(float(v))
                except ValueError:
                    pass
                return [1, [9, v]]
            return [1, [typ, src[1]]]
        if src[0] == 'ref':
            return [3, src[1], [typ, default]]
        return [3, src[1], [typ, default]]

    def cond(self, e):
        if not self.is_bool(e):
            self.err('condition is not boolean: %r' % (e,))
        k = e[0]
        if k == 'not':
            return self.block('operator_not', {'OPERAND': [2, self.cond(e[1])]})
        if k == 'bin':
            op = e[1]
            if op in ('and', 'or'):
                return self.block('operator_' + op, {'OPERAND1': [2, self.cond(e[2])],
                                                     'OPERAND2': [2, self.cond(e[3])]})
            if op == '!=':
                return self.block('operator_not', {'OPERAND': [2, self.cond(('bin', '==', e[2], e[3]))]})
            if op == '<=':
                return self.block('operator_not', {'OPERAND': [2, self.cond(('bin', '>', e[2], e[3]))]})
            if op == '>=':
                return self.block('operator_not', {'OPERAND': [2, self.cond(('bin', '<', e[2], e[3]))]})
            opc = {'==': 'operator_equals', '<': 'operator_lt', '>': 'operator_gt'}[op]
            return self.block(opc, {'OPERAND1': self.inp(e[2], 10), 'OPERAND2': self.inp(e[3], 10)})
        if k == 'call':
            name, args = e[1], e[2]
            if name == 'mousedown':
                return self.block('sensing_mousedown')
            if name == 'key':
                menu = self.block('sensing_keyoptions', fields={'KEY_OPTION': [args[0][1], None]}, shadow=True)
                return self.block('sensing_keypressed', {'KEY_OPTION': [1, menu]})
            if name == 'contains':
                return self.block('operator_contains', {'STRING1': self.inp(args[0], 10), 'STRING2': self.inp(args[1], 10)})
            if name == 'has':
                return self.block('data_listcontainsitem', {'ITEM': self.inp(args[1], 10)},
                                  {'LIST': self.list_field(args[0][1])})
        self.err('bad condition %r' % (e,))

    def call_value(self, name, args):
        def need(n):
            if len(args) != n:
                self.err('%s takes %d args' % (name, n))
        if name in MATHOPS:
            need(1)
            return ('blk', self.block('operator_mathop', {'NUM': self.inp(args[0], 4)},
                                      {'OPERATOR': [MATHOPS[name], None]}))
        if name == 'round':
            need(1)
            return ('blk', self.block('operator_round', {'NUM': self.inp(args[0], 4)}))
        if name == 'join':
            if len(args) < 2:
                self.err('join needs 2+ args')
            # right-nested join
            if len(args) == 2:
                return ('blk', self.block('operator_join', {'STRING1': self.inp(args[0], 10),
                                                            'STRING2': self.inp(args[1], 10)}))
            return ('blk', self.block('operator_join', {'STRING1': self.inp(args[0], 10),
                                                        'STRING2': self.inp(('call', 'join', args[1:]), 10)}))
        if name == 'letter':
            need(2)
            return ('blk', self.block('operator_letter_of', {'LETTER': self.inp(args[0], 6),
                                                             'STRING': self.inp(args[1], 10)}))
        if name == 'strlen':
            need(1)
            return ('blk', self.block('operator_length', {'STRING': self.inp(args[0], 10)}))
        if name == 'count':
            need(1)
            return ('blk', self.block('data_lengthoflist', fields={'LIST': self.list_field(args[0][1])}))
        if name == 'indexof':
            need(2)
            return ('blk', self.block('data_itemnumoflist', {'ITEM': self.inp(args[1], 10)},
                                      {'LIST': self.list_field(args[0][1])}))
        if name == 'random':
            need(2)
            return ('blk', self.block('operator_random', {'FROM': self.inp(args[0], 4), 'TO': self.inp(args[1], 4)}))
        simple = {'mousex': 'sensing_mousex', 'mousey': 'sensing_mousey', 'answer': 'sensing_answer',
                  'timer': 'sensing_timer', 'days': 'sensing_dayssince2000'}
        if name in simple:
            need(0)
            return ('blk', self.block(simple[name]))
        if name == 'costumenum':
            return ('blk', self.block('looks_costumenumbername', fields={'NUMBER_NAME': ['number', None]}))
        self.err('unknown function %s' % name)

    # ---- statements
    def stmts(self, body):
        ids = []
        for s in body:
            self.ln = s[-1]
            r = self.stmt(s)
            if isinstance(r, list):
                ids.extend(r)
            else:
                ids.append(r)
        for a, b in zip(ids, ids[1:]):
            self.blocks[a]['next'] = b
            self.blocks[b]['parent'] = a
        return ids

    def substack(self, body, parent_holder):
        ids = self.stmts(body)
        if not ids:
            return None
        return ids[0]

    def mk_c(self, opcode, inputs, subs):
        """Make a C block; subs maps input name -> body."""
        for key, body in subs.items():
            ids = self.stmts(body)
            if ids:
                inputs[key] = [2, ids[0]]
        bid = self.block(opcode, inputs)
        for key in subs:
            if key in inputs:
                self.blocks[inputs[key][1]]['parent'] = bid
        return bid

    def stmt(self, s):
        k = s[0]
        if k == 'set':
            return self.block('data_setvariableto', {'VALUE': self.inp(s[2], 10)}, {'VARIABLE': self.var_field(s[1])})
        if k == 'change':
            return self.block('data_changevariableby', {'VALUE': self.inp(s[2], 4)}, {'VARIABLE': self.var_field(s[1])})
        if k == 'replace':
            return self.block('data_replaceitemoflist', {'INDEX': self.inp(s[2], 7), 'ITEM': self.inp(s[3], 10)},
                              {'LIST': self.list_field(s[1])})
        if k == 'if':
            cond = self.cond(s[1])
            if s[3] is None:
                b = self.mk_c('control_if', {'CONDITION': [2, cond]}, {'SUBSTACK': s[2]})
            else:
                b = self.mk_c('control_if_else', {'CONDITION': [2, cond]}, {'SUBSTACK': s[2], 'SUBSTACK2': s[3]})
            self.blocks[cond]['parent'] = b
            return b
        if k == 'while':
            cond = self.cond(('not', s[1]))
            b = self.mk_c('control_repeat_until', {'CONDITION': [2, cond]}, {'SUBSTACK': s[2]})
            self.blocks[cond]['parent'] = b
            return b
        if k == 'until':
            cond = self.cond(s[1])
            b = self.mk_c('control_repeat_until', {'CONDITION': [2, cond]}, {'SUBSTACK': s[2]})
            self.blocks[cond]['parent'] = b
            return b
        if k == 'repeat':
            return self.mk_c('control_repeat', {'TIMES': self.inp(s[1], 6)}, {'SUBSTACK': s[2]})
        if k == 'forever':
            return self.mk_c('control_forever', {}, {'SUBSTACK': s[1]})
        if k == 'for':
            _, var, a, b, body, ln = s
            init = self.stmt(['set', var, a, ln])
            body2 = body + [['change', var, ('num', 1), ln]]
            if a[0] == 'num':
                times = fold(('bin', '+', fold(('bin', '-', b, a)), ('num', 1)))
            else:
                times = ('bin', '+', ('bin', '-', b, a), ('num', 1))
            loop = self.mk_c('control_repeat', {'TIMES': self.inp(times, 6)}, {'SUBSTACK': body2})
            return [init, loop]
        if k == 'return':
            return self.block('control_stop', fields={'STOP_OPTION': ['this script', None]},
                              mutation={'tagName': 'mutation', 'children': [], 'hasnext': 'false'})
        if k == 'expr':
            e = s[1]
            if e[0] == 'method':
                return self.list_method(e[1], e[2], e[3])
            return self.call_stmt(e[1], e[2])
        self.err('bad statement %r' % (s,))

    def list_method(self, lst, meth, args):
        f = {'LIST': self.list_field(lst)}
        if meth == 'add':
            return self.block('data_addtolist', {'ITEM': self.inp(args[0], 10)}, f)
        if meth == 'clear':
            return self.block('data_deletealloflist', {}, f)
        if meth == 'del':
            return self.block('data_deleteoflist', {'INDEX': self.inp(args[0], 7)}, f)
        if meth == 'insert':
            return self.block('data_insertatlist', {'INDEX': self.inp(args[0], 7), 'ITEM': self.inp(args[1], 10)}, f)
        if meth == 'show':
            return self.block('data_showlist', {}, f)
        if meth == 'hide':
            return self.block('data_hidelist', {}, f)
        self.err('unknown list method %s' % meth)

    def call_stmt(self, name, args):
        def need(n):
            if len(args) != n:
                self.err('%s takes %d args' % (name, n))
        if name in self.callable:
            info = self.callable[name]
            if len(args) != len(info['argids']):
                self.err('%s takes %d args' % (name, len(info['argids'])))
            inputs = {aid: self.inp(a, 10) for aid, a in zip(info['argids'], args)}
            return self.block('procedures_call', inputs, mutation={
                'tagName': 'mutation', 'children': [], 'proccode': info['proccode'],
                'argumentids': json.dumps(info['argids']), 'warp': info['warp']})
        if name == 'goto':
            need(2)
            return self.block('motion_gotoxy', {'X': self.inp(args[0], 4), 'Y': self.inp(args[1], 4)})
        simple = {'pendown': 'pen_penDown', 'penup': 'pen_penUp', 'erase': 'pen_clear', 'stamp': 'pen_stamp',
                  'hide': 'looks_hide', 'show': 'looks_show'}
        if name in simple:
            need(0)
            return self.block(simple[name])
        if name == 'pensize':
            need(1)
            return self.block('pen_setPenSizeTo', {'SIZE': self.inp(args[0], 4)})
        if name == 'pencolor':
            need(1)
            return self.block('pen_setPenColorToColor', {'COLOR': self.inp(args[0], 9)})
        if name == 'setsize':
            need(1)
            return self.block('looks_setsizeto', {'SIZE': self.inp(args[0], 4)})
        if name == 'costume':
            need(1)
            a = args[0]
            if a[0] == 'str':
                menu = self.block('looks_costume', fields={'COSTUME': [a[1], None]}, shadow=True)
                return self.block('looks_switchcostumeto', {'COSTUME': [1, menu]})
            menu = self.block('looks_costume', fields={'COSTUME': ['_fence', None]}, shadow=True)
            src = self.value(a)
            ref = src[1] if src[0] != 'lit' else None
            return self.block('looks_switchcostumeto', {'COSTUME': [3, ref, menu]})
        if name == 'ask':
            need(1)
            return self.block('sensing_askandwait', {'QUESTION': self.inp(args[0], 10)})
        if name == 'wait':
            need(1)
            return self.block('control_wait', {'DURATION': self.inp(args[0], 5)})
        if name == 'broadcast':
            need(1)
            msg = args[0][1]
            if msg not in self.broadcasts:
                bid = 'bc_' + re.sub(r'\W', '_', msg)
                self.stage.setdefault('broadcasts', {})[bid] = msg
                self.broadcasts[msg] = bid
            return self.block('event_broadcast', {'BROADCAST_INPUT': [1, [11, msg, self.broadcasts[msg]]]})
        self.err('unknown statement/proc %s' % name)

    # ---- top level
    def compile(self, prog, layout_x=1400):
        # declare vars & lists
        for name in prog.vars:
            if name in self.vars:
                raise CompileError('variable %r already exists' % name)
            vid = self.nid()
            self.sprite['variables'][vid] = [name, 0]
            self.vars[name] = vid
        for name in prog.lists:
            if name in self.lists:
                raise CompileError('list %r already exists' % name)
            lid = self.nid()
            self.sprite['lists'][lid] = [name, []]
            self.lists[name] = lid
        for name in prog.globals:
            if name not in self.gvars and name not in self.glists:
                raise CompileError('unknown global %r' % name)
        for short, code in prog.externs.items():
            if code not in self.procs:
                raise CompileError('extern: no procedure %r' % code)
            self.callable[short] = self.procs[code]
        # declare own procs first (so calls can be forward)
        for node in prog.procs:
            _, name, params, warp, body, ln, _c = node
            code = ' '.join([name] + ['%s'] * len(params))
            if name in self.callable or code in self.procs:
                raise CompileError('line %d: duplicate procedure %s' % (ln, name))
            info = {'proccode': code, 'argids': [self.nid() for _ in params], 'warp': 'true' if warp else 'false',
                    'names': params}
            self.procs[code] = info
            self.callable[name] = info
        scripts = []
        for node in prog.procs:
            _, name, params, warp, body, ln, cmt = node
            info = self.callable[name]
            self.cur_params = params
            self.ln = ln
            argshadows = {}
            for aid, pname in zip(info['argids'], params):
                argshadows[aid] = self.block('argument_reporter_string_number', fields={'VALUE': [pname, None]}, shadow=True)
            proto = self.block('procedures_prototype', {aid: [1, sid] for aid, sid in argshadows.items()}, shadow=True,
                               mutation={'tagName': 'mutation', 'children': [], 'proccode': info['proccode'],
                                         'argumentids': json.dumps(info['argids']),
                                         'argumentnames': json.dumps(params),
                                         'argumentdefaults': json.dumps([''] * len(params)),
                                         'warp': info['warp']})
            d = self.block('procedures_definition', {'custom_block': [1, proto]}, top=True)
            self.blocks[proto]['parent'] = d
            ids = self.stmts(body)
            if ids:
                self.blocks[d]['next'] = ids[0]
                self.blocks[ids[0]]['parent'] = d
            scripts.append((d, cmt))
        self.cur_params = []
        for node in prog.hats:
            _, kind, arg, body, ln, cmt = node
            self.ln = ln
            if kind == 'flag':
                h = self.block('event_whenflagclicked', top=True)
            elif kind == 'key':
                h = self.block('event_whenkeypressed', fields={'KEY_OPTION': [arg, None]}, top=True)
            elif kind == 'broadcast':
                if arg not in self.broadcasts:
                    bid = 'bc_' + re.sub(r'\W', '_', arg)
                    self.stage.setdefault('broadcasts', {})[bid] = arg
                    self.broadcasts[arg] = bid
                h = self.block('event_whenbroadcastreceived', fields={'BROADCAST_OPTION': [arg, self.broadcasts[arg]]}, top=True)
            else:
                raise CompileError('line %d: unknown hat %s' % (ln, kind))
            ids = self.stmts(body)
            if ids:
                self.blocks[h]['next'] = ids[0]
                self.blocks[ids[0]]['parent'] = h
            scripts.append((h, cmt))
        # layout: columns of scripts
        x, y, colw = layout_x, 0, 900
        comments = self.sprite.setdefault('comments', {})
        for sid, cmt in scripts:
            h = self.count_height(sid)
            if y > 0 and y + h > 12000:
                x += colw
                y = 0
            self.blocks[sid]['x'] = x
            self.blocks[sid]['y'] = y
            if cmt:
                cid = self.nid()
                comments[cid] = {'blockId': sid, 'x': x + 520, 'y': y, 'width': 360,
                                 'height': 40 + 18 * len(cmt), 'minimized': False, 'text': '\n'.join(cmt)}
            y += h + 120

    def count_height(self, bid):
        n = 0
        stack = [bid]
        while stack:
            b = stack.pop()
            if not b:
                continue
            n += 1
            blk = self.blocks[b]
            stack.append(blk['next'])
            for key in ('SUBSTACK', 'SUBSTACK2'):
                if key in blk['inputs']:
                    stack.append(blk['inputs'][key][1])
                    n += 1
        return n * 48 + 60
