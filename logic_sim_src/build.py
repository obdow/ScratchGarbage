"""Builds logic_sim.sb3 from claude_text.sb3 (the Pen Text Engine) + logic_sim.sl.

usage: python3 build.py [path/to/claude_text.sb3] [out.sb3]
"""
import hashlib
import json
import math
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import slc  # noqa: E402
from demos import DEMOS  # noqa: E402
from parts import PARTS, part_tables, SEGTAB  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'claude_text.sb3')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, '..', 'logic_sim.sb3')

z = zipfile.ZipFile(SRC)
project = json.loads(z.read('project.json'))
assets = {n: z.read(n) for n in z.namelist() if n != 'project.json'}

stage = project['targets'][0]
sprite = project['targets'][1]
assert sprite['name'] == 'Text Engine'

# ---------------------------------------------------------------- strip the engine demo + benchmark
B = sprite['blocks']


def collect(bid, acc):
    stack = [bid]
    while stack:
        b = stack.pop()
        if not isinstance(b, str) or b not in B or b in acc:
            continue
        acc.add(b)
        blk = B[b]
        stack.append(blk.get('next'))
        for v in blk.get('inputs', {}).values():
            for x in v[1:]:
                if isinstance(x, str):
                    stack.append(x)


remove = set()
for bid, b in list(B.items()):
    if not (isinstance(b, dict) and b.get('topLevel')):
        continue
    op = b['opcode']
    kill = False
    if op == 'procedures_definition':
        proto = B[b['inputs']['custom_block'][1]]
        code = proto['mutation']['proccode']
        kill = code.startswith('_demo') or code.startswith('_bench')
    elif op == 'event_whenbroadcastreceived':
        kill = b['fields']['BROADCAST_OPTION'][0] == 'TE demo'
    elif op == 'event_whenkeypressed':
        kill = b['fields']['KEY_OPTION'][0] in ('space', 'b')
    if kill:
        collect(bid, remove)
for bid in remove:
    del B[bid]
# any remaining reference to a removed proc would break the project
for b in B.values():
    if isinstance(b, dict) and b['opcode'] == 'procedures_call':
        assert not b['mutation']['proccode'].startswith(('_demo', '_bench')), b
sprite['comments'] = {k: c for k, c in sprite.get('comments', {}).items()
                      if c.get('blockId') not in remove and not c['text'].startswith(('DEMO', 'BENCHMARK'))}
used = json.dumps(B)
for k in list(sprite['variables']):
    if sprite['variables'][k][0].startswith(('_demo', '_bench')):
        assert k not in used
        del sprite['variables'][k]
for k in list(sprite['lists']):
    if sprite['lists'][k][0].startswith(('_demo', '_bench')):
        assert k not in used
        del sprite['lists'][k]
# stage: drop the green-flag "broadcast TE demo" script and the benchmark list
stage['blocks'] = {}
stage['broadcasts'] = {k: v for k, v in stage['broadcasts'].items() if v != 'TE demo'}
stage['lists'] = {k: v for k, v in stage['lists'].items() if v[0] != 'TE benchmark results'}
stage['lists']['circuit_code_list'] = ['Circuit code', []]

sprite['name'] = 'Logic Sim'
sprite['visible'] = False

# ---------------------------------------------------------------- stage backdrop (dark)
bg_svg = ('<svg version="1.1" xmlns="http://www.w3.org/2000/svg" width="480" height="360" '
          'viewBox="0 0 480 360"><rect x="0" y="0" width="480" height="360" fill="#0d1218"/></svg>').encode()
bg_md5 = hashlib.md5(bg_svg).hexdigest()
old_bg = stage['costumes'][0]['md5ext']
assets.pop(old_bg, None)
assets[bg_md5 + '.svg'] = bg_svg
stage['costumes'] = [{'name': 'board', 'bitmapResolution': 1, 'dataFormat': 'svg', 'assetId': bg_md5,
                      'md5ext': bg_md5 + '.svg', 'rotationCenterX': 240, 'rotationCenterY': 180}]

# ---------------------------------------------------------------- compile
src = open(os.path.join(HERE, 'logic_sim.sl')).read()
prog = slc.parse_program(src)
gen = slc.Gen(sprite, stage, prefix='ls')
gen.compile(prog, layout_x=2600)

# ---------------------------------------------------------------- baked data
data = part_tables()
data['segtab'] = SEGTAB
data['led_on'] = [0xff4d4d, 0x3dff8a, 0xffd23d, 0x4da6ff, 0xf2f6ff]
data['led_off'] = [0x3d1f22, 0x1c3a2a, 0x3b3419, 0x1c2c40, 0x30353c]
data['led_glow'] = [0x55ff4d4d, 0x553dff8a, 0x55ffd23d, 0x554da6ff, 0x55f2f6ff]
data['speeds'] = [0.125, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64]
data['speedname'] = ['1/8 t/f', '1/4 t/f', '1/2 t/f', '1 t/f', '2 t/f', '4 t/f', '8 t/f', '16 t/f', '32 t/f', '64 t/f']

# toolbar / zoom buttons: x1, x2, y1, y2, label, tip, has background
BUTTONS = [
    (-236, -196, 157, 177, 'Run', 'Run / pause the simulation (Space)', 1),
    (-192, -158, 157, 177, 'Step', 'Advance one tick (S)', 1),
    (-154, -136, 157, 177, '–', 'Slower: fewer simulation ticks per frame', 1),
    (-80, -62, 157, 177, '+', 'Faster: more simulation ticks per frame', 1),
    (-58, -40, 157, 177, '‹', 'Previous demo (Left arrow)', 1),
    (94, 112, 157, 177, '›', 'Next demo (Right arrow)', 1),
    (117, 147, 157, 177, 'New', 'Start an empty board', 1),
    (150, 180, 157, 177, 'Save', 'Save the board as a code you can copy', 1),
    (183, 213, 157, 177, 'Load', 'Load a board from a code', 1),
    (216, 236, 157, 177, '?', 'Help (H)', 1),
    (-236, -188, -132, -116, '+', 'Zoom in (scroll / Up arrow)', 1),
    (-236, -188, -152, -136, '–', 'Zoom out (scroll / Down arrow)', 1),
    (-236, -188, -172, -156, 'Fit', 'Fit the circuit on screen (F)', 1),
    (-38, 92, 157, 177, '', 'Click to show / hide the demo notes (I)', 0),
]
for i, key in enumerate(['btn_x1', 'btn_x2', 'btn_y1', 'btn_y2', 'btn_label', 'btn_tip', 'btn_bg']):
    data[key] = [b[i] for b in BUTTONS]

data['demo_name'] = [d['name'] for d in DEMOS]
data['demo_desc'] = [d['desc'] for d in DEMOS]
data['demo_code'] = [d['code'] for d in DEMOS]
data['demo_speed'] = [d['speed'] for d in DEMOS]
data['demo_info'] = [d['info'] for d in DEMOS]

data['help_lines'] = [
    '•  Drag a part from the palette on the left onto the board. Hover a palette item to see what it does.',
    '•  Wires: drag from a pin to another pin. Outputs (right side) connect to inputs (left side). An output can feed many inputs.',
    '•  Drag a wire end off an input pin to move or remove it. Hover a wire and press X to delete it, or drag its middle segment to re-route it.',
    '•  Click switches and constants to flip them, hold buttons down, click clocks to change their speed, LEDs to change colour and truth tables to reset them.',
    '•  Drag parts to move them. Drop a part on the palette (or hover it and press X) to delete it. Hover and press L to give it a label.',
    '•  Drag empty space to pan. Scroll, Up/Down or the +/– buttons zoom, F fits everything on screen.',
    '•  Space runs / pauses, S steps one tick, Left/Right switch demos, I shows the demo notes.',
    '•  Every part takes one tick to react, so you can watch signals ripple through and build latches and oscillators from gates.',
    '•  Save gives you a code to copy; Load pastes a code back in.',
    'Click anywhere to close.',
]

for name, values in data.items():
    if name in gen.lists:
        sprite['lists'][gen.lists[name]][1] = values
    else:
        raise SystemExit('baked list %s is not declared in logic_sim.sl' % name)
declared = set(prog.lists)
missing = [n for n in declared if n.startswith(('tp_', 'op_', 'tx_', 'btn_', 'demo_', 'pin_', 'led_')) and n not in data]
assert not missing, missing

# ---------------------------------------------------------------- monitor for the save code list
project['monitors'] = [{
    'id': 'circuit_code_list', 'mode': 'list', 'opcode': 'data_listcontents',
    'params': {'LIST': 'Circuit code'}, 'spriteName': None, 'value': [],
    'width': 400, 'height': 90, 'x': 40, 'y': 245, 'visible': False}]

# ---------------------------------------------------------------- notes
sprite['comments']['ls_readme'] = {
    'blockId': None, 'x': 2600, 'y': -700, 'width': 620, 'height': 560, 'minimized': False,
    'text': open(os.path.join(HERE, 'README_IN_PROJECT.txt')).read()}

project['meta'] = {'semver': '3.0.0', 'vm': '5.0.0', 'agent': 'logic-sim-builder'}

with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as out:
    out.writestr('project.json', json.dumps(project, separators=(',', ':')))
    for n, d in assets.items():
        out.writestr(n, d)
print('wrote', OUT, 'blocks:', len(sprite['blocks']), 'demos:', len(DEMOS))
