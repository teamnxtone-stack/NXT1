import { X, Download } from "lucide-react";
import { assetUrl } from "@/lib/api";

export default function ImagePreviewModal({ projectId, asset, onClose }) {
  if (!asset) return null;
  const url = assetUrl(projectId, asset.filename);
  return (
    <div
      className="fixed inset-0 z-50 bg-graphite-scrim-strong backdrop-blur-sm flex items-center justify-center p-6"
      onClick={onClose}
      data-testid="image-preview-modal"
    >
      <div
        className="nxt-panel rounded-sm bg-[#1F1F23] max-w-[92vw] max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="h-11 shrink-0 flex items-center justify-between px-4 border-b border-white/5">
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">{asset.filename}</div>
            <div className="nxt-overline">{Math.round((asset.size || 0) / 1024)} KB · {asset.content_type}</div>
          </div>
          <div className="flex items-center gap-2">
            <a
              href={url}
              download={asset.filename}
              className="nxt-btn !py-1.5 !px-3"
              data-testid="image-preview-download"
            >
              <Download size={12} /> Download
            </a>
            <button onClick={onClose} className="p-1.5 text-zinc-500 hover:text-white" aria-label="Close">
              <X size={16} />
            </button>
          </div>
        </div>
        <div className="flex-1 min-h-0 overflow-auto p-6 flex items-center justify-center surface-0">
          <img
            src={url}
            alt={asset.filename}
            className="max-w-full max-h-[78vh] object-contain"
            style={{ imageRendering: "auto" }}
          />
        </div>
      </div>
    </div>
  );
}
