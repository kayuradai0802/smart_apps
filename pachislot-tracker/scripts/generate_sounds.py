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
PLATE_IR = make_ir(1.1, 0.32, seed=903, low=300, high=9500)


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


def normalize_stereo(stereo: np.ndarray, peak: float = 0.85) -> np.ndarray:
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
           loop: bool = False, width_ms: float = 14.0, saturate: float = 1.15,
           already_stereo: bool = False) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    wav_path = os.path.join(OUT_DIR, f"{name}.wav")
    mp3_path = os.path.join(OUT_DIR, f"{name}.mp3")
    if already_stereo:
        # 呼び出し側でステレオバスを組み立て済み（EDM 系ループなど）: サチュレーション + 正規化のみ行う。
        stereo = soft_clip(signal, saturate) if saturate else signal
        if not loop:
            stereo = fade_edges_stereo(stereo)
        stereo = normalize_stereo(stereo)
    else:
        stereo = finalize(signal, reverb_ir=reverb_ir, reverb_mix=reverb_mix, loop=loop, width_ms=width_ms, saturate=saturate)
    write_wav(wav_path, stereo)
    wav_to_mp3(wav_path, mp3_path)
    os.remove(wav_path)
    print(f"generated {mp3_path}")


# ---------------------------------------------------------------------------
# EDM/トランス系ヘルパー（動的フィルタ・サイドチェイン・ディレイ）
# ---------------------------------------------------------------------------

def time_varying_filter(signal: np.ndarray, filter_fn, chunk_ms: float = 25.0) -> np.ndarray:
    """短いチャンクに分けて overlap-add することで、時間変化するフィルタ（ワブル/ライザー等）を実現する。"""
    n = len(signal)
    chunk = max(64, int(SR * chunk_ms / 1000))
    hop = chunk // 2
    window = np.hanning(chunk)
    out = np.zeros(n + chunk)
    norm = np.zeros(n + chunk)
    pos = 0
    while pos < n:
        seg = signal[pos:pos + chunk]
        if len(seg) < chunk:
            seg = np.pad(seg, (0, chunk - len(seg)))
        filtered = filter_fn(seg, pos / SR)
        out[pos:pos + chunk] += filtered * window
        norm[pos:pos + chunk] += window
        pos += hop
    norm[norm == 0] = 1.0
    return (out / norm)[:n]


def time_varying_lowpass(signal: np.ndarray, cutoff_fn, chunk_ms: float = 25.0) -> np.ndarray:
    return time_varying_filter(signal, lambda seg, t: smooth_lowpass(seg, cutoff_fn(t)), chunk_ms=chunk_ms)


def time_varying_bandpass(signal: np.ndarray, low_fn, high_fn, chunk_ms: float = 25.0) -> np.ndarray:
    return time_varying_filter(signal, lambda seg, t: smooth_bandpass(seg, low_fn(t), high_fn(t)), chunk_ms=chunk_ms)


def pluck_wave(freq: float, duration: float, voices: int = 5, detune_cents: float = 14.0) -> np.ndarray:
    """トランス系の「プラック」音: スーパーソウに、明るく開いて素早く閉じるフィルターエンベロープを掛ける。"""
    raw = unison_wave(freq, duration, sawtooth, voices=voices, detune_cents=detune_cents)
    decay_tau = max(duration * 0.35, 0.03)
    return time_varying_lowpass(raw, lambda t: 7000 * math.exp(-t / decay_tau) + 700)


def wobble_bass(freq: float, duration: float, lfo_hz: float = 4.0, cutoff_base: float = 350.0,
                 cutoff_range: float = 900.0, voices: int = 3) -> np.ndarray:
    """LFO でローパスのカットオフを揺らす EDM 的なうねりベース。"""
    raw = unison_wave(freq, duration, sawtooth, voices=voices, detune_cents=6)
    return time_varying_lowpass(
        raw, lambda t: cutoff_base + cutoff_range * (0.5 + 0.5 * math.sin(2 * math.pi * lfo_hz * t)),
    )


def sidechain_env(n_samples: int, bpm: float, hit_beats: list[float], depth: float = 0.65,
                   release_beats: float = 0.4, attack_s: float = 0.004) -> np.ndarray:
    """キックに合わせて他レイヤーを一瞬ダッキングさせる「ポンピング」エンベロープ。"""
    beat_dur = 60.0 / bpm
    env = np.ones(n_samples)
    attack_n = max(1, int(SR * attack_s))
    release_n = max(1, int(SR * release_beats * beat_dur))
    for b in hit_beats:
        idx = int(SR * b * beat_dur)
        if idx >= n_samples:
            continue
        dip_end = min(n_samples, idx + attack_n)
        rec_end = min(n_samples, idx + attack_n + release_n)
        if dip_end > idx:
            env[idx:dip_end] = np.linspace(1.0, 1 - depth, dip_end - idx)
        if rec_end > dip_end:
            env[dip_end:rec_end] = np.linspace(1 - depth, 1.0, rec_end - dip_end)
    return env


def ping_pong_echo(mono: np.ndarray, delay_s: float = 0.18, feedback: float = 0.4, taps: int = 5,
                    lowpass_start: float = 7000.0) -> np.ndarray:
    """左右交互にこだまするピンポンディレイ（ウェット成分のみを返す。ドライとは呼び出し側で合成する）。"""
    d = max(1, int(SR * delay_s))
    n = len(mono) + d * (taps + 1)
    left = np.zeros(n)
    right = np.zeros(n)
    side_right = True
    pos = d
    amp = 1.0
    for i in range(taps):
        amp *= feedback
        cutoff = max(800.0, lowpass_start - i * 900)
        tap = smooth_lowpass(mono, cutoff) * amp
        bus = right if side_right else left
        end = min(n, pos + len(tap))
        if end > pos:
            bus[pos:end] += tap[: end - pos]
        pos += d
        side_right = not side_right
    return np.stack([left, right])


def make_clap(duration: float = 0.22) -> np.ndarray:
    """複数のノイズバーストを重ねた EDM 的なクラップ音。"""
    n = int(SR * duration)
    out = np.zeros(n)
    for i, off in enumerate([0.0, 0.008, 0.016, 0.028]):
        idx = int(SR * off)
        burst_dur = 0.03
        burst = smooth_bandpass(white_noise(burst_dur, seed=700 + i), 1000, 8000) * exp_decay(burst_dur, 0.012)
        end = min(n, idx + len(burst))
        if end > idx:
            out[idx:end] += burst[: end - idx] * 0.8
    tail = smooth_bandpass(white_noise(duration, seed=709), 1200, 6000) * exp_decay(duration, 0.06)
    out += tail * 0.5
    return soft_clip(out, 1.3)


def gated_reverb(dry: np.ndarray, ir: np.ndarray, gate_s: float = 0.16, mix_amount: float = 0.5) -> np.ndarray:
    """80's/EDM 的なゲートリバーブ: 尾を短く強制的に切ってパンチを保ったまま空間感を足す。"""
    wet = fft_convolve(dry, ir)
    gate_n = int(SR * gate_s)
    if gate_n < len(wet):
        fade = min(int(SR * 0.01), len(wet) - gate_n)
        if fade > 0:
            wet[gate_n:gate_n + fade] *= np.linspace(1, 0, fade)
        wet[gate_n + fade:] = 0
    wet_peak = np.max(np.abs(wet))
    dry_peak = np.max(np.abs(dry)) if len(dry) else 0
    if wet_peak > 0:
        wet = wet / wet_peak * dry_peak
    dry_padded = np.pad(dry, (0, len(wet) - len(dry)))
    return dry_padded * (1 - mix_amount) + wet * mix_amount


def make_riser_buildup(duration: float = 1.6) -> np.ndarray:
    """ドロップ/ファンファーレ直前の緊張感を煽るライザー（上昇ノイズ+チャープ+着地インパクト）。"""
    noise = white_noise(duration, seed=808)
    swept = time_varying_bandpass(
        noise,
        lambda t: 200 + (t / duration) * 3000,
        lambda t: 1200 + (t / duration) * 9000,
    )
    t = t_axis(duration)
    rise_env = (t / duration) ** 1.5
    chirp_freq = 200 + (t / duration) * 1600
    chirp_phase = 2 * math.pi * np.cumsum(chirp_freq) / SR
    chirp = np.sin(chirp_phase) * rise_env * 0.4
    body = swept * rise_env + chirp
    tail_hit = make_impact_hit(0.4)
    body = np.pad(body, (0, max(0, len(tail_hit) - len(body))))
    tail_hit = np.pad(tail_hit, (0, len(body) - len(tail_hit)))
    return soft_clip(body * 0.8 + tail_hit * 0.7, 1.3)


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


def make_hat(duration: float = 0.05, seed: int = 0, open_: bool = False) -> np.ndarray:
    tau = 0.22 if open_ else 0.035
    return smooth_bandpass(white_noise(duration, seed=seed), 6000, 14000) * exp_decay(duration, tau)


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
    """チャンス目/ボーナス告知風の短い上昇アルペジオ（短いライザー→ベル+パッド+プラック+きらめき）。"""
    notes = ["C5", "E5", "G5", "C6", "G5", "C6"]
    riser = make_riser_buildup(0.5) * 0.5
    lead = bell_arpeggio(notes, 0.1)
    pluck_layer = np.concatenate([
        pluck_wave(NOTE_FREQS[n], 0.1, voices=4, detune_cents=12) for n in notes
    ]) * 0.35
    dur = max(len(lead), len(pluck_layer)) / SR
    pad = make_pad(["C4", "E4", "G4"], dur, voices=4, detune_cents=8, cutoff=1800) * 0.4
    sparkle = smooth_bandpass(white_noise(dur, seed=3), 4000, 9500) * exp_decay(dur, 0.22) * 0.18
    body = mix(lead, pluck_layer, pad, sparkle, weights=[1.0, 1.0, 1.0, 1.0])
    return mix(riser, np.pad(body, (len(riser), 0)), weights=[1.0, 1.0])


def make_impact_hit(duration: float = 0.5) -> np.ndarray:
    """ファンファーレ冒頭のインパクト（キック+クラッシュ）。"""
    kick = make_kick(min(duration, 0.28))
    kick = np.pad(kick, (0, int(SR * duration) - len(kick)))
    crash = smooth_bandpass(white_noise(duration, seed=77), 2500, 14000) * exp_decay(duration, 0.3)
    return soft_clip(kick * 1.1 + crash * 0.45, 1.3)


def make_big_win_fanfare() -> np.ndarray:
    """大当り/ビッグボーナス風ファンファーレ: ライザー→インパクト→ブラス主旋律(+プラック二重)+ハモリ
    +サイドチェインされたパッド+ディレイの掛かった余韻+コインの雨。ステレオバスを直接返す。"""
    riser = make_riser_buildup(0.9)

    melody_notes = ["C5", "E5", "G5", "C6", "G5", "E5", "C6", "E6", "G6"]
    melody = brass_arpeggio(melody_notes, 0.13, voices=4)
    pluck_double = np.concatenate([
        pluck_wave(NOTE_FREQS[n], 0.13, voices=4, detune_cents=13) for n in melody_notes
    ]) * 0.4
    harmony = brass_arpeggio(
        ["C4", "E4", "G4", "C5", "G4", "E4", "C5", "E5", "G5"], 0.13, voices=3,
    ) * 0.5
    dur = len(melody) / SR

    pad = make_pad(["C4", "E4", "G4"], dur, voices=5, detune_cents=10, cutoff=2600) * 0.35
    pump = sidechain_env(len(pad), bpm=60.0 / 0.13, hit_beats=list(range(9)), depth=0.4, release_beats=0.6)
    pad = pad * pump[: len(pad)]

    impact = gated_reverb(make_impact_hit(0.5), HALL_IR, gate_s=0.35, mix_amount=0.55)

    core = mix(melody, pluck_double, harmony, pad, weights=[1.0, 1.0, 1.0, 1.0])
    core = mix(core, impact, weights=[1.0, 0.9])
    core = apply_reverb(core, HALL_IR, mix_amount=0.3)
    core_echo = ping_pong_echo(core, delay_s=0.13, feedback=0.3, taps=4)

    full = np.concatenate([riser, core])
    coin_tail = make_coin_payout(16)
    coin_start = len(riser) + int(SR * dur * 0.55)
    full = mix(full, np.pad(coin_tail, (coin_start, 0)), weights=[1.0, 0.6])

    stereo = to_stereo(full, width_ms=20)
    echo_padded = np.pad(core_echo, ((0, 0), (len(riser), 0)))
    n = stereo.shape[1]
    if echo_padded.shape[1] < n:
        echo_padded = np.pad(echo_padded, ((0, 0), (0, n - echo_padded.shape[1])))
    return stereo + echo_padded[:, :n] * 0.5


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


def make_edm_drum_bus(total_beats: int, bpm: float) -> np.ndarray:
    """EDM/トランス的な四つ打りキック + クラップ(ゲートリバーブ) + 16分ハットのドラムバス。"""
    beat_dur = 60.0 / bpm
    n = int(SR * total_beats * beat_dur)
    bus = np.zeros(n)

    def place(sig: np.ndarray, beat_pos: float, gain: float = 1.0) -> None:
        idx = int(SR * beat_pos * beat_dur)
        end = min(n, idx + len(sig))
        if end > idx:
            bus[idx:end] += sig[: end - idx] * gain

    kick = make_kick()
    clap = gated_reverb(make_clap(), ROOM_IR, gate_s=0.16, mix_amount=0.45)
    for b in range(total_beats):
        place(kick, b, 0.95)
    for b in range(1, total_beats, 2):
        place(clap, b, 0.8)

    step_dur = 0.25
    steps = int(total_beats / step_dur)
    for i in range(steps):
        open_ = (i % 8 == 7)
        hat = make_hat(seed=800 + i, open_=open_) * (0.1 if not open_ else 0.15)
        place(hat, i * step_dur)
    return bus


def make_pad_progression(chords: list[list[str]], seg_beats: float, bpm: float, voices: int = 6,
                          detune_cents: float = 11.0, cutoff: float = 2400.0) -> np.ndarray:
    """区間ごとにコードを切り替えるパッド（ベースのコード進行に追従させて厚みと動きを出す）。"""
    beat_dur = 60.0 / bpm
    seg_dur = seg_beats * beat_dur
    segs = [make_pad(chord, seg_dur, voices=voices, detune_cents=detune_cents, cutoff=cutoff) for chord in chords]
    return np.concatenate(segs)


def make_bgm_loop_edm(bpm: float, chords: list[list[str]], lead_gain: float, bass_gain: float,
                       drum_gain: float, lead_voices: int, bass_voices: int,
                       pad_sidechain_depth: float = 0.7, bass_sidechain_depth: float = 0.45,
                       riser_tail: bool = False) -> np.ndarray:
    """EDM/トランス系 BGM ループ: 四つ打り+クラップ+ハット、サイドチェインでポンピングするパッド/ベース、
    スーパーソウのプラックリード（ピンポンディレイ付き）、コード進行するプレートリバーブパッド。"""
    total_beats = 8
    beat_dur = 60.0 / bpm

    drums = make_edm_drum_bus(total_beats, bpm) * drum_gain
    n = len(drums)

    kick_beats = list(range(total_beats))
    duck_pad = sidechain_env(n, bpm, kick_beats, depth=pad_sidechain_depth, release_beats=0.45)
    duck_bass = sidechain_env(n, bpm, kick_beats, depth=bass_sidechain_depth, release_beats=0.3)

    pad = make_pad_progression(chords, seg_beats=total_beats / len(chords), bpm=bpm, voices=6,
                                detune_cents=11, cutoff=2500) * 0.4
    pad = pad[:n] if len(pad) >= n else np.pad(pad, (0, n - len(pad)))
    pad = apply_reverb_circular(pad, PLATE_IR, mix_amount=0.35) * duck_pad

    lead_notes = ["C5", "E5", "G5", "E5", "F5", "A5", "G5", "E5",
                  "C5", "D5", "E5", "G5", "D5", "F5", "E5", "C5"]
    lead_tone = lambda f, d: pluck_wave(f, d, voices=lead_voices, detune_cents=13)
    lead = render_track([Step(nn, 0.5) for nn in lead_notes], bpm, lead_tone, gain=lead_gain)
    lead = lead[:n] if len(lead) >= n else np.pad(lead, (0, n - len(lead)))
    lead_echo = ping_pong_echo(lead, delay_s=beat_dur / 2, feedback=0.35, taps=4)
    lead_echo = lead_echo[:, :n] if lead_echo.shape[1] >= n else np.pad(lead_echo, ((0, 0), (0, n - lead_echo.shape[1])))

    bass_notes = ["C4", "C4", "G4", "G4", "A4", "A4", "F4", "F4"]
    bass_tone = lambda f, d: wobble_bass(f, d, lfo_hz=bpm / 60.0, voices=bass_voices)
    bass = render_track([Step(nn, 1.0) for nn in bass_notes], bpm, bass_tone, octave_shift=-1,
                         gain=bass_gain, sub_gain=0.3)
    bass = bass[:n] if len(bass) >= n else np.pad(bass, (0, n - len(bass)))
    bass = bass * duck_bass

    mono_bus = mix(drums, pad, bass, weights=[1.0, 1.0, 1.0])
    stereo = to_stereo(mono_bus, width_ms=14)
    stereo = stereo + np.stack([lead, lead]) * 0.9 + lead_echo * 0.55

    if riser_tail:
        riser = make_riser_buildup(min(1.4, n / SR * 0.4)) * 0.45
        riser_stereo = to_stereo(riser, width_ms=20)
        tail_start = max(0, n - riser_stereo.shape[1])
        stereo[:, tail_start:] += riser_stereo[:, : n - tail_start]

    return stereo


def make_bgm_normal_loop() -> np.ndarray:
    chords = [["C4", "E4", "G4"], ["G4", "B4", "D5"], ["A4", "C5", "E5"], ["F4", "A4", "C5"]]
    return make_bgm_loop_edm(bpm=124, chords=chords, lead_gain=0.34, bass_gain=0.4, drum_gain=1.0,
                              lead_voices=5, bass_voices=2, pad_sidechain_depth=0.65, bass_sidechain_depth=0.4)


def make_bgm_bonus_loop() -> np.ndarray:
    """ボーナス中風の、テンポが速く音圧・ユニゾンも厚い派手なループ（末尾にライザーで次周へのつなぎを演出）。"""
    chords = [["C4", "E4", "G4"], ["G4", "B4", "D5"], ["A4", "C5", "E5"], ["F4", "A4", "C5"]]
    return make_bgm_loop_edm(bpm=150, chords=chords, lead_gain=0.38, bass_gain=0.46, drum_gain=1.15,
                              lead_voices=7, bass_voices=3, pad_sidechain_depth=0.75, bass_sidechain_depth=0.5,
                              riser_tail=True)


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
    export("buildup_riser", make_riser_buildup(1.6), reverb_ir=HALL_IR, reverb_mix=0.25, width_ms=20)
    export("bonus_chance_jingle", make_bonus_chance_jingle(), reverb_ir=HALL_IR, reverb_mix=0.3, width_ms=18)
    export("big_win_fanfare", make_big_win_fanfare(), already_stereo=True, saturate=1.25)
    export("reg_win_fanfare", make_reg_win_fanfare(), reverb_ir=HALL_IR, reverb_mix=0.25, width_ms=16)
    export("bgm_normal_loop", make_bgm_normal_loop(), loop=True, already_stereo=True, saturate=1.2)
    export("bgm_bonus_loop", make_bgm_bonus_loop(), loop=True, already_stereo=True, saturate=1.25)


if __name__ == "__main__":
    main()
