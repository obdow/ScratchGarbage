#!/usr/bin/env node
// Regression tests for the physics engine in physics_2d.sb3.
// Compiles the engine to JS (tools/dsl_to_js.py) and runs scenes headless.
//   node tools/test_physics.js
const { execFileSync } = require('child_process');
const os = require('os'), path = require('path'), fs = require('fs');
const out = path.join(os.tmpdir(), `physics_engine_${process.pid}.js`);
execFileSync('python3', [path.join(__dirname, 'dsl_to_js.py'), out], { stdio: 'inherit' });

function fresh() {
  delete require.cache[require.resolve(out)];
  const E = require(out);
  const call = (code, ...a) => E.PR[code](...a);
  call('init settings');
  return { ...E, call, num: (name) => E.L(name).map(Number) };
}
const frames = (E, n) => { for (let f = 0; f < n; f++) { E.call('physics frame'); E.call('compute metrics'); } };
const scene = (E, k) => E.call('load scene n: %s', k);
let failed = 0;
function check(name, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${detail}`);
  if (!ok) failed++;
}
function finite(E) { return ['b x', 'b y', 'b vx', 'b vy', 'b w'].every(l => E.num(l).every(Number.isFinite)); }

// 1. 78-box pyramid settles in place and goes to sleep
{
  const E = fresh(); scene(E, 1);
  const x0 = E.num('b x'), y0 = E.num('b y');
  frames(E, 600);
  const st = E.num('b static'), x = E.num('b x'), y = E.num('b y');
  let drift = 0, n = 0;
  for (let i = 0; i < x.length; i++) if (!st[i]) { drift = Math.max(drift, Math.hypot(x[i] - x0[i], y[i] - y0[i])); n++; }
  check('pyramid stands', drift < 3, `max drift ${drift.toFixed(3)} px over ${n} boxes`);
  check('pyramid sleeps', +E.V['n awake'] === 0, `awake ${E.V['n awake']} asleep ${E.V['n asleep']}`);
}
// 2. tall column (12 boxes) stays upright
{
  const E = fresh(); E.call('reset world'); E.call('random material');
  for (let k = 0; k < 12; k++) E.call('add box x: %s y: %s w: %s h: %s angle: %s', 0, -150 + 20 * k, 20, 20, 0);
  E.V.sleeping = 0;
  frames(E, 600);
  const x = E.num('b x').slice(4);
  const spread = Math.max(...x.map(Math.abs));
  check('12-box column', spread < 2, `max |x| ${spread.toFixed(3)} px`);
}
// 3. Newton's cradle conserves energy and passes momentum to the far ball
{
  const E = fresh(); scene(E, 3);
  frames(E, 5); const e0 = +E.V.energy; let far = -1e9;
  for (let f = 0; f < 400; f++) { frames(E, 1); far = Math.max(far, E.num('b x')[9]); }
  const e1 = +E.V.energy;
  check('cradle energy', Math.abs(e1 - e0) / e0 < 0.03, `${e0.toFixed(2)} J -> ${e1.toFixed(2)} J`);
  check('cradle swing-out', far > 150, `last ball reached x=${far.toFixed(1)}`);
}
// 4. bridge (closed chain of revolute joints) settles instead of gaining energy
{
  const E = fresh(); scene(E, 4);
  frames(E, 1200);
  check('bridge settles', +E.V.ke < 0.05 && finite(E), `KE ${(+E.V.ke).toExponential(2)} J, awake ${E.V['n awake']}`);
}
// 5. friction ramps: the µ = 0.8 box sticks, the µ = 0.05 box leaves its ramp
{
  const E = fresh(); scene(E, 6);
  const x0 = E.num('b x'), y0 = E.num('b y');
  frames(E, 300);
  const x = E.num('b x'), y = E.num('b y'), ty = E.num('b static');
  const boxes = []; for (let i = 0; i < x.length; i++) if (!ty[i]) boxes.push(Math.hypot(x[i] - x0[i], y[i] - y0[i]));
  check('high friction sticks', boxes[2] < 1, `µ0.80 moved ${boxes[2].toFixed(2)} px`);
  check('low friction slides', boxes[0] > 100, `µ0.05 moved ${boxes[0].toFixed(1)} px`);
}
// 6. every scene stays finite and bounded, with and without warm starting
for (const warm of [1, 0]) for (let k = 1; k <= 7; k++) {
  const E = fresh(); scene(E, k); E.V.warm = warm;
  E.call('compute metrics');
  const e0 = +E.V.energy;
  frames(E, 480);
  const e = +E.V.energy;
  check(`scene ${k} warm=${warm} stable`, finite(E) && e < e0 * 1.05 + 1, `E ${e0.toFixed(1)} -> ${e.toFixed(1)} J`);
}
fs.unlinkSync(out);
console.log(failed ? `\n${failed} check(s) failed` : '\nall checks passed');
process.exit(failed ? 1 : 0);
