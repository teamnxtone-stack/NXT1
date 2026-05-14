/**
 * OpenReelOverlay — when the OpenReel video-studio sidecar is reachable, takes
 * over the entire StudioPage with a full-page iframe (the primary video editor).
 * When NOT reachable, renders nothing — the native Fal.ai Studio stays the
 * dormant fallback so nothing breaks.
 *
 * Set STUDIO_URL in backend .env to override the default http://localhost:5174.
 */
import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import api from "@/lib/api";

function isPublicUrl(url) {
  if (!url) return false;
  return /^https?:\/\//i.test(url) &&
         !/(localhost|127\.0\.0\.1|0\.0\.0\.0)/i.test(url);
}

export default function OpenReelOverlay() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let cancel = false;
    const probe = async () => {
      try {
        const r = await api.get("/v1/agentos/studio/status");
        if (!cancel) setStatus(r.data);
      } catch {
        if (!cancel) setStatus({ reachable: false, url: "" });
      }
    };
    probe();
    const t = setInterval(probe, 30_000);
    return () => { cancel = true; clearInterval(t); };
  }, []);

  if (!status?.reachable || !isPublicUrl(status.url)) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex flex-col"
      style={{ background: "#0A0A0B" }}
      data-testid="openreel-overlay"
    >
      <header
        className="flex items-center gap-3 h-11 px-3 sm:px-4"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <span className="mono text-[10.5px] tracking-[0.28em] uppercase"
              style={{ color: "rgba(255,255,255,0.45)" }}>studio · openreel</span>
        <span className="ml-1 mono text-[9.5px] px-1.5 py-0.5 rounded font-semibold"
              style={{ background: "rgba(167,139,250,0.18)", color: "#A78BFA" }}>READY</span>
        <span className="flex-1" />
        <a
          href={status.url}
          target="_blank"
          rel="noreferrer"
          className="text-[11.5px] inline-flex items-center gap-1 opacity-70 hover:opacity-100"
          style={{ color: "#FAFAFA" }}
          data-testid="openreel-open-tab"
        >
          Open in new tab <ExternalLink size={11} />
        </a>
      </header>
      <iframe
        title="openreel"
        src={status.url}
        className="flex-1 w-full border-0"
        style={{ background: "#0A0A0B" }}
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-downloads"
      />
    </div>
  );
}
