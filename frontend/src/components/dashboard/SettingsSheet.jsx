/**
 * SettingsSheet — single bottom-sheet/right-drawer that holds settings the
 * user shouldn't see on the front of the dashboard:
 *   • Access Requests (admin inbox for the public form)
 *   • Secrets (masked configured/not configured list — never real values)
 *
 * Hidden by default, opened from the gear icon in the dashboard header.
 */
import { useEffect, useState } from "react";
import { Code2, Eye, EyeOff, Inbox, Key, Users } from "lucide-react";
import SheetOverlay from "@/components/builder/SheetOverlay";
import AccessRequestsPanel from "./AccessRequestsPanel";
import UsersPanel from "./UsersPanel";
import { getSecretsStatus } from "@/lib/api";
import { useDevMode } from "@/lib/devMode";

const TABS = [
  { id: "requests", label: "Requests", icon: Inbox },
  { id: "users", label: "Users", icon: Users },
  { id: "secrets", label: "Secrets", icon: Key },
  { id: "developer", label: "Developer", icon: Code2 },
];

export default function SettingsSheet({ open, onClose, initialTab = "requests" }) {
  const [tab, setTab] = useState(initialTab);
  useEffect(() => {
    if (open) setTab(initialTab);
  }, [open, initialTab]);

  return (
    <SheetOverlay
      open={open}
      onClose={onClose}
      title="Settings"
      size="md"
      testId="settings-sheet"
    >
      <div className="h-full flex flex-col">
        <div className="shrink-0 flex border-b border-white/10">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm transition ${
                tab === t.id
                  ? "text-white border-b-2 border-emerald-400 bg-white/[0.02]"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
              data-testid={`settings-tab-${t.id}`}
            >
              <t.icon size={13} />
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto">
          {tab === "requests" && (
            <div className="p-4">
              <AccessRequestsPanel />
            </div>
          )}
          {tab === "secrets" && <SecretsTab />}
          {tab === "users" && <UsersPanel />}
          {tab === "developer" && <DeveloperTab />}
        </div>
      </div>
    </SheetOverlay>
  );
}

function DeveloperTab() {
  const [devMode, setDev] = useDevMode();
  return (
    <div className="p-4 sm:p-5 space-y-5" data-testid="developer-tab">
      <div>
        <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500 mb-2">
          Developer Mode
        </div>
        <div className="border border-white/10 surface-1 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <span className="h-9 w-9 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
              <Code2 size={16} className="text-zinc-300" />
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-[14px] font-medium text-white">
                Show advanced developer tools
              </div>
              <div className="text-[12px] text-zinc-400 mt-1 leading-relaxed">
                When on, NXT1 surfaces the file explorer, Monaco editor, runtime
                logs, env vars, and version history inside Tools. Off, the
                chat-first experience hides everything that isn’t a deploy or
                domain action.
              </div>
            </div>
            <button
              type="button"
              onClick={() => setDev(!devMode)}
              className={`relative h-6 w-11 rounded-full border transition shrink-0 ${
                devMode
                  ? "bg-emerald-400/90 border-emerald-300"
                  : "bg-white/5 border-white/15"
              }`}
              data-testid="settings-dev-mode-toggle"
              aria-pressed={devMode}
              aria-label="Toggle developer mode"
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-[#1F1F23] shadow transition-all ${
                  devMode ? "left-[22px]" : "left-0.5"
                }`}
              />
            </button>
          </div>
          <div className="mt-4 flex items-center gap-2 text-[11px] mono uppercase tracking-wider">
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full border ${
                devMode
                  ? "text-emerald-300 border-emerald-400/30 bg-emerald-500/10"
                  : "text-zinc-400 border-white/10 bg-white/5"
              }`}
              data-testid="settings-dev-mode-status"
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  devMode ? "bg-emerald-400" : "bg-zinc-500"
                }`}
              />
              {devMode ? "developer · on" : "consumer · on"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function SecretsTab() {
  const [items, setItems] = useState([]);
  const [shown, setShown] = useState({});

  useEffect(() => {
    getSecretsStatus()
      .then(({ data }) => setItems(data.items || []))
      .catch(() => setItems([]));
  }, []);

  const grouped = items.reduce((acc, it) => {
    (acc[it.group] = acc[it.group] || []).push(it);
    return acc;
  }, {});
  const groupOrder = ["core", "ai", "deploy", "data"];
  const groupLabels = {
    core: "Core",
    ai: "AI providers",
    deploy: "Deploy & DNS",
    data: "Data & storage",
  };

  return (
    <div className="p-4 sm:p-5 space-y-6" data-testid="secrets-tab">
      <p className="text-[12px] text-zinc-500 leading-relaxed">
        These are the connections NXT1 uses to deploy, build, and run your
        software. Real values are never sent to the browser — you only see a
        configured / not-configured status. Update them server-side via the
        environment file.
      </p>
      {groupOrder.map((g) =>
        grouped[g] ? (
          <div key={g}>
            <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500 mb-2">
              {groupLabels[g]}
            </div>
            <div className="space-y-2">
              {grouped[g].map((it) => (
                <div
                  key={it.key}
                  className="border border-white/10 surface-1 rounded-xl p-3.5"
                  data-testid={`secret-${it.key}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="text-[11px] mono tracking-wider uppercase text-zinc-500">
                        {it.key}
                      </div>
                      <div className="text-sm text-white truncate">
                        {it.label}
                      </div>
                    </div>
                    <span
                      className={`mono text-[10px] tracking-wider px-2 py-1 rounded-full border ${
                        it.configured
                          ? "text-emerald-300 border-emerald-400/30 bg-emerald-500/10"
                          : "text-zinc-500 border-white/10 bg-white/5"
                      }`}
                    >
                      {it.configured ? "CONFIGURED" : "NOT SET"}
                    </span>
                  </div>
                  <div className="mt-2.5 flex items-center gap-2">
                    <div className="flex-1 h-9 px-3 flex items-center bg-graphite-scrim-soft border border-white/10 rounded-lg mono text-[13px] text-zinc-300 tracking-[0.18em]">
                      {it.configured
                        ? shown[it.key]
                          ? "(server-only)"
                          : it.masked
                        : ""}
                    </div>
                    {it.configured && (
                      <button
                        onClick={() =>
                          setShown((s) => ({ ...s, [it.key]: !s[it.key] }))
                        }
                        className="h-9 w-9 flex items-center justify-center rounded-lg bg-white/5 border border-white/10 text-zinc-400 hover:text-white"
                        title="Real values stay on the server"
                        data-testid={`secret-toggle-${it.key}`}
                      >
                        {shown[it.key] ? (
                          <Eye size={14} />
                        ) : (
                          <EyeOff size={14} />
                        )}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null
      )}
    </div>
  );
}
