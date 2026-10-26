"""The `capacity` EEG toy profile: fresh subjects per replicate under a declared class rule.

Stdlib only and seeded: the same rule, separation, seed and sizes give the same
bytes, so a remote notebook can regenerate a replicate instead of downloading it.

Each subject carries a deviation that scales the Theta and Beta amplitudes on the
fronto-central channels; the class follows one of three rules:

- ``monotone``: the deviation log Theta/Beta offset is drawn from N(+-d'/2, 1) by
  class, so the subject-level Bayes limit is Phi(d'/2).
- ``interaction``: independent N(0, 1) Theta and Beta deviations; class 1 when
  both deviate in the same direction (the log ratio carries no class).
- ``frequency-two``: a Theta deviation uniform on [-pi, pi); class 1 where
  cos(2u) > 0.

Every epoch is narrowband Theta, Beta and Alpha (sums of sinusoids at random
frequencies inside each band) over an AR(1) red-noise background, mixed with
the neighbouring channels, with a frontal eye blink in a fraction of the epochs.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import struct
from array import array
from pathlib import Path

GENERATOR_VERSION = 1
RULES = ("monotone", "interaction", "frequency-two")
#: The 19-channel montage of the declared dataset, in its own order.
CHANNELS = ("Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2",
            "F7", "F8", "T7", "T8", "P7", "P8", "Fz", "Cz", "Pz")
FRONTAL = ("Fp1", "Fp2", "F3", "F4", "F7", "F8", "Fz")
CENTRAL = ("C3", "C4", "Cz")
BLINK_CHANNELS = {"Fp1": 1.0, "Fp2": 1.0, "F7": 0.5, "F8": 0.5, "F3": 0.3, "F4": 0.3, "Fz": 0.3}
BANDS = {"theta": (4.0, 8.0), "beta": (13.0, 30.0), "alpha": (8.0, 12.0)}
PARAMETERS = {
    "sinusoidsPerBand": 4,       # narrowband activity = sum of this many sinusoids per band
    "rhythmScale": 3.0,          # rhythm amplitude relative to the unit-variance background
    "betaWeight": 0.7,           # Beta amplitude relative to Theta
    "alphaLogSd": 0.25,          # per-epoch log-amplitude sd of the common Alpha
    "effectGain": 1.0,           # deviation -> log-amplitude gain on the effect channels
    "withinSd": 0.4,             # per-epoch deviation jitter around the subject's deviation
    "subjectGainLogSd": 0.05,    # per-subject overall gain, log sd
    "backgroundAr": 0.95,        # AR(1) coefficient of the red-noise background
    "neighbourMix": 0.5,         # share of the signal taken from the two neighbouring channels
    "blinkProbability": 0.15,    # probability of one frontal blink per epoch
    "blinkAmplitude": 6.0,
    "blinkWidthSamples": 6.0,
}


def subject_deviation(rule: str, label: int, d_prime: float, rng: random.Random) -> dict:
    """The subject's deviation, drawn conditionally on its class so groups stay balanced."""
    if rule == "monotone":
        return {"ratio": rng.gauss(d_prime * (label - 0.5), 1.0)}
    if rule == "interaction":
        theta, beta = abs(rng.gauss(0.0, 1.0)), abs(rng.gauss(0.0, 1.0))
        sign = 1.0 if rng.random() < 0.5 else -1.0
        return {"theta": sign * theta, "beta": (sign if label else -sign) * beta}
    # frequency-two: class 1 on |u| < pi/4 or |u| > 3pi/4, class 0 on the two middle arcs.
    offset = rng.uniform(0.0, math.pi / 2)
    if label:
        u = offset - math.pi / 4 if rng.random() < 0.5 else offset + 3 * math.pi / 4
        u = (u + math.pi) % (2 * math.pi) - math.pi
    else:
        u = offset + math.pi / 4 if rng.random() < 0.5 else offset - 3 * math.pi / 4
    return {"theta": u}


def log_amplitudes(rule: str, deviation: dict, jitter: float) -> tuple[float, float]:
    """Log Theta and log Beta amplitude factors on the effect channels for one epoch."""
    gain = PARAMETERS["effectGain"]
    if rule == "monotone":
        r = deviation["ratio"] + jitter
        return gain * r / 2, -gain * r / 2
    if rule == "interaction":
        return gain * (deviation["theta"] + jitter), gain * (deviation["beta"] + jitter)
    return gain * (deviation["theta"] + jitter) / (math.pi / 2), 0.0


def band_source(rng: random.Random, band: str, length: int, sfreq: float) -> list[float]:
    lo, hi = BANDS[band]
    k = PARAMETERS["sinusoidsPerBand"]
    norm = math.sqrt(2.0 / k)
    out = [0.0] * length
    for _ in range(k):
        w = 2.0 * math.pi * rng.uniform(lo, hi) / sfreq
        phase = rng.uniform(0.0, 2.0 * math.pi)
        for t in range(length):
            out[t] += norm * math.sin(w * t + phase)
    return out


def background(rng: random.Random, length: int) -> list[float]:
    a = PARAMETERS["backgroundAr"]
    scale = math.sqrt(1.0 - a * a)
    x = rng.gauss(0.0, 1.0)
    out = []
    for _ in range(length):
        x = a * x + scale * rng.gauss(0.0, 1.0)
        out.append(x)
    return out


def epoch(rule: str, deviation: dict, gain: float, rng: random.Random, length: int, sfreq: float) -> list[list[float]]:
    effect = set(FRONTAL) | set(CENTRAL)
    log_theta, log_beta = log_amplitudes(rule, deviation, PARAMETERS["withinSd"] * rng.gauss(0.0, 1.0))
    alpha_amp = math.exp(PARAMETERS["alphaLogSd"] * rng.gauss(0.0, 1.0))
    scale = PARAMETERS["rhythmScale"]
    sources = []
    for name in CHANNELS:
        th = math.exp(log_theta) if name in effect else 1.0
        be = PARAMETERS["betaWeight"] * (math.exp(log_beta) if name in effect else 1.0)
        theta, beta = band_source(rng, "theta", length, sfreq), band_source(rng, "beta", length, sfreq)
        alpha, noise = band_source(rng, "alpha", length, sfreq), background(rng, length)
        sources.append([scale * (th * a + be * b + alpha_amp * c) + d
                        for a, b, c, d in zip(theta, beta, alpha, noise)])
    if rng.random() < PARAMETERS["blinkProbability"]:
        centre = rng.uniform(0.15 * length, 0.85 * length)
        width = PARAMETERS["blinkWidthSamples"]
        bump = [PARAMETERS["blinkAmplitude"] * math.exp(-0.5 * ((t - centre) / width) ** 2) for t in range(length)]
        for name, weight in BLINK_CHANNELS.items():
            row = sources[CHANNELS.index(name)]
            for t in range(length):
                row[t] += weight * bump[t]
    m = PARAMETERS["neighbourMix"]
    n = len(sources)
    mixed = []
    for c in range(n):
        left, right = sources[max(c - 1, 0)], sources[min(c + 1, n - 1)]
        own = sources[c]
        mixed.append([gain * ((1 - m) * own[t] + m / 2 * (left[t] + right[t])) for t in range(length)])
    return mixed


def generate(rule: str, d_prime: float, seed: int, sizes: dict, n_per_subject: int,
             length: int = 256, sfreq: float = 128.0) -> tuple[array, dict]:
    """One replicate: float32 values (epochs x channels x samples) and its metadata."""
    if rule not in RULES:
        raise ValueError(f"rule {rule!r}: one of {', '.join(RULES)}")
    rng = random.Random(f"capacity-v{GENERATOR_VERSION}|{rule}|{d_prime!r}|{seed}")
    values = array("f")
    subjects, epochs_meta = [], {"subject": [], "split": [], "label": []}
    for split in ("train", "validation", "test"):
        for index in range(sizes[split]):
            label = index % 2
            deviation = subject_deviation(rule, label, d_prime, rng)
            gain = math.exp(PARAMETERS["subjectGainLogSd"] * rng.gauss(0.0, 1.0))
            name = f"{split[:2]}{index:03d}"
            subjects.append({"subject": name, "split": split, "label": label, "deviation": deviation})
            for _ in range(n_per_subject):
                for row in epoch(rule, deviation, gain, rng, length, sfreq):
                    values.extend(row)
                epochs_meta["subject"].append(name)
                epochs_meta["split"].append(split)
                epochs_meta["label"].append(label)
    meta = {"schema": 1, "generator": "capacity", "generatorVersion": GENERATOR_VERSION, "rule": rule,
            "dPrime": d_prime if rule == "monotone" else None, "seed": seed, "sizes": dict(sizes),
            "nPerSubject": n_per_subject, "shape": [len(epochs_meta["label"]), len(CHANNELS), length],
            "sfreq": sfreq, "channels": list(CHANNELS), "effectChannels": {"frontal": list(FRONTAL),
                                                                           "central": list(CENTRAL)},
            "parameters": dict(PARAMETERS), "subjects": subjects, "epochs": epochs_meta}
    return values, meta


def write_npy(path: Path, values: array, shape: list[int]) -> str:
    """Write a little-endian float32 .npy (format 1.0) and return its sha256."""
    if values.itemsize != 4:
        raise ValueError("float32 values expected")
    data = values if struct.pack("=f", 1.0) == struct.pack("<f", 1.0) else _swapped(values)
    header = "{'descr': '<f4', 'fortran_order': False, 'shape': (%s), }" % (
        ", ".join(str(n) for n in shape) + ("," if len(shape) == 1 else ""))
    pad = 64 - (10 + len(header) + 1) % 64
    blob = b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header) + pad + 1) + header.encode("latin1") \
        + b" " * pad + b"\n" + data.tobytes()
    path.write_bytes(blob)
    return hashlib.sha256(blob).hexdigest()


def _swapped(values: array) -> array:
    copy = array("f", values)
    copy.byteswap()
    return copy


def member_name(rule: str, d_prime: float, seed: int) -> str:
    """File stem of one replicate: `<rule>[-d<d'>]-s<seed>`."""
    tag = f"-d{d_prime:g}" if rule == "monotone" else ""
    return f"{rule}{tag}-s{seed}"


def write_member(folder: Path, rule: str, d_prime: float, seed: int, sizes: dict, n_per_subject: int,
                 length: int = 256, sfreq: float = 128.0) -> dict:
    values, meta = generate(rule, d_prime, seed, sizes, n_per_subject, length, sfreq)
    stem = member_name(rule, d_prime, seed)
    folder.mkdir(parents=True, exist_ok=True)
    meta["sha256"] = write_npy(folder / f"{stem}.npy", values, meta["shape"])
    meta["file"] = f"{stem}.npy"
    (folder / f"{stem}.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return meta
