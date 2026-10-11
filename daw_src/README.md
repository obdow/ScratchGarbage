# Pen DAW – source

`../pen_daw.sb3` is a pen-rendered digital audio workstation for **TurboWarp**
(1280×720, 60 FPS, high-quality pen, no fencing – stored in the project's
TurboWarp settings comment, so TurboWarp picks them up automatically). All text
is drawn with the pen text engine from `../claude_text.sb3`.

Open it at <https://turbowarp.org> (File → Load from your computer) and press
the green flag. A demo song is loaded; press **Space** to play it.

## Features

* **Playlist** – 8 lanes (one per track), place / move / erase pattern clips,
  zoom, scroll, loop region and start marker on the ruler, playhead follow.
* **Piano roll** – draw / select / erase tools, move + resize with snap
  (1/32 … bar, triplets, off), box select, duplicate, quantize, select all,
  velocity lane, zoom, pitch + time scrolling, note names, drum-row mode.
* **Drum step sequencer** – 10-piece kit, 16 steps per bar page, click or
  drag-paint steps, accents, swing.
* **Mixer** – per-track volume fader + level meter, pan, transpose, fine tune
  (cents), release time, mute, solo; master fader.
* **Transport** – play / pause / stop, pattern or song mode, loop, metronome,
  tempo (drag or type), swing, position + time display.
* **Instruments** – sampled Piano, E-Piano, Organ, Saw Lead, Square Lead,
  Pluck, Soft Pad, Bell, Sub Bass, Synth Bass and a Drum Kit (kick, snare,
  clap, hats, toms, crash, rim, cowbell). Samples are synthesized by
  `gen_samples.py`.
* **Computer keyboard** – Z…M / Q…U rows play the selected track (–/= octave),
  with live **recording** into the current pattern (optionally quantized).
* **Undo / redo** (40 steps), **save / load** as a text save code.

## Building

```
pip install numpy
python3 build.py      # writes ../pen_daw.sb3
python3 validate.py   # static checks on the generated project
```

`build.py` loads `claude_text.sb3`, removes the engine's demo + benchmark,
widens the engine's culling bounds from 480×360 to 1280×720, compiles the
`.sbx` sources into blocks, adds the `Audio` sprite with the samples and writes
the TurboWarp settings.

| file | contents |
| --- | --- |
| `sbc.py` | compiler for the small `.sbx` language → Scratch 3 blocks |
| `common.sbx` | stage variables / lists shared by both sprites |
| `audio.sbx` | `Audio` sprite: clock, scheduler, voice clones |
| `ui_core.sbx` | pen + text primitives, widgets, input, song data, save codes, undo |
| `ui_main.sbx` | main loop, keyboard, transport, top bar, sidebar, popups |
| `ui_views.sbx` | playlist, piano roll, step sequencer, mixer |
| `gen_samples.py` | instrument sample synthesis |
| `demo_song.py` | demo song + save code format description |

### The `.sbx` language

Python-like indentation. Everything compiles 1:1 to ordinary Scratch blocks,
so the result stays editable in the TurboWarp editor.

```
global bpm                      # stage variable (global x = "Scratch name" to alias)
var x, y                        # sprite variable
list notes / glist shared       # sprite / stage list
const BAR = 192                 # compile-time constant
macro clamp(v, a, b) = min(max(v, a), b)
extern te_draw(t, x, y) = "draw text %s at x: %s y: %s"   # existing custom block

proc rect(x, y, w, h, c):      # custom block, run without screen refresh
    if w < 1 or h < 1:
        return
    pencolor(c)
    ...

when flag:
    forever:
        frame()
```

Statements: `x = e`, `x += e`, `L[i] = e`, `L.add(e)`, `L.insert(i, e)`,
`L.delete(i)`, `L.clear()`, `if / elif / else`, `while`, `until`,
`repeat n`, `forever`, `for i = a to b`, `return`, built-in commands
(`goto`, `pendown`, `pencolor`, `stamp`, `playsound`, `setpitch`, `clone`,
`ask`, `wait`, …) and custom-block calls. Expressions: arithmetic, `%`, `~`
(join), comparisons, `and / or / not`, `L[i]`, `L.len`, `L.index(x)`,
`L.has(x)`, `round`, `floor`, `abs`, `min`, `max`, `letter`, `strlen`,
`key("x")`, `num(bool)`, `mouse_x`, `timer`, `answer`, …

## How the audio works

Scratch can't synthesize sound, so every instrument is a sample played with
the sound *pitch* effect (10 units = 1 semitone, ±3 octaves). Each note is a
clone of the `Audio` sprite with its own volume / pan / pitch. Scratch stops a
sound when the same sound slot is started again, even from another clone, so
each melodic instrument has 6 slots (drums 3) used round-robin. Notes end by
fading the clone's volume over the track's release time.

The clock runs from the timer: every frame the scheduler fires all notes whose
start lies between the previous and current song position (48 ticks per beat).
