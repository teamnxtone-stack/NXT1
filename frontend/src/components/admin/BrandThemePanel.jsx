/**
 * BrandThemePanel — form-driven editor for site brand & theme.
 *
 * The form payload is sent to POST /api/admin/brand which routes through the
 * existing site-editor pipeline (same diff, history, GitHub push, rollback).
 * After a propose, the operator reviews + applies the same way as a plain
 * Site Editor edit.
 */
import { useState } from "react";
import { Loader2, Palette, RotateCcw, Send, X } from "lucide-react";
import { toast } from "sonner";
import {
  adminUpdateBrand,
  siteEditorApply,
} from "@/lib/api";

const BUTTON_STYLES = ["rounded", "pill", "sharp"];
const SECTION_SPACINGS = ["compact", "comfortable", "airy"];

const FONT_OPTIONS = [
  "Cabinet Grotesk",
  "Inter",
  "IBM Plex Sans",
  "Space Grotesk",
  "Manrope",
  "Geist",
];

const EMPTY = {
  primary_color: "",
  accent_color: "",
  background_color: "",
  heading_font: "",
  body_font: "",
  wordmark: "",
  tagline: "",
  hero_headline: "",
  hero_subhead: "",
  primary_cta_label: "",
  secondary_cta_label: "",
  footer_attribution: "",
  button_style: "",
  section_spacing: "",
  notes: "",
};

export default function BrandThemePanel() {
  const [form, setForm] = useState(EMPTY);
  const [proposing, setProposing] = useState(false);
  const [proposal, setProposal] = useState(null);
  const [applying, setApplying] = useState(false);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const propose = async () => {
    // At least one field must have a value
    const filled = Object.entries(form).filter(([, v]) => v && v.toString().trim()).length;
    if (filled === 0) {
      toast.error("Set at least one field to propose a change.");
      return;
    }
    setProposing(true);
    setProposal(null);
    try {
      const { data } = await adminUpdateBrand(form);
      setProposal(data);
      toast.success("Proposal generated — review and apply.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't generate proposal");
    } finally {
      setProposing(false);
    }
  };

  const apply = async () => {
    if (!proposal) return;
    setApplying(true);
    try {
      const { data } = await siteEditorApply(proposal.edit_id, { push_to_github: true });
      const ghErr = data?.github?.error;
      if (ghErr) {
        toast.warning("Applied locally — GitHub push failed", { description: ghErr });
      } else if (data?.github?.repo_url) {
        toast.success("Applied + pushed. Vercel will auto-deploy.", {
          description: data.github.repo_url,
          action: { label: "Open repo", onClick: () => window.open(data.github.repo_url, "_blank") },
        });
      } else {
        toast.success("Applied to disk.");
      }
      setProposal(null);
      setForm(EMPTY);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Apply failed");
    } finally {
      setApplying(false);
    }
  };

  const reset = () => setForm(EMPTY);

  return (
    <div className="p-4 sm:p-6" data-testid="brand-theme-panel">
      <div className="max-w-3xl">
        <div className="mono text-[10px] tracking-[0.32em] uppercase text-zinc-500 mb-1.5">
          // brand &amp; theme
        </div>
        <h1
          className="text-2xl sm:text-3xl font-black tracking-tighter mb-1.5"
          style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
        >
          Visual identity, public copy, layout.
        </h1>
        <p className="text-zinc-400 text-[13px] mb-6 leading-relaxed">
          Fill any subset of fields below — leave the rest blank. Submitting
          generates a structured edit through the Site Editor pipeline; you
          review the diff, apply, and Vercel auto-deploys.
        </p>

        <Section title="Colors">
          <div className="grid sm:grid-cols-3 gap-3">
            <ColorField label="Primary" value={form.primary_color} onChange={(v) => set("primary_color", v)} testid="brand-primary-color" />
            <ColorField label="Accent" value={form.accent_color} onChange={(v) => set("accent_color", v)} testid="brand-accent-color" />
            <ColorField label="Background" value={form.background_color} onChange={(v) => set("background_color", v)} testid="brand-background-color" />
          </div>
        </Section>

        <Section title="Typography">
          <div className="grid sm:grid-cols-2 gap-3">
            <SelectField
              label="Heading font"
              value={form.heading_font}
              options={FONT_OPTIONS}
              onChange={(v) => set("heading_font", v)}
              testid="brand-heading-font"
            />
            <SelectField
              label="Body font"
              value={form.body_font}
              options={FONT_OPTIONS}
              onChange={(v) => set("body_font", v)}
              testid="brand-body-font"
            />
          </div>
        </Section>

        <Section title="Wordmark & tagline">
          <div className="grid sm:grid-cols-2 gap-3">
            <TextField
              label="Wordmark"
              value={form.wordmark}
              placeholder="NXT1"
              onChange={(v) => set("wordmark", v)}
              testid="brand-wordmark"
            />
            <TextField
              label="Tagline"
              value={form.tagline}
              placeholder="Discover · Develop · Deliver"
              onChange={(v) => set("tagline", v)}
              testid="brand-tagline"
            />
          </div>
        </Section>

        <Section title="Public hero">
          <TextField
            label="Hero headline"
            value={form.hero_headline}
            placeholder="Software, from ideas."
            onChange={(v) => set("hero_headline", v)}
            testid="brand-hero-headline"
          />
          <TextField
            label="Hero sub-headline"
            value={form.hero_subhead}
            placeholder="NXT1 turns natural language into real apps, websites, APIs…"
            multiline
            onChange={(v) => set("hero_subhead", v)}
            testid="brand-hero-subhead"
          />
          <div className="grid sm:grid-cols-2 gap-3">
            <TextField
              label="Primary CTA label"
              value={form.primary_cta_label}
              placeholder="Sign Up — start building"
              onChange={(v) => set("primary_cta_label", v)}
              testid="brand-cta-primary"
            />
            <TextField
              label="Secondary CTA label"
              value={form.secondary_cta_label}
              placeholder="Sign In"
              onChange={(v) => set("secondary_cta_label", v)}
              testid="brand-cta-secondary"
            />
          </div>
        </Section>

        <Section title="Footer & legal">
          <TextField
            label="Footer attribution"
            value={form.footer_attribution}
            placeholder="A product of Jwood Technologies"
            onChange={(v) => set("footer_attribution", v)}
            testid="brand-footer-attribution"
          />
        </Section>

        <Section title="Layout presets">
          <div className="grid sm:grid-cols-2 gap-3">
            <ChipsField
              label="Button style"
              value={form.button_style}
              options={BUTTON_STYLES}
              onChange={(v) => set("button_style", v)}
              testid="brand-button-style"
            />
            <ChipsField
              label="Section spacing"
              value={form.section_spacing}
              options={SECTION_SPACINGS}
              onChange={(v) => set("section_spacing", v)}
              testid="brand-section-spacing"
            />
          </div>
        </Section>

        <Section title="Notes for the agent (optional)">
          <TextField
            label=""
            value={form.notes}
            multiline
            placeholder="Anything else worth knowing about this change."
            onChange={(v) => set("notes", v)}
            testid="brand-notes"
          />
        </Section>

        <div className="flex flex-wrap gap-2 mt-2">
          <button
            type="button"
            onClick={propose}
            disabled={proposing}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-emerald-400 text-black text-sm font-semibold hover:bg-emerald-300 transition disabled:opacity-60"
            data-testid="brand-propose"
          >
            {proposing ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} strokeWidth={2.5} />}
            {proposing ? "Generating proposal…" : "Propose changes"}
          </button>
          <button
            type="button"
            onClick={reset}
            disabled={proposing}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-transparent border border-white/15 text-zinc-200 text-sm hover:border-white/30 hover:text-white transition disabled:opacity-60"
            data-testid="brand-reset"
          >
            <RotateCcw size={13} />
            Reset
          </button>
        </div>

        {proposal && (
          <BrandProposalCard
            proposal={proposal}
            applying={applying}
            onApply={apply}
            onDiscard={() => setProposal(null)}
          />
        )}
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="mb-5 pb-5 border-b border-white/5 last:border-0">
      <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500 mb-3 flex items-center gap-1.5">
        <Palette size={10} />
        {title}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function FieldLabel({ children }) {
  return (
    <span className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-1.5">
      {children}
    </span>
  );
}

function TextField({ label, value, onChange, placeholder, multiline, testid }) {
  return (
    <label className="block">
      {label && <FieldLabel>{label}</FieldLabel>}
      {multiline ? (
        <textarea
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="nxt-auth-input resize-y"
          data-testid={testid}
        />
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="nxt-auth-input"
          data-testid={testid}
        />
      )}
    </label>
  );
}

function ColorField({ label, value, onChange, testid }) {
  const valid = /^#[0-9a-fA-F]{6}$/.test(value || "");
  return (
    <label className="block">
      <FieldLabel>{label}</FieldLabel>
      <div className="flex items-stretch gap-2">
        <input
          type="color"
          value={valid ? value : "#1F1F23"}
          onChange={(e) => onChange(e.target.value)}
          className="h-10 w-12 rounded-lg bg-[#1F1F23] border border-white/10 cursor-pointer"
          data-testid={`${testid}-picker`}
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="#5EEAD4"
          className="nxt-auth-input flex-1 mono text-[12.5px]"
          data-testid={testid}
        />
      </div>
    </label>
  );
}

function SelectField({ label, value, options, onChange, testid }) {
  return (
    <label className="block">
      <FieldLabel>{label}</FieldLabel>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="nxt-auth-input appearance-none cursor-pointer"
        data-testid={testid}
      >
        <option value="">— unchanged —</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

function ChipsField({ label, value, options, onChange, testid }) {
  return (
    <div>
      <FieldLabel>{label}</FieldLabel>
      <div className="flex flex-wrap gap-1.5" data-testid={testid}>
        {options.map((o) => {
          const sel = value === o;
          return (
            <button
              type="button"
              key={o}
              onClick={() => onChange(sel ? "" : o)}
              className={`px-3 py-1.5 rounded-full text-[11.5px] mono uppercase tracking-wider border transition ${
                sel
                  ? "bg-white text-black border-white"
                  : "border-white/15 text-zinc-300 hover:border-white/30 hover:text-white"
              }`}
              data-testid={`${testid}-${o}`}
            >
              {o}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function BrandProposalCard({ proposal, applying, onApply, onDiscard }) {
  return (
    <div
      className="mt-5 rounded-2xl border border-emerald-400/25 bg-gradient-to-br from-[#0d1614] via-[#1F1F23] to-[#1F1F23] p-5"
      data-testid="brand-proposal"
    >
      <div className="flex items-start gap-3 mb-3">
        <span className="h-9 w-9 rounded-full bg-emerald-500/15 border border-emerald-400/30 flex items-center justify-center shrink-0">
          <Palette size={14} className="text-emerald-300" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] mono uppercase tracking-[0.28em] text-emerald-400 mb-1">
            Brand & Theme proposal · {proposal.files?.length || 0} files
          </div>
          <div className="text-[15px] font-semibold text-emerald-100 mb-1.5">
            {proposal.summary}
          </div>
          {proposal.explanation && (
            <p className="text-[13px] text-zinc-300 leading-relaxed">
              {proposal.explanation}
            </p>
          )}
        </div>
      </div>
      <div className="space-y-1.5 mb-4">
        {(proposal.files || []).map((f) => (
          <div
            key={f.path}
            className="flex items-center gap-2 text-[12px] mono text-zinc-300 bg-graphite-scrim-soft border border-white/5 rounded-lg px-3 py-2"
          >
            <span className="truncate">{f.path}</span>
            <span className="ml-auto text-zinc-500">{(f.content || "").length.toLocaleString()} chars</span>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          onClick={onApply}
          disabled={applying}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-emerald-400 text-black text-sm font-semibold shadow hover:bg-emerald-300 transition disabled:opacity-60"
          data-testid="brand-apply"
        >
          {applying ? <Loader2 size={13} className="animate-spin" /> : null}
          {applying ? "Pushing to GitHub…" : "Apply + push"}
        </button>
        <button
          onClick={onDiscard}
          disabled={applying}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-transparent border border-white/15 text-zinc-200 text-sm hover:border-white/30 hover:text-white transition disabled:opacity-60"
          data-testid="brand-discard"
        >
          <X size={13} />
          Discard
        </button>
      </div>
    </div>
  );
}
