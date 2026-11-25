import { api } from "./api";
import { getState, setState } from "./store";
import { isRTL } from "./i18n";

let audioEl: HTMLAudioElement | null = null;
let utterance: SpeechSynthesisUtterance | null = null;

export function speechText(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/[#*_>✅❌⚠️⛔⏭⏹•]/g, " ")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 1500);
}

export function voices(): SpeechSynthesisVoice[] {
  return typeof speechSynthesis !== "undefined" ? speechSynthesis.getVoices() : [];
}

function pickVoice(text: string, preferred: string): SpeechSynthesisVoice | undefined {
  const all = voices();
  const hebrew = isRTL(text);
  const pref = all.find((v) => v.name === preferred);
  if (pref && pref.lang.toLowerCase().startsWith(hebrew ? "he" : "en")) return pref;
  return all.find((v) => v.lang.toLowerCase().startsWith(hebrew ? "he" : "en")) || pref;
}

export function stopSpeaking() {
  if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
  if (audioEl) { audioEl.pause(); audioEl.src = ""; audioEl = null; }
  utterance = null;
  if (getState().speaking) setState({ speaking: false, orb: getState().orb === "speaking" ? "idle" : getState().orb });
}

export async function speak(markdown: string, onEnd?: () => void): Promise<void> {
  const v = getState().settings?.voice;
  if (!v || v.tts_engine === "off") return onEnd?.();
  const text = speechText(markdown);
  if (!text) return onEnd?.();
  stopSpeaking();
  const finish = () => {
    setState({ speaking: false, orb: getState().orb === "speaking" ? "idle" : getState().orb });
    onEnd?.();
  };
  setState({ speaking: true, orb: "speaking" });
  if (v.tts_engine === "openai") {
    try {
      const blob = await api<Blob>("/api/voice/tts", { body: { text }, blob: true });
      audioEl = new Audio(URL.createObjectURL(blob));
      audioEl.onended = finish;
      audioEl.onerror = finish;
      await audioEl.play();
      return;
    } catch {
      /* fall back to system voice */
    }
  }
  if (typeof speechSynthesis === "undefined") return finish();
  utterance = new SpeechSynthesisUtterance(text);
  const voice = pickVoice(text, v.voice_name);
  if (voice) { utterance.voice = voice; utterance.lang = voice.lang; } else utterance.lang = isRTL(text) ? "he-IL" : "en-US";
  utterance.rate = v.rate || 1;
  utterance.onend = finish;
  utterance.onerror = finish;
  speechSynthesis.speak(utterance);
}
