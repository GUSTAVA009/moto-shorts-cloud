#!/usr/bin/env python3
"""Original, deterministic, sample-free action soundtrack for Shorts.

Generates PCM WAV using only Python's standard library. No musical samples,
copyrighted recordings, subscriptions, network calls or local user files.
"""
from array import array
import math
from pathlib import Path
import random
import sys
import wave

BPM = 128
SAMPLE_RATE = 32000
SEED = 21844
TWO_PI = 2 * math.pi

# All notes are newly synthesized, sample-free and independent of recorded music.
# Different categories receive different harmony and rhythm rather than the same
# audio bed applied to every new video.
STYLES = {
    "action": {
        "chords": [(40, [64, 67, 71]), (36, [60, 64, 67]), (43, [67, 71, 74]), (38, [62, 66, 69])],
        "kick": ((0, .61), (1.5, .34), (2, .52), (3.25, .27)),
        "snare": (.30, 1, 3), "hat": .11, "bass": .29, "lead": .088,
    },
    "night-drive": {
        "chords": [(45, [69, 72, 76]), (41, [65, 69, 72]), (36, [60, 64, 67]), (43, [67, 71, 74])],
        "kick": ((0, .48), (2, .50)), "snare": (.22, 1, 3),
        "hat": .07, "bass": .31, "lead": .118,
    },
    "garage-groove": {
        "chords": [(38, [62, 65, 69]), (34, [58, 62, 65]), (41, [65, 69, 72]), (36, [60, 64, 67])],
        "kick": ((0, .58), (1.75, .34), (3, .48)), "snare": (.36, 1.0, 2.75),
        "hat": .085, "bass": .35, "lead": .063,
    },
    "race-breakbeat": {
        "chords": [(43, [67, 70, 74]), (39, [63, 67, 70]), (46, [70, 74, 77]), (41, [65, 69, 72])],
        "kick": ((0, .65), (.75, .26), (1.5, .49), (2, .60), (3.5, .35)),
        "snare": (.36, 1, 2.5, 3), "hat": .125, "bass": .30, "lead": .10,
    },
    "desert-cinematic": {
        "chords": [(47, [71, 74, 78]), (43, [67, 71, 74]), (38, [62, 66, 69]), (45, [69, 73, 76])],
        "kick": ((0, .46), (2, .40)), "snare": (.16, 3),
        "hat": .05, "bass": .30, "lead": .10,
    },
}


def midi_frequency(note):
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def generate(path, seconds, bpm=BPM, sample_rate=SAMPLE_RATE, style="action", seed=None):
    """Generate a fresh background track matching the episode's atmosphere."""
    if not (4.0 <= seconds <= 180.0):
        raise ValueError("Music duration must be 4-180 seconds")
    if style not in STYLES or not (50 <= int(bpm) <= 200):
        raise ValueError("Unsupported original music style or BPM")
    settings = STYLES[style]
    n = math.ceil(seconds * sample_rate)
    samples = array("f", [0.0]) * n
    rng = random.Random(SEED if seed is None else int(seed))
    beat = 60.0 / float(bpm)
    bar = beat * 4

    def add_note(start, note, length, strength=0.22, kind="pluck"):
        first = int(start * sample_rate)
        if first >= n or first < 0:
            return
        count = min(int(length * sample_rate), n - first)
        if count <= 0:
            return
        frequency = midi_frequency(note)
        dt = 1.0 / sample_rate
        ph1 = 0.0
        ph2 = 0.0
        for k in range(count):
            t = k * dt
            attack = min(1.0, t / 0.012)
            if kind == "bass":
                envelope = math.exp(-t * 3.9) * attack
                bend = 1 + 0.09 * math.exp(-t * 22)
                ph1 += TWO_PI * frequency * bend * dt
                ph2 += TWO_PI * frequency * 2 * dt
                value = (math.sin(ph1) + 0.18 * math.sin(ph2)) * envelope
            else:
                envelope = math.exp(-t * 8.2) * attack
                ph1 += TWO_PI * frequency * dt
                ph2 += TWO_PI * frequency * 2 * dt
                value = (math.sin(ph1) + 0.20 * math.sin(ph2)) * envelope
            samples[first + k] += value * strength

    def add_kick(start, strength=0.60):
        first = int(start * sample_rate)
        if first < 0 or first >= n:
            return
        count = min(int(0.34 * sample_rate), n - first)
        phase = 0.0
        for k in range(count):
            t = k / sample_rate
            freq = 49.0 + 115.0 * math.exp(-t * 31.0)
            phase += TWO_PI * freq / sample_rate
            envelope = math.exp(-t * 14.0)
            tick = rng.uniform(-1.0, 1.0) * math.exp(-t * 230.0) * 0.10
            samples[first + k] += strength * (math.sin(phase) * envelope + tick)

    def add_snare(start, strength=0.30):
        first = int(start * sample_rate)
        if first < 0 or first >= n:
            return
        count = min(int(0.19 * sample_rate), n - first)
        previous = 0.0
        for k in range(count):
            t = k / sample_rate
            noise = rng.uniform(-1.0, 1.0)
            bright = noise - previous * 0.75
            previous = noise
            envelope = math.exp(-t * 24.0)
            tone = math.sin(TWO_PI * 181.0 * t) * math.exp(-t * 31.0)
            samples[first + k] += strength * (0.75 * bright + 0.25 * tone) * envelope

    def add_hat(start, strength=0.115, open_hat=False):
        first = int(start * sample_rate)
        if first < 0 or first >= n:
            return
        count = min(int((0.17 if open_hat else 0.07) * sample_rate), n - first)
        previous = 0.0
        speed = 23.0 if open_hat else 68.0
        for k in range(count):
            t = k / sample_rate
            noise = rng.uniform(-1.0, 1.0)
            bright = noise - previous
            previous = noise
            samples[first + k] += bright * math.exp(-t * speed) * strength

    chords = settings["chords"]
    bars = math.ceil(seconds / bar)
    for b in range(bars):
        tbar = b * bar
        root, tones = chords[b % len(chords)]
        if tbar >= seconds:
            break

        # Tight modern kick/snare groove; variation avoids machine-gun repetition.
        for pos, level in settings["kick"]:
            at = tbar + pos * beat
            if at < seconds:
                add_kick(at, level)
        snare_strength, *snare_beats = settings["snare"]
        for pos in snare_beats:
            at = tbar + pos * beat
            if at < seconds:
                add_snare(at, snare_strength)
        for h in range(8):
            at = tbar + h * beat / 2
            if at < seconds:
                add_hat(at, settings["hat"] * (0.7 if h % 2 == 0 else 1.0),
                        open_hat=(h == 7 and b % 2 == 1))

        for pos, level in ((0.0, 0.29), (0.75, 0.15), (2.0, 0.22),
                           (2.75, 0.18)):
            at = tbar + pos * beat
            if at < seconds:
                add_note(at, root, 0.61 * beat,
                         level * settings["bass"] / .29, "bass")

        # Musical tonal motif, sparse enough to leave room for spoken narration.
        for j, pos in enumerate((0.0, 1.5, 2.5, 3.5)):
            at = tbar + pos * beat
            if at < seconds:
                note = tones[(j + b) % len(tones)]
                add_note(at, note + (12 if j == 3 else 0),
                         0.56, settings["lead"])

    # Prevent clipping, fade in/out to avoid crackle at Shorts edits.
    peak = max((abs(v) for v in samples), default=0)
    scale = min(0.84 / max(peak, 1e-6), 1.0)
    fade = min(int(0.35 * sample_rate), n // 5)
    pcm = array("h")
    for i, value in enumerate(samples):
        beginning = min(1.0, i / max(1, int(0.10 * sample_rate)))
        ending = min(1.0, (n - i - 1) / max(1, fade))
        val = max(-1.0, min(1.0, value * scale * beginning * ending))
        pcm.append(int(val * 32760))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())
    return {"wav": str(path), "seconds": seconds, "bpm": bpm,
            "style": "original procedural " + style,
            "source": "deterministic programmatic synthesis; no samples"}

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python soundtrack.py PATH.wav duration_seconds")
    print(generate(sys.argv[1], float(sys.argv[2])))
