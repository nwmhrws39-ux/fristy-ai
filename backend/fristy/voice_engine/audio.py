"""Audio decoding helpers (WAV PCM -> float32 mono 16 kHz)."""
from __future__ import annotations

import io
import wave

import numpy as np

TARGET_SR = 16000


def wav_to_float32(data: bytes) -> np.ndarray:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            sr, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"invalid WAV audio: {exc}") from exc
    if width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif width == 1:
        audio = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    else:
        raise ValueError(f"unsupported sample width {width}")
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    if sr != TARGET_SR and len(audio):
        n_out = int(len(audio) * TARGET_SR / sr)
        audio = np.interp(np.linspace(0, len(audio) - 1, n_out), np.arange(len(audio)), audio).astype(np.float32)
    return audio


def float32_to_wav(audio: np.ndarray, sr: int = TARGET_SR) -> bytes:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio)))) if len(audio) else 0.0
