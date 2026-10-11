"""Synthesizes the instrument samples used by pen_daw.sb3 (mono 16-bit WAV)."""
import io
import math
import random
import wave

import numpy as np

SR = 22050
rng = np.random.default_rng(1234)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def t_axis(dur):
    return np.arange(int(SR * dur)) / SR


def env_adsr(n, a, d, s, r_start=None, r=0.05):
    """Attack/decay/sustain envelope with a short fade at the very end."""
    t = np.arange(n) / SR
    e = np.ones(n) * s
    if a > 0:
        m = t < a
        e[m] = t[m] / a
    m = (t >= a) & (t < a + d)
    e[m] = 1 - (1 - s) * (t[m] - a) / d
    fade = int(r * SR)
    e[-fade:] *= np.linspace(1, 0, fade)
    return e


def additive(f, dur, partials, phase_rand=True):
    t = t_axis(dur)
    out = np.zeros_like(t)
    for k, amp, decay in partials:
        fk = f * k
        if fk >= SR / 2 * 0.95:
            continue
        ph = rng.uniform(0, 2 * np.pi) if phase_rand else 0
        out += amp * np.sin(2 * np.pi * fk * t + ph) * (np.exp(-t * decay) if decay else 1)
    return out


def saw(f, t, nyq_frac=0.9, bright=1.0):
    out = np.zeros_like(t)
    k = 1
    while f * k < SR / 2 * nyq_frac:
        out += np.sin(2 * np.pi * f * k * t) / k * (bright ** (k - 1))
        k += 1
    return out * 0.6


def square(f, t, nyq_frac=0.9):
    out = np.zeros_like(t)
    k = 1
    while f * k < SR / 2 * nyq_frac:
        out += np.sin(2 * np.pi * f * k * t) / k
        k += 2
    return out * 0.8


def onepole_lp(x, cutoff):
    """cutoff may be scalar or per-sample array (Hz)."""
    y = np.zeros_like(x)
    c = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = 1 - np.exp(-2 * np.pi * c / SR)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def svf_lp(x, cutoff, q):
    """Chamberlin state-variable low-pass with per-sample cutoff."""
    c = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    low = band = 0.0
    y = np.zeros_like(x)
    damp = 1.0 / q
    for i in range(len(x)):
        f = 2 * math.sin(math.pi * min(c[i], SR * 0.2) / SR)
        low += f * band
        high = x[i] - low - damp * band
        band += f * high
        y[i] = low
    return y


def normalize(x, peak=0.89):
    m = np.max(np.abs(x))
    return x / m * peak if m > 0 else x


# ----------------------------------------------------------------------------- melodic

def piano():
    f = mtof(60)
    dur = 3.2
    parts = []
    for k in range(1, 18):
        inh = k * math.sqrt(1 + 0.0004 * k * k)
        parts.append((inh, 1.0 / (k ** 1.15), 0.9 + 0.55 * k))
    x = additive(f, dur, parts)
    # second string slightly detuned for chorus
    x += 0.6 * additive(f * 1.0012, dur, parts)
    t = t_axis(dur)
    hammer = rng.normal(0, 1, len(t)) * np.exp(-t * 60) * 0.25
    x = x + onepole_lp(hammer, 3000)
    x *= np.minimum(1, t / 0.002)
    x *= env_adsr(len(t), 0, 0.01, 1, r=0.2)
    return normalize(x)


def epiano():
    f = mtof(60)
    dur = 3.0
    t = t_axis(dur)
    idx = 1.8 * np.exp(-t * 3.0) + 0.15
    mod = np.sin(2 * np.pi * f * t)
    car = np.sin(2 * np.pi * f * t + idx * mod)
    tine = np.sin(2 * np.pi * f * 7.0 * t) * np.exp(-t * 18) * 0.25
    x = (car + tine) * np.exp(-t * 1.1)
    x *= np.minimum(1, t / 0.003)
    x *= 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)  # tremolo
    x *= env_adsr(len(t), 0, 0.01, 1, r=0.2)
    return normalize(x)


def organ():
    f = mtof(60)
    dur = 3.0
    t = t_axis(dur)
    vib = 0.003 * np.sin(2 * np.pi * 6.2 * t)
    x = np.zeros_like(t)
    for k, a in [(0.5, 0.6), (1, 1.0), (2, 0.7), (3, 0.45), (4, 0.35), (6, 0.2), (8, 0.15)]:
        x += a * np.sin(2 * np.pi * f * k * t * (1 + vib))
    click = rng.normal(0, 1, len(t)) * np.exp(-t * 300) * 0.15
    x = x + click
    x *= env_adsr(len(t), 0.008, 0.05, 0.9, r=0.1)
    return normalize(x)


def saw_lead():
    f = mtof(60)
    dur = 3.0
    t = t_axis(dur)
    x = saw(f, t) + saw(f * 1.006, t) * 0.8 + saw(f * 0.994, t) * 0.8
    cut = 2500 + 3500 * np.exp(-t * 4)
    x = svf_lp(x, cut, 1.2)
    x *= env_adsr(len(t), 0.005, 0.2, 0.8, r=0.1)
    return normalize(x)


def square_lead():
    f = mtof(60)
    dur = 3.0
    t = t_axis(dur)
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.6)
    # integrate frequency for vibrato
    ph = np.cumsum(f * vib) / SR
    x = np.zeros_like(t)
    k = 1
    while f * k < SR / 2 * 0.85:
        x += np.sin(2 * np.pi * k * ph) / k
        k += 2
    x = onepole_lp(x, 4500)
    x *= env_adsr(len(t), 0.004, 0.1, 0.85, r=0.1)
    return normalize(x)


def pluck():
    f = mtof(60)
    dur = 2.2
    n = int(SR * dur)
    period = SR / f
    p = int(period)
    frac = period - p
    buf = rng.uniform(-1, 1, p)
    buf = onepole_lp(buf, 6000)
    out = np.zeros(n)
    last = 0.0
    ring = list(buf)
    idx = 0
    for i in range(n):
        a = ring[idx % p]
        b = ring[(idx + 1) % p]
        v = 0.996 * (0.5 * (a + b))
        out[i] = a
        ring[idx % p] = v * (1 - frac * 0.0)
        idx += 1
    t = t_axis(dur)
    out *= env_adsr(n, 0.001, 0.01, 1, r=0.15)
    return normalize(out)


def pad():
    f = mtof(60)
    dur = 4.0
    t = t_axis(dur)
    x = np.zeros_like(t)
    for d in (-0.012, -0.006, 0, 0.005, 0.011):
        x += saw(f * (1 + d), t, bright=0.93)
    x += 0.5 * saw(f * 0.5 * 1.003, t, bright=0.9)
    lfo = 1400 + 500 * np.sin(2 * np.pi * 0.4 * t)
    x = svf_lp(x, lfo, 0.9)
    x *= env_adsr(len(t), 0.35, 0.5, 0.85, r=0.3)
    return normalize(x)


def bell():
    f = mtof(60)
    dur = 3.5
    t = t_axis(dur)
    idx = 3.0 * np.exp(-t * 1.5)
    mod = np.sin(2 * np.pi * f * 3.5 * t)
    x = np.sin(2 * np.pi * f * t + idx * mod) * np.exp(-t * 1.0)
    x += 0.3 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 2.5)
    x *= np.minimum(1, t / 0.002)
    x *= env_adsr(len(t), 0, 0.01, 1, r=0.2)
    return normalize(x)


def sub_bass():
    f = mtof(48)
    dur = 2.6
    t = t_axis(dur)
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t) + 0.08 * np.sin(2 * np.pi * 3 * f * t)
    x = np.tanh(1.5 * x)
    x *= env_adsr(len(t), 0.004, 0.3, 0.85, r=0.1)
    return normalize(x)


def synth_bass():
    f = mtof(48)
    dur = 2.2
    t = t_axis(dur)
    x = saw(f, t) + 0.6 * square(f * 1.003, t)
    cut = 300 + 2600 * np.exp(-t * 9)
    x = svf_lp(x, cut, 3.5)
    x = np.tanh(2.0 * x)
    x *= env_adsr(len(t), 0.002, 0.4, 0.7, r=0.1)
    return normalize(x)


# ----------------------------------------------------------------------------- drums

def kick():
    dur = 0.6
    t = t_axis(dur)
    fr = 45 + 120 * np.exp(-t * 30)
    ph = np.cumsum(fr) / SR
    x = np.sin(2 * np.pi * ph) * np.exp(-t * 7)
    x += rng.normal(0, 1, len(t)) * np.exp(-t * 200) * 0.3
    x = np.tanh(2.2 * x)
    return normalize(x * env_adsr(len(t), 0, 0.01, 1, r=0.05))


def snare():
    dur = 0.45
    t = t_axis(dur)
    tone = (np.sin(2 * np.pi * 185 * t) + 0.5 * np.sin(2 * np.pi * 330 * t)) * np.exp(-t * 22)
    noise = rng.normal(0, 1, len(t))
    noise = noise - onepole_lp(noise, 1500)
    x = tone * 0.7 + noise * np.exp(-t * 13) * 0.8
    return normalize(x * env_adsr(len(t), 0, 0.01, 1, r=0.05))


def clap():
    dur = 0.5
    t = t_axis(dur)
    noise = rng.normal(0, 1, len(t))
    noise = svf_lp(noise - onepole_lp(noise, 900), 2500, 2)
    e = np.zeros_like(t)
    for off in (0, 0.011, 0.022, 0.034):
        m = t >= off
        e[m] += np.exp(-(t[m] - off) * (140 if off < 0.03 else 14))
    return normalize(noise * e * env_adsr(len(t), 0, 0.01, 1, r=0.05))


def hat(open_=False):
    dur = 0.6 if open_ else 0.15
    t = t_axis(dur)
    x = np.zeros_like(t)
    for fr in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0):
        x += np.sign(np.sin(2 * np.pi * fr * 2.3 * t))
    x += rng.normal(0, 1, len(t)) * 1.5
    x = x - onepole_lp(x, 7000)
    x = x - onepole_lp(x, 6000)
    x *= np.exp(-t * (6 if open_ else 45))
    return normalize(x * env_adsr(len(t), 0, 0.01, 1, r=0.03), 0.6)


def tom(freq):
    dur = 0.6
    t = t_axis(dur)
    fr = freq * (1 + 0.6 * np.exp(-t * 18))
    ph = np.cumsum(fr) / SR
    x = np.sin(2 * np.pi * ph) * np.exp(-t * 6)
    x += onepole_lp(rng.normal(0, 1, len(t)), 3000) * np.exp(-t * 60) * 0.3
    return normalize(x * env_adsr(len(t), 0, 0.01, 1, r=0.05))


def crash():
    dur = 1.8
    t = t_axis(dur)
    x = rng.normal(0, 1, len(t))
    for fr in (342, 523, 721, 991, 1270):
        x += 0.3 * np.sign(np.sin(2 * np.pi * fr * 3.1 * t))
    x = x - onepole_lp(x, 4000)
    x *= np.exp(-t * 2.2) * np.minimum(1, t / 0.003)
    return normalize(x * env_adsr(len(t), 0, 0.01, 1, r=0.2), 0.6)


def rim():
    dur = 0.12
    t = t_axis(dur)
    x = (np.sin(2 * np.pi * 1700 * t) + 0.6 * np.sin(2 * np.pi * 820 * t)) * np.exp(-t * 70)
    x += rng.normal(0, 1, len(t)) * np.exp(-t * 300) * 0.4
    return normalize(x * env_adsr(len(t), 0, 0.01, 1, r=0.02), 0.7)


def cowbell():
    dur = 0.5
    t = t_axis(dur)
    x = np.sign(np.sin(2 * np.pi * 540 * t)) + np.sign(np.sin(2 * np.pi * 800 * t))
    x = svf_lp(x, 2500, 3) * np.exp(-t * 9)
    return normalize(x * env_adsr(len(t), 0, 0.01, 1, r=0.03), 0.7)


def click(freq):
    dur = 0.08
    t = t_axis(dur)
    x = np.sin(2 * np.pi * freq * t) * np.exp(-t * 60)
    return normalize(x * env_adsr(len(t), 0, 0.01, 1, r=0.01), 0.8)


MELODIC = [
    # (name, generator, root midi note)
    ('Piano', piano, 60),
    ('E-Piano', epiano, 60),
    ('Organ', organ, 60),
    ('Saw Lead', saw_lead, 60),
    ('Square Lead', square_lead, 60),
    ('Pluck', pluck, 60),
    ('Soft Pad', pad, 60),
    ('Bell', bell, 60),
    ('Sub Bass', sub_bass, 48),
    ('Synth Bass', synth_bass, 48),
]
DRUMS = [
    ('Kick', kick), ('Snare', snare), ('Clap', clap), ('Closed Hat', lambda: hat(False)),
    ('Open Hat', lambda: hat(True)), ('Low Tom', lambda: tom(105)), ('High Tom', lambda: tom(165)),
    ('Crash', crash), ('Rim', rim), ('Cowbell', cowbell),
]
CLICKS = [('Click Hi', lambda: click(1760)), ('Click Lo', lambda: click(1100))]


def level(x, target_rms, win=0.5):
    """Scale so the first `win` seconds hit target_rms without clipping."""
    head = x[:int(SR * win)]
    rms = float(np.sqrt(np.mean(head ** 2)))
    g = min(target_rms / max(rms, 1e-9), 0.95 / max(np.max(np.abs(x)), 1e-9))
    return x * g


def to_wav(x):
    pcm = np.clip(x * 32767, -32768, 32767).astype('<i2').tobytes()
    bio = io.BytesIO()
    with wave.open(bio, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return bio.getvalue(), len(x)


def generate():
    """Returns list of (name, wav_bytes, sample_count) in a fixed order:
    10 melodic, 10 drums, 2 clicks."""
    out = []
    for name, g, root in MELODIC:
        out.append((name,) + to_wav(level(g(), 0.22)))
    for name, g in DRUMS:
        out.append((name,) + to_wav(level(g(), 0.3, 0.1)))
    for name, g in CLICKS:
        out.append((name,) + to_wav(g()))
    return out


if __name__ == '__main__':
    import os
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else 'samples_out'
    os.makedirs(d, exist_ok=True)
    for name, data, n in generate():
        with open(os.path.join(d, name.replace(' ', '_') + '.wav'), 'wb') as f:
            f.write(data)
        print(name, n / SR, 's', len(data) // 1024, 'KB')
