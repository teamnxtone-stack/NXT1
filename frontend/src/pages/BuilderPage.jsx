/**
 * Builder — bolt.diy mounted fullscreen.
 *
 * The legacy native builder (ChatPanel, PreviewPanel, FileExplorer,
 * BuilderBootSequence, BoltDiyOverlay) has been retired. The one and only
 * builder is bolt.diy, served from `services/bolt-engine` and reachable via
 * the public proxy under `/bolt/*`.
 *
 * We embed it via an iframe with `allow="cross-origin-isolated"` so the
 * inner WebContainer can run Node.js in-browser. The bolt-engine service
 * sets `Cross-Origin-Embedder-Policy: credentialless` + COOP itself; the
 * outer NXT1 shell doesn't need to be isolated, only the iframe.
 */
import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Brand from "@/components/Brand";

const BOLT_PATH = (process.env.REACT_APP_BOLT_URL || "/api/bolt-engine/").replace(/\/?$/, "/");

export default function BuilderPage() {
  const { projectId } = useParams();
  const [src, setSrc] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // Pass project id as a query string for future deep-linking. bolt.diy
    // currently ignores it; we keep it so we can wire context later without
    // changing the URL contract.
    const u = new URL(BOLT_PATH, window.location.origin);
    if (projectId) u.searchParams.set("project", projectId);
    setSrc(u.toString());
  }, [projectId]);

  return (
    <div
      className="fixed inset-0 flex flex-col"
      style={{ background: "var(--nxt-bg)", color: "var(--nxt-fg)" }}
      data-testid="builder-page"
    >
      {/* Slim NXT1 header — keeps brand + a way back to the workspace.
          bolt.diy renders its own chrome inside the iframe. */}
      <header
        className="shrink-0 flex items-center justify-between px-3 sm:px-4 h-12"
        style={{
          background: "var(--nxt-bg-2)",
          borderBottom: "1px solid var(--nxt-border)",
        }}
        data-testid="builder-header"
      >
        <div className="flex items-center gap-3">
          <Link
            to="/workspace"
            className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[12.5px] transition"
            style={{
              color: "var(--nxt-fg-dim)",
              border: "1px solid var(--nxt-border-soft)",
            }}
            data-testid="builder-back"
          >
            <ArrowLeft size={13} /> Workspace
          </Link>
          <span className="hidden sm:inline-flex items-center gap-2">
            <Brand size="sm" gradient />
            <span
              className="mono text-[10px] tracking-[0.22em] uppercase"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              · Builder
            </span>
          </span>
        </div>
        <a
          href={src || BOLT_PATH}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[12px] transition"
          style={{
            color: "var(--nxt-fg-dim)",
            border: "1px solid var(--nxt-border-soft)",
          }}
          data-testid="builder-open-new-tab"
          title="Open in new tab"
        >
          <ExternalLink size={12} />
          <span className="hidden sm:inline">New tab</span>
        </a>
      </header>

      {/* Loading flash so the iframe boot doesn't show a flash of black. */}
      {!loaded && (
        <div
          className="absolute inset-x-0 bottom-0 top-12 flex items-center justify-center"
          style={{ background: "var(--nxt-bg)" }}
        >
          <div className="mono text-[11px] tracking-[0.24em] uppercase opacity-60">
            Loading builder…
          </div>
        </div>
      )}

      {src && (
        <iframe
          key={src}
          src={src}
          title="NXT1 Builder"
          allow="cross-origin-isolated; clipboard-read; clipboard-write"
          // `credentialless` lets us iframe a COEP:require-corp document
          // without the outer page being cross-origin-isolated.
          // https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe#credentialless
          credentialless="true"
          onLoad={() => setLoaded(true)}
          className="flex-1 w-full border-0"
          style={{ background: "var(--nxt-bg)" }}
          data-testid="builder-iframe"
        />
      )}
    </div>
  );
}
