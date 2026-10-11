# Logic Sim (Scratch, pen-rendered)

`../logic_sim.sb3` is a digital logic simulator for Scratch / TurboWarp. Everything is drawn
with the pen; all text uses the Pen Text Engine from `../claude_text.sb3`.

## Features
- 20 parts: AND, OR, NOT, NAND, NOR, XOR, XNOR, buffer, switch, push button, clock,
  constant, LED, hex display, 7-segment display, D flip-flop, 7-segment decoder,
  text label, truth-table probe, 8-bit number display.
- Editor: drag parts from the palette, drag pin to pin to wire, drag wire middles to
  re-route, X to delete, L to label, pan / zoom / fit.
- One tick of delay per part, so latches, flip-flops and oscillators work from gates.
  Run / pause / single-step and 1/8 to 64 ticks per frame.
- Save / Load as a text code (`LS1;P,...;W,...`).
- 13 demos: AND/OR, NOT/XOR, NAND/NOR/XNOR, half & full adders, 4-bit ripple-carry adder,
  SR latch, gated D latch, master-slave D flip-flop, 4-bit counter + 7-segment,
  7-segment decoder, ring oscillator, traffic light, "NAND makes everything".

## Building
```
python3 build.py            # reads ../claude_text.sb3, writes ../logic_sim.sb3
```
- `slc.py` – a small compiler from a readable script language to Scratch blocks.
- `logic_sim.sl` – the simulator itself (compiled into the "Logic Sim" sprite).
- `parts.py` – part pins and drawing geometry (baked into lists).
- `demos.py` – the demo circuits.
