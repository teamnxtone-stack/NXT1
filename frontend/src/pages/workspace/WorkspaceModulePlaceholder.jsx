/**
 * NXT1 — Generic module placeholder.
 *
 * Used by Drafts / Deployments / Domains / Providers / Settings / Site Editor
 * until each module has its dedicated implementation. Renders an elegant
 * empty state with a clear next-action; never feels broken or unfinished.
 */
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";

export default function WorkspaceModulePlaceholder({
  title,
  subtitle,
  rationale,
  icon: Icon,
  primary,
  secondary,
  testId,
  badge,
}) {
  const navigate = useNavigate();
  return (
    <div className="px-4 sm:px-8 pt-8 sm:pt-12 max-w-[820px] mx-auto" data-testid={testId}>
      <h1 className="text-2xl sm:text-[28px] font-semibold tracking-tight mb-1">{title}</h1>
      {subtitle && <p className="text-[13px] text-white/45 mb-6">{subtitle}</p>}

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="rounded-2xl p-7 sm:p-9 text-center"
        style={{
          background: "linear-gradient(180deg, rgba(48,48,56,0.45) 0%, rgba(36,36,40,0.45) 100%)",
          border: "1px solid rgba(255,255,255,0.06)",
          backdropFilter: "blur(14px) saturate(140%)",
        }}
      >
        {Icon && (
          <div
            className="mx-auto h-12 w-12 rounded-2xl flex items-center justify-center mb-4"
            style={{
              background: "rgba(94,234,212,0.10)",
              border: "1px solid rgba(94,234,212,0.22)",
            }}
          >
            <Icon size={18} className="text-[#5EEAD4]" />
          </div>
        )}
        {badge && (
          <div className="mono text-[9.5px] tracking-[0.32em] uppercase text-white/40 mb-2">{badge}</div>
        )}
        <div className="text-[16px] sm:text-[17px] text-white font-medium mb-1.5 tracking-tight">
          {rationale}
        </div>
        <div className="flex items-center justify-center gap-2 mt-5">
          {primary && (
            <button
              type="button"
              onClick={() => navigate(primary.to)}
              className="inline-flex items-center gap-1.5 h-10 px-4 rounded-xl text-[13.5px] font-semibold transition"
              style={{
                background: "#5EEAD4",
                color: "#1F1F23",
                boxShadow: "0 10px 26px -10px rgba(94,234,212,0.45)",
              }}
              data-testid={`${testId}-primary`}
            >
              {primary.label}
            </button>
          )}
          {secondary && (
            <button
              type="button"
              onClick={() => navigate(secondary.to)}
              className="h-10 px-4 rounded-xl text-[13.5px] text-white/75 hover:text-white transition"
              style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}
              data-testid={`${testId}-secondary`}
            >
              {secondary.label}
            </button>
          )}
        </div>
      </motion.div>
    </div>
  );
}
