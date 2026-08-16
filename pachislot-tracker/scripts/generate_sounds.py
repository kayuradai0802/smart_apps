#!/usr/bin/env python3
"""
パチスロ風の効果音・BGMをオリジナルに音声合成して生成するスクリプト。

特定の実機のサウンド（著作権のある音源）を録音・複製するのではなく、
NumPy による波形合成でそれらしい雰囲気の音を一から作り、WAV -> MP3 に
変換して書き出す。私用の作業用サウンド素材として利用する目的。

使い方:
    python3 scripts/generate_sounds.py

出力先:
    public/sounds/generated/*.mp3
"""

from __future__ import annotations

import math
import os
import subprocess
import wave
from dataclasses import dataclass

import numpy as np

SR = 44100
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "sounds", "generated")

# ---------------------------------------------------------------------------
# 基本波形・エンベロープ
# ---------------------------------------------------------------------------

def t_axis(duration: float) -> np.ndarray:
    return np.linspace(0, duration, int(SR * duration), endpoint=False)


def sine(freq: float, duration: float, phase: float = 0.0) -> np.ndarray:
    t = t_axis(duration)
    return np.sin(2 * math.pi * freq * t + phase)


def square(freq: float, duration: float, duty: float = 0.5) -> np.ndarray:
    t = t_axis(duration)
    frac = np.mod(freq * t, 1.0)
    return np.where(frac < duty, 1.0, -1.0)


def triangle(freq: float, duration: float) -> np.ndarray:
    t = t_axis(duration)
    frac = np.mod(freq * t, 1.0)
    return 2 * np.abs(2 * frac - 1) - 1


def sawtooth(freq: float, duration: float) -> np.ndarray:
    t = t_axis(duration)
    frac = np.mod(freq * t, 1.0)
    return 2 * frac - 1


def white_noise(duration: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, int(SR * duration))


def exp_decay(duration: float, tau: float) -> np.ndarray:
    t = t_axis(duration)
    return np.exp(-t / tau)


def adsr(duration: float, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    n = int(SR * duration)
    a = max(1, int(SR * attack))
    d = max(1, int(SR * decay))
    r = max(1, int(SR * release))
    s = max(0, n - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1, a, endpoint=False),
        np.linspace(1, sustain, d, endpoint=False),
        np.full(s, sustain),
        np.linspace(sustain, 0, r),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n]


def bandpass(signal: np.ndarray, low: float, high: float) -> np.ndarray:
    """簡易 FFT バンドパスフィルタ。"""
    spec = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1 / SR)
    mask = (freqs >= low) & (freqs <= high)
    spec = spec * mask
    return np.fft.irfft(spec, n=len(signal))


def lowpass(signal: np.ndarray, cutoff: float) -> np.ndarray:
    return bandpass(signal, 0, cutoff)


def mix(*layers: np.ndarray, weights: list[float] | None = None) -> np.ndarray:
    length = max(len(x) for x in layers)
    out = np.zeros(length)
    for i, layer in enumerate(layers):
        w = 1.0 if weights is None else weights[i]
        out[: len(layer)] += layer * w
    return out


def normalize(signal: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = np.max(np.abs(signal)) if len(signal) else 0
    if m == 0:
        return signal
    return signal / m * peak


def fade_edges(signal: np.ndarray, fade_s: float = 0.005) -> np.ndarray:
    n = int(SR * fade_s)
    if n <= 0 or n * 2 >= len(signal):
        return signal
    win = np.ones(len(signal))
    win[:n] = np.linspace(0, 1, n)
    win[-n:] = np.linspace(1, 0, n)
    return signal * win


NOTE_FREQS = {
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00,
    "A4": 440.00, "B4": 493.88,
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46, "G5": 783.99,
    "A5": 880.00, "B5": 987.77,
    "C6": 1046.50, "D6": 1174.66, "E6": 1318.51, "G6": 1567.98,
}


# ---------------------------------------------------------------------------
# WAV 書き出し / MP3 変換
# ---------------------------------------------------------------------------

def write_wav(path: str, signal: np.ndarray) -> None:
    signal = np.clip(signal, -1.0, 1.0)
    pcm = (signal * 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def wav_to_mp3(wav_path: str, mp3_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
         "-codec:a", "libmp3lame", "-qscale:a", "3", mp3_path],
        check=True,
    )


def export(name: str, signal: np.ndarray) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    wav_path = os.path.join(OUT_DIR, f"{name}.wav")
    mp3_path = os.path.join(OUT_DIR, f"{name}.mp3")
    write_wav(wav_path, normalize(fade_edges(signal)))
    wav_to_mp3(wav_path, mp3_path)
    os.remove(wav_path)
    print(f"generated {mp3_path}")


# ---------------------------------------------------------------------------
# 個別サウンドの合成
# ---------------------------------------------------------------------------

def make_coin_insert() -> np.ndarray:
    """メダル投入音: 高域の金属的な「チン」。"""
    partials = [3100, 4650, 6200, 8100]
    layers = [sine(f, 0.25) * exp_decay(0.25, 0.05) for f in partials]
    click = white_noise(0.01) * exp_decay(0.01, 0.003)
    body = mix(*layers, weights=[1.0, 0.6, 0.4, 0.25])
    return mix(body, np.pad(click, (0, len(body) - len(click))), weights=[0.8, 0.6])


def make_coin_payout(n_coins: int = 8) -> np.ndarray:
    """メダル払い出し音: メダル投入音を不規則な間隔で連打。"""
    rng = np.random.default_rng(42)
    total = 1.6
    out = np.zeros(int(SR * total))
    single = make_coin_insert()
    t = 0.0
    for i in range(n_coins):
        idx = int(SR * t)
        end = min(len(out), idx + len(single))
        out[idx:end] += single[: end - idx] * rng.uniform(0.7, 1.0)
        t += rng.uniform(0.04, 0.09)
    return out


def make_reel_spin_loop(duration: float = 2.0) -> np.ndarray:
    """リール回転音のループ: フィルタしたノイズ + 周期的なノッチ音。"""
    noise = bandpass(white_noise(duration, seed=7), 150, 900)
    hum = sine(90, duration) * 0.15
    # リールのコマ送りっぽい周期的なティック
    tick_hz = 14.0
    t = t_axis(duration)
    tick_env = (np.mod(t * tick_hz, 1.0) < 0.08).astype(float)
    tick = bandpass(white_noise(duration, seed=11), 800, 2500) * tick_env
    sig = mix(noise, hum, tick, weights=[0.5, 1.0, 0.6])
    return sig * 0.6


def make_reel_stop() -> np.ndarray:
    """リール停止音: 低音の「ガコン」。"""
    thud = sine(85, 0.15) * exp_decay(0.15, 0.03)
    thud2 = sine(140, 0.1) * exp_decay(0.1, 0.02)
    clack = bandpass(white_noise(0.05), 500, 3000) * exp_decay(0.05, 0.01)
    return mix(thud, thud2, clack, weights=[1.0, 0.5, 0.7])


def make_lever_click() -> np.ndarray:
    """スタートレバー操作音。"""
    click = bandpass(white_noise(0.03), 1500, 5000) * exp_decay(0.03, 0.006)
    tick = sine(2200, 0.02) * exp_decay(0.02, 0.004)
    return mix(click, tick, weights=[0.9, 0.5])


def make_button_beep() -> np.ndarray:
    """ボタン押下ビープ。"""
    return square(1800, 0.06) * adsr(0.06, 0.002, 0.02, 0.3, 0.03) * 0.5


def arpeggio(notes: list[str], note_dur: float, wave_fn=square) -> np.ndarray:
    segs = []
    for n in notes:
        freq = NOTE_FREQS[n]
        env = adsr(note_dur, 0.005, 0.03, 0.6, note_dur * 0.4)
        segs.append(wave_fn(freq, note_dur) * env)
    return np.concatenate(segs)


def make_bonus_chance_jingle() -> np.ndarray:
    """チャンス目/ボーナス告知風の短い上昇アルペジオ。"""
    notes = ["C5", "E5", "G5", "C6", "G5", "C6"]
    lead = arpeggio(notes, 0.09, wave_fn=square)
    sparkle = bandpass(white_noise(len(lead) / SR, seed=3), 4000, 9000) * exp_decay(len(lead) / SR, 0.2) * 0.15
    return mix(lead, sparkle, weights=[0.5, 1.0])


def make_big_win_fanfare() -> np.ndarray:
    """大当り/ビッグボーナス風ファンファーレ。"""
    melody = arpeggio(
        ["C5", "E5", "G5", "C6", "G5", "E5", "C6", "E6", "G6"],
        0.12,
        wave_fn=square,
    )
    harmony = arpeggio(
        ["C4", "E4", "G4", "C5", "G4", "E4", "C5", "E5", "G5"],
        0.12,
        wave_fn=triangle,
    ) * 0.5
    dur = len(melody) / SR
    coin_tail = make_coin_payout(14)
    fanfare = mix(melody, harmony, weights=[1.0, 1.0])
    return mix(fanfare, np.pad(coin_tail, (int(SR * dur * 0.6), 0)), weights=[1.0, 0.7])


def make_reg_win_fanfare() -> np.ndarray:
    """小役/レギュラーボーナス風の短いファンファーレ。"""
    melody = arpeggio(["E5", "G5", "C6"], 0.09, wave_fn=square)
    return melody * 0.8


# ---------------------------------------------------------------------------
# BGM ループ（簡易シーケンサー）
# ---------------------------------------------------------------------------

@dataclass
class Step:
    note: str | None  # None = 休符
    beats: float


def render_track(steps: list[Step], bpm: float, wave_fn, octave_shift: int = 0, gain: float = 1.0) -> np.ndarray:
    beat_dur = 60.0 / bpm
    out = []
    for step in steps:
        dur = step.beats * beat_dur
        if step.note is None:
            out.append(np.zeros(int(SR * dur)))
            continue
        freq = NOTE_FREQS[step.note] * (2 ** octave_shift)
        env = adsr(dur, 0.004, dur * 0.15, 0.5, dur * 0.25)
        out.append(wave_fn(freq, dur) * env * gain)
    return np.concatenate(out) if out else np.zeros(0)


def hihat_track(n_steps: int, bpm: float, gain: float = 0.2) -> np.ndarray:
    beat_dur = 60.0 / bpm
    step_dur = beat_dur / 2
    out = []
    for i in range(n_steps):
        hat = bandpass(white_noise(step_dur, seed=100 + i), 4000, 12000) * exp_decay(step_dur, step_dur * 0.15)
        out.append(hat * gain)
    return np.concatenate(out)


def make_bgm_loop(bpm: float, seed_tag: str) -> np.ndarray:
    lead_notes = ["C5", "E5", "G5", "E5", "F5", "A5", "G5", "E5",
                   "C5", "D5", "E5", "G5", "D5", "F5", "E5", "C5"]
    lead = render_track([Step(n, 0.5) for n in lead_notes], bpm, square, gain=0.35)

    bass_notes = ["C4", "C4", "G4", "G4", "A4", "A4", "F4", "F4"]
    bass = render_track([Step(n, 1.0) for n in bass_notes], bpm, triangle, octave_shift=-1, gain=0.45)

    n_steps = int(len(lead_notes) / 2)
    hats = hihat_track(n_steps, bpm)

    length = max(len(lead), len(bass), len(hats))
    lead = np.pad(lead, (0, length - len(lead)))
    bass = np.pad(bass, (0, length - len(bass)))
    hats = np.pad(hats, (0, length - len(hats)))
    return mix(lead, bass, hats, weights=[1.0, 1.0, 1.0]) * 0.7


def make_bgm_normal_loop() -> np.ndarray:
    return make_bgm_loop(bpm=118, seed_tag="normal")


def make_bgm_bonus_loop() -> np.ndarray:
    """ボーナス中風の少しテンポの速い派手なループ。"""
    base = make_bgm_loop(bpm=150, seed_tag="bonus")
    sparkle = bandpass(white_noise(len(base) / SR, seed=55), 5000, 10000) * 0.05
    return mix(base, sparkle)


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    export("coin_insert", make_coin_insert())
    export("coin_payout", make_coin_payout())
    export("reel_spin_loop", make_reel_spin_loop())
    export("reel_stop", make_reel_stop())
    export("lever_click", make_lever_click())
    export("button_beep", make_button_beep())
    export("bonus_chance_jingle", make_bonus_chance_jingle())
    export("big_win_fanfare", make_big_win_fanfare())
    export("reg_win_fanfare", make_reg_win_fanfare())
    export("bgm_normal_loop", make_bgm_normal_loop())
    export("bgm_bonus_loop", make_bgm_bonus_loop())


if __name__ == "__main__":
    main()
