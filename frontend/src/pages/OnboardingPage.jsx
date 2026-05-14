/**
 * OnboardingPage — first-run screen after signup. Captures use case + optional
 * custom build request, then routes to dashboard. Submission posts to
 * /api/users/me/onboarding (which also cross-posts to access_requests inbox).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import Brand from "@/components/Brand";
import GradientBackdrop from "@/components/GradientBackdrop";
import PublicFooter from "@/components/PublicFooter";
import { submitOnboarding, userMe } from "@/lib/api";

const USE_CASES = [
  { id: "build_app", label: "Build an app or SaaS" },
  { id: "build_website", label: "Build a website / marketing site" },
  { id: "build_api", label: "Build an API or backend service" },
  { id: "build_dashboard", label: "Build an internal tool / dashboard" },
  { id: "custom", label: "Custom engagement (Jwood Technologies team)" },
  { id: "exploring", label: "Just exploring" },
];

export default function OnboardingPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [form, setForm] = useState({
    company: "",
    use_case: "",
    request: "",
    referral: "",
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    userMe()
      .then(({ data }) => {
        setUser(data);
        if (data.role === "admin" || data.onboarded) navigate("/workspace");
      })
      .catch(() => navigate("/signin"));
  }, [navigate]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.use_case) {
      toast.error("Pick what you want to do.");
      return;
    }
    setSubmitting(true);
    try {
      await submitOnboarding(form);
      toast.success("You're in. Welcome to NXT1.");
      navigate("/workspace");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't save onboarding");
    } finally {
      setSubmitting(false);
    }
  };

  const skip = () => navigate("/workspace");

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden text-white flex flex-col"
      data-testid="onboarding-page"
      style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}
    >
      <GradientBackdrop intensity="medium" variant="auth" />
      <header className="relative z-20 px-6 sm:px-10 py-5 flex items-center justify-between">
        <Brand size="md" gradient />
        <button
          onClick={skip}
          className="text-[11px] tracking-wider uppercase text-white/55 hover:text-white transition"
          data-testid="onboarding-skip-button"
        >
          Skip for now →
        </button>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-5 py-10">
        <div
          className="w-full max-w-[640px] rounded-2xl border border-white/15 bg-graphite-scrim backdrop-blur-md p-6 sm:p-9"
          data-testid="onboarding-card"
        >
          <div className="mono text-[10px] tracking-[0.32em] uppercase text-emerald-300 mb-3 flex items-center gap-1.5">
            <Sparkles size={11} />
            Welcome{user?.name ? `, ${user.name.split(" ")[0]}` : ""}
          </div>
          <h1
            className="text-3xl sm:text-4xl font-black tracking-tighter mb-2"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
          >
            What do you want to build?
          </h1>
          <p className="text-white/70 text-sm mb-7 leading-relaxed">
            This helps NXT1 tailor the agent team to your work. You can change
            this later — or pick "Just exploring" and dive straight in.
          </p>

          <form onSubmit={submit} className="space-y-5">
            <fieldset>
              <legend className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-2">
                Primary use case <span className="text-[#ff8a3d]">*</span>
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
                      data-testid={`onboarding-usecase-${uc.id}`}
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
                data-testid="onboarding-company-input"
              />
            </label>

            <label className="block">
              <span className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-1.5">
                Briefly: what are you trying to build?
              </span>
              <textarea
                rows={3}
                value={form.request}
                onChange={(e) => setForm({ ...form, request: e.target.value })}
                placeholder="A roofing company website with online booking, calendar sync, and a customer portal."
                className="nxt-auth-input resize-y"
                data-testid="onboarding-request-input"
              />
              <span className="block text-[11px] text-white/45 mt-1.5 leading-snug">
                If you picked "Custom engagement", the Jwood Technologies team
                gets this directly.
              </span>
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
                data-testid="onboarding-referral-input"
              />
            </label>

            <div className="flex gap-2 pt-2">
              <button
                type="submit"
                disabled={submitting}
                className="nxt-btn-primary flex-1 !py-3 group"
                data-testid="onboarding-submit-button"
              >
                {submitting ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <>
                    Take me to NXT1
                    <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </main>
      <PublicFooter />
    </div>
  );
}
