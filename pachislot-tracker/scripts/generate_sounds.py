#!/usr/bin/env python3
"""
パチスロ風の効果音・BGMをオリジナルに音声合成して生成するスクリプト。

特定の実機のサウンド（著作権のある音源）を録音・複製するのではなく、
NumPy による波形合成でそれらしい雰囲気の音を一から作り、WAV -> MP3 に
変換して書き出す。私用の作業用サウンド素材として利用する目的。

音を「重厚」にするために以下を重ねている:
- ユニゾン（デチューンした複数波形の重ね合わせ = コーラス感）
- 倍音を積んだ加算合成（ベル/ブラス風のトーン）
- サブベース（1オクターブ下の正弦波）で低域の厚み
- 疑似リバーブ（合成インパルス応答との畳み込み）で空間の広がり
- ソフトサチュレーション（tanh）でアナログ的な温かみ・音の「糊」
- ハース効果によるステレオ化

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


def rich_lead_wave(freq: float, duration: float) -> np.ndarray:
    """矩形波+ノコギリ波をブレンドした、芯としゃりの両方を持つリード波形。"""
    return 0.6 * square(freq, duration) + 0.4 * sawtooth(freq, duration)


def rich_bass_wave(freq: float, duration: float) -> np.ndarray:
    """三角波+デューティ狭めの矩形波で太さを出すベース波形。"""
    return 0.55 * triangle(freq, duration) + 0.45 * square(freq, duration, duty=0.3)


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


def smooth_bandpass(signal: np.ndarray, low: float, high: float, roll: float = 0.25) -> np.ndarray:
    """コサイン状のロールオフを持つバンドパス（ブリックウォールによるリンギングを回避）。"""
    n = len(signal)
    spec = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    roll_low = max(low * roll, 1.0)
    roll_high = max(high * roll, 1.0)
    mask = np.where(
        freqs < low - roll_low, 0.0,
        np.where(
            freqs < low, (freqs - (low - roll_low)) / roll_low,
            np.where(
                freqs < high, 1.0,
                np.where(freqs < high + roll_high, 1 - (freqs - high) / roll_high, 0.0),
            ),
        ),
    )
    mask = np.clip(mask, 0.0, 1.0)
    return np.fft.irfft(spec * mask, n=n)


def smooth_lowpass(signal: np.ndarray, cutoff: float, roll_frac: float = 0.3) -> np.ndarray:
    n = len(signal)
    spec = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    roll = max(cutoff * roll_frac, 1.0)
    mask = np.where(freqs < cutoff, 1.0, np.where(freqs < cutoff + roll, 1 - (freqs - cutoff) / roll, 0.0))
    mask = np.clip(mask, 0.0, 1.0)
    return np.fft.irfft(spec * mask, n=n)


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


def soft_clip(signal: np.ndarray, drive: float = 1.4) -> np.ndarray:
    """tanh によるソフトサチュレーション。倍音を足して音を太く・温かくする。"""
    return np.tanh(signal * drive) / np.tanh(drive)


NOTE_FREQS = {
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00,
    "A4": 440.00, "B4": 493.88,
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46, "G5": 783.99,
    "A5": 880.00, "B5": 987.77,
    "C6": 1046.50, "D6": 1174.66, "E6": 1318.51, "G6": 1567.98,
}


# ---------------------------------------------------------------------------
# ユニゾン（コーラス）/ 加算合成
# ---------------------------------------------------------------------------

def unison_wave(freq: float, duration: float, wave_fn, voices: int = 3, detune_cents: float = 10.0) -> np.ndarray:
    """複数のデチューンした声部を重ねて厚みを出す（スーパーソウ的手法）。"""
    out = np.zeros(int(SR * duration))
    for i in range(voices):
        frac = (i / (voices - 1) - 0.5) if voices > 1 else 0.0
        detuned = freq * (2 ** (frac * 2 * detune_cents / 1200))
        voice = wave_fn(detuned, duration)
        out[: len(voice)] += voice
    return out / voices


def brass_tone(freq: float, duration: float, voices: int = 3, detune_cents: float = 9.0,
               vibrato_rate: float = 5.5, vibrato_depth: float = 0.008) -> np.ndarray:
    """倍音を積んだ加算合成 + デチューン + ビブラートによるブラス風の厚いトーン。"""
    t = t_axis(duration)
    n = len(t)
    vibrato = 1.0 + vibrato_depth * np.sin(2 * math.pi * vibrato_rate * t)
    harmonics = [1, 2, 3, 4, 5]
    amps = [1.0, 0.55, 0.35, 0.2, 0.1]
    amp_sum = sum(amps)
    out = np.zeros(n)
    for v in range(voices):
        frac = (v / (voices - 1) - 0.5) if voices > 1 else 0.0
        detune_mult = 2 ** (frac * 2 * detune_cents / 1200)
        inst_freq = freq * detune_mult * vibrato
        phase = 2 * math.pi * np.cumsum(inst_freq) / SR
        for h, a in zip(harmonics, amps):
            out += a * np.sin(phase * h)
    return out / (voices * amp_sum)


def bell_tone(freq: float, duration: float) -> np.ndarray:
    """非整数倍音を使ったベル/金属的なトーン。"""
    partials = [1.0, 2.0, 2.76, 4.07, 5.4]
    amps = [1.0, 0.55, 0.35, 0.2, 0.12]
    t = t_axis(duration)
    out = np.zeros(len(t))
    for p, a in zip(partials, amps):
        tau = max(0.3 / max(p * 0.6, 1.0), 0.05)
        out += a * np.sin(2 * math.pi * freq * p * t) * np.exp(-t / tau)
    return out / sum(amps)


def make_pad(chord_notes: list[str], duration: float, voices: int = 5, detune_cents: float = 10.0,
             cutoff: float = 2200.0) -> np.ndarray:
    """デチューンしたノコギリ波を積んだサステインパッド（下敷きの厚み）。"""
    layers = [unison_wave(NOTE_FREQS[n], duration, sawtooth, voices=voices, detune_cents=detune_cents)
              for n in chord_notes]
    pad = mix(*layers, weights=[1.0] * len(layers))
    pad = smooth_lowpass(pad, cutoff)
    env = adsr(duration, attack=duration * 0.18, decay=duration * 0.1, sustain=0.8, release=duration * 0.25)
    return pad * env / len(chord_notes)


# ---------------------------------------------------------------------------
# 疑似リバーブ
# ---------------------------------------------------------------------------

def make_ir(duration: float, decay_tau: float, seed: int, low: float = 250.0, high: float = 8000.0) -> np.ndarray:
    """減衰させたフィルタ済みノイズによる、合成リバーブ・インパルス応答。"""
    noise = white_noise(duration, seed=seed)
    ir = noise * exp_decay(duration, decay_tau)
    ir = smooth_bandpass(ir, low, high)
    peak = np.max(np.abs(ir))
    return ir / peak if peak > 0 else ir


def fft_convolve(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = len(a) + len(b) - 1
    spec = np.fft.rfft(a, n) * np.fft.rfft(b, n)
    return np.fft.irfft(spec, n=n)


def apply_reverb(signal: np.ndarray, ir: np.ndarray, mix_amount: float = 0.3) -> np.ndarray:
    """単発サウンド用: 尾を伸ばす線形畳み込みリバーブ。"""
    wet = fft_convolve(signal, ir)
    wet_peak = np.max(np.abs(wet))
    dry_peak = np.max(np.abs(signal)) if len(signal) else 0
    if wet_peak > 0:
        wet = wet / wet_peak * dry_peak
    dry = np.pad(signal, (0, len(wet) - len(signal)))
    return dry * (1 - mix_amount) + wet * mix_amount


def apply_reverb_circular(signal: np.ndarray, ir: np.ndarray, mix_amount: float = 0.25) -> np.ndarray:
    """ループ素材用: 長さを変えない循環畳み込みリバーブ（尾が先頭に自然に回り込みシームレスなまま残響を足せる）。"""
    n = len(signal)
    ir_padded = np.zeros(n)
    length = min(len(ir), n)
    ir_padded[:length] = ir[:length]
    wet = np.fft.irfft(np.fft.rfft(signal) * np.fft.rfft(ir_padded), n=n)
    wet_peak = np.max(np.abs(wet))
    dry_peak = np.max(np.abs(signal)) if n else 0
    if wet_peak > 0:
        wet = wet / wet_peak * dry_peak
    return signal * (1 - mix_amount) + wet * mix_amount


ROOM_IR = make_ir(0.7, 0.22, seed=901, low=250, high=9000)
HALL_IR = make_ir(2.6, 0.9, seed=902, low=150, high=7000)


# ---------------------------------------------------------------------------
# ステレオ化 / 仕上げ / 書き出し
# ---------------------------------------------------------------------------

def to_stereo(mono: np.ndarray, width_ms: float = 14.0) -> np.ndarray:
    """ハース効果（片チャンネルを数ミリ秒遅らせる）で自然な広がりを持たせる。"""
    d = int(SR * width_ms / 1000)
    left = mono.copy()
    right = np.zeros_like(mono)
    if 0 < d < len(mono):
        right[d:] = mono[: len(mono) - d]
    else:
        right = mono.copy()
    right = smooth_lowpass(right, 11000)
    return np.stack([left, right * 0.96])


def normalize_stereo(stereo: np.ndarray, peak: float = 0.92) -> np.ndarray:
    m = np.max(np.abs(stereo))
    if m == 0:
        return stereo
    return stereo / m * peak


def fade_edges_stereo(stereo: np.ndarray, fade_s: float = 0.008) -> np.ndarray:
    n = int(SR * fade_s)
    if n <= 0 or n * 2 >= stereo.shape[1]:
        return stereo
    win = np.ones(stereo.shape[1])
    win[:n] = np.linspace(0, 1, n)
    win[-n:] = np.linspace(1, 0, n)
    return stereo * win


def finalize(signal: np.ndarray, reverb_ir: np.ndarray | None = None, reverb_mix: float = 0.25,
             loop: bool = False, width_ms: float = 14.0, saturate: float = 1.15) -> np.ndarray:
    sig = soft_clip(signal, saturate) if saturate else signal
    if reverb_ir is not None:
        sig = apply_reverb_circular(sig, reverb_ir, reverb_mix) if loop else apply_reverb(sig, reverb_ir, reverb_mix)
    stereo = to_stereo(sig, width_ms=width_ms)
    if not loop:
        stereo = fade_edges_stereo(stereo)
    return normalize_stereo(stereo)


def write_wav(path: str, stereo: np.ndarray) -> None:
    stereo = np.clip(stereo, -1.0, 1.0)
    interleaved = np.empty(stereo.shape[1] * 2, dtype=np.int16)
    interleaved[0::2] = (stereo[0] * 32767).astype(np.int16)
    interleaved[1::2] = (stereo[1] * 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(interleaved.tobytes())


def wav_to_mp3(wav_path: str, mp3_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
         "-codec:a", "libmp3lame", "-b:a", "192k", mp3_path],
        check=True,
    )


def export(name: str, signal: np.ndarray, *, reverb_ir: np.ndarray | None = ROOM_IR, reverb_mix: float = 0.22,
           loop: bool = False, width_ms: float = 14.0, saturate: float = 1.15) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    wav_path = os.path.join(OUT_DIR, f"{name}.wav")
    mp3_path = os.path.join(OUT_DIR, f"{name}.mp3")
    stereo = finalize(signal, reverb_ir=reverb_ir, reverb_mix=reverb_mix, loop=loop, width_ms=width_ms, saturate=saturate)
    write_wav(wav_path, stereo)
    wav_to_mp3(wav_path, mp3_path)
    os.remove(wav_path)
    print(f"generated {mp3_path}")


# ---------------------------------------------------------------------------
# 打楽器（BGM のドラムバス用）
# ---------------------------------------------------------------------------

def make_kick(duration: float = 0.28) -> np.ndarray:
    t = t_axis(duration)
    freq_env = 150 * np.exp(-t / 0.045) + 45
    phase = 2 * math.pi * np.cumsum(freq_env) / SR
    body = np.sin(phase) * exp_decay(duration, 0.11)
    click = white_noise(0.006, seed=501)
    click = np.pad(click, (0, len(t) - len(click))) * exp_decay(duration, 0.004)
    return soft_clip(body * 1.1 + click * 0.6, 1.3)


def make_snare(duration: float = 0.18) -> np.ndarray:
    tone = sine(190, duration) * exp_decay(duration, 0.05) * 0.5
    noise = smooth_bandpass(white_noise(duration, seed=502), 1200, 9000) * exp_decay(duration, 0.08)
    return soft_clip(tone + noise * 1.1, 1.2)


def make_hat(duration: float = 0.05, seed: int = 0, open_: bool = False) -> np.ndarray:
    tau = 0.22 if open_ else 0.035
    return smooth_bandpass(white_noise(duration, seed=seed), 6000, 14000) * exp_decay(duration, tau)


def build_drum_bus(total_beats: int, bpm: float) -> np.ndarray:
    """キック(1,3拍)+スネア(2,4拍)+8分ハットのフルなドラムバス。"""
    beat_dur = 60.0 / bpm
    n = int(SR * total_beats * beat_dur)
    bus = np.zeros(n)

    def place(sig: np.ndarray, beat_pos: float, gain: float = 1.0) -> None:
        idx = int(SR * beat_pos * beat_dur)
        end = min(n, idx + len(sig))
        if end > idx:
            bus[idx:end] += sig[: end - idx] * gain

    kick = make_kick()
    snare = make_snare()
    for b in range(0, total_beats, 2):
        place(kick, b, 0.9)
    for b in range(1, total_beats, 2):
        place(snare, b, 0.75)

    step_dur = 0.5
    steps = int(total_beats / step_dur)
    for i in range(steps):
        open_ = (i % 4 == 3)
        hat = make_hat(seed=600 + i, open_=open_) * (0.16 if not open_ else 0.11)
        place(hat, i * step_dur)
    return bus


# ---------------------------------------------------------------------------
# 個別サウンドの合成
# ---------------------------------------------------------------------------

def make_coin_insert() -> np.ndarray:
    """メダル投入音: 非整数倍音を重ねた金属的な「チン」+ 低めのボディ音。"""
    partials = [1.0, 1.5, 2.24, 3.1, 4.65, 6.2]
    amps = [1.0, 0.75, 0.55, 0.4, 0.28, 0.16]
    base = 2050.0
    layers = [sine(base * p, 0.32) * exp_decay(0.32, 0.06 / max(p * 0.5, 1)) for p in partials]
    body = mix(*layers, weights=amps)
    thunk = sine(520, 0.06) * exp_decay(0.06, 0.02) * 0.3
    click = white_noise(0.01, seed=11) * exp_decay(0.01, 0.003)
    return mix(body, thunk, np.pad(click, (0, len(body) - len(click))), weights=[0.85, 1.0, 0.6])


def make_coin_payout(n_coins: int = 10) -> np.ndarray:
    """メダル払い出し音: メダル投入音を不規則な間隔で連打し、厚みのある「ジャラジャラ」に。"""
    rng = np.random.default_rng(42)
    total = 1.8
    out = np.zeros(int(SR * total))
    single = make_coin_insert()
    t = 0.0
    for i in range(n_coins):
        idx = int(SR * t)
        end = min(len(out), idx + len(single))
        out[idx:end] += single[: end - idx] * rng.uniform(0.65, 1.0)
        t += rng.uniform(0.035, 0.085)
    return out


def make_reel_spin_loop(duration: float = 2.4) -> np.ndarray:
    """リール回転音のループ: フィルタしたノイズ + サブの唸り + 周期的なノッチ音（2層）。"""
    noise = smooth_bandpass(white_noise(duration, seed=7), 150, 900)
    noise2 = smooth_bandpass(white_noise(duration, seed=71), 300, 1400) * 0.4
    hum = sine(88, duration) * 0.18
    tick_hz = 14.0
    t = t_axis(duration)
    tick_env = (np.mod(t * tick_hz, 1.0) < 0.08).astype(float)
    tick = smooth_bandpass(white_noise(duration, seed=11), 800, 2600) * tick_env
    tick2 = smooth_bandpass(white_noise(duration, seed=12), 1800, 4000) * tick_env * 0.4
    sig = mix(noise, noise2, hum, tick, tick2, weights=[0.5, 0.35, 1.0, 0.6, 0.4])
    return sig * 0.6


def make_reel_stop() -> np.ndarray:
    """リール停止音: サブベースを効かせた低音の「ガコン」。"""
    sub = sine(55, 0.16) * exp_decay(0.16, 0.035) * 0.6
    thud = sine(85, 0.15) * exp_decay(0.15, 0.03)
    thud2 = sine(140, 0.1) * exp_decay(0.1, 0.02)
    clack = smooth_bandpass(white_noise(0.05, seed=21), 500, 3000) * exp_decay(0.05, 0.01)
    return soft_clip(mix(sub, thud, thud2, clack, weights=[1.0, 1.0, 0.5, 0.7]), 1.25)


def make_lever_click() -> np.ndarray:
    """スタートレバー操作音。"""
    click = smooth_bandpass(white_noise(0.03, seed=31), 1500, 5000) * exp_decay(0.03, 0.006)
    tick = sine(2200, 0.02) * exp_decay(0.02, 0.004)
    body = sine(340, 0.03) * exp_decay(0.03, 0.008) * 0.3
    return mix(click, tick, body, weights=[0.9, 0.5, 1.0])


def make_button_beep() -> np.ndarray:
    """ボタン押下ビープ（2声ユニゾン + 倍音）。"""
    fund = unison_wave(1800, 0.07, square, voices=2, detune_cents=5)
    harmonic = sine(3600, 0.07) * 0.2
    return mix(fund, harmonic, weights=[1.0, 1.0]) * adsr(0.07, 0.002, 0.02, 0.35, 0.035) * 0.55


def brass_arpeggio(notes: list[str], note_dur: float, voices: int = 3) -> np.ndarray:
    segs = []
    for n in notes:
        freq = NOTE_FREQS[n]
        tone = brass_tone(freq, note_dur, voices=voices)
        env = adsr(note_dur, 0.008, 0.05, 0.7, note_dur * 0.35)
        segs.append(tone * env)
    return np.concatenate(segs)


def bell_arpeggio(notes: list[str], note_dur: float) -> np.ndarray:
    segs = []
    for n in notes:
        freq = NOTE_FREQS[n]
        segs.append(bell_tone(freq, note_dur))
    return np.concatenate(segs)


def make_bonus_chance_jingle() -> np.ndarray:
    """チャンス目/ボーナス告知風の短い上昇アルペジオ（ベル+パッド+きらめき）。"""
    notes = ["C5", "E5", "G5", "C6", "G5", "C6"]
    lead = bell_arpeggio(notes, 0.1)
    dur = len(lead) / SR
    pad = make_pad(["C4", "E4", "G4"], dur, voices=4, detune_cents=8, cutoff=1800) * 0.4
    sparkle = smooth_bandpass(white_noise(dur, seed=3), 4000, 9500) * exp_decay(dur, 0.22) * 0.18
    return mix(lead, pad, sparkle, weights=[1.0, 1.0, 1.0])


def make_impact_hit(duration: float = 0.5) -> np.ndarray:
    """ファンファーレ冒頭のインパクト（キック+クラッシュ）。"""
    kick = make_kick(min(duration, 0.28))
    kick = np.pad(kick, (0, int(SR * duration) - len(kick)))
    crash = smooth_bandpass(white_noise(duration, seed=77), 2500, 14000) * exp_decay(duration, 0.3)
    return soft_clip(kick * 1.1 + crash * 0.45, 1.3)


def make_big_win_fanfare() -> np.ndarray:
    """大当り/ビッグボーナス風ファンファーレ: ブラス風ユニゾン主旋律 + ハモリ + パッド + コインの雨。"""
    melody = brass_arpeggio(
        ["C5", "E5", "G5", "C6", "G5", "E5", "C6", "E6", "G6"], 0.13, voices=4,
    )
    harmony = brass_arpeggio(
        ["C4", "E4", "G4", "C5", "G4", "E4", "C5", "E5", "G5"], 0.13, voices=3,
    ) * 0.5
    dur = len(melody) / SR
    pad = make_pad(["C4", "E4", "G4"], dur, voices=5, detune_cents=10, cutoff=2600) * 0.35
    impact = make_impact_hit(0.5)
    fanfare = mix(melody, harmony, pad, weights=[1.0, 1.0, 1.0])
    fanfare = mix(fanfare, impact, weights=[1.0, 0.8])
    coin_tail = make_coin_payout(16)
    return mix(fanfare, np.pad(coin_tail, (int(SR * dur * 0.55), 0)), weights=[1.0, 0.6])


def make_reg_win_fanfare() -> np.ndarray:
    """小役/レギュラーボーナス風の短いファンファーレ（ブラス風ユニゾン + 軽いパッド）。"""
    melody = brass_arpeggio(["E5", "G5", "C6"], 0.1, voices=3)
    dur = len(melody) / SR
    pad = make_pad(["C4", "E4", "G4"], dur, voices=3, detune_cents=7, cutoff=2000) * 0.25
    return mix(melody, pad, weights=[1.0, 1.0]) * 0.85


# ---------------------------------------------------------------------------
# BGM ループ（簡易シーケンサー）
# ---------------------------------------------------------------------------

@dataclass
class Step:
    note: str | None  # None = 休符
    beats: float


def render_track(steps: list[Step], bpm: float, tone_fn, octave_shift: int = 0, gain: float = 1.0,
                  sub_gain: float = 0.0) -> np.ndarray:
    beat_dur = 60.0 / bpm
    out = []
    for step in steps:
        dur = step.beats * beat_dur
        if step.note is None:
            out.append(np.zeros(int(SR * dur)))
            continue
        freq = NOTE_FREQS[step.note] * (2 ** octave_shift)
        env = adsr(dur, 0.005, dur * 0.15, 0.5, dur * 0.25)
        tone = tone_fn(freq, dur) * env
        if sub_gain > 0:
            tone = tone + sine(freq / 2, dur) * env * sub_gain
        out.append(tone * gain)
    return np.concatenate(out) if out else np.zeros(0)


def make_bgm_loop(bpm: float, pad_chord: list[str], lead_gain: float, bass_gain: float,
                   drum_gain: float, lead_voices: int, bass_voices: int) -> np.ndarray:
    lead_notes = ["C5", "E5", "G5", "E5", "F5", "A5", "G5", "E5",
                   "C5", "D5", "E5", "G5", "D5", "F5", "E5", "C5"]
    lead_tone = lambda f, d: unison_wave(f, d, rich_lead_wave, voices=lead_voices, detune_cents=7)
    lead = render_track([Step(n, 0.5) for n in lead_notes], bpm, lead_tone, gain=lead_gain)

    bass_notes = ["C4", "C4", "G4", "G4", "A4", "A4", "F4", "F4"]
    bass_tone = lambda f, d: unison_wave(f, d, rich_bass_wave, voices=bass_voices, detune_cents=5)
    bass = render_track([Step(n, 1.0) for n in bass_notes], bpm, bass_tone, octave_shift=-1,
                         gain=bass_gain, sub_gain=0.35)

    total_beats = 8
    drums = build_drum_bus(total_beats, bpm) * drum_gain

    pad_duration = total_beats * (60.0 / bpm)
    pad = make_pad(pad_chord, pad_duration, voices=5, detune_cents=9, cutoff=1900) * 0.3

    length = max(len(lead), len(bass), len(drums), len(pad))
    lead = np.pad(lead, (0, length - len(lead)))
    bass = np.pad(bass, (0, length - len(bass)))
    drums = np.pad(drums, (0, length - len(drums)))
    pad = np.pad(pad, (0, length - len(pad)))
    return mix(lead, bass, drums, pad, weights=[1.0, 1.0, 1.0, 1.0])


def make_bgm_normal_loop() -> np.ndarray:
    return make_bgm_loop(bpm=118, pad_chord=["C4", "G4", "E4"], lead_gain=0.32, bass_gain=0.4,
                          drum_gain=1.0, lead_voices=2, bass_voices=2)


def make_bgm_bonus_loop() -> np.ndarray:
    """ボーナス中風の、テンポが速くユニゾンも厚い派手なループ。"""
    base = make_bgm_loop(bpm=150, pad_chord=["C4", "G4", "E4", "B4"], lead_gain=0.36, bass_gain=0.45,
                          drum_gain=1.15, lead_voices=3, bass_voices=3)
    sparkle = smooth_bandpass(white_noise(len(base) / SR, seed=55), 5000, 11000) * 0.06
    return mix(base, sparkle)


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    export("coin_insert", make_coin_insert(), reverb_mix=0.15, width_ms=9)
    export("coin_payout", make_coin_payout(), reverb_mix=0.18, width_ms=11)
    export("reel_spin_loop", make_reel_spin_loop(), loop=True, reverb_mix=0.12, width_ms=16)
    export("reel_stop", make_reel_stop(), reverb_mix=0.15, width_ms=8, saturate=1.3)
    export("lever_click", make_lever_click(), reverb_mix=0.08, width_ms=6)
    export("button_beep", make_button_beep(), reverb_mix=0.1, width_ms=6)
    export("bonus_chance_jingle", make_bonus_chance_jingle(), reverb_ir=HALL_IR, reverb_mix=0.3, width_ms=18)
    export("big_win_fanfare", make_big_win_fanfare(), reverb_ir=HALL_IR, reverb_mix=0.32, width_ms=22, saturate=1.25)
    export("reg_win_fanfare", make_reg_win_fanfare(), reverb_ir=HALL_IR, reverb_mix=0.25, width_ms=16)
    export("bgm_normal_loop", make_bgm_normal_loop(), loop=True, reverb_ir=HALL_IR, reverb_mix=0.16, width_ms=20, saturate=1.2)
    export("bgm_bonus_loop", make_bgm_bonus_loop(), loop=True, reverb_ir=HALL_IR, reverb_mix=0.18, width_ms=20, saturate=1.25)


if __name__ == "__main__":
    main()
