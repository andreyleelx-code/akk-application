"""Percussive fingerstyle arrangement over the chord progression of «Бардак» (Балкон ожиданий).

Chords/tempo taken from public chord sites (D#m key, 143 BPM; verse i–III–VI–III,
chorus i–VI–III–V). The top-line melody is an original fingerstyle line, not the vocal.

Guitar: sampled steel-string acoustic (FluidR3 GM, program 25) rendered by FluidSynth.
Body percussion (thumb kick on the top, palm slap, nail ticks) is synthesized and mixed in.

Usage: python3 bardak_fingerstyle.py out.wav
"""
import subprocess, sys, wave, os, tempfile
import numpy as np
import mido

SR = 44100
BPM = 143
STEP = 60 / BPM / 4          # 16th note
CAPO = 6                     # Am shapes, capo 6 -> D#m
SF2 = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
rng = np.random.default_rng(11)

# ------------------------------------------------------------------ arrangement (Am shapes)
CHORDS = {
    #      bass root, bass alt, inner voices
    "Am": (45, 52, (57, 60, 64)),
    "C": (48, 55, (52, 55, 60)),
    "F": (41, 48, (53, 57, 60)),
    "E": (40, 47, (52, 56, 59)),
}

VERSE_CH = ["Am", "C", "F", "C"] * 2
VERSE_MEL = [
    [(0, 69, 2), (2, 72, 2), (4, 76, 4), (8, 74, 2), (10, 72, 2), (12, 71, 2), (14, 72, 2)],
    [(0, 67, 4), (4, 72, 2), (6, 74, 2), (8, 76, 6), (14, 74, 2)],
    [(0, 72, 3), (3, 69, 1), (4, 72, 4), (8, 77, 4), (12, 76, 4)],
    [(0, 76, 6), (6, 74, 2), (8, 72, 8)],
    [(0, 69, 2), (2, 72, 2), (4, 76, 4), (8, 74, 2), (10, 72, 2), (12, 71, 2), (14, 72, 2)],
    [(0, 67, 2), (2, 69, 2), (4, 72, 4), (8, 76, 4), (12, 79, 4)],
    [(0, 77, 4), (4, 76, 2), (6, 74, 2), (8, 72, 4), (12, 69, 4)],
    [(0, 71, 4), (4, 72, 4), (8, 67, 8)],
]
CHORUS_CH = ["Am", "F", "C", "E"] * 2
CHORUS_MEL = [
    [(0, 76, 2), (2, 76, 2), (4, 79, 4), (8, 76, 4), (12, 74, 2), (14, 72, 2)],
    [(0, 72, 4), (4, 77, 4), (8, 76, 4), (12, 74, 4)],
    [(0, 72, 2), (2, 74, 2), (4, 76, 4), (8, 79, 6), (14, 76, 2)],
    [(0, 76, 4), (4, 71, 4), (8, 68, 4), (12, 71, 4)],
    [(0, 76, 2), (2, 76, 2), (4, 79, 4), (8, 76, 4), (12, 74, 2), (14, 72, 2)],
    [(0, 72, 4), (4, 77, 4), (8, 76, 4), (12, 74, 4)],
    [(0, 79, 4), (4, 76, 4), (8, 72, 4), (12, 74, 4)],
    [(0, 76, 8), (8, 71, 4), (12, 68, 4)],
]
INTRO = [("Am", [(0, 76), (8, 81)]), ("C", [(0, 79), (8, 76)]),
         ("F", [(0, 77), (8, 81)]), ("C", [(0, 79), (8, 72)])]
BREAK = [("Am", [(0, 76)]), ("F", [(0, 77)]), ("C", [(0, 79)]), ("E", [(0, 80)])]

bars = []  # (chord, melody, mode, harmonics)
bars += [(c, [], "intro", h) for c, h in INTRO]
bars += [(c, m, "verse", []) for c, m in zip(VERSE_CH, VERSE_MEL)]
bars += [(c, m, "verse2", []) for c, m in zip(VERSE_CH, VERSE_MEL)]
bars += [(c, m, "chorus", []) for c, m in zip(CHORUS_CH, CHORUS_MEL)]
bars += [(c, [], "break", h) for c, h in BREAK]
bars += [(c, m, "chorus", []) for c, m in zip(CHORUS_CH, CHORUS_MEL)]
bars += [(c, m, "chorus", []) for c, m in zip(CHORUS_CH, CHORUS_MEL)]
bars += [("Am", [(0, 76, 4), (4, 72, 4), (8, 69, 8)], "outro", [(0, 81)])]
bars += [("Am", [], "end", [])]

# ------------------------------------------------------------------ note + hit lists
notes = []   # (time_s, midi, dur_s, velocity)
hits = []    # (time_s, kind, velocity)


def jitter():
    return float(rng.normal(0, 0.007))


def vel(v):
    return int(np.clip(v + rng.normal(0, 6), 20, 127))


def note(step, m, dur_steps, v, off=0.0):
    notes.append((step * STEP + off + jitter(), m + CAPO, dur_steps * STEP, vel(v)))


for b, (ch, mel, mode, harm) in enumerate(bars):
    s0 = b * 16
    root, alt, inner = CHORDS[ch]

    if mode == "end":
        for k, m in enumerate((root, alt, *inner, 69)):
            note(s0, m, 40, 85, 0.03 * k)
        break

    # thumb bass
    if mode in ("intro", "outro"):
        note(s0, root, 16, 80)
    elif mode == "break":
        for st, m in ((0, root), (6, root), (10, alt)):
            note(s0 + st, m, 4, 95)
    else:
        for st, m in ((0, root), (6, alt), (8, root), (14, alt)):
            note(s0 + st, m, 6, 92)

    # inner voices
    if mode in ("intro", "verse", "outro"):
        order = [0, 1, 2, 1]
        for st in range(0, 16, 2):
            if mode == "verse" and st in (4, 12):
                continue
            note(s0 + st, inner[order[(st // 2) % 4]], 4, 58)
    elif mode == "verse2":
        for st in (2, 6, 10, 14):
            for k, m in enumerate(inner):
                note(s0 + st, m, 2, 52, 0.01 * k)
    elif mode == "chorus":
        for st in (0, 8):
            for k, m in enumerate(inner):
                note(s0 + st, m, 6, 70, 0.014 * k)
        for st in (3, 6, 11, 14):  # quick up-strums
            for k, m in enumerate(reversed(inner)):
                note(s0 + st, m, 2, 55, 0.007 * k)

    # melody (top line)
    for st, m, ln in mel:
        note(s0 + st, m, ln + 1, 100)

    # high bell-like notes in intro/break (stand-in for harmonics)
    for st, m in harm:
        note(s0 + st, m, 12, 75)

    # body percussion
    if mode == "verse":
        hits += [((s0 + st) * STEP, "kick", 0.8) for st in (0, 8)]
        hits += [((s0 + st) * STEP + jitter(), "slap", 0.65) for st in (4, 12)]
    elif mode == "verse2":
        hits += [((s0 + st) * STEP, "kick", 0.9) for st in (0, 8, 10)]
        hits += [((s0 + st) * STEP + jitter(), "slap", 0.75) for st in (4, 12)]
    elif mode == "chorus":
        hits += [((s0 + st) * STEP, "kick", 1.0) for st in (0, 7, 10)]
        hits += [((s0 + st) * STEP, "slap", 0.9) for st in (4, 12)]
        hits += [((s0 + st) * STEP + jitter(), "tick", 0.10 + 0.07 * (st % 4 == 2))
                 for st in range(0, 16, 2) if st not in (4, 12)]
    elif mode == "break":
        hits += [((s0 + st) * STEP, "kick", 1.0) for st in (0, 3, 6, 10)]
        hits += [((s0 + st) * STEP, "slap", 0.9 if st != 15 else 0.45) for st in (4, 12, 15)]

# ------------------------------------------------------------------ MIDI -> FluidSynth
mid = mido.MidiFile(ticks_per_beat=960)
tr = mido.MidiTrack()
mid.tracks.append(tr)
tempo = mido.bpm2tempo(120)  # absolute seconds are encoded directly; 120 bpm => 1 beat = 0.5 s
tr.append(mido.MetaMessage("set_tempo", tempo=tempo))
tr.append(mido.Message("program_change", program=25, channel=0))
tr.append(mido.Message("control_change", control=91, value=25, channel=0))  # reverb send


def to_ticks(t):
    return int(round(max(0.0, t) / 0.5 * 960))


events = []
for t, m, d, v in notes:
    events.append((to_ticks(t), 1, mido.Message("note_on", note=m, velocity=v, channel=0)))
    events.append((to_ticks(t + d), 0, mido.Message("note_off", note=m, velocity=0, channel=0)))
events.sort(key=lambda e: (e[0], e[1]))
last = 0
for tick, _, msg in events:
    msg.time = tick - last
    last = tick
    tr.append(msg)

tmp = tempfile.mkdtemp()
mid_path = os.path.join(tmp, "g.mid")
gtr_path = os.path.join(tmp, "g.wav")
mid.save(mid_path)
subprocess.run(["fluidsynth", "-ni", "-g", "0.6", "-r", str(SR), "-F", gtr_path, SF2, mid_path],
               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

with wave.open(gtr_path) as w:
    g = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, 2) / 32768.0


# ------------------------------------------------------------------ synthesized body percussion
def onepole_lp(x, a):
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def kick(v):
    t = np.arange(int(0.22 * SR)) / SR
    f = 55 + 70 * np.exp(-t * 40)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 22)
    wood = np.sin(2 * np.pi * 210 * t) * np.exp(-t * 60) * 0.25
    knock = onepole_lp(rng.uniform(-1, 1, len(t)), 0.25) * np.exp(-t * 250) * 0.5
    return (body + wood + knock) * v


def slap(v):
    t = np.arange(int(0.18 * SR)) / SR
    n = rng.uniform(-1, 1, len(t))
    bp = onepole_lp(n - onepole_lp(n, 0.08), 0.45)
    snap = bp * np.exp(-t * 32)
    thump = np.sin(2 * np.pi * 165 * t) * np.exp(-t * 45) * 0.7
    buzz = np.sin(2 * np.pi * 330 * t + 2 * np.sin(2 * np.pi * 47 * t)) * np.exp(-t * 55) * 0.25
    return (snap * 1.1 + thump + buzz) * v


def tick(v):
    t = np.arange(int(0.04 * SR)) / SR
    n = rng.uniform(-1, 1, len(t))
    return (n - onepole_lp(n, 0.35)) * np.exp(-t * 140) * v


GEN = {"kick": kick, "slap": slap, "tick": tick}
perc = np.zeros(len(g) + SR)
for t, kind, v in hits:
    s = GEN[kind](v)
    i = int(t * SR)
    perc[i:i + len(s)] += s[: len(perc) - i]
perc = perc[: len(g)]

# short room reverb on percussion so it sits in the same space as the guitar
rt = np.arange(int(0.5 * SR)) / SR
ir = onepole_lp(rng.normal(0, 1, len(rt)), 0.3) * np.exp(-rt * 9)
ir[: int(0.008 * SR)] = 0
nfft = 1 << (len(perc) + len(ir)).bit_length()
wet = np.fft.irfft(np.fft.rfft(perc, nfft) * np.fft.rfft(ir, nfft), nfft)[: len(perc)]
perc = perc + wet / (np.abs(wet).max() + 1e-9) * np.abs(perc).max() * 0.15

gpk = np.abs(g).max()
mix = g / gpk + np.stack([perc, perc], axis=1) * 0.55
mix = np.tanh(mix * 1.1) / np.tanh(1.1)
mix /= np.abs(mix).max() / 0.95

# trim trailing silence
alive = np.where(np.abs(mix).max(axis=1) > 1e-3)[0]
mix = mix[: alive[-1] + SR // 2]
fade = min(len(mix), SR // 2)
mix[-fade:] *= np.linspace(1, 0, fade)[:, None]

with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((mix * 32767).astype(np.int16).tobytes())
print(f"wrote {sys.argv[1]} {len(mix)/SR:.1f}s, {len(notes)} notes, {len(hits)} hits")
