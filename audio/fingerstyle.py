"""Synthesized percussive fingerstyle guitar demo (original arrangement, A minor).

Karplus-Strong strings + body-percussion (thumb "kick" on the top, palm "snare" slap),
thumb bass, inner arpeggio, top-line melody, harmonics.
"""
import numpy as np
import wave, sys

SR = 44100
BPM = 92
STEP = 60 / BPM / 4  # 16th note in seconds
rng = np.random.default_rng(7)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def onepole_lp(x, a):
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def pluck(midi, dur, vel=1.0, bright=0.5, decay=0.996, mute=False):
    f = mtof(midi)
    n_total = int(dur * SR)
    N = max(2, int(round(SR / f)))
    buf = rng.uniform(-1, 1, N)
    buf = onepole_lp(buf, 0.15 + 0.8 * bright)
    buf -= buf.mean()
    d = 0.90 if mute else decay
    blocks = [buf]
    prev = buf
    while sum(len(b) for b in blocks) < n_total:
        nxt = d * 0.5 * (prev + np.roll(prev, -1))
        blocks.append(nxt)
        prev = nxt
    out = np.concatenate(blocks)[:n_total]
    # pick attack transient + gentle release at the end
    att = np.minimum(1, np.arange(n_total) / (0.002 * SR))
    rel_len = min(n_total, int(0.03 * SR))
    env = att.copy()
    env[-rel_len:] *= np.linspace(1, 0, rel_len)
    return out * env * vel


def harmonic(midi, dur, vel=0.5):
    f = mtof(midi)
    t = np.arange(int(dur * SR)) / SR
    s = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t) + 0.08 * np.sin(6 * np.pi * f * t)
    env = np.exp(-t * 1.6) * np.minimum(1, t / 0.003)
    return s * env * vel


def kick(vel=1.0):
    t = np.arange(int(0.25 * SR)) / SR
    f = 45 + 60 * np.exp(-t * 35)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 18)
    click = rng.uniform(-1, 1, len(t)) * np.exp(-t * 400) * 0.25
    return (body + click) * vel


def slap(vel=1.0):
    t = np.arange(int(0.22 * SR)) / SR
    noise = rng.uniform(-1, 1, len(t))
    hp = noise - onepole_lp(noise, 0.12)
    bp = onepole_lp(hp, 0.55)
    snap = bp * np.exp(-t * 28)
    thump = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 40) * 0.6
    # muted strings rattling under the palm
    rattle = sum(pluck(m, 0.22, 0.35, 0.9, mute=True) for m in (52, 57, 62))
    return (snap * 0.9 + thump + rattle[: len(t)]) * vel


def tick(vel=0.3):
    t = np.arange(int(0.05 * SR)) / SR
    n = rng.uniform(-1, 1, len(t))
    n = n - onepole_lp(n, 0.3)
    return n * np.exp(-t * 120) * vel


def body_ir():
    t = np.arange(int(0.08 * SR)) / SR
    ir = np.zeros_like(t)
    for f, d, a in ((98, 30, 1.0), (205, 45, 0.6), (390, 70, 0.3), (720, 110, 0.15)):
        ir += a * np.sin(2 * np.pi * f * t) * np.exp(-t * d)
    ir /= np.abs(ir).sum() / 8
    ir[0] += 1.0
    return ir


def fft_convolve(x, h):
    n = len(x) + len(h) - 1
    nfft = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(h, nfft), nfft)[:n]
    return y[: len(x)]


def reverb(x, mix=0.18):
    t = np.arange(int(1.6 * SR)) / SR
    ir = rng.normal(0, 1, len(t)) * np.exp(-t * 3.2)
    ir = onepole_lp(ir, 0.35)
    ir[: int(0.012 * SR)] = 0
    wet = fft_convolve(x, ir)
    wet *= np.abs(x).max() / (np.abs(wet).max() + 1e-9)
    return x * (1 - mix) + wet * mix


# ---------------------------------------------------------------- arrangement
CHORDS = {
    #       bass root, bass alt, inner voices
    "Am": (45, 40, (57, 60, 64)),
    "F": (41, 48, (53, 57, 60)),
    "C": (48, 43, (52, 55, 60)),
    "G": (43, 50, (50, 55, 59)),
    "E": (40, 47, (52, 56, 59)),
    "Dm": (50, 45, (50, 53, 57)),
}

VERSE_MEL = [
    [(0, 76, 3), (3, 74, 1), (4, 72, 4), (8, 71, 2), (10, 72, 2), (12, 69, 4)],
    [(0, 72, 3), (3, 69, 1), (4, 72, 2), (6, 74, 2), (8, 76, 6), (14, 74, 2)],
    [(0, 72, 4), (4, 67, 2), (6, 69, 2), (8, 72, 4), (12, 74, 4)],
    [(0, 71, 6), (6, 67, 2), (8, 74, 4), (12, 71, 4)],
    [(0, 76, 3), (3, 74, 1), (4, 72, 4), (8, 71, 2), (10, 72, 2), (12, 69, 4)],
    [(0, 72, 3), (3, 74, 1), (4, 76, 4), (8, 77, 4), (12, 76, 4)],
    [(0, 79, 4), (4, 76, 2), (6, 74, 2), (8, 72, 6), (14, 71, 2)],
    [(0, 74, 8), (8, 71, 4), (12, 67, 4)],
]
VERSE_CH = ["Am", "F", "C", "G", "Am", "F", "C", "G"]

CHORUS_MEL = [
    [(0, 81, 4), (4, 79, 2), (6, 77, 2), (8, 76, 4), (12, 77, 4)],
    [(0, 79, 6), (6, 77, 2), (8, 74, 4), (12, 71, 4)],
    [(0, 72, 4), (4, 76, 4), (8, 81, 8)],
    [(0, 79, 2), (2, 77, 2), (4, 76, 4), (8, 72, 2), (10, 74, 2), (12, 76, 4)],
    [(0, 81, 4), (4, 79, 2), (6, 77, 2), (8, 76, 4), (12, 77, 4)],
    [(0, 79, 4), (4, 83, 4), (8, 81, 4), (12, 79, 4)],
    [(0, 76, 4), (4, 79, 4), (8, 84, 8)],
    [(0, 83, 6), (6, 80, 2), (8, 76, 8)],
]
CHORUS_CH = ["F", "G", "Am", "Am", "F", "G", "C", "E"]

BRIDGE_CH = ["Dm", "Am", "F", "E"]
BRIDGE_HARM = [[(0, 74), (8, 77)], [(0, 76), (8, 72)], [(0, 77), (8, 72)], [(0, 76), (8, 80)]]

INTRO_CH = ["Am", "F", "C", "E"]
INTRO_HARM = [[(0, 76), (8, 81)], [(0, 77), (8, 81)], [(0, 79), (8, 76)], [(0, 80), (8, 83)]]

bars = []  # (chord, melody, mode, harmonics)
for c, h in zip(INTRO_CH, INTRO_HARM):
    bars.append((c, [], "intro", h))
for c, m in zip(VERSE_CH, VERSE_MEL):
    bars.append((c, m, "verse", []))
for c, m in zip(CHORUS_CH, CHORUS_MEL):
    bars.append((c, m, "chorus", []))
for c, h in zip(BRIDGE_CH, BRIDGE_HARM):
    bars.append((c, [], "bridge", h))
for c, m in zip(CHORUS_CH, CHORUS_MEL):
    bars.append((c, m, "chorus", []))
bars.append(("Am", [(0, 76, 4), (4, 72, 4), (8, 69, 8)], "outro", [(0, 81)]))
bars.append(("Am", [], "end", []))

total = int((len(bars) * 16 + 32) * STEP * SR)
strings_L = np.zeros(total)
strings_R = np.zeros(total)
perc = np.zeros(total)


def put(track, sig, step_pos, offset=0.0):
    i = int((step_pos * STEP + offset) * SR)
    j = min(total, i + len(sig))
    if i < total:
        track[i:j] += sig[: j - i]


def humanize():
    return rng.normal(0, 0.006)


for b, (ch, mel, mode, harm) in enumerate(bars):
    s0 = b * 16
    root, alt, inner = CHORDS[ch]

    if mode == "end":
        # final ringing chord + harmonic
        for k, m in enumerate((root, alt + 12, *inner, 76)):
            put(strings_L if k < 2 else strings_R, pluck(m, 5.0, 0.7, 0.45, 0.9985), s0, 0.025 * k)
        put(strings_R, harmonic(81, 5.0, 0.35), s0, 0.15)
        break

    # --- thumb bass
    if mode in ("intro", "outro"):
        put(strings_L, pluck(root, 3.0, 0.8, 0.35, 0.998), s0)
    else:
        pattern = [(0, root), (3, alt), (8, root), (11, alt)] if mode != "bridge" else [(0, root), (10, root), (14, alt)]
        for st, m in pattern:
            put(strings_L, pluck(m, 0.9, 0.9, 0.4, 0.997), s0 + st, humanize())

    # --- inner arpeggio / strums
    if mode in ("intro", "verse", "outro"):
        order = [0, 1, 2, 1]
        for st in range(0, 16, 2):
            if mode == "verse" and st in (4, 12):
                continue  # leave room for the slap
            m = inner[order[(st // 2) % 4]]
            put(strings_R, pluck(m, 1.2, 0.38, 0.5, 0.9965), s0 + st, humanize())
    elif mode == "chorus":
        for st in (2, 6, 10, 14):  # off-beat up-strums
            for k, m in enumerate(reversed(inner)):
                put(strings_R, pluck(m, 0.5, 0.32, 0.6, 0.995), s0 + st, 0.008 * k + humanize())
        for st in (0, 8):
            for k, m in enumerate(inner):
                put(strings_R, pluck(m, 1.0, 0.4, 0.55, 0.997), s0 + st, 0.012 * k)

    # --- body percussion
    if mode == "verse":
        for st in (0, 10):
            put(perc, kick(0.9), s0 + st)
        for st in (4, 12):
            put(perc, slap(0.75), s0 + st, humanize())
    elif mode == "chorus":
        for st in (0, 7, 10):
            put(perc, kick(1.0), s0 + st)
        for st in (4, 12):
            put(perc, slap(0.95), s0 + st)
        for st in range(16):
            if st not in (4, 12):
                put(perc, tick(0.12 + 0.08 * (st % 2 == 0)), s0 + st, humanize())
    elif mode == "bridge":
        for st in (0, 3, 6, 10):
            put(perc, kick(1.0), s0 + st)
        for st in (4, 12, 15):
            put(perc, slap(0.9 if st != 15 else 0.5), s0 + st)

    # --- melody
    for st, m, ln in mel:
        put(strings_R, pluck(m, ln * STEP + 0.6, 0.75, 0.62, 0.9975), s0 + st, humanize())

    # --- harmonics
    for st, m in harm:
        put(strings_R, harmonic(m, 3.0, 0.32), s0 + st)

ir = body_ir()
L_dry = fft_convolve(strings_L * 0.8 + strings_R * 0.35, ir) + perc * 0.9
R_dry = fft_convolve(strings_R * 0.8 + strings_L * 0.35, ir) + perc * 0.9
L = reverb(L_dry)
R = reverb(R_dry)
mix = np.stack([L, R], axis=1)
mix = np.tanh(mix / np.abs(mix).max() * 1.4) * 0.89
mix /= np.abs(mix).max() / 0.95
pcm = (mix * 32767).astype(np.int16)

out = sys.argv[1]
with wave.open(out, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote", out, f"{len(pcm)/SR:.1f}s")
