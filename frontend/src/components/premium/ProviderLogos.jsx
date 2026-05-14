/**
 * NXT1 — Real Provider Logo Glyphs (Phase 19)
 *
 * Uses the actual brand logos shipped in /public/logos. We render them as
 * <img> so they stay crisp on retina and respect the user-provided art.
 *
 * Each logo has its own visual treatment:
 *   • Claude     — orange splat on graphite tile
 *   • ChatGPT    — knot, inverted to white-on-graphite
 *   • Gemini     — blue sparkle (full colour)
 *   • Grok       — bold S/X, inverted to white-on-graphite
 *   • DeepSeek   — blue whale on white tile
 *   • Auto       — NXT1 mark (in-house orbit dot)
 */
import React from "react";

export function ProviderLogo({ provider, size = 16, invert = false, className = "" }) {
  const src = {
    anthropic: "/logos/claude.png",
    openai:    "/logos/openai.png",
    gemini:    "/logos/gemini.png",
    grok:      "/logos/grok.png",
    xai:       "/logos/grok.png",       // xai/grok share a brand asset
    deepseek:  "/logos/deepseek.webp",
  }[provider];

  // Auto / Emergent → render an in-house orbit glyph (SVG, no external asset)
  if (!src) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
        <circle cx="12" cy="12" r="3" fill="currentColor" />
        <path d="M12 3a9 9 0 110 18 9 9 0 010-18z" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.55" />
      </svg>
    );
  }

  // Whether to invert (ChatGPT and Grok are black-on-white logos → must turn white)
  const needsInvert =
    provider === "openai" || provider === "grok" || provider === "xai" || invert;

  return (
    <img
      src={src}
      alt={`${provider} logo`}
      width={size}
      height={size}
      className={`select-none pointer-events-none ${className}`}
      style={
        needsInvert
          ? { filter: "brightness(0) invert(1)", objectFit: "contain" }
          : { objectFit: "contain" }
      }
      draggable={false}
    />
  );
}

/* Back-compat named exports (some code still imports ClaudeLogo etc.) */
export const ClaudeLogo   = (p) => <ProviderLogo provider="anthropic" {...p} />;
export const OpenAILogo   = (p) => <ProviderLogo provider="openai"    {...p} />;
export const GeminiLogo   = (p) => <ProviderLogo provider="gemini"    {...p} />;
export const GrokLogo     = (p) => <ProviderLogo provider="grok"      {...p} />;
export const DeepSeekLogo = (p) => <ProviderLogo provider="deepseek"  {...p} />;
export const EmergentLogo = (p) => <ProviderLogo provider="emergent"  {...p} />;
