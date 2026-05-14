/**
 * Premium UI Blocks — Barrel export + registry-id → component lookup.
 *
 * Every entry in `/app/backend/data/ui_registry.json` whose `id` is also
 * a key in `BLOCK_MAP` resolves to a real React component here. The
 * UIBlockGallery uses `getBlockComponent(id)` to render an in-page
 * preview; the build agent uses the same map to drop these components
 * into generated apps.
 *
 * Block ids NOT yet implemented as components stay in the registry as
 * "documentation-only" entries (the AI agent can still reference them).
 */
import SpotlightHero from "./SpotlightHero";
import BentoGridHero from "./BentoGridHero";
import BackgroundBeamsHero from "./BackgroundBeamsHero";
import ShineBorderCard from "./ShineBorderCard";
import ThreeDPinCard from "./ThreeDPinCard";
import LogoMarquee from "./LogoMarquee";
import OrbitingCircles from "./OrbitingCircles";
import AceternityBento from "./AceternityBento";
import {
  AnimatedGradientText,
  TypingAnimation,
  DotPattern,
  WavyBackground,
  Meteors,
  SearchWithShortcut,
  PasswordStrengthInput,
} from "./Primitives";
import { ParticleField, AnimatedGlobe } from "./R3FFallbacks";

export {
  SpotlightHero,
  BentoGridHero,
  BackgroundBeamsHero,
  ShineBorderCard,
  ThreeDPinCard,
  LogoMarquee,
  OrbitingCircles,
  AceternityBento,
  AnimatedGradientText,
  TypingAnimation,
  DotPattern,
  WavyBackground,
  Meteors,
  SearchWithShortcut,
  PasswordStrengthInput,
  ParticleField,
  AnimatedGlobe,
};

/** Map every registry block id to a concrete React component. */
export const BLOCK_MAP = {
  "hero.aceternity.spotlight":          SpotlightHero,
  "hero.magicui.bento":                 BentoGridHero,
  "hero.aceternity.background-beams":   BackgroundBeamsHero,
  "card.magicui.shine-border":          ShineBorderCard,
  "card.aceternity.3d-pin":             ThreeDPinCard,
  "feature.magicui.marquee":            LogoMarquee,
  "feature.magicui.orbiting-circles":   OrbitingCircles,
  "feature.aceternity.bento-grid":      AceternityBento,
  "text.magicui.animated-gradient":     AnimatedGradientText,
  "text.magicui.typing-animation":      TypingAnimation,
  "background.magicui.dot-pattern":     DotPattern,
  "background.aceternity.wavy":         WavyBackground,
  "background.aceternity.meteors":      Meteors,
  "input.originui.search-with-shortcut": SearchWithShortcut,
  "input.originui.password-strength":   PasswordStrengthInput,
  "scene.r3f.particles":                ParticleField,
  "scene.r3f.globe":                    AnimatedGlobe,
};

export function getBlockComponent(blockId) {
  return BLOCK_MAP[blockId] || null;
}

export function blockIsImplemented(blockId) {
  return Boolean(BLOCK_MAP[blockId]);
}
