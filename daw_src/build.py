"""Builds ../pen_daw.sb3 from the pen text engine (../claude_text.sb3) + the .sbx sources.

    python3 build.py            # writes ../pen_daw.sb3
"""
import hashlib
import json
import os
import sys
import zipfile

import gen_samples
import demo_song
from sbc import compile_files, CompileError

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENGINE = os.path.join(ROOT, 'claude_text.sb3')
OUT = os.path.join(ROOT, 'pen_daw.sb3')

W, H = 1280, 720
MELODIC_COPIES = 6
DRUM_COPIES = 3

TW_CONFIG = {
    'framerate': 60,
    'runtimeOptions': {'maxClones': 300, 'miscLimits': True, 'fencing': False},
    'interpolation': False,
    'turbo': False,
    'hq': True,
    'width': W,
    'height': H,
}


def md5(data):
    return hashlib.md5(data).hexdigest()


def load_engine():
    z = zipfile.ZipFile(ENGINE)
    proj = json.loads(z.read('project.json'))
    assets = {n: z.read(n) for n in z.namelist() if n != 'project.json'}
    return proj, assets


def strip_demo(sprite):
    """Remove the demo + benchmark scripts, their variables/lists and comments."""
    blocks = sprite['blocks']
    demo_hats = {'TE demo'}
    drop_roots = []
    for bid, b in blocks.items():
        if not isinstance(b, dict) or not b.get('topLevel'):
            continue
        op = b['opcode']
        if op == 'procedures_definition':
            proto = blocks[b['inputs']['custom_block'][1]]
            if proto['mutation']['proccode'].startswith(('_demo', '_bench')):
                drop_roots.append(bid)
        elif op == 'event_whenbroadcastreceived' and b['fields']['BROADCAST_OPTION'][0] in demo_hats:
            drop_roots.append(bid)
        elif op == 'event_whenkeypressed':
            drop_roots.append(bid)

    def collect(bid, acc):
        if bid is None or bid in acc or bid not in blocks:
            return
        acc.add(bid)
        b = blocks[bid]
        if isinstance(b, list):
            return
        for inp in b.get('inputs', {}).values():
            for v in inp[1:]:
                if isinstance(v, str):
                    collect(v, acc)
        collect(b.get('next'), acc)
    dead = set()
    for r in drop_roots:
        collect(r, dead)
    for bid in dead:
        del blocks[bid]
    # comments attached to dead blocks or describing the demo
    for cid in list(sprite['comments']):
        c = sprite['comments'][cid]
        if c.get('blockId') in dead or c['text'].startswith(('DEMO', 'BENCHMARK')):
            del sprite['comments'][cid]
    for vid in list(sprite['variables']):
        if sprite['variables'][vid][0].startswith(('_demo', '_bench')):
            del sprite['variables'][vid]
    for lid in list(sprite['lists']):
        if sprite['lists'][lid][0].startswith(('_demo', '_bench')):
            del sprite['lists'][lid]
    return len(dead)


def patch_stage_bounds(sprite):
    """The engine culls/fences glyphs against a 480x360 stage; widen it to W x H."""
    repl = {240: W // 2, -240: -W // 2, 180: H // 2, -180: -H // 2}
    targets = {'_visL', '_visR', '_visB', '_visT', '_inL', '_inR', '_inB', '_inT'}
    blocks = sprite['blocks']
    n = 0
    for b in blocks.values():
        if not isinstance(b, dict) or b['opcode'] != 'data_setvariableto':
            continue
        if b['fields']['VARIABLE'][0] not in targets:
            continue
        sub = blocks[b['inputs']['VALUE'][1]]
        lit = sub['inputs']['NUM1'][1]
        v = float(lit[1])
        if int(v) in repl:
            lit[1] = str(repl[int(v)])
            n += 1
    assert n == 8, f'expected to patch 8 bounds, patched {n}'


def existing_procs(sprite):
    out = {}
    for b in sprite['blocks'].values():
        if isinstance(b, dict) and b['opcode'] == 'procedures_prototype':
            m = b['mutation']
            out[m['proccode']] = {'proccode': m['proccode'],
                                  'argids': json.loads(m['argumentids']),
                                  'argnames': json.loads(m['argumentnames']),
                                  'warp': m.get('warp') in ('true', True)}
    return out


def svg_rect(w, h, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}"><rect width="{w}" height="{h}" fill="{color}"/></svg>').encode()


def main():
    proj, assets = load_engine()
    stage = proj['targets'][0]
    te = proj['targets'][1]
    assert te['name'] == 'Text Engine'

    removed = strip_demo(te)
    patch_stage_bounds(te)
    # the stage only broadcast "TE demo" on green flag
    stage['blocks'] = {}
    stage['comments'] = {}
    stage['lists'] = {k: v for k, v in stage['lists'].items() if not v[0].startswith('TE benchmark')}
    stage['broadcasts'] = {k: v for k, v in stage['broadcasts'].items() if v != 'TE demo'}

    # shared symbol tables
    stage_vars = {v[0]: k for k, v in stage['variables'].items()}
    stage_lists = {v[0]: k for k, v in stage['lists'].items()}
    broadcasts = {v: k for k, v in stage['broadcasts'].items()}

    # generated data (instrument tables, demo song)
    samples = gen_samples.generate()
    gen_path = os.path.join(HERE, '_generated.sbx')
    with open(gen_path, 'w') as f:
        f.write(generated_source())

    try:
        ui = compile_files([os.path.join(HERE, p) for p in
                            ('common.sbx', '_generated.sbx', 'ui_core.sbx', 'ui_views.sbx',
                             'ui_main.sbx')],
                           sprite_name='Text Engine', stage_vars=stage_vars,
                           stage_lists=stage_lists, broadcasts=broadcasts,
                           existing_procs=existing_procs(te), id_prefix='u')
        au = compile_files([os.path.join(HERE, p) for p in ('common.sbx', 'audio.sbx')],
                           sprite_name='Audio', stage_vars=stage_vars,
                           stage_lists=stage_lists, broadcasts=broadcasts, id_prefix='a')
    except CompileError as e:
        print('COMPILE ERROR:', e)
        sys.exit(1)

    te['blocks'].update(ui.blocks)
    for sname, vid in ui.local_vars.items():
        te['variables'][vid] = [sname, 0]
    for sname, lid in ui.local_lists.items():
        te['lists'][lid] = [sname, []]

    # stage variables / lists / broadcasts
    have = {v[0] for v in stage['variables'].values()}
    for sname, vid in stage_vars.items():
        if sname not in have:
            stage['variables'][vid] = [sname, 0]
    have = {v[0] for v in stage['lists'].values()}
    for sname, lid in stage_lists.items():
        if sname not in have:
            stage['lists'][lid] = [sname, []]
    stage['broadcasts'] = {bid: name for name, bid in broadcasts.items()}

    # stage backdrop sized to the custom stage
    bg = svg_rect(W, H, '#15161b')
    bg_id = md5(bg)
    assets[bg_id + '.svg'] = bg
    stage['costumes'] = [{'name': 'backdrop', 'bitmapResolution': 1, 'dataFormat': 'svg',
                          'assetId': bg_id, 'md5ext': bg_id + '.svg',
                          'rotationCenterX': W // 2, 'rotationCenterY': H // 2}]
    stage['currentCostume'] = 0
    # TurboWarp settings: 60 fps, no fencing, high quality pen, 1280x720
    stage['comments'] = {'twconfig': {
        'blockId': None, 'x': 0, 'y': 0, 'width': 350, 'height': 170, 'minimized': False,
        'text': 'Configuration for https://turbowarp.org/\nYou can move, resize, and minimize '
                'this comment, but don\'t edit it by hand. This comment can be deleted to '
                'remove the stored settings.\n' + json.dumps(TW_CONFIG, separators=(',', ':'))
                + ' // _twconfig_'}}

    # audio sprite with the sampled instruments
    sounds = []
    for i, (name, data, n) in enumerate(samples):
        aid = md5(data)
        assets[aid + '.wav'] = data
        entry = {'assetId': aid, 'dataFormat': 'wav', 'format': '', 'rate': gen_samples.SR,
                 'sampleCount': n, 'md5ext': aid + '.wav'}
        if i < 10:
            copies = MELODIC_COPIES
        elif i < 20:
            copies = DRUM_COPIES
        else:
            copies = 1
        for c in range(copies):
            sounds.append(dict(entry, name=f'{name} {c + 1}'))
    assert len(sounds) == 10 * MELODIC_COPIES + 10 * DRUM_COPIES + 2
    dot = svg_rect(2, 2, '#000000')
    dot_id = md5(dot)
    assets[dot_id + '.svg'] = dot
    audio = {
        'isStage': False, 'name': 'Audio',
        'variables': {vid: [sname, 0] for sname, vid in au.local_vars.items()},
        'lists': {lid: [sname, []] for sname, lid in au.local_lists.items()},
        'broadcasts': {}, 'blocks': au.blocks, 'comments': {
            'note': {'blockId': None, 'x': 600, 'y': 0, 'width': 420, 'height': 200,
                     'minimized': False, 'text': AUDIO_NOTE}},
        'currentCostume': 0,
        'costumes': [{'name': 'dot', 'bitmapResolution': 1, 'dataFormat': 'svg', 'assetId': dot_id,
                      'md5ext': dot_id + '.svg', 'rotationCenterX': 1, 'rotationCenterY': 1}],
        'sounds': sounds, 'volume': 100, 'layerOrder': 2, 'visible': False, 'x': 0, 'y': 0,
        'size': 100, 'direction': 90, 'draggable': False, 'rotationStyle': 'all around',
    }
    te['layerOrder'] = 1
    te['comments']['dawnote'] = {'blockId': None, 'x': -900, 'y': 0, 'width': 480, 'height': 300,
                                 'minimized': False, 'text': UI_NOTE}
    proj['targets'] = [stage, te, audio]

    # list monitor used to show the save code
    save_lid = stage_lists['SAVE CODE']
    proj['monitors'] = [{
        'id': save_lid, 'mode': 'list', 'opcode': 'data_listcontents',
        'params': {'LIST': 'SAVE CODE'}, 'spriteName': None, 'value': [],
        'width': 760, 'height': 300, 'visible': False,
        # TurboWarp offsets monitors by the stage size difference when loading
        'x': 260 - (W - 480) // 2, 'y': 230 - (H - 360) // 2}]
    proj['meta'] = {'semver': '3.0.0', 'vm': '5.0.0', 'agent': 'pen-daw-builder'}
    proj['extensions'] = ['pen']

    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('project.json', json.dumps(proj, separators=(',', ':')))
        used = {c['md5ext'] for t in proj['targets'] for c in t['costumes']} | \
               {s['md5ext'] for t in proj['targets'] for s in t['sounds']}
        for name in sorted(used):
            z.writestr(name, assets[name])
    nblocks = sum(len(t['blocks']) for t in proj['targets'])
    print(f'removed {removed} demo blocks; UI {len(ui.blocks)} blocks, audio {len(au.blocks)} '
          f'blocks, total {nblocks}; {len(sounds)} sound slots')
    print(f'wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)')


AUDIO_NOTE = '''PEN DAW - AUDIO ENGINE

The original sprite runs the transport: every frame it converts the timer into a song position (ticks, 48 per beat) and fires every note whose start falls between the previous and the current position. Swing delays odd 16ths.

Each note becomes a clone ("voice"): it sets its own volume / pan / pitch effect, starts one of several copies of the instrument sample (Scratch cuts a sound off when the same sound slot is restarted, so every instrument has 6 slots used round-robin), waits for the note length, fades out over the track's release time and deletes itself.

The UI never touches clones directly: it writes live notes into the q_ lists, and sets the playing / song_pos / seek_req variables.'''

UI_NOTE = '''PEN DAW - USER INTERFACE

Everything is drawn with the pen every frame (immediate-mode UI). Text uses the pen text engine blocks on the right; the engine's culling bounds were widened for the 1280x720 stage.

Source code: daw_src/*.sbx in the repository (compiled by daw_src/build.py). Editing the blocks here works too, but rebuilding from source will overwrite it.'''


def generated_source():
    lines = ['# generated by build.py - do not edit', 'proc init_tables():']
    lines.append('    inst_name.clear()')
    lines.append('    inst_root.clear()')
    for name, g, root in gen_samples.MELODIC:
        lines.append(f'    inst_name.add("{name}")')
        lines.append(f'    inst_root.add({root})')
    lines.append('    inst_name.add("Drum Kit")')
    lines.append('    inst_root.add(0)')
    lines.append('    drum_name.clear()')
    for name in demo_song.DRUM_SHORT:
        lines.append(f'    drum_name.add("{name}")')
    lines.append(f'const DEMO_SONG = "{demo_song.save_code()}"')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    main()
