import { useEffect, useRef } from "react";
import { useStore } from "../lib/store";

/** Live microphone/speech waveform bars. Uses rAF only while active. */
export default function Waveform({ bars = 28, className = "" }: { bars?: number; className?: string }) {
  const listening = useStore((s) => s.listening);
  const speaking = useStore((s) => s.speaking);
  const levelRef = useRef(0);
  const level = useStore((s) => s.micLevel);
  levelRef.current = level;
  const ref = useRef<HTMLDivElement>(null);
  const active = listening || speaking;

  useEffect(() => {
    if (!active) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const el = ref.current;
      if (el) {
        const lv = listening ? levelRef.current : 0.45 + 0.25 * Math.sin((t - t0) / 180);
        Array.from(el.children).forEach((child, i) => {
          const wave = Math.abs(Math.sin((t - t0) / 160 + i * 0.55)) * 0.6 + 0.4;
          const center = 1 - Math.abs(i - bars / 2) / (bars / 2);
          (child as HTMLElement).style.transform = `scaleY(${Math.max(0.08, lv * wave * (0.4 + center))})`;
        });
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, listening, bars]);

  return (
    <div ref={ref} className={`flex h-10 items-center gap-[3px] ${className}`} aria-hidden>
      {Array.from({ length: bars }).map((_, i) => (
        <span key={i} className={`h-full w-[3px] origin-center rounded-full transition-colors ${listening ? "bg-cyan-300/80" : "bg-accent/80"}`}
              style={{ transform: "scaleY(0.08)" }} />
      ))}
    </div>
  );
}
