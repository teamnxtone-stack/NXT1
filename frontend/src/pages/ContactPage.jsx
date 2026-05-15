/**
 * NXT One — Contact page.
 *
 * The legacy "email us at hello@" card was replaced with the real NXT One
 * assistant. Visitors now have a structured intake (first name → last name →
 * email/phone) then can chat freely about access, the platform, or anything
 * else. Leads land in `/api/admin/nxt-chat/leads` for the workspace owner.
 */
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import Brand from "@/components/Brand";
import GradientBackdrop from "@/components/GradientBackdrop";
import NxtChatBot from "@/components/landing/NxtChatBot";
import PublicFooter from "@/components/PublicFooter";

export default function ContactPage() {
  return (
    <div
      className="relative min-h-screen w-full overflow-hidden flex flex-col"
      style={{ background: "var(--nxt-bg)", color: "var(--nxt-fg)" }}
      data-testid="contact-page"
    >
      <GradientBackdrop variant="auth" intensity="soft" />

      <header className="relative z-20 px-5 sm:px-10 pt-5 sm:pt-6 flex items-center justify-between">
        <Brand size="md" gradient />
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-[13px] px-3 py-2 transition-colors"
          style={{ color: "var(--nxt-fg-dim)" }}
          data-testid="contact-back"
        >
          <ArrowLeft size={13} /> Back
        </Link>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center">
        <div className="w-full max-w-[920px] px-5 sm:px-8 py-6 sm:py-10">
          <NxtChatBot inline />
        </div>
      </main>

      <div className="relative z-10">
        <PublicFooter />
      </div>
    </div>
  );
}
