"""Speech-to-text (local faster-whisper or OpenAI) and optional cloud text-to-speech.

Local transcription and wake-word detection never leave the PC. The default
system TTS runs in the desktop app (Windows SAPI voices via speechSynthesis).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Optional

import httpx
import numpy as np

from ..computer_control.base import ActionError
from .audio import float32_to_wav, rms, wav_to_float32
from .wake import detect_wake

log = logging.getLogger(__name__)


class VoiceEngine:
    def __init__(self, settings_store, secrets, models_dir, bus=None):
        self.settings = settings_store
        self.secrets = secrets
        self.models_dir = models_dir
        self.bus = bus
        self._models: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.loading: Optional[str] = None
        self.last_error: Optional[str] = None
        self.mic_enabled = True

    @staticmethod
    def local_available() -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        v = self.settings.current.voice
        return {"local_stt_available": self.local_available(), "loaded_models": list(self._models),
                "loading": self.loading, "last_error": self.last_error, "stt_engine": v.stt_engine,
                "mic_enabled": self.mic_enabled, "cloud_stt": v.stt_engine == "openai",
                "cloud_tts": v.tts_engine == "openai"}

    def _model(self, size: str):
        with self._lock:
            if size in self._models:
                return self._models[size]
            try:
                from faster_whisper import WhisperModel
            except Exception as exc:
                raise ActionError("Local speech recognition (faster-whisper) is not installed.",
                                  "stt_unavailable") from exc
            self.loading = size
            if self.bus:
                self.bus.publish("voice.model_loading", model=size)
            try:
                # int8 on CPU keeps RAM low (~1 GB for 'small'); CUDA is used automatically if present.
                try:
                    model = WhisperModel(size, device="auto", compute_type="int8",
                                         download_root=str(self.models_dir / "whisper"))
                except Exception:
                    model = WhisperModel(size, device="cpu", compute_type="int8",
                                         download_root=str(self.models_dir / "whisper"))
            except Exception as exc:
                self.last_error = str(exc)
                raise ActionError(f"Could not load Whisper model '{size}': {exc}. The first use downloads it from "
                                  "huggingface.co (internet required once).", "stt_model_failed") from exc
            finally:
                self.loading = None
            self._models[size] = model
            if self.bus:
                self.bus.publish("voice.model_ready", model=size)
            return model

    def _transcribe_local(self, audio: np.ndarray, size: str, language: Optional[str], beam: int = 5) -> dict:
        model = self._model(size)
        t0 = time.time()
        segments, info = model.transcribe(audio, language=language, beam_size=beam, vad_filter=True,
                                          condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text, "language": info.language, "language_probability": round(info.language_probability, 3),
                "engine": f"local:{size}", "elapsed_ms": round((time.time() - t0) * 1000)}

    async def _transcribe_openai(self, wav: bytes, language: Optional[str]) -> dict:
        key = self.secrets.get("openai_api_key")
        if not key:
            raise ActionError("OpenAI API key is required for cloud speech recognition.", "stt_no_key")
        base = self.settings.current.ai.providers["openai"].base_url or "https://api.openai.com/v1"
        data = {"model": "whisper-1"}
        if language:
            data["language"] = language
        t0 = time.time()
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{base}/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                                  data=data, files={"file": ("speech.wav", wav, "audio/wav")})
        if r.status_code >= 400:
            raise ActionError(f"OpenAI transcription failed ({r.status_code}): {r.text[:200]}", "stt_failed")
        return {"text": r.json().get("text", "").strip(), "language": language, "engine": "openai:whisper-1",
                "elapsed_ms": round((time.time() - t0) * 1000)}

    async def transcribe(self, wav: bytes, language: Optional[str] = None) -> dict:
        if not self.mic_enabled:
            raise ActionError("Microphone is disabled.", "mic_disabled")
        v = self.settings.current.voice
        lang = language or (None if v.language == "auto" else v.language)
        try:
            audio = await asyncio.to_thread(wav_to_float32, wav)
        except ValueError as exc:
            raise ActionError(str(exc), "bad_audio") from exc
        if len(audio) < 1600 or rms(audio) < 0.003:
            return {"text": "", "language": lang, "engine": "none", "silent": True}
        if v.stt_engine == "openai":
            return await self._transcribe_openai(float32_to_wav(audio), lang)
        return await asyncio.to_thread(self._transcribe_local, audio, v.whisper_model, lang)

    async def check_wake(self, wav: bytes) -> dict:
        """Wake word detection: always local (tiny/base Whisper), never cloud."""
        if not self.mic_enabled:
            return {"detected": False, "reason": "mic_disabled"}
        v = self.settings.current.voice
        audio = await asyncio.to_thread(wav_to_float32, wav)
        if len(audio) < 4000 or rms(audio) < 0.005 or len(audio) > 16000 * 6:
            return {"detected": False}
        res = await asyncio.to_thread(self._transcribe_local, audio, v.wake_model, None, 1)
        detected, rest = detect_wake(res["text"], v.wake_phrases)
        return {"detected": detected, "text": res["text"], "command": rest if detected else "",
                "elapsed_ms": res.get("elapsed_ms")}

    async def synthesize_cloud(self, text: str) -> bytes:
        v = self.settings.current.voice
        key = self.secrets.get("openai_api_key")
        if not key:
            raise ActionError("OpenAI API key is required for cloud text-to-speech.", "tts_no_key")
        base = self.settings.current.ai.providers["openai"].base_url or "https://api.openai.com/v1"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{base}/audio/speech", headers={"Authorization": f"Bearer {key}"},
                                  json={"model": "gpt-4o-mini-tts", "voice": v.openai_voice, "input": text[:4000],
                                        "speed": v.rate, "response_format": "mp3"})
        if r.status_code >= 400:
            raise ActionError(f"OpenAI TTS failed ({r.status_code}): {r.text[:200]}", "tts_failed")
        return r.content

    def preload(self) -> None:
        v = self.settings.current.voice
        if v.enabled and v.stt_engine == "local" and self.local_available():
            threading.Thread(target=lambda: self._safe_load(v.whisper_model), daemon=True).start()

    def _safe_load(self, size: str) -> None:
        try:
            self._model(size)
        except Exception as exc:
            log.info("whisper preload failed: %s", exc)
