/**
 * BoltDiyOverlay — when bolt.diy sidecar is reachable, takes over the
 * entire BuilderPage with a full-page iframe (the new primary builder).
 * When NOT reachable (preview pod, fresh self-host without --profile builder),
 * renders a small dismissable banner above the existing NXT1 builder so the
 * legacy flow stays usable for demos.
 *
 * Set BOLT_DIY_URL in your .env to override the default http://localhost:5173.
 */
import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import api from "@/lib/api";

export default function BoltDiyOverlay() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let cancel = false;
    const probe = async () => {
      try {
        const r = await api.get("/v1/agentos/builder/status");
        if (!cancel) setStatus(r.data);
      } catch {
        if (!cancel) setStatus({ reachable: false, url: "http://localhost:5173" });
      }
    };
    probe();
    const t = setInterval(probe, 30_000);
    return () => { cancel = true; clearInterval(t); };
  }, []);

  // bolt.diy is up — take over the entire screen
  if (status?.reachable) {
    return (
      <div
        className="fixed inset-0 z-[60] flex flex-col"
        style={{ background: "#0A0A0B" }}
        data-testid="boltdiy-overlay"
      >
        <header
          className="flex items-center gap-3 h-11 px-3 sm:px-4"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
        >
          <span className="mono text-[10.5px] tracking-[0.28em] uppercase"
                style={{ color: "rgba(255,255,255,0.45)" }}>builder · bolt.diy</span>
          <span className="ml-1 mono text-[9.5px] px-1.5 py-0.5 rounded font-semibold"
                style={{ background: "rgba(94,234,212,0.18)", color: "#5EEAD4" }}>READY</span>
          <span className="flex-1" />
          <a
            href={status.url}
            target="_blank"
            rel="noreferrer"
            className="text-[11.5px] inline-flex items-center gap-1 opacity-70 hover:opacity-100"
            style={{ color: "#FAFAFA" }}
          >
            Open in new tab <ExternalLink size={11} />
          </a>
        </header>
        <iframe
          title="bolt.diy"
          src={status.url}
          className="flex-1 w-full border-0"
          style={{ background: "#0A0A0B" }}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-downloads"
        />
      </div>
    );
  }

  // bolt.diy not running — render NOTHING. The existing NXT1 builder
  // stays fully functional below; no banner, no tech-y bash hints.
  return null;
}
