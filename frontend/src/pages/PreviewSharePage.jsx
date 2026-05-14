/**
 * PreviewSharePage — branded NXT1 wrapper around a shared preview.
 *
 * Loads the preview HTML client-side and renders it via iframe srcdoc so
 * neither the URL bar nor the iframe `src` attribute ever expose the
 * underlying backend host. The page reads as a clean NXT1-native experience.
 */
import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { Copy, ExternalLink, RefreshCw, Sparkles } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function PreviewSharePage() {
  const { slug } = useParams();
  const shareUrl = typeof window !== "undefined" ? window.location.href : "";
  const [copied, setCopied] = useState(false);
  const [html, setHtml] = useState("");
  const [status, setStatus] = useState("loading"); // loading | ready | private | missing | error
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    document.title = `Preview · NXT1`;
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    fetch(`${BACKEND_URL}/api/preview/${slug}`, { cache: "no-store" })
      .then(async (r) => {
        if (r.status === 403) {
          if (!cancelled) setStatus("private");
          return null;
        }
        if (r.status === 404) {
          if (!cancelled) setStatus("missing");
          return null;
        }
        if (!r.ok) {
          if (!cancelled) setStatus("error");
          return null;
        }
        let text = await r.text();
        // Rewrite any /api/preview/{slug}/... relative asset paths so the
        // iframe (srcdoc context) can resolve them. Avoids leaking the host
        // anywhere user-visible — only resolves at fetch time.
        text = text.replace(
          /((?:src|href)=["'])\/api\/preview\//g,
          `$1${BACKEND_URL}/api/preview/`
        );
        if (!cancelled) {
          setHtml(text);
          setStatus("ready");
        }
        return text;
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [slug, reloadKey]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* ignore */
    }
  };

  const openInNewTab = () => {
    if (!html) return;
    const w = window.open();
    if (w) {
      w.document.write(html);
      w.document.close();
    }
  };

  return (
    <div
      className="h-[100dvh] w-full surface-recessed flex flex-col"
      data-testid="preview-share-page"
    >
      <header
        className="h-12 shrink-0 border-b border-white/10 flex items-center justify-between px-3 sm:px-5 gap-3 bg-[#1F1F23]/95 backdrop-blur-md"
        data-testid="preview-share-header"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className="text-[14px] tracking-[0.18em] font-bold"
            style={{
              fontFamily: "'Cabinet Grotesk', sans-serif",
              backgroundImage:
                "linear-gradient(90deg,#5EEAD4 0%,#ffb86b 60%,#ff8a3d 100%)",
              backgroundClip: "text",
              WebkitBackgroundClip: "text",
              color: "transparent",
            }}
          >
            NXT1
          </span>
          <span className="hidden sm:inline-flex items-center gap-1 text-[10px] mono uppercase tracking-[0.32em] text-emerald-300/80">
            <Sparkles size={10} />
            preview
          </span>
          <span className="text-[11px] mono text-zinc-500 truncate max-w-[140px] sm:max-w-[260px] ml-2">
            /{slug}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => setReloadKey((k) => k + 1)}
            className="h-8 w-8 flex items-center justify-center rounded-full border border-white/15 text-zinc-300 hover:text-white hover:border-white/30 transition"
            data-testid="preview-share-reload-button"
            aria-label="Reload"
            title="Reload"
          >
            <RefreshCw size={12} />
          </button>
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] mono uppercase tracking-wider border border-white/15 text-zinc-200 hover:border-white/30 hover:text-white transition"
            data-testid="preview-share-copy-button"
          >
            <Copy size={11} />
            {copied ? "copied" : "copy link"}
          </button>
          <button
            type="button"
            onClick={openInNewTab}
            disabled={status !== "ready"}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] mono uppercase tracking-wider bg-white text-black hover:bg-zinc-200 transition disabled:opacity-50"
            data-testid="preview-share-open-button"
          >
            open
            <ExternalLink size={11} />
          </button>
        </div>
      </header>

      <div className="flex-1 min-h-0 bg-[#1F1F23] relative">
        {status === "loading" && <CenterMsg>loading preview…</CenterMsg>}
        {status === "missing" && (
          <CenterMsg>This preview link is invalid or has been removed.</CenterMsg>
        )}
        {status === "private" && (
          <CenterMsg>The owner has set this preview to private.</CenterMsg>
        )}
        {status === "error" && (
          <CenterMsg>Something went wrong loading this preview.</CenterMsg>
        )}
        {status === "ready" && (
          <iframe
            title="NXT1 preview"
            srcDoc={html}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            className="w-full h-full bg-white block"
            data-testid="preview-share-iframe"
          />
        )}
      </div>

      <div className="hidden sm:flex shrink-0 border-t border-white/5 surface-recessed px-5 py-2 items-center justify-between">
        <span className="text-[10px] mono uppercase tracking-[0.3em] text-zinc-600">
          built with nxt1 · jwood technologies
        </span>
        <span className="text-[10px] mono uppercase tracking-[0.3em] text-zinc-700">
          shareable preview · ephemeral · branded
        </span>
      </div>
    </div>
  );
}

function CenterMsg({ children }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center text-zinc-500 mono text-[12px] uppercase tracking-[0.3em]">
      <span className="inline-flex items-center gap-2">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
        {children}
      </span>
    </div>
  );
}

