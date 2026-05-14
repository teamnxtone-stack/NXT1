/**
 * RequestAccessWall — shown to authenticated users whose access_status !==
 * "approved". They have an account but aren't yet admitted to the full
 * platform. Submit form cross-posts into the admin Requests inbox.
 */
import { useEffect, useState } from "react";
import { Loader2, LogOut, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";
import Brand from "@/components/Brand";
import GradientBackdrop from "@/components/GradientBackdrop";
import PublicFooter from "@/components/PublicFooter";
import { submitOnboarding } from "@/lib/api";
import { clearToken } from "@/lib/auth";

const USE_CASES = [
  { id: "build_app", label: "Build an app or SaaS" },
  { id: "build_website", label: "Build a website" },
  { id: "build_api", label: "Build an API or backend" },
  { id: "build_dashboard", label: "Internal tool / dashboard" },
  { id: "custom", label: "Custom engagement (Jwood Technologies)" },
  { id: "exploring", label: "Just exploring" },
];

export default function RequestAccessWall({ user }) {
  const [form, setForm] = useState({
    company: "",
    use_case: "",
    request: "",
    referral: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(user?.onboarded || false);

  useEffect(() => {
    setSubmitted(user?.onboarded || false);
  }, [user?.onboarded]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.use_case) {
      toast.error("Pick what you want to do.");
      return;
    }
    setSubmitting(true);
    try {
      await submitOnboarding(form);
      setSubmitted(true);
      toast.success("Request submitted. We'll be in touch.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't submit request");
    } finally {
      setSubmitting(false);
    }
  };

  const signOut = () => {
    clearToken();
    window.location.href = "/";
  };

  const denied = user?.access_status === "denied";

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden text-white flex flex-col"
      data-testid="request-access-wall"
      style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}
    >
      <GradientBackdrop intensity="medium" />
      <header className="relative z-20 px-6 sm:px-10 py-5 flex items-center justify-between">
        <Brand size="md" gradient />
        <button
          onClick={signOut}
          className="inline-flex items-center gap-1.5 text-[12px] tracking-wider uppercase text-white/55 hover:text-white transition"
          data-testid="request-wall-signout"
        >
          <LogOut size={12} />
          Sign out
        </button>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-5 py-10">
        <div
          className="w-full max-w-[640px] rounded-2xl border border-white/15 bg-graphite-scrim backdrop-blur-md p-6 sm:p-9"
          data-testid="request-access-card"
        >
          <div className={`mono text-[10px] tracking-[0.32em] uppercase mb-3 flex items-center gap-1.5 ${
            denied ? "text-amber-300" : "text-emerald-300"
          }`}>
            {denied ? <ShieldCheck size={11} /> : <Sparkles size={11} />}
            {denied ? "Access not yet granted" : `Welcome${user?.name ? `, ${user.name.split(" ")[0]}` : ""}`}
          </div>
          <h1
            className="text-3xl sm:text-4xl font-black tracking-tighter mb-2"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
          >
            {submitted ? "Request received." : "Request access."}
          </h1>
          <p className="text-white/70 text-sm mb-7 leading-relaxed">
            {submitted ? (
              <>
                NXT1 is a private build during the Jwood Technologies beta. The
                team will review your request and email you at{" "}
                <span className="text-white">{user?.email}</span> when access
                is granted. You'll see the full studio the next time you sign in.
              </>
            ) : (
              <>
                NXT1 is currently a private build. Tell us a little about what
                you'd like to build and the Jwood Technologies team will grant
                access shortly. You'll keep this account.
              </>
            )}
          </p>

          {!submitted && (
            <form onSubmit={submit} className="space-y-5">
              <fieldset>
                <legend className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-2">
                  What do you want to do? <span className="text-[#ff8a3d]">*</span>
                </legend>
                <div className="grid sm:grid-cols-2 gap-2">
                  {USE_CASES.map((uc) => {
                    const sel = form.use_case === uc.id;
                    return (
                      <label
                        key={uc.id}
                        className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg border cursor-pointer transition ${
                          sel
                            ? "border-emerald-400/50 bg-emerald-500/10 text-white"
                            : "border-white/10 bg-white/[0.02] text-white/80 hover:border-white/25"
                        }`}
                        data-testid={`request-usecase-${uc.id}`}
                      >
                        <input
                          type="radio"
                          name="use_case"
                          value={uc.id}
                          checked={sel}
                          onChange={() => setForm({ ...form, use_case: uc.id })}
                          className="accent-emerald-400 shrink-0"
                        />
                        <span className="text-[13px] leading-snug">{uc.label}</span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <label className="block">
                <span className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-1.5">
                  Company / Project name (optional)
                </span>
                <input
                  value={form.company}
                  onChange={(e) => setForm({ ...form, company: e.target.value })}
                  placeholder="Acme, Inc."
                  className="nxt-auth-input"
                  data-testid="request-company-input"
                />
              </label>

              <label className="block">
                <span className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-1.5">
                  What are you trying to build?
                </span>
                <textarea
                  rows={3}
                  value={form.request}
                  onChange={(e) => setForm({ ...form, request: e.target.value })}
                  placeholder="A roofing company website with online booking, calendar sync, and a customer portal."
                  className="nxt-auth-input resize-y"
                  data-testid="request-request-input"
                />
              </label>

              <label className="block">
                <span className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-1.5">
                  How did you hear about NXT1? (optional)
                </span>
                <input
                  value={form.referral}
                  onChange={(e) => setForm({ ...form, referral: e.target.value })}
                  placeholder="Twitter, friend, search…"
                  className="nxt-auth-input"
                  data-testid="request-referral-input"
                />
              </label>

              <button
                type="submit"
                disabled={submitting}
                className="nxt-btn-primary w-full !py-3 mt-2"
                data-testid="request-submit-button"
              >
                {submitting ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <>Request access</>
                )}
              </button>
            </form>
          )}

          {submitted && (
            <div
              className="rounded-xl border border-emerald-400/20 bg-emerald-500/[0.06] p-4 text-[13px] text-emerald-100 leading-relaxed"
              data-testid="request-submitted-state"
            >
              Your account is signed in but not yet activated. We don't expose
              the studio until access is approved. You can sign out and check
              back later — your request stays on file.
            </div>
          )}
        </div>
      </main>
      <PublicFooter />
    </div>
  );
}
