import { useMemo, useRef, useState } from "react";
import {
  FileCode,
  FileText,
  Image as ImageIcon,
  Upload,
  Loader2,
  ChevronDown,
  ChevronRight,
  Folder,
  Trash2,
  Pencil,
} from "lucide-react";
import { uploadAsset, deleteFile, deleteAsset, assetUrl, renameFile } from "@/lib/api";
import { toast } from "sonner";
import ImagePreviewModal from "@/components/builder/ImagePreviewModal";
import { useFileActivity } from "@/lib/fileActivity";

const iconFor = (path) => {
  if (path.endsWith(".html")) return <FileCode size={13} className="text-orange-400" />;
  if (path.endsWith(".css")) return <FileCode size={13} className="text-blue-400" />;
  if (path.endsWith(".js")) return <FileCode size={13} className="text-yellow-400" />;
  if (path.endsWith(".md")) return <FileText size={13} className="text-zinc-300" />;
  if (path.endsWith(".json")) return <FileCode size={13} className="text-emerald-400" />;
  if (path.endsWith(".py")) return <FileCode size={13} className="text-sky-400" />;
  if (/\.(png|jpe?g|gif|svg|webp)$/i.test(path)) return <ImageIcon size={13} className="text-emerald-400" />;
  return <FileText size={13} className="text-zinc-400" />;
};

// Build a tree of folders/files from a flat list of paths
function buildTree(paths) {
  const root = { name: "", path: "", children: {}, files: [] };
  for (const p of paths) {
    const parts = p.split("/");
    let node = root;
    let cur = "";
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      cur = cur ? `${cur}/${part}` : part;
      if (!node.children[part]) {
        node.children[part] = { name: part, path: cur, children: {}, files: [] };
      }
      node = node.children[part];
    }
    node.files.push({ path: p, name: parts[parts.length - 1] });
  }
  return root;
}

// Flatten tree to a render list with depth + open-state.
// Avoid mutual-recursion components (which previously caused a Babel
// "Maximum call stack size exceeded" compile error).
function flattenTree(root, openMap) {
  const out = [];
  const walk = (node, depth) => {
    const folders = Object.values(node.children).sort((a, b) => a.name.localeCompare(b.name));
    for (const f of folders) {
      const isOpen = openMap[f.path] !== false; // default open
      out.push({ kind: "folder", node: f, depth, open: isOpen });
      if (isOpen) walk(f, depth + 1);
    }
    const files = (node.files || []).slice().sort((a, b) => a.name.localeCompare(b.name));
    for (const f of files) {
      out.push({ kind: "file", file: f, depth });
    }
  };
  walk(root, 1);
  return out;
}

export default function FileExplorer({
  files,
  assets,
  activeFile,
  onSelect,
  onAssetUploaded,
  onFilesChanged,
  projectId,
}) {
  const fileInput = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [openMap, setOpenMap] = useState({}); // path -> bool
  const [renaming, setRenaming] = useState(null); // path being renamed
  const [renameValue, setRenameValue] = useState("");
  const [previewAsset, setPreviewAsset] = useState(null);
  const activity = useFileActivity();   // { [path]: { state: "writing"|"recent", since } }

  const tree = useMemo(() => buildTree((files || []).map((f) => f.path)), [files]);
  const items = useMemo(() => flattenTree(tree, openMap), [tree, openMap]);

  const toggle = (path) => setOpenMap((m) => ({ ...m, [path]: m[path] === false ? true : false }));

  const onUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      await uploadAsset(projectId, f);
      toast.success(`Uploaded ${f.name}`);
      onAssetUploaded?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleRenameSubmit = async (e, oldPath) => {
    e.preventDefault?.();
    const newPath = (renameValue || "").trim();
    if (!newPath || newPath === oldPath) {
      setRenaming(null);
      return;
    }
    if ((files || []).some((f) => f.path === newPath)) {
      toast.error(`${newPath} already exists`);
      return;
    }
    try {
      await renameFile(projectId, oldPath, newPath);
      toast.success(`Renamed to ${newPath}`);
      setRenaming(null);
      onFilesChanged?.();
      if (activeFile === oldPath) onSelect?.(newPath);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Rename failed");
    }
  };

  const handleDeleteFile = async (path) => {
    if (!window.confirm(`Delete ${path}?`)) return;
    try {
      await deleteFile(projectId, path);
      toast.success(`Deleted ${path}`);
      onFilesChanged?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Delete failed");
    }
  };

  const handleDeleteAsset = async (id, name) => {
    if (!window.confirm(`Delete asset ${name}?`)) return;
    try {
      await deleteAsset(projectId, id);
      toast.success(`Deleted ${name}`);
      onAssetUploaded?.();
    } catch {
      toast.error("Delete failed");
    }
  };

  return (
    <div className="flex flex-col h-full surface-recessed" data-testid="file-explorer">
      <div className="h-10 shrink-0 flex items-center px-3 border-b border-white/5">
        <span className="nxt-overline">// explorer</span>
      </div>
      <div className="flex-1 overflow-y-auto py-2 mono text-[13px]" data-testid="file-explorer-tree">
        <div className="flex items-center gap-1 px-2 py-1 text-zinc-300">
          <ChevronDown size={11} />
          <Folder size={12} className="text-zinc-500" />
          <span className="text-xs">project</span>
        </div>

        {items.map((it, idx) => {
          if (it.kind === "folder") {
            return (
              <button
                key={`f-${it.node.path}-${idx}`}
                onClick={() => toggle(it.node.path)}
                className="flex items-center gap-1 w-full text-left text-zinc-400 hover:text-white py-0.5"
                style={{ paddingLeft: 8 + it.depth * 12 }}
              >
                {it.open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                <Folder size={12} className="text-zinc-500" />
                <span className="text-xs">{it.node.name}</span>
              </button>
            );
          }
          const f = it.file;
          const active = activeFile === f.path;
          const act = activity[f.path]?.state;   // "writing" | "recent" | undefined
          if (renaming === f.path) {
            return (
              <form
                key={`rename-${f.path}`}
                onSubmit={(e) => handleRenameSubmit(e, f.path)}
                style={{ paddingLeft: 8 + it.depth * 12 }}
                className="flex items-center gap-1 py-0.5"
              >
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onBlur={(e) => handleRenameSubmit(e, f.path)}
                  onKeyDown={(e) => { if (e.key === "Escape") setRenaming(null); }}
                  className="nxt-input !py-0.5 !px-1 text-[12px] mono"
                  data-testid={`rename-input-${f.path}`}
                />
              </form>
            );
          }
          return (
            <div
              key={`file-${f.path}`}
              className={`flex items-center gap-2 group transition rounded-sm ${
                active
                  ? "bg-white/10 text-white"
                  : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
              }`}
              style={{ paddingLeft: 8 + it.depth * 12 }}
            >
              <button
                onClick={() => onSelect?.(f.path)}
                onDoubleClick={() => {
                  if (f.path === "index.html") return;
                  setRenameValue(f.path);
                  setRenaming(f.path);
                }}
                className="flex-1 flex items-center gap-2 text-left px-2 py-1 min-w-0"
                data-testid={`file-item-${f.path}`}
                title="Double-click to rename"
              >
                {iconFor(f.path)}
                <span className="truncate">{f.name}</span>
                {act ? (
                  <span
                    aria-hidden
                    title={act === "writing" ? "writing…" : "recently changed"}
                    className={[
                      "ml-auto mr-1 inline-block h-1.5 w-1.5 rounded-full shrink-0",
                      act === "writing"
                        ? "bg-[#C8B98C] animate-pulse"
                        : "bg-[#C8B98C]/60",
                    ].join(" ")}
                    data-testid={`file-activity-${act}-${f.path}`}
                  />
                ) : null}
              </button>
              {f.path !== "index.html" && (
                <>
                  <button
                    onClick={() => { setRenameValue(f.path); setRenaming(f.path); }}
                    className="opacity-0 group-hover:opacity-100 transition text-zinc-500 hover:text-white px-1"
                    title="Rename"
                    data-testid={`rename-file-${f.path}`}
                  >
                    <Pencil size={10} />
                  </button>
                  <button
                    onClick={() => handleDeleteFile(f.path)}
                    className="opacity-0 group-hover:opacity-100 transition text-zinc-500 hover:text-red-400 px-1.5"
                    title="Delete file"
                    data-testid={`delete-file-${f.path}`}
                  >
                    <Trash2 size={11} />
                  </button>
                </>
              )}
            </div>
          );
        })}

        <div className="mt-3 border-t border-white/5 pt-2">
          <div className="flex items-center gap-1 px-2 py-1 text-zinc-400">
            <ChevronDown size={11} />
            <Folder size={12} className="text-zinc-500" />
            <span className="text-xs">assets</span>
            <span className="ml-auto nxt-overline text-zinc-600">{(assets || []).length}</span>
          </div>
          {(assets || []).length === 0 ? (
            <div className="px-7 py-1 text-zinc-600 text-xs">(none)</div>
          ) : (
            assets.map((a) => {
              const isImg = /\.(png|jpe?g|gif|svg|webp)$/i.test(a.filename);
              return (
                <div
                  key={a.id}
                  className="group flex items-center gap-2 px-2 py-1 pl-7 text-zinc-400 text-xs hover:bg-white/5 transition"
                  data-testid={`asset-${a.filename}`}
                >
                  {isImg ? (
                    <button onClick={() => setPreviewAsset(a)} className="shrink-0" title="Preview">
                      <img
                        src={assetUrl(projectId, a.filename)}
                        alt=""
                        className="h-4 w-4 object-cover rounded-sm border border-white/10"
                      />
                    </button>
                  ) : (
                    iconFor(a.filename)
                  )}
                  <button
                    onClick={() => isImg && setPreviewAsset(a)}
                    className="truncate flex-1 text-left hover:text-white transition"
                    data-testid={`asset-open-${a.filename}`}
                  >
                    {a.filename}
                  </button>
                  <button
                    onClick={() => handleDeleteAsset(a.id, a.filename)}
                    className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 px-1"
                    title="Delete asset"
                  >
                    <Trash2 size={10} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
      <div className="shrink-0 p-2 border-t border-white/5">
        <button
          onClick={() => fileInput.current?.click()}
          disabled={uploading}
          className="nxt-btn w-full !py-2 !text-xs"
          data-testid="upload-asset-button"
        >
          {uploading ? (
            <>
              <Loader2 size={12} className="animate-spin" /> Uploading
            </>
          ) : (
            <>
              <Upload size={12} /> Upload Asset
            </>
          )}
        </button>
        <input
          ref={fileInput}
          type="file"
          className="hidden"
          onChange={onUpload}
          accept="image/*,.txt,.json,.csv,.pdf"
        />
      </div>
      <ImagePreviewModal
        projectId={projectId}
        asset={previewAsset}
        onClose={() => setPreviewAsset(null)}
      />
    </div>
  );
}
