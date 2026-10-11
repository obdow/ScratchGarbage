"""Static checks on ../pen_daw.sb3 so the project also opens cleanly in the editor."""
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
z = zipfile.ZipFile(os.path.join(os.path.dirname(HERE), 'pen_daw.sb3'))
proj = json.loads(z.read('project.json'))
names = set(z.namelist())
errors = []
stage = proj['targets'][0]
stage_vars = {k for k in stage['variables']}
stage_lists = {k for k in stage['lists']}

for t in proj['targets']:
    B = t['blocks']
    tv = set(t['variables']) | stage_vars
    tl = set(t['lists']) | stage_lists
    protos = {}
    for bid, b in B.items():
        if isinstance(b, dict) and b['opcode'] == 'procedures_prototype':
            m = b['mutation']
            protos[m['proccode']] = (json.loads(m['argumentids']), json.loads(m['argumentnames']))
    for c in t['costumes'] + t['sounds']:
        if c['md5ext'] not in names:
            errors.append(f'{t["name"]}: missing asset {c["md5ext"]}')
    for bid, b in B.items():
        where = f'{t["name"]}/{bid}'
        if isinstance(b, list):
            if b[0] == 12 and b[2] not in tv:
                errors.append(f'{where}: top-level var reporter to unknown var')
            continue
        if b['next'] and (b['next'] not in B or B[b['next']]['parent'] != bid):
            errors.append(f'{where}: bad next link')
        if b['parent'] and b['parent'] not in B:
            errors.append(f'{where}: missing parent')
        if not b['parent'] and not b['topLevel']:
            errors.append(f'{where}: orphan block {b["opcode"]}')
        for iname, inp in b['inputs'].items():
            for v in inp[1:]:
                if isinstance(v, str):
                    if v not in B:
                        errors.append(f'{where}: input {iname} -> missing {v}')
                    elif B[v]['parent'] != bid:
                        errors.append(f'{where}: input {iname} child has wrong parent')
                elif isinstance(v, list) and v and v[0] == 12 and v[2] not in tv:
                    errors.append(f'{where}: unknown variable {v[1]}')
                elif isinstance(v, list) and v and v[0] == 13 and v[2] not in tl:
                    errors.append(f'{where}: unknown list {v[1]}')
        for fname, f in b['fields'].items():
            if fname == 'VARIABLE' and f[1] not in tv:
                errors.append(f'{where}: field var {f[0]} unknown')
            if fname == 'LIST' and f[1] not in tl:
                errors.append(f'{where}: field list {f[0]} unknown')
            if fname == 'BROADCAST_OPTION' and f[1] not in stage['broadcasts']:
                errors.append(f'{where}: unknown broadcast {f[0]}')
        if b['opcode'] == 'procedures_call':
            m = b['mutation']
            if m['proccode'] not in protos:
                errors.append(f'{where}: call to undefined {m["proccode"]}')
            elif json.loads(m['argumentids']) != protos[m['proccode']][0]:
                errors.append(f'{where}: arg ids mismatch {m["proccode"]}')
        if b['opcode'] == 'event_broadcast':
            bc = b['inputs']['BROADCAST_INPUT'][1]
            if bc[2] not in stage['broadcasts']:
                errors.append(f'{where}: unknown broadcast {bc[1]}')
    # argument reporters must be inside a definition that declares them
    for bid, b in B.items():
        if isinstance(b, dict) and b['opcode'] == 'argument_reporter_string_number' and not b['shadow']:
            p = bid
            while B[p]['parent']:
                p = B[p]['parent']
            top = B[p]
            if top['opcode'] != 'procedures_definition':
                errors.append(f'{t["name"]}/{bid}: argument reporter outside definition')
                continue
            proto = B[top['inputs']['custom_block'][1]]
            if b['fields']['VALUE'][0] not in json.loads(proto['mutation']['argumentnames']):
                errors.append(f'{t["name"]}/{bid}: unknown argument {b["fields"]["VALUE"][0]}')

print(f'{sum(len(t["blocks"]) for t in proj["targets"])} blocks checked, {len(errors)} problems')
for e in errors[:50]:
    print(' ', e)
sys.exit(1 if errors else 0)
