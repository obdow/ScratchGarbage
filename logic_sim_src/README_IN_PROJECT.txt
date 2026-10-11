LOGIC SIM  -  a digital logic simulator drawn entirely with the pen

Built on the Pen Text Engine (the custom blocks at the far left of this sprite,
unchanged apart from removing its demo + benchmark). All text is stamped by it.

HOW IT WORKS
- Parts live in parallel lists: c_type, c_x, c_y, c_state, ...
- Each input pin has an entry in in_src = the output slot that drives it
  (slot 1 is "ground", a constant 0, used by unconnected inputs).
- tick: every part reads its inputs from outv (last tick), writes outn,
  then outn is copied to outv. So every part has exactly one tick of delay,
  which makes latches, flip-flops and ring oscillators behave realistically.
- Part graphics are data: lists op_k/op_a.. hold lines + colour classes per
  part type, so drawops can draw any part at any zoom (and the palette icons).
- Wires are routed orthogonally; in_mid stores a user-dragged bend.
- Save/Load format: "LS1;P,type,x,y,state,param,label;W,dst,pin,src,pin,mid"

These scripts are generated from logic_sim_src/*.sl by build.py in the repo,
so editing the text source and rebuilding is the easiest way to change it.
Best in TurboWarp (60 FPS + high quality pen), runs in vanilla Scratch too.
