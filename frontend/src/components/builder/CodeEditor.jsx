import Editor, { DiffEditor } from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
import { Save, RotateCcw, Loader2 } from "lucide-react";
import { upsertFile } from "@/lib/api";
import { toast } from "sonner";

const langOf = (path) => {
  if (!path) return "plaintext";
  if (path.endsWith(".html")) return "html";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".js") || path.endsWith(".jsx")) return "javascript";
  if (path.endsWith(".ts") || path.endsWith(".tsx")) return "typescript";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".py")) return "python";
  if (path.endsWith(".yml") || path.endsWith(".yaml")) return "yaml";
  return "plaintext";
};

const editorOpts = {
  fontFamily: "'JetBrains Mono', Menlo, monospace",
  fontSize: 13,
  lineHeight: 1.55,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  smoothScrolling: true,
  cursorBlinking: "smooth",
  renderLineHighlight: "gutter",
  padding: { top: 12, bottom: 12 },
  scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
  bracketPairColorization: { enabled: true },
  guides: { bracketPairs: true },
  formatOnPaste: false,
  formatOnType: false,
};

const defineNxtTheme = (monaco) => {
  monaco.editor.defineTheme("nxt1", {
    base: "vs-dark",
    inherit: true,
    rules: [],
    colors: {
      "editor.background": "#0d0d0d",
      "editor.foreground": "#f8f8f2",
      "editor.lineHighlightBackground": "#161616",
      "editorLineNumber.foreground": "#3a3a3e",
      "editorLineNumber.activeForeground": "#a1a1aa",
      "editor.selectionBackground": "#2a2a2e",
      "editor.inactiveSelectionBackground": "#1f1f22",
      "editorCursor.foreground": "#ffffff",
      "editorWidget.background": "#1F1F23",
      "editorIndentGuide.background": "#1a1a1a",
      "editorIndentGuide.activeBackground": "#2a2a2e",
    },
  });
};

export function CodeEditor({ projectId, file, onSaved }) {
  const editorRef = useRef(null);
  const [value, setValue] = useState(file?.content || "");
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setValue(file?.content || "");
    setDirty(false);
  }, [file?.path, file?.content]);

  const onMount = (editor, monaco) => {
    editorRef.current = editor;
    defineNxtTheme(monaco);
    monaco.editor.setTheme("nxt1");
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => save());
  };

  const save = async () => {
    if (!file || saving) return;
    setSaving(true);
    try {
      await upsertFile(projectId, file.path, value);
      toast.success(`Saved ${file.path}`);
      setDirty(false);
      onSaved?.(file.path, value);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    setValue(file?.content || "");
    setDirty(false);
  };

  if (!file) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
        Select a file to edit
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0" data-testid="code-editor">
      <div className="h-9 shrink-0 flex items-center justify-between px-3 border-b border-white/5">
        <span className="nxt-overline truncate max-w-[60%]">{file.path}</span>
        <div className="flex items-center gap-1">
          {dirty && (
            <span className="text-[11px] mono text-amber-300 mr-2">● unsaved</span>
          )}
          <button
            onClick={reset}
            disabled={!dirty || saving}
            className="nxt-btn !py-1 !px-2 !text-[11px]"
            data-testid="editor-reset"
          >
            <RotateCcw size={11} /> Reset
          </button>
          <button
            onClick={save}
            disabled={!dirty || saving}
            className="nxt-btn-primary !py-1 !px-2 !text-[11px]"
            data-testid="editor-save"
          >
            {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />} Save
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          theme="nxt1"
          language={langOf(file.path)}
          value={value}
          onChange={(v) => {
            setValue(v ?? "");
            setDirty(v !== file.content);
          }}
          onMount={onMount}
          options={editorOpts}
        />
      </div>
    </div>
  );
}

export function CodeDiffViewer({ original, modified, language }) {
  const onMount = (editor, monaco) => {
    defineNxtTheme(monaco);
    monaco.editor.setTheme("nxt1");
  };
  return (
    <div className="flex-1 min-h-0" data-testid="code-diff-viewer">
      <DiffEditor
        height="100%"
        theme="nxt1"
        original={original || ""}
        modified={modified || ""}
        language={language || "plaintext"}
        onMount={onMount}
        options={{
          ...editorOpts,
          renderSideBySide: true,
          readOnly: true,
          originalEditable: false,
        }}
      />
    </div>
  );
}

export { langOf };
