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


def midi_frequency(note):
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def generate(path, seconds, bpm=BPM, sample_rate=SAMPLE_RATE):
    """Render a short, energetic E-minor electronic groove beneath narration."""
    if not (4.0 <= seconds <= 180.0):
        raise ValueError("Music duration must be 4-180 seconds")
    n = math.ceil(seconds * sample_rate)
    samples = array("f", [0.0]) * n
    rng = random.Random(SEED)
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

    # E minor, C major, G major, D major. Bass roots E2, C2, G2, D2.
    chords = [
        (40, [64, 67, 71]),  # Em
        (36, [60, 64, 67]),  # C
        (43, [67, 71, 74]),  # G
        (38, [62, 66, 69]),  # D
    ]
    bars = math.ceil(seconds / bar)
    for b in range(bars):
        tbar = b * bar
        root, tones = chords[b % len(chords)]
        if tbar >= seconds:
            break

        # Tight modern kick/snare groove; variation avoids machine-gun repetition.
        for pos, level in ((0.0, 0.61), (1.5, 0.34), (2.0, 0.52),
                           (3.25 if b % 2 == 0 else 3.5, 0.27)):
            at = tbar + pos * beat
            if at < seconds:
                add_kick(at, level)
        for pos in (1, 3):
            at = tbar + pos * beat
            if at < seconds:
                add_snare(at, 0.26 if pos == 1 else 0.32)
        for h in range(8):
            at = tbar + h * beat / 2
            if at < seconds:
                add_hat(at, (0.075 if h % 2 == 0 else 0.11),
                        open_hat=(h == 7 and b % 2 == 1))

        for pos, level in ((0.0, 0.29), (0.75, 0.15), (2.0, 0.22),
                           (2.75, 0.18)):
            at = tbar + pos * beat
            if at < seconds:
                add_note(at, root, 0.61 * beat, level, "bass")

        # Musical tonal motif, sparse enough to leave room for spoken narration.
        for j, pos in enumerate((0.0, 1.5, 2.5, 3.5)):
            at = tbar + pos * beat
            if at < seconds:
                note = tones[(j + b) % len(tones)]
                add_note(at, note + (12 if j == 3 else 0), 0.56, 0.088)

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
            "style": "original electronic action groove, E minor",
            "source": "deterministic programmatic synthesis; no samples"}

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python soundtrack.py PATH.wav duration_seconds")
    print(generate(sys.argv[1], float(sys.argv[2])))
