/**
 * Premium UI blocks — text + background utilities.
 *
 * Bundle of small, dependency-free animation primitives covering the
 * remaining registry kinds (text / background / input).
 */
import { useEffect, useState } from "react";
import { motion } from "framer-motion";

// ── text.magicui.animated-gradient ──────────────────────────────────────
export function AnimatedGradientText({ children, className = "" }) {
  return (
    <span
      data-testid="block-text-animated-gradient"
      className={`bg-clip-text text-transparent inline-block ${className}`}
      style={{
        backgroundImage:
          "linear-gradient(120deg, #a78bfa 0%, #22d3ee 25%, #34d399 50%, #fcd34d 75%, #a78bfa 100%)",
        backgroundSize: "300% 100%",
        animation: "agt-shift 8s ease infinite",
      }}
    >
      {children}
      <style>{`@keyframes agt-shift { 0%,100% { background-position: 0% 50% } 50% { background-position: 100% 50% } }`}</style>
    </span>
  );
}

// ── text.magicui.typing-animation ───────────────────────────────────────
export function TypingAnimation({
  text = "Building your app...",
  speed = 38,
  cursor = true,
  className = "",
}) {
  const [out, setOut] = useState("");
  useEffect(() => {
    let i = 0;
    setOut("");
    const id = setInterval(() => {
      i += 1;
      setOut(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, speed);
    return () => clearInterval(id);
  }, [text, speed]);
  return (
    <span data-testid="block-text-typing" className={className}>
      {out}
      {cursor && (
        <span
          aria-hidden
          className="inline-block w-[2px] ml-0.5"
          style={{
            height: "1em",
            background: "currentColor",
            animation: "blink 1s infinite",
            verticalAlign: "-0.15em",
          }}
        />
      )}
      <style>{`@keyframes blink { 50% { opacity: 0 } }`}</style>
    </span>
  );
}

// ── background.magicui.dot-pattern ──────────────────────────────────────
export function DotPattern({
  size = 1.5,
  spacing = 22,
  color = "rgba(255,255,255,0.08)",
  className = "",
}) {
  return (
    <div
      aria-hidden
      data-testid="block-bg-dot-pattern"
      className={`absolute inset-0 pointer-events-none ${className}`}
      style={{
        backgroundImage: `radial-gradient(circle, ${color} ${size}px, transparent ${size}px)`,
        backgroundSize: `${spacing}px ${spacing}px`,
        maskImage:
          "radial-gradient(ellipse at center, black 30%, transparent 70%)",
      }}
    />
  );
}

// ── background.aceternity.wavy ──────────────────────────────────────────
export function WavyBackground({ className = "", color = "rgba(139,92,246,0.18)" }) {
  return (
    <div
      aria-hidden
      data-testid="block-bg-wavy"
      className={`absolute inset-0 pointer-events-none overflow-hidden ${className}`}
    >
      <svg viewBox="0 0 1200 600" className="w-full h-full">
        <defs>
          <linearGradient id="wavy-grad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="rgba(139,92,246,0)" />
            <stop offset="50%" stopColor={color} />
            <stop offset="100%" stopColor="rgba(34,211,238,0)" />
          </linearGradient>
        </defs>
        {[0, 1, 2].map((i) => (
          <motion.path
            key={i}
            d="M 0 300 Q 300 200 600 300 T 1200 300"
            stroke="url(#wavy-grad)"
            strokeWidth="2"
            fill="none"
            initial={{ pathLength: 0 }}
            animate={{
              pathLength: 1,
              d: [
                "M 0 300 Q 300 200 600 300 T 1200 300",
                "M 0 300 Q 300 400 600 300 T 1200 300",
                "M 0 300 Q 300 200 600 300 T 1200 300",
              ],
            }}
            transition={{
              duration: 8 + i * 1.5,
              repeat: Infinity,
              ease: "easeInOut",
              delay: i * 0.7,
            }}
            opacity={0.7 - i * 0.2}
          />
        ))}
      </svg>
    </div>
  );
}

// ── background.aceternity.meteors ───────────────────────────────────────
export function Meteors({ count = 16 }) {
  const meteors = Array.from({ length: count }, (_, i) => i);
  return (
    <div
      aria-hidden
      data-testid="block-bg-meteors"
      className="absolute inset-0 pointer-events-none overflow-hidden"
    >
      {meteors.map((i) => {
        const left = Math.random() * 100;
        const delay = Math.random() * 5;
        const duration = 4 + Math.random() * 6;
        return (
          <span
            key={i}
            className="absolute h-px"
            style={{
              top: `${Math.random() * 50}%`,
              left: `${left}%`,
              width: `${60 + Math.random() * 80}px`,
              background:
                "linear-gradient(90deg, rgba(255,255,255,0.6), transparent)",
              transform: "rotate(215deg)",
              animation: `meteor ${duration}s ${delay}s linear infinite`,
              opacity: 0,
            }}
          />
        );
      })}
      <style>{`
        @keyframes meteor {
          0%   { transform: translate(0, 0) rotate(215deg); opacity: 0; }
          10%  { opacity: 1; }
          100% { transform: translate(-400px, 400px) rotate(215deg); opacity: 0; }
        }
      `}</style>
    </div>
  );
}

// ── input.originui.search-with-shortcut ─────────────────────────────────
export function SearchWithShortcut({
  placeholder = "Search anything...",
  shortcut = "⌘K",
  onChange,
  value,
}) {
  return (
    <div
      data-testid="block-input-search-shortcut"
      className="relative w-full"
    >
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        className="w-full pl-10 pr-14 py-2.5 rounded-xl outline-none text-[13px]"
        style={{
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.1)",
          color: "white",
        }}
      />
      <span
        aria-hidden
        className="absolute left-3 top-1/2 -translate-y-1/2 text-[14px]"
        style={{ color: "rgba(255,255,255,0.4)" }}
      >
        ⌕
      </span>
      <kbd
        className="absolute right-2 top-1/2 -translate-y-1/2 mono text-[10px] px-1.5 py-0.5 rounded"
        style={{
          background: "rgba(255,255,255,0.06)",
          color: "rgba(255,255,255,0.6)",
          border: "1px solid rgba(255,255,255,0.1)",
        }}
      >
        {shortcut}
      </kbd>
    </div>
  );
}

// ── input.originui.password-strength ────────────────────────────────────
export function PasswordStrengthInput({
  value = "",
  onChange,
  placeholder = "Password",
}) {
  const score = scorePassword(value);
  const colors = ["#52525b", "#ef4444", "#f59e0b", "#22d3ee", "#10b981"];
  const labels = ["", "Weak", "Fair", "Good", "Strong"];
  return (
    <div data-testid="block-input-password-strength" className="w-full">
      <input
        type="password"
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2.5 rounded-xl outline-none text-[13px]"
        style={{
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.1)",
          color: "white",
        }}
      />
      <div className="flex gap-1 mt-2">
        {[1, 2, 3, 4].map((seg) => (
          <div
            key={seg}
            className="h-1 flex-1 rounded-full transition"
            style={{
              background: score >= seg ? colors[score] : "rgba(255,255,255,0.08)",
            }}
          />
        ))}
      </div>
      {value && (
        <div
          className="mono text-[10px] uppercase tracking-[0.2em] mt-1.5"
          style={{ color: colors[score] }}
        >
          {labels[score]}
        </div>
      )}
    </div>
  );
}

function scorePassword(pw) {
  if (!pw) return 0;
  let s = 0;
  if (pw.length >= 8) s += 1;
  if (pw.length >= 12) s += 1;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s += 1;
  if (/[0-9]/.test(pw) && /[^A-Za-z0-9]/.test(pw)) s += 1;
  return Math.min(s, 4);
}
