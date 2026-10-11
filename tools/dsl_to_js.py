#!/usr/bin/env python3
"""
Compiles the physics program (the same sb3dsl source that build_physics_sb3.py
turns into Scratch blocks) to plain JavaScript with Scratch semantics, so the
engine can be regression-tested quickly in Node without a browser:

    node tools/test_physics.js          # runs this script itself

Pen, looks and text-engine blocks become no-ops; everything else (variables,
lists, maths, custom blocks) behaves like Scratch.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["PHYS_NO_SAVE"] = "1"
import sb3dsl as D  # noqa: E402

g = {"__file__": os.path.join(HERE, "build_physics_sb3.py"), "__name__": "physbuild"}
try:
    exec(open(g["__file__"]).read(), g)
except SystemExit:
    pass
P = g["P"]

def q(s): return json.dumps(s)
def ex(e):
    if isinstance(e, D.Lit): e = e.v
    if not isinstance(e, D.Expr):
        if isinstance(e, bool): return 'true' if e else 'false'
        if isinstance(e, (int, float)): return repr(float(e)) if isinstance(e, float) else str(e)
        return q(e)
    if isinstance(e, D.VarRef): return f'V[{q(e.name)}]'
    if isinstance(e, D.ArgRef): return f'A[{q(e.name)}]'
    op = e.opcode; I = {k: v[1] for k, v in e.inputs.items()}
    N = lambda k: f'n({ex(I[k])})'
    S = lambda k: f's({ex(I[k])})'
    if op == 'operator_add': return f'({N("NUM1")}+{N("NUM2")})'
    if op == 'operator_subtract': return f'({N("NUM1")}-{N("NUM2")})'
    if op == 'operator_multiply': return f'({N("NUM1")}*{N("NUM2")})'
    if op == 'operator_divide': return f'({N("NUM1")}/{N("NUM2")})'
    if op == 'operator_mod': return f'mod({N("NUM1")},{N("NUM2")})'
    if op == 'operator_lt': return f'(cmp({ex(I["OPERAND1"])},{ex(I["OPERAND2"])})<0)'
    if op == 'operator_gt': return f'(cmp({ex(I["OPERAND1"])},{ex(I["OPERAND2"])})>0)'
    if op == 'operator_equals': return f'(cmp({ex(I["OPERAND1"])},{ex(I["OPERAND2"])})===0)'
    if op == 'operator_and': return f'(b({ex(I["OPERAND1"])})&&b({ex(I["OPERAND2"])}))'
    if op == 'operator_or': return f'(b({ex(I["OPERAND1"])})||b({ex(I["OPERAND2"])}))'
    if op == 'operator_not': return f'(!b({ex(I["OPERAND"])}))'
    if op == 'operator_join': return f'({S("STRING1")}+{S("STRING2")})'
    if op == 'operator_letter_of': return f'({S("STRING")}[{N("LETTER")}-1]||"")'
    if op == 'operator_length': return f'{S("STRING")}.length'
    if op == 'operator_round': return f'Math.round({N("NUM")})'
    if op == 'operator_random': return f'rnd({ex(I["FROM"])},{ex(I["TO"])})'
    if op == 'operator_mathop': return f'mop({q(e.fields["OPERATOR"][0])},{N("NUM")})'
    if op == 'data_itemoflist': return f'li({q(e.fields["LIST"].name)},{ex(I["INDEX"])})'
    if op == 'data_lengthoflist': return f'L({q(e.fields["LIST"].name)}).length'
    if op == 'data_itemnumoflist': return f'lidx({q(e.fields["LIST"].name)},{ex(I["ITEM"])})'
    if op in ('sensing_mousex',): return 'IO.mx'
    if op in ('sensing_mousey',): return 'IO.my'
    if op == 'sensing_mousedown': return 'IO.md'
    if op == 'sensing_keypressed': return f'!!IO.keys[{ex(I["KEY_OPTION"])}]'
    if op in ('sensing_timer',): return 'IO.t'
    if op == 'sensing_dayssince2000': return '(Date.now()/86400000)'
    if op == 'looks_costumenumbername': return '"_fence"'
    raise NotImplementedError(op)

def st(stmts, ind):
    out = []
    p = '  ' * ind
    for s_ in stmts:
        op = s_.opcode; I = {k: v[1] for k, v in s_.inputs.items()}
        if op == 'data_setvariableto': out.append(f'{p}V[{q(s_.fields["VARIABLE"].name)}]={ex(I["VALUE"])};')
        elif op == 'data_changevariableby':
            nm = q(s_.fields["VARIABLE"].name); out.append(f'{p}V[{nm}]=n(V[{nm}])+n({ex(I["VALUE"])});')
        elif op == 'data_addtolist': out.append(f'{p}L({q(s_.fields["LIST"].name)}).push({ex(I["ITEM"])});')
        elif op == 'data_deletealloflist': out.append(f'{p}L({q(s_.fields["LIST"].name)}).length=0;')
        elif op == 'data_replaceitemoflist': out.append(f'{p}lset({q(s_.fields["LIST"].name)},{ex(I["INDEX"])},{ex(I["ITEM"])});')
        elif op == 'data_deleteoflist': out.append(f'{p}ldel({q(s_.fields["LIST"].name)},{ex(I["INDEX"])});')
        elif op == 'data_insertatlist': out.append(f'{p}lins({q(s_.fields["LIST"].name)},{ex(I["INDEX"])},{ex(I["ITEM"])});')
        elif op == 'control_if':
            out.append(f'{p}if(b({ex(I["CONDITION"])})){{'); out += st(s_.subs.get('SUBSTACK', []), ind+1); out.append(p+'}')
        elif op == 'control_if_else':
            out.append(f'{p}if(b({ex(I["CONDITION"])})){{'); out += st(s_.subs.get('SUBSTACK', []), ind+1)
            out.append(p+'}else{'); out += st(s_.subs.get('SUBSTACK2', []), ind+1); out.append(p+'}')
        elif op == 'control_repeat':
            out.append(f'{p}for(let _r=Math.round(n({ex(I["TIMES"])}));_r>0;_r--){{'); out += st(s_.subs.get('SUBSTACK', []), ind+1); out.append(p+'}')
        elif op == 'control_repeat_until':
            out.append(f'{p}{{let _g=0;while(!b({ex(I["CONDITION"])})){{if(++_g>1e7)throw new Error("loop");'); out += st(s_.subs.get('SUBSTACK', []), ind+1); out.append(p+'}}')
        elif op == 'control_forever':
            out.append(f'{p}/* forever omitted */')
        elif op == 'procedures_call':
            m = s_.mutation; ids = json.loads(m['argumentids'])
            out.append(f'{p}PR[{q(m["proccode"])}]({",".join(ex(s_.inputs[i][1]) for i in ids)});')
        elif op in ('pen_penUp','pen_penDown','pen_clear','pen_stamp','pen_setPenSizeTo','pen_setPenColorToColor','pen_setPenColorParamTo','motion_gotoxy','looks_switchcostumeto','looks_hide','control_stop'):
            out.append(f'{p}IO.gfx++;')
        else: raise NotImplementedError(op)
    return out

lines = []
for pr in P.procs:
    with D._sub() as body:
        pr.fn(*[D.ArgRef(a) for a in pr.argnames])
    args = ','.join(f'a{i}' for i in range(len(pr.argnames)))
    amap = ','.join(f'{q(a)}:a{i}' for i, a in enumerate(pr.argnames))
    lines.append(f'PR[{q(pr.proccode)}]=function({args}){{const A={{{amap}}};')
    lines += st(body, 1)
    lines.append('};')
# text engine stubs
for code in ['draw text %s at x: %s y: %s','set text size to %s','set text align %s vertical %s','set text color hue: %s brightness: %s','set text transparency to %s','reset text style']:
    lines.append(f'PR[{q(code)}]=function(){{}};')
lists = {}
for t in (P.sprite, P.stage):
    for lid, (nm, val, *r) in t['lists'].items(): lists[nm] = val
RT = open(os.path.join(HERE, 'js_runtime.js')).read()
open(sys.argv[1], 'w').write(RT + '\nconst LISTS0=' + json.dumps(lists) + ';\nfor(const k in LISTS0) LS[k]=LISTS0[k].slice();\n' + '\n'.join(lines) + '\nmodule.exports={V,LS,PR,IO,L};\n')
print('ok', len(lines))
