"""
sb3dsl - a tiny Python DSL that compiles to Scratch 3 blocks.

Scratch code is written as ordinary Python that *emits* blocks:

    v.x = v.x + 1                      # set [x] to ((x) + (1))
    with If(v.x > 10):                 # if <(x) > (10)> then
        l.items.add(join("x=", v.x))   #   add (join [x=] (x)) to [items]
    with Else():                       # else
        pen_down()

Expressions are built with Python operators (+ - * / %, < > <= >=, & | ~),
statements are appended to whichever stack is currently open, and
`with` blocks open substacks.  Custom blocks are declared with @proc and
called like Python functions.  The result is merged into an existing .sb3
(the pen text engine) so its custom blocks can be called directly.
"""
import contextlib
import hashlib
import json
import zipfile

# ---------------------------------------------------------------- expressions


def _num(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        r = repr(v)
        return r
    return str(v)


def lit(v):
    return v if isinstance(v, Expr) else Lit(v)


class Expr:
    is_bool = False

    def __add__(s, o): return Op("operator_add", NUM1=("num", s), NUM2=("num", o))
    def __radd__(s, o): return Op("operator_add", NUM1=("num", o), NUM2=("num", s))
    def __sub__(s, o): return Op("operator_subtract", NUM1=("num", s), NUM2=("num", o))
    def __rsub__(s, o): return Op("operator_subtract", NUM1=("num", o), NUM2=("num", s))
    def __mul__(s, o): return Op("operator_multiply", NUM1=("num", s), NUM2=("num", o))
    def __rmul__(s, o): return Op("operator_multiply", NUM1=("num", o), NUM2=("num", s))
    def __truediv__(s, o): return Op("operator_divide", NUM1=("num", s), NUM2=("num", o))
    def __rtruediv__(s, o): return Op("operator_divide", NUM1=("num", o), NUM2=("num", s))
    def __mod__(s, o): return Op("operator_mod", NUM1=("num", s), NUM2=("num", o))
    def __rmod__(s, o): return Op("operator_mod", NUM1=("num", o), NUM2=("num", s))
    def __neg__(s): return Op("operator_subtract", NUM1=("num", 0), NUM2=("num", s))

    def __lt__(s, o): return BOp("operator_lt", OPERAND1=("text", s), OPERAND2=("text", o))
    def __gt__(s, o): return BOp("operator_gt", OPERAND1=("text", s), OPERAND2=("text", o))
    def __le__(s, o): return ~(s > o)
    def __ge__(s, o): return ~(s < o)

    def __and__(s, o): return BOp("operator_and", OPERAND1=("bool", s), OPERAND2=("bool", o))
    def __or__(s, o): return BOp("operator_or", OPERAND1=("bool", s), OPERAND2=("bool", o))
    def __invert__(s): return BOp("operator_not", OPERAND=("bool", s))

    __hash__ = object.__hash__


class Lit(Expr):
    def __init__(s, v):
        s.v = v


class Op(Expr):
    def __init__(s, opcode, fields=None, mutation=None, **inputs):
        s.opcode = opcode
        s.inputs = inputs
        s.fields = fields or {}
        s.mutation = mutation


class BOp(Op):
    is_bool = True


class VarRef(Expr):
    def __init__(s, name):
        s.name = name


class ArgRef(Expr):
    def __init__(s, name):
        s.name = name


def eq(a, b): return BOp("operator_equals", OPERAND1=("text", a), OPERAND2=("text", b))
def ne(a, b): return ~eq(a, b)


def join(*parts):
    parts = list(parts)
    if len(parts) == 1:
        return Op("operator_join", STRING1=("text", parts[0]), STRING2=("text", ""))
    e = parts[-1]
    for p in reversed(parts[:-1]):
        e = Op("operator_join", STRING1=("text", p), STRING2=("text", e))
    return e


def letter(i, s): return Op("operator_letter_of", LETTER=("whole", i), STRING=("text", s))
def strlen(s): return Op("operator_length", STRING=("text", s))
def mathop(name, x): return Op("operator_mathop", fields={"OPERATOR": [name, None]}, NUM=("num", x))
def sqrt(x): return mathop("sqrt", x)
def abs_(x): return mathop("abs", x)
def floor(x): return mathop("floor", x)
def ceil(x): return mathop("ceiling", x)
def sin(x): return mathop("sin", x)   # degrees
def cos(x): return mathop("cos", x)   # degrees
def atan(x): return mathop("atan", x)
def round_(x): return Op("operator_round", NUM=("num", x))
def rand(a, b): return Op("operator_random", FROM=("num", a), TO=("num", b))
def mouse_x(): return Op("sensing_mousex")
def mouse_y(): return Op("sensing_mousey")
def mouse_down(): return BOp("sensing_mousedown")
def timer(): return Op("sensing_timer")
def days_since_2000(): return Op("sensing_dayssince2000")
def clock_ms(): return days_since_2000() * 86400000
def key_pressed(k): return BOp("sensing_keypressed", KEY_OPTION=(("menu", "sensing_keyoptions", "KEY_OPTION"), k))
def costume_name(): return Op("looks_costumenumbername", fields={"NUMBER_NAME": ["name", None]})


# ----------------------------------------------------------------- statements

class Stmt:
    def __init__(s, opcode, inputs=None, fields=None, subs=None, mutation=None):
        s.opcode = opcode
        s.inputs = inputs or {}
        s.fields = fields or {}
        s.subs = subs or {}
        s.mutation = mutation


_stack = []


def emit(st):
    if not _stack:
        raise RuntimeError("statement emitted outside of a script")
    _stack[-1].append(st)
    return st


def stmt(opcode, fields=None, mutation=None, **inputs):
    return emit(Stmt(opcode, inputs, fields, mutation=mutation))


@contextlib.contextmanager
def _sub():
    body = []
    _stack.append(body)
    try:
        yield body
    finally:
        _stack.pop()


@contextlib.contextmanager
def If(cond):
    with _sub() as body:
        yield
    emit(Stmt("control_if", {"CONDITION": ("bool", cond)}, subs={"SUBSTACK": body}))


@contextlib.contextmanager
def Else():
    last = _stack[-1][-1]
    assert last.opcode == "control_if", "Else() must directly follow If()"
    with _sub() as body:
        yield
    last.opcode = "control_if_else"
    last.subs["SUBSTACK2"] = body


@contextlib.contextmanager
def Repeat(n):
    with _sub() as body:
        yield
    emit(Stmt("control_repeat", {"TIMES": ("whole", n)}, subs={"SUBSTACK": body}))


@contextlib.contextmanager
def RepeatUntil(cond):
    with _sub() as body:
        yield
    emit(Stmt("control_repeat_until", {"CONDITION": ("bool", cond)}, subs={"SUBSTACK": body}))


def While(cond):
    return RepeatUntil(~cond)


@contextlib.contextmanager
def Forever():
    with _sub() as body:
        yield
    emit(Stmt("control_forever", subs={"SUBSTACK": body}))


@contextlib.contextmanager
def For(var, start, end):
    """for var = start .. end (inclusive, end evaluated once)."""
    setvar(var, start)
    with Repeat(end - start + 1 if isinstance(start, Expr) or isinstance(end, Expr) else end - start + 1):
        yield
        setvar(var, var + 1)


def setvar(var, value):
    assert isinstance(var, VarRef)
    stmt("data_setvariableto", fields={"VARIABLE": var}, VALUE=("text", value))


def changevar(var, value):
    stmt("data_changevariableby", fields={"VARIABLE": var}, VALUE=("num", value))


def stop_this():
    stmt("control_stop", fields={"STOP_OPTION": ["this script", None]},
         mutation={"tagName": "mutation", "children": [], "hasnext": "false"})


# pen / motion / looks
def pen_up(): stmt("pen_penUp")
def pen_down(): stmt("pen_penDown")
def erase_all(): stmt("pen_clear")
def stamp(): stmt("pen_stamp")
def pen_size(s): stmt("pen_setPenSizeTo", SIZE=("num", s))
def pen_color(c): stmt("pen_setPenColorToColor", COLOR=("color", c))
def pen_param(param, value):
    stmt("pen_setPenColorParamTo", COLOR_PARAM=(("menu", "pen_menu_colorParam", "colorParam"), param), VALUE=("num", value))
def goto(x, y): stmt("motion_gotoxy", X=("num", x), Y=("num", y))
def switch_costume(c): stmt("looks_switchcostumeto", COSTUME=(("menu", "looks_costume", "COSTUME"), c))
def hide(): stmt("looks_hide")


# ------------------------------------------------------- variables and lists

class _VarNS:
    """v.foo_bar reads variable 'foo bar'; v.foo_bar = x sets it."""

    def __init__(s, prefix=""):
        object.__setattr__(s, "_prefix", prefix)

    def _name(s, n):
        return s._prefix + n.replace("_", " ")

    def __getattr__(s, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return VarRef(s._name(n))

    def __setattr__(s, n, value):
        setvar(VarRef(s._name(n)), value)

    def __getitem__(s, name):
        return VarRef(name)

    def __setitem__(s, name, value):
        setvar(VarRef(name), value)


def Locals(prefix):
    """Per-procedure scratch variables: Locals('solve').i -> variable 'solve.i'."""
    return _VarNS(prefix + ".")


v = _VarNS()


class ListRef:
    def __init__(s, name):
        s.name = name

    def __getitem__(s, i):
        return Op("data_itemoflist", fields={"LIST": s}, INDEX=("int", i))

    def __setitem__(s, i, value):
        stmt("data_replaceitemoflist", fields={"LIST": s}, INDEX=("int", i), ITEM=("text", value))

    def add(s, value):
        stmt("data_addtolist", fields={"LIST": s}, ITEM=("text", value))

    def clear(s):
        stmt("data_deletealloflist", fields={"LIST": s})

    def delete(s, i):
        stmt("data_deleteoflist", fields={"LIST": s}, INDEX=("int", i))

    def insert(s, i, value):
        stmt("data_insertatlist", fields={"LIST": s}, INDEX=("int", i), ITEM=("text", value))

    def index(s, value):
        return Op("data_itemnumoflist", fields={"LIST": s}, ITEM=("text", value))

    @property
    def length(s):
        return Op("data_lengthoflist", fields={"LIST": s})


class _ListNS:
    def __getattr__(s, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return ListRef(n.replace("_", " "))

    def __getitem__(s, name):
        return ListRef(name)


l = _ListNS()


# ----------------------------------------------------------------- procedures

class Proc:
    def __init__(s, project, proccode, argnames, warp=True, fn=None, argids=None):
        s.project = project
        s.proccode = proccode
        s.argnames = argnames
        s.warp = warp
        s.fn = fn
        s.argids = argids or [project.newid("a") for _ in argnames]

    def __call__(s, *args):
        assert len(args) == len(s.argnames), (s.proccode, args)
        inputs = {aid: ("text", a) for aid, a in zip(s.argids, args)}
        emit(Stmt("procedures_call", inputs, mutation={
            "tagName": "mutation", "children": [], "proccode": s.proccode,
            "argumentids": json.dumps(s.argids), "warp": "true" if s.warp else "false"}))


# ------------------------------------------------------------------- project

SHADOW_TYPES = {"num": 4, "pos": 5, "whole": 6, "int": 7, "angle": 8, "color": 9, "text": 10}


class Project:
    def __init__(s, base_sb3, sprite_name):
        with zipfile.ZipFile(base_sb3) as z:
            s.files = {n: z.read(n) for n in z.namelist()}
        s.pj = json.loads(s.files["project.json"])
        s.stage = next(t for t in s.pj["targets"] if t["isStage"])
        s.sprite = next(t for t in s.pj["targets"] if t["name"] == sprite_name)
        s._id = 0
        s.procs = []
        s.scripts = []      # (kind, payload) top-level scripts to build
        s.blocks = s.sprite["blocks"]

    # -- ids, variables
    def newid(s, prefix="p"):
        s._id += 1
        return f"phx{prefix}{s._id}"

    def var_id(s, name):
        for t in (s.sprite, s.stage):
            for vid, (n, *_r) in t["variables"].items():
                if n == name:
                    return vid
        vid = s.newid("v")
        s.sprite["variables"][vid] = [name, 0]
        return vid

    def list_id(s, name):
        for t in (s.sprite, s.stage):
            for lid, (n, *_r) in t["lists"].items():
                if n == name:
                    return lid
        lid = s.newid("l")
        s.sprite["lists"][lid] = [name, []]
        return lid

    def set_list_contents(s, name, items):
        s.sprite["lists"][s.list_id(name)][1] = list(items)

    # -- existing custom blocks (text engine)
    def external_proc(s, proccode):
        for b in s.blocks.values():
            if isinstance(b, dict) and b.get("opcode") == "procedures_prototype" and b["mutation"]["proccode"] == proccode:
                m = b["mutation"]
                return Proc(s, proccode, json.loads(m["argumentnames"]), m["warp"] in ("true", True),
                            argids=json.loads(m["argumentids"]))
        raise KeyError(proccode)

    def proc(s, warp=True, name=None):
        """Decorator: def foo_bar(a, b) -> custom block 'foo bar a: %s b: %s'."""
        def deco(fn):
            import inspect
            argnames = list(inspect.signature(fn).parameters)
            title = name or fn.__name__.replace("_", " ")
            proccode = title + "".join(f" {a.replace('_', ' ')}: %s" for a in argnames)
            p = Proc(s, proccode, [a.replace("_", " ") for a in argnames], warp, fn)
            s.procs.append(p)
            return p
        return deco

    def script(s, hat_opcode, fields=None):
        def deco(fn):
            s.scripts.append((hat_opcode, fields or {}, fn))
            return fn
        return deco

    # -- removing parts of the base project
    def remove_scripts(s, target, predicate):
        B = target["blocks"]

        def root(bid):
            seen = 0
            while B[bid].get("parent"):
                bid = B[bid]["parent"]
                seen += 1
                assert seen < 100000
            return bid
        tops = {bid for bid, b in B.items() if isinstance(b, dict) and b.get("topLevel") and predicate(B, b)}
        dead = {bid for bid, b in B.items() if isinstance(b, dict) and root(bid) in tops}
        for bid in dead:
            del B[bid]
        for cid in list(target.get("comments", {})):
            if target["comments"][cid].get("blockId") in dead:
                del target["comments"][cid]
        return len(dead)

    # -- compiling
    def _new_block(s, opcode, parent, shadow=False, toplevel=False):
        bid = s.newid()
        b = {"opcode": opcode, "next": None, "parent": parent, "inputs": {}, "fields": {},
             "shadow": shadow, "topLevel": toplevel}
        s.blocks[bid] = b
        return bid, b

    def _fields(s, fields):
        out = {}
        for k, val in fields.items():
            if isinstance(val, VarRef):
                out[k] = [val.name, s.var_id(val.name)]
            elif isinstance(val, ListRef):
                out[k] = [val.name, s.list_id(val.name)]
            else:
                out[k] = val
        return out

    def _expr(s, e, parent):
        """Compile a reporter expression to a block id (Lit / VarRef handled by _input)."""
        if isinstance(e, ArgRef):
            bid, b = s._new_block("argument_reporter_string_number", parent)
            b["fields"] = {"VALUE": [e.name, None]}
            return bid
        if isinstance(e, VarRef):
            bid, b = s._new_block("data_variable", parent)
            b["fields"] = {"VARIABLE": [e.name, s.var_id(e.name)]}
            return bid
        assert isinstance(e, Op), e
        bid, b = s._new_block(e.opcode, parent)
        b["fields"] = s._fields(e.fields)
        for name, (kind, val) in e.inputs.items():
            b["inputs"][name] = s._input(kind, val, bid)
        if e.mutation:
            b["mutation"] = e.mutation
        return bid

    def _input(s, kind, val, parent):
        if isinstance(kind, tuple) and kind[0] == "menu":
            _, shop, field = kind
            if isinstance(val, Expr) and not isinstance(val, Lit):
                default = {"looks_costume": "_fence", "sensing_keyoptions": "space",
                           "pen_menu_colorParam": "color"}[shop]
                sid, sb = s._new_block(shop, parent, shadow=True)
                sb["fields"] = {field: [default, None]}
                return [3, s._expr(val, parent), sid]
            sid, sb = s._new_block(shop, parent, shadow=True)
            sb["fields"] = {field: [val.v if isinstance(val, Lit) else val, None]}
            return [1, sid]
        if kind == "bool":
            assert isinstance(val, Expr) and not isinstance(val, (Lit, VarRef)), \
                f"boolean slot needs a boolean block, got {val!r}"
            return [2, s._expr(val, parent)]
        st = SHADOW_TYPES[kind]
        if kind == "color":
            default = "#000000"
            if not isinstance(val, Expr):
                return [1, [9, "#%06x" % int(val)]]
        else:
            default = ""
        if not isinstance(val, Expr) or isinstance(val, Lit):
            raw = val.v if isinstance(val, Lit) else val
            return [1, [st, _num(raw)]]
        if isinstance(val, VarRef):
            return [3, [12, val.name, s.var_id(val.name)], [st, default]]
        return [3, s._expr(val, parent), [st, default]]

    def _chain(s, stmts, parent):
        """Compile a list of statements; returns first block id."""
        first = None
        prev = None
        for st in stmts:
            bid, b = s._new_block(st.opcode, prev if prev else parent)
            b["fields"] = s._fields(st.fields)
            for name, (kind, val) in st.inputs.items():
                b["inputs"][name] = s._input(kind, val, bid)
            for name, body in st.subs.items():
                if body:
                    b["inputs"][name] = [2, s._chain(body, bid)]
            if st.mutation:
                b["mutation"] = st.mutation
            if prev:
                s.blocks[prev]["next"] = bid
            else:
                first = bid
            prev = bid
        return first

    def _place(s, nblocks):
        # simple column layout for the editor
        if not hasattr(s, "_cursor"):
            s._cursor = [2600, 0, 0]
        x, y, col = s._cursor
        h = 60 + nblocks * 26
        if y + h > 9000 and y > 0:
            x += 900
            y = 0
        s._cursor = [x, y + h + 60, col]
        return x, y

    def build(s):
        count = lambda body: sum(1 + sum(count(b) for b in st.subs.values()) for st in body)
        for hat, fields, fn in s.scripts:
            with _sub() as body:
                fn()
            bid, b = s._new_block(hat, None, toplevel=True)
            b["fields"] = fields
            b["x"], b["y"] = s._place(count(body))
            if body:
                b["next"] = s._chain(body, bid)
        for p in s.procs:
            with _sub() as body:
                p.fn(*[ArgRef(a) for a in p.argnames])
            did, d = s._new_block("procedures_definition", None, toplevel=True)
            d["x"], d["y"] = s._place(count(body))
            pid, pb = s._new_block("procedures_prototype", did, shadow=True)
            d["inputs"]["custom_block"] = [1, pid]
            for aid, an in zip(p.argids, p.argnames):
                rid, rb = s._new_block("argument_reporter_string_number", pid, shadow=True)
                rb["fields"] = {"VALUE": [an, None]}
                pb["inputs"][aid] = [1, rid]
            pb["mutation"] = {"tagName": "mutation", "children": [], "proccode": p.proccode,
                              "argumentids": json.dumps(p.argids), "argumentnames": json.dumps(p.argnames),
                              "argumentdefaults": json.dumps(["" for _ in p.argnames]),
                              "warp": "true" if p.warp else "false"}
            if body:
                d["next"] = s._chain(body, did)
        s.validate()

    def validate(s):
        procs = {b["mutation"]["proccode"] for b in s.blocks.values()
                 if isinstance(b, dict) and b.get("opcode") == "procedures_prototype"}
        for bid, b in s.blocks.items():
            if not isinstance(b, dict):
                continue
            if b.get("opcode") == "procedures_call":
                assert b["mutation"]["proccode"] in procs, "call to undefined block: " + b["mutation"]["proccode"]
            for name, inp in b["inputs"].items():
                for x in inp[1:]:
                    if isinstance(x, str):
                        assert x in s.blocks, (bid, name, x)
                        assert s.blocks[x]["parent"] == bid, (bid, name, x)
            if b.get("next"):
                assert s.blocks[b["next"]]["parent"] == bid
        # every referenced variable must exist
        ids = set()
        for t in (s.sprite, s.stage):
            ids |= set(t["variables"]) | set(t["lists"])
        for b in s.blocks.values():
            if not isinstance(b, dict):
                continue
            for f in b["fields"].values():
                if isinstance(f, list) and len(f) > 1 and f[1] and f[1] not in ids and \
                        b["opcode"].startswith("data_"):
                    raise AssertionError(("missing variable", b["opcode"], f))

    def add_comment(s, target, text, x, y, w=420, h=300):
        cid = s.newid("c")
        target.setdefault("comments", {})[cid] = {"blockId": None, "x": x, "y": y, "width": w, "height": h,
                                                  "minimized": False, "text": text}

    def save(s, path):
        s.files["project.json"] = json.dumps(s.pj, separators=(",", ":")).encode()
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for n in sorted(s.files, key=lambda n: (n != "project.json", n)):
                zi = zipfile.ZipInfo(n, date_time=(2026, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, s.files[n])
        return hashlib.md5(s.files["project.json"]).hexdigest()
