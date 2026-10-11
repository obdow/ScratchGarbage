"""The demo song loaded when the project starts, in PenDAW save-code format.

Save code (comma separated):
  PDAW1, bpm, swing, master, loop_on, loop_start_bar, loop_end_bar, song_mode,
  8 x [name, instrument, volume, pan, mute, solo, transpose, fine(cents), release(ms), cur_pattern],
  pattern_count, pattern_count x [name, length(ticks), track, note_count,
                                  note_count x [start, length, pitch, velocity]],
  clip_count, clip_count x [track, start_bar, pattern],
  END
Ticks: 48 per beat, 192 per bar. Drum notes use pitch 0..9 = drum row.
"""

DRUM_SHORT = ['Kick', 'Snare', 'Clap', 'Cl. Hat', 'Op. Hat', 'Lo Tom', 'Hi Tom', 'Crash', 'Rim',
              'Cowbell']
S = 12  # one 16th note in ticks


def save_code():
    tracks = [
        # name, inst, vol, pan, mute, solo, tr, fine, rel
        ['Drums', 11, 85, 0, 0, 0, 0, 0, 0],
        ['Bass', 10, 75, 0, 0, 0, 0, 0, 40],
        ['Keys', 2, 55, -25, 0, 0, 0, 0, 150],
        ['Lead', 4, 50, 10, 0, 0, 0, 0, 90],
        ['Pad', 7, 40, 0, 0, 0, 0, 0, 450],
        ['Pluck', 6, 42, 30, 0, 0, 0, 0, 60],
        ['Piano', 1, 70, 0, 0, 0, 0, 0, 120],
        ['Bells', 8, 35, -35, 0, 0, 0, 0, 300],
    ]
    patterns = []   # name, len, track(1-based), notes

    def pat(name, bars, track, notes):
        patterns.append([name, bars * 192, track, notes])
        return len(patterns)

    # drums
    beat = []
    for st in (0, 4, 8, 12):
        beat.append([st * S, S, 0, 120])
    for st in (4, 12):
        beat.append([st * S, S, 1, 105])
        beat.append([st * S, S, 2, 70])
    for st in range(0, 16, 2):
        beat.append([st * S, S, 3, 90 if st % 4 == 2 else 60])
    beat.append([14 * S, S, 4, 70])
    beat.append([7 * S, S, 0, 70])
    p_beat = pat('Beat', 1, 1, beat)
    fill = [[0, S, 0, 120], [4 * S, S, 1, 100], [8 * S, S, 0, 120], [6 * S, S, 0, 80]]
    for st, row in ((10, 6), (11, 6), (12, 5), (13, 5), (14, 1), (15, 1)):
        fill.append([st * S, S, row, 85 + st * 2])
    for st in range(0, 10, 2):
        fill.append([st * S, S, 3, 70])
    p_fill = pat('Fill', 1, 1, fill)
    crash = [n[:] for n in beat] + [[0, S, 7, 110]]
    p_crash = pat('Beat+Crash', 1, 1, crash)

    chords = [  # Am F C G
        (45, [57, 60, 64]), (41, [57, 60, 65]), (48, [55, 60, 64]), (43, [55, 59, 62])]
    bass = []
    for b, (root, _) in enumerate(chords):
        for st in range(0, 16, 2):
            pitch = root + (12 if st in (6, 14) else 0)
            bass.append([b * 192 + st * S, 18, pitch, 110 if st % 4 == 0 else 85])
    p_bass = pat('Bassline', 4, 2, bass)

    keys = []
    for b, (_, ch) in enumerate(chords):
        for st, ln in ((0, 5), (6, 2), (8, 5), (14, 2)):
            for p in ch:
                keys.append([b * 192 + st * S, ln * S - 2, p, 95 if st in (0, 8) else 70])
    p_keys = pat('Chords', 4, 3, keys)

    lead_notes = [
        (0, 4, 69), (4, 2, 72), (6, 4, 76), (10, 2, 74), (12, 4, 72),
        (16, 4, 69), (20, 2, 72), (22, 4, 77), (26, 2, 76), (28, 4, 72),
        (32, 4, 67), (36, 2, 72), (38, 4, 76), (42, 2, 79), (44, 4, 76),
        (48, 4, 74), (52, 2, 71), (54, 4, 67), (58, 6, 69)]
    lead = [[st * S, ln * S - 2, p + 12, 100] for st, ln, p in lead_notes]
    p_lead = pat('Melody', 4, 4, lead)

    pad = []
    for b, (_, ch) in enumerate(chords):
        for p in ch:
            pad.append([b * 192, 190, p - 12, 90])
        pad.append([b * 192, 190, ch[0] + 12, 70])
    p_pad = pat('Pad', 4, 5, pad)

    pl = []
    for b, (_, ch) in enumerate(chords):
        seq = [ch[0] + 12, ch[1] + 12, ch[2] + 12, ch[1] + 12]
        for st in range(16):
            pl.append([b * 192 + st * S, S - 2, seq[st % 4], 100 if st % 4 == 0 else 75])
    p_pluck = pat('Arp', 4, 6, pl)

    p_bell = pat('Sparkle', 4, 8, [[0, 4 * S, 88, 90], [8 * S, 4 * S, 84, 70],
                                   [2 * 192, 4 * S, 84, 90], [2 * 192 + 8 * S, 4 * S, 79, 70]])
    p_piano = pat('Piano 1', 2, 7, [])

    cur = {1: p_beat, 2: p_bass, 3: p_keys, 4: p_lead, 5: p_pad, 6: p_pluck, 7: p_piano, 8: p_bell}

    clips = []
    for bar in (0, 4, 8, 12):
        clips.append([5, bar, p_pad])
        clips.append([3, bar, p_keys])
    for bar in range(4, 16):
        if bar in (7, 15):
            clips.append([1, bar, p_fill])
        elif bar in (4, 8, 12):
            clips.append([1, bar, p_crash])
        else:
            clips.append([1, bar, p_beat])
    for bar in (4, 8, 12):
        clips.append([2, bar, p_bass])
    for bar in (8, 12):
        clips.append([4, bar, p_lead])
        clips.append([6, bar, p_pluck])
    clips.append([8, 12, p_bell])

    tok = ['PDAW1', 108, 25, 80, 0, 8, 16, 1]
    for i, t in enumerate(tracks):
        tok += t + [cur[i + 1]]
    tok.append(len(patterns))
    for name, ln, tr, notes in patterns:
        tok += [name, ln, tr, len(notes)]
        for n in notes:
            tok += n
    tok.append(len(clips))
    for c in clips:
        tok += c
    tok.append('END')
    s = ','.join(str(x) for x in tok)
    assert '"' not in s
    return s


if __name__ == '__main__':
    s = save_code()
    print(len(s), s[:300])
