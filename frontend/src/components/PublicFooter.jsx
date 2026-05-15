/**
 * NXT1 — PublicFooter
 *
 * Tasteful footer for landing + auth. Subtle Jwood Technologies attribution
 * + Made in the USA badge. Theme-aware contrast.
 */
import { Link } from "react-router-dom";
import Brand from "@/components/Brand";

export default function PublicFooter() {
  return (
    <footer
      className="relative z-10 w-full px-5 sm:px-6 pb-7 pt-2"
      data-testid="public-footer"
    >
      <div
        className="mx-auto max-w-[920px] flex flex-col sm:flex-row items-center justify-end gap-3 text-[11px]"
        style={{ color: "var(--nxt-fg-faint)" }}
      >
        <div className="flex items-center gap-4 sm:gap-5">
          <Link to="/privacy" className="transition-colors" style={{ color: "inherit" }} data-testid="footer-privacy">Privacy</Link>
          <Link to="/terms"   className="transition-colors" style={{ color: "inherit" }} data-testid="footer-terms">Terms</Link>
          <Link to="/contact" className="transition-colors" style={{ color: "inherit" }} data-testid="footer-contact">Contact</Link>
          <Link to="/access"  className="transition-colors" style={{ color: "inherit" }} data-testid="footer-workspace">Workspace</Link>
        </div>
      </div>

      {/* Attribution row — NXT1 (colorful) · Jwood Technologies (clean) · USA flag */}
      <div
        className="mt-4 flex flex-wrap items-center justify-center gap-x-2.5 gap-y-1 text-[11px] leading-none"
        style={{ color: "var(--nxt-fg-faint)" }}
        data-testid="footer-attribution"
      >
        <Brand size="sm" gradient />
        <span style={{ opacity: 0.55 }}>·</span>
        <span data-testid="footer-jwood-attribution">
          A product of <span style={{ color: "var(--nxt-fg-dim)" }}>Jwood Technologies</span>
        </span>
        <span style={{ opacity: 0.55 }}>·</span>
        <span
          className="inline-flex items-center gap-1.5"
          data-testid="footer-made-in-usa"
        >
          <USFlag />
          <span>Made in the USA</span>
        </span>
      </div>
    </footer>
  );
}

function USFlag() {
  return (
    <svg
      width="16"
      height="11"
      viewBox="0 0 16 11"
      aria-hidden
      style={{ borderRadius: 1.5, overflow: "hidden", display: "inline-block", flex: "0 0 auto" }}
    >
      <rect width="16" height="11" fill="#B22234" />
      <rect y="1.55" width="16" height="1.55" fill="#FFFFFF" />
      <rect y="4.65" width="16" height="1.55" fill="#FFFFFF" />
      <rect y="7.75" width="16" height="1.55" fill="#FFFFFF" />
      <rect width="6.6" height="6.2" fill="#3C3B6E" />
      <circle cx="1.6" cy="1.6" r="0.35" fill="#FFFFFF" />
      <circle cx="3.2" cy="1.6" r="0.35" fill="#FFFFFF" />
      <circle cx="4.8" cy="1.6" r="0.35" fill="#FFFFFF" />
      <circle cx="2.4" cy="3.0" r="0.35" fill="#FFFFFF" />
      <circle cx="4.0" cy="3.0" r="0.35" fill="#FFFFFF" />
      <circle cx="1.6" cy="4.4" r="0.35" fill="#FFFFFF" />
      <circle cx="3.2" cy="4.4" r="0.35" fill="#FFFFFF" />
      <circle cx="4.8" cy="4.4" r="0.35" fill="#FFFFFF" />
    </svg>
  );
}
