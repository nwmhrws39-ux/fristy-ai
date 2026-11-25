import { motion } from "framer-motion";
import { useStore, OrbState } from "../lib/store";

const PALETTE: Record<OrbState, { core: string; glow: string; ring: string; speed: number }> = {
  idle: { core: "var(--accent)", glow: "var(--accent)", ring: "var(--accent-2)", speed: 18 },
  listening: { core: "34 211 238", glow: "34 211 238", ring: "165 243 252", speed: 10 },
  thinking: { core: "var(--accent)", glow: "var(--accent)", ring: "var(--accent-2)", speed: 3 },
  speaking: { core: "var(--accent-2)", glow: "var(--accent)", ring: "255 255 255", speed: 8 },
  executing: { core: "251 191 36", glow: "var(--accent)", ring: "253 230 138", speed: 4 },
  error: { core: "239 68 68", glow: "239 68 68", ring: "252 165 165", speed: 24 },
};

function c(v: string, a = 1) {
  return v.startsWith("var(") ? `rgb(${v} / ${a})` : `rgb(${v} / ${a})`;
}

export default function Orb({ size = 220, onClick }: { size?: number; onClick?: () => void }) {
  const state = useStore((s) => s.orb);
  const level = useStore((s) => s.micLevel);
  const p = PALETTE[state];
  const pulse = state === "listening" ? 1 + level * 0.35 : 1;
  const ringStyle = (dur: number, rev = false) => ({ animation: `${rev ? "spin-rev" : "spin-slow"} ${dur}s linear infinite` });

  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }} onClick={onClick}
         role={onClick ? "button" : undefined} aria-label={`FRISTY ${state}`}>
      {/* ambient glow */}
      <motion.div className="absolute inset-0 rounded-full blur-3xl"
        style={{ background: `radial-gradient(circle, ${c(p.glow, 0.55)} 0%, transparent 65%)` }}
        animate={{ scale: state === "thinking" ? [1, 1.12, 1] : pulse, opacity: state === "error" ? [0.5, 0.9, 0.5] : 0.9 }}
        transition={{ duration: state === "thinking" ? 1.4 : 0.25, repeat: state === "thinking" || state === "error" ? Infinity : 0 }} />
      {/* ripples while speaking / listening */}
      {(state === "speaking" || state === "listening") && [0, 1, 2].map((i) => (
        <span key={i} className="absolute rounded-full border"
          style={{ width: size * 0.62, height: size * 0.62, borderColor: c(p.ring, 0.45),
                   animation: `ripple ${state === "speaking" ? 1.8 : 2.4}s ease-out ${i * 0.6}s infinite` }} />
      ))}
      {/* outer dashed ring */}
      <svg className="absolute inset-0" viewBox="0 0 200 200" style={ringStyle(p.speed * 2)}>
        <circle cx="100" cy="100" r="94" fill="none" stroke={c(p.ring, 0.25)} strokeWidth="0.6" strokeDasharray="2 6" />
      </svg>
      {/* arc ring */}
      <svg className="absolute inset-0" viewBox="0 0 200 200" style={ringStyle(p.speed, true)}>
        <defs>
          <linearGradient id="arc" x1="0" x2="1">
            <stop offset="0" stopColor={c(p.ring, 0)} />
            <stop offset="1" stopColor={c(p.ring, 0.95)} />
          </linearGradient>
        </defs>
        <circle cx="100" cy="100" r="84" fill="none" stroke="url(#arc)" strokeWidth="1.6" strokeDasharray="140 388" strokeLinecap="round" />
        <circle cx="100" cy="100" r="84" fill="none" stroke={c(p.ring, 0.08)} strokeWidth="1" />
      </svg>
      {/* executing: orbiting satellites */}
      {state === "executing" && (
        <svg className="absolute inset-0" viewBox="0 0 200 200" style={ringStyle(2.2)}>
          {[0, 120, 240].map((a) => (
            <circle key={a} cx={100 + 74 * Math.cos((a * Math.PI) / 180)} cy={100 + 74 * Math.sin((a * Math.PI) / 180)} r="3.2" fill={c(p.core)} />
          ))}
        </svg>
      )}
      {/* inner tick ring */}
      <svg className="absolute" viewBox="0 0 200 200" style={{ width: size * 0.78, height: size * 0.78, ...ringStyle(p.speed * 1.5) }}>
        {Array.from({ length: 48 }).map((_, i) => {
          const a = (i / 48) * Math.PI * 2;
          const r1 = 92, r2 = i % 4 === 0 ? 84 : 88;
          return <line key={i} x1={100 + r1 * Math.cos(a)} y1={100 + r1 * Math.sin(a)} x2={100 + r2 * Math.cos(a)} y2={100 + r2 * Math.sin(a)}
                       stroke={c(p.ring, i % 4 === 0 ? 0.55 : 0.2)} strokeWidth="1" />;
        })}
      </svg>
      {/* core sphere */}
      <motion.div className="relative rounded-full"
        style={{
          width: size * 0.46, height: size * 0.46,
          background: `radial-gradient(circle at 35% 30%, rgb(255 255 255 / 0.85) 0%, ${c(p.core, 0.95)} 18%, ${c(p.core, 0.55)} 45%, rgb(10 5 20 / 0.95) 78%)`,
          boxShadow: `0 0 40px ${c(p.glow, 0.7)}, inset 0 0 30px ${c(p.core, 0.6)}, inset 0 -10px 25px rgb(0 0 0 / 0.6)`,
        }}
        animate={state === "idle" ? { scale: [1, 1.035, 1] } : { scale: state === "speaking" ? [1, 1.08, 0.98, 1.05, 1] : pulse }}
        transition={{ duration: state === "idle" ? 4 : state === "speaking" ? 0.9 : 0.15, repeat: state === "idle" || state === "speaking" ? Infinity : 0 }}>
        <div className="absolute inset-0 rounded-full mix-blend-screen opacity-70"
             style={{ background: `conic-gradient(from 0deg, transparent, ${c(p.ring, 0.35)}, transparent 40%)`, ...ringStyle(p.speed / 2) }} />
      </motion.div>
    </div>
  );
}
