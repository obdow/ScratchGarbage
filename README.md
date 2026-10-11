# ScratchGarbage

## `physics_2d.sb3`: 2D rigid-body physics for TurboWarp

An advanced 2D rigid-body sandbox. Everything is drawn with **pen**, and every label uses the pen
text engine from `claude_text.sb3`. Open it in [TurboWarp](https://turbowarp.org/editor). The
project stores its TurboWarp settings (60 FPS, high-quality pen, no fencing, 480×360).

**Engine**
- Circles and convex polygons. Collisions use SAT plus reference/incident-face clipping, giving
  2-point manifolds.
- Sort-and-sweep broadphase. The order list is insertion-sorted every step, which is about O(n).
- Sequential-impulse solver, as in Box2D-lite:
  - accumulated-impulse clamping
  - Coulomb friction and restitution
  - Baumgarte stabilisation
  - warm starting, with contacts matched between steps by feature key
- Joints: soft revolute joints, distance joints, damped springs and a mouse spring.
- Union-find islands and sleeping.
- Units: 50 px = 1 m and density 1 kg/m², so every readout is in SI units (N, J, kg·m/s).

**What you see**
- Velocity and angular-velocity arrows.
- Per-body forces: weight, reaction and net force.
- Contact points with normal and friction forces.
- AABBs and joint forces.
- A stats panel showing FPS, timings, awake/asleep/static counts, islands, broadphase pairs,
  energy, momentum and angular momentum.
- Live graphs of KE, PE, total energy and |p|.
- A hover inspector for any body.

**Controls** (press **H** in the project for this list)

| key | action |
| --- | --- |
| mouse | drag a body, or click empty space to spawn |
| C / B / P | spawn tool: circle / box / polygon |
| X / E | delete the body under the mouse / blast at the mouse |
| 1–7, R | scenes (pyramid, playground, Newton's cradle, rope bridge, dominoes, friction ramps, joints), reset |
| Space / N | pause / single step |
| V F K A G I | overlays: velocity, forces, contacts, AABBs, graphs, stats |
| ↑ ↓ / ← → | gravity ±1 m/s² / solver iterations ±1 |
| S / T / O / M | substeps / time scale / warm starting / sleeping |

### Rebuilding

The `.sb3` is generated, so edit the Python sources and rebuild rather than editing the blocks:

```sh
python3 tools/build_physics_sb3.py   # writes physics_2d.sb3 from claude_text.sb3
node tools/test_physics.js           # headless regression tests of the engine
```

- `tools/sb3dsl.py` is a small Python DSL that compiles to Scratch 3 blocks: Python operators
  become reporters, and `with If(...)` / `with Repeat(...)` open substacks.
- `tools/build_physics_sb3.py` is the physics engine: bodies, collision, solver, joints and
  sleeping.
- `tools/physics_view.py` holds the rendering, HUD, input, scenes and main loop.
- `tools/dsl_to_js.py` and `tools/js_runtime.js` compile the same program to JavaScript with
  Scratch semantics, so `test_physics.js` can test the engine without a browser.

The physics code lives inside the text engine's sprite, as that engine's README recommends. Text is
drawn with direct calls to its custom blocks within the same warp-speed frame.
