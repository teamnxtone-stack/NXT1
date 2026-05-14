"""NXT1 — Scaffold registry (Phase 11 W4 — Track 1).

All built-in scaffolds are declared here. Each scaffold has:
  id            (slug)
  label         (display)
  framework     ("Next.js" / "React + Vite" / "Expo" / …)
  kind          (matches inference_service kinds for auto-selection)
  capabilities  (free-form tags for UI filtering)
  package_manager ("pnpm" | "yarn" | "npm" | "pip" | "none")
  build_command   string
  start_command   string
  preview_command string
  env_vars      list of required env var names
  files         dict of (relative path -> file content)
  notes         string with deployment hints

Real generation today only consumes the manifest fields — file contents
are used as the *initial baseline* the AI customises. The contents kept
in _BUILTIN are intentionally minimal: enough to build, preview, and
deploy cleanly. Generation extends from there.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Minimal-but-real file bodies. Kept short so the registry stays readable.
# All files are valid out-of-the-box — the AI extends them per prompt.
# ---------------------------------------------------------------------------
_PKG_REACT_VITE = '{\n  "name": "nxt1-app",\n  "private": true,\n  "version": "0.1.0",\n  "type": "module",\n  "scripts": {\n    "dev": "vite",\n    "build": "vite build",\n    "preview": "vite preview"\n  },\n  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1" },\n  "devDependencies": { "@vitejs/plugin-react": "^4.3.4", "vite": "^5.4.10", "tailwindcss": "^3.4.13", "postcss": "^8.4.47", "autoprefixer": "^10.4.20" }\n}\n'

_PKG_NEXTJS = '{\n  "name": "nxt1-app",\n  "version": "0.1.0",\n  "private": true,\n  "scripts": {\n    "dev": "next dev",\n    "build": "next build",\n    "start": "next start"\n  },\n  "dependencies": { "next": "15.0.0", "react": "^18.3.1", "react-dom": "^18.3.1" },\n  "devDependencies": { "@types/node": "^22", "@types/react": "^18", "@types/react-dom": "^18", "tailwindcss": "^3.4.13", "postcss": "^8.4.47", "autoprefixer": "^10.4.20", "typescript": "^5" }\n}\n'

_PKG_EXPO = '{\n  "name": "nxt1-mobile",\n  "version": "0.1.0",\n  "main": "node_modules/expo/AppEntry.js",\n  "scripts": {\n    "start": "expo start",\n    "web": "expo start --web",\n    "ios": "expo start --ios",\n    "android": "expo start --android"\n  },\n  "dependencies": { "expo": "~52.0.0", "expo-router": "~4.0.0", "react": "18.3.1", "react-native": "0.76.0", "react-native-safe-area-context": "4.12.0" }\n}\n'

_FASTAPI_MAIN = 'from fastapi import FastAPI\nfrom fastapi.middleware.cors import CORSMiddleware\n\napp = FastAPI(title="NXT1 Service")\napp.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])\n\n@app.get("/api/health")\ndef health():\n    return {"ok": True}\n'

_FASTAPI_REQS = 'fastapi==0.115.0\nuvicorn[standard]==0.30.6\npython-dotenv==1.0.1\n'

_EXPRESS_INDEX = 'import express from "express";\nconst app = express();\napp.get("/api/health", (_req, res) => res.json({ ok: true }));\nconst port = process.env.PORT || 8080;\napp.listen(port, () => console.log(`NXT1 service on ${port}`));\n'

_EXTENSION_MANIFEST = '{\n  "manifest_version": 3,\n  "name": "NXT1 Extension",\n  "version": "0.1.0",\n  "description": "Built with NXT1.",\n  "action": { "default_popup": "popup.html" },\n  "permissions": ["activeTab", "storage"]\n}\n'

_SCAFFOLDS: List[Dict] = [
    {
        "id": "react-vite",
        "label": "React + Vite Website",
        "framework": "React + Vite + Tailwind",
        "kind": "react-vite",
        "capabilities": ["spa", "vite", "tailwind", "static"],
        "package_manager": "pnpm",
        "build_command":   "pnpm install && pnpm build",
        "start_command":   "pnpm dev",
        "preview_command": "pnpm preview",
        "env_vars":        [],
        "files": {
            "package.json": _PKG_REACT_VITE,
            "index.html":   '<!doctype html><html><head><meta charset="utf-8"><title>NXT1</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>',
            "src/main.jsx": 'import { createRoot } from "react-dom/client";\nimport App from "./App";\nimport "./index.css";\ncreateRoot(document.getElementById("root")).render(<App />);\n',
            "src/App.jsx":  'export default function App() { return <main className="p-8"><h1 className="text-2xl font-semibold">NXT1 — React + Vite</h1></main>; }\n',
            "src/index.css": '@tailwind base;\n@tailwind components;\n@tailwind utilities;\n',
            "tailwind.config.js": 'export default { content: ["./index.html", "./src/**/*.{js,jsx}"], theme: { extend: {} }, plugins: [] };\n',
        },
        "notes": "Static SPA. Deploys to Vercel, Netlify, or Cloudflare Pages out of the box.",
    },
    {
        "id": "nextjs-tailwind",
        "label": "Next.js SaaS / App",
        "framework": "Next.js 15 + Tailwind",
        "kind": "nextjs-tailwind",
        "capabilities": ["ssr", "app-router", "tailwind", "api-routes"],
        "package_manager": "pnpm",
        "build_command":   "pnpm install && pnpm build",
        "start_command":   "pnpm start",
        "preview_command": "pnpm dev",
        "env_vars":        [],
        "files": {
            "package.json":      _PKG_NEXTJS,
            "app/layout.tsx":    'export default function RootLayout({ children }: { children: React.ReactNode }) { return (<html><body>{children}</body></html>); }\n',
            "app/page.tsx":      'export default function Page() { return <main className="p-8"><h1 className="text-2xl font-semibold">NXT1 — Next.js</h1></main>; }\n',
            "app/globals.css":   '@tailwind base;\n@tailwind components;\n@tailwind utilities;\n',
            "tailwind.config.ts": 'import type { Config } from "tailwindcss"; const c: Config = { content: ["./app/**/*.{ts,tsx}"], theme: { extend: {} }, plugins: [] }; export default c;\n',
            "tsconfig.json":     '{"compilerOptions":{"target":"ES2017","lib":["dom","dom.iterable","esnext"],"allowJs":true,"skipLibCheck":true,"strict":false,"noEmit":true,"esModuleInterop":true,"module":"esnext","moduleResolution":"bundler","resolveJsonModule":true,"isolatedModules":true,"jsx":"preserve","plugins":[{"name":"next"}]},"include":["next-env.d.ts","**/*.ts","**/*.tsx"],"exclude":["node_modules"]}\n',
        },
        "notes": "App Router + Tailwind. Deploys cleanly to Vercel; works on Netlify/Cloudflare with their Next adapters.",
    },
    {
        "id": "fullstack-fastapi-react",
        "label": "Full Stack (FastAPI + React)",
        "framework": "FastAPI + React + Vite",
        "kind": "fullstack-fastapi-react",
        "capabilities": ["full-stack", "api", "spa", "mongo-ready"],
        "package_manager": "pnpm + pip",
        "build_command":   "cd frontend && pnpm install && pnpm build && cd ../backend && pip install -r requirements.txt",
        "start_command":   "cd backend && uvicorn main:app --host 0.0.0.0 --port 8080",
        "preview_command": "cd backend && uvicorn main:app --reload --port 8080",
        "env_vars":        ["MONGO_URL"],
        "files": {
            "backend/main.py":         _FASTAPI_MAIN,
            "backend/requirements.txt": _FASTAPI_REQS,
            "frontend/package.json":   _PKG_REACT_VITE,
            "frontend/index.html":     '<!doctype html><html><head><meta charset="utf-8"><title>NXT1</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>',
            "frontend/src/main.jsx":   'import { createRoot } from "react-dom/client"; import App from "./App"; createRoot(document.getElementById("root")).render(<App />);',
            "frontend/src/App.jsx":    'export default function App() { return <main><h1>NXT1 — Full Stack</h1></main>; }',
        },
        "notes": "Frontend on Vercel/Netlify, Backend on Railway/Render. Wire REACT_APP_BACKEND_URL on the frontend.",
    },
    {
        "id": "fastapi-backend",
        "label": "FastAPI Backend",
        "framework": "FastAPI",
        "kind": "fastapi-backend",
        "capabilities": ["api", "backend", "python"],
        "package_manager": "pip",
        "build_command":   "pip install -r requirements.txt",
        "start_command":   "uvicorn main:app --host 0.0.0.0 --port 8080",
        "preview_command": "uvicorn main:app --reload --port 8080",
        "env_vars":        [],
        "files": {
            "main.py":          _FASTAPI_MAIN,
            "requirements.txt": _FASTAPI_REQS,
        },
        "notes": "Backend-only service. Railway/Render/Fly host this best.",
    },
    {
        "id": "express-backend",
        "label": "Express Backend",
        "framework": "Express.js",
        "kind": "express-backend",
        "capabilities": ["api", "backend", "node"],
        "package_manager": "pnpm",
        "build_command":   "pnpm install",
        "start_command":   "node index.js",
        "preview_command": "node index.js",
        "env_vars":        [],
        "files": {
            "package.json":   '{"name":"nxt1-express","version":"0.1.0","type":"module","scripts":{"start":"node index.js"},"dependencies":{"express":"^4.19.2"}}\n',
            "index.js":       _EXPRESS_INDEX,
        },
        "notes": "Node service. Railway/Render/Fly compatible.",
    },
    {
        "id": "expo-rn",
        "label": "Expo Mobile App",
        "framework": "Expo SDK 52 + Expo Router",
        "kind": "expo-rn",
        "capabilities": ["mobile", "ios", "android", "web"],
        "package_manager": "pnpm",
        "build_command":   "pnpm install",
        "start_command":   "pnpm start",
        "preview_command": "pnpm web",
        "env_vars":        [],
        "files": {
            "package.json":         _PKG_EXPO,
            "app.json":             '{"expo":{"name":"NXT1","slug":"nxt1","scheme":"nxt1","version":"0.1.0"}}\n',
            "app/_layout.tsx":      'import { Stack } from "expo-router"; export default function Layout() { return <Stack />; }\n',
            "app/index.tsx":        'import { Text, View } from "react-native"; export default function Home() { return (<View><Text>NXT1 — Expo</Text></View>); }\n',
        },
        "notes": "Builds for iOS / Android / Web via Expo. Use EAS for native binaries.",
    },
    {
        "id": "browser-extension",
        "label": "Chrome Extension",
        "framework": "Manifest V3",
        "kind": "browser-extension",
        "capabilities": ["browser-extension", "chrome", "manifest-v3"],
        "package_manager": "none",
        "build_command":   "echo 'no build step'",
        "start_command":   "echo 'load unpacked in chrome://extensions'",
        "preview_command": "echo 'load unpacked'",
        "env_vars":        [],
        "files": {
            "manifest.json": _EXTENSION_MANIFEST,
            "popup.html":    '<!doctype html><html><body><h1 style="font:14px system-ui;padding:12px">NXT1</h1></body></html>',
        },
        "notes": "Load unpacked or publish to the Chrome Web Store.",
    },
    {
        "id": "ai-chat-streaming",
        "label": "AI Chat App",
        "framework": "Next.js + Provider OS",
        "kind": "ai-chat-streaming",
        "capabilities": ["ai", "sse", "chat", "streaming"],
        "package_manager": "pnpm",
        "build_command":   "pnpm install && pnpm build",
        "start_command":   "pnpm start",
        "preview_command": "pnpm dev",
        "env_vars":        ["ANTHROPIC_API_KEY"],  # or OPENAI_API_KEY
        "files": {
            "package.json": _PKG_NEXTJS,
            "app/page.tsx":  'export default function Page() { return <main><h1>NXT1 — AI Chat</h1></main>; }\n',
            "app/layout.tsx": 'export default function L({ children }: { children: React.ReactNode }) { return (<html><body>{children}</body></html>); }\n',
        },
        "notes": "Wire the streaming endpoint to your provider key (ANTHROPIC_API_KEY / OPENAI_API_KEY / EMERGENT_LLM_KEY).",
    },
    {
        "id": "dashboard",
        "label": "Dashboard / Admin",
        "framework": "React + Vite + Tailwind",
        "kind": "dashboard",
        "capabilities": ["dashboard", "admin", "data-table"],
        "package_manager": "pnpm",
        "build_command":   "pnpm install && pnpm build",
        "start_command":   "pnpm preview",
        "preview_command": "pnpm dev",
        "env_vars":        [],
        "files": {
            "package.json": _PKG_REACT_VITE,
            "index.html":   '<!doctype html><html><head><meta charset="utf-8"><title>NXT1 Dashboard</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>',
            "src/main.jsx": 'import { createRoot } from "react-dom/client"; import App from "./App"; createRoot(document.getElementById("root")).render(<App />);',
            "src/App.jsx":  'export default function App() { return <main><aside>Sidebar</aside><section>Dashboard</section></main>; }',
        },
        "notes": "Card grid + table baseline. Add charts via Recharts as needed.",
    },
    {
        "id": "portfolio",
        "label": "Portfolio Site",
        "framework": "Next.js 15",
        "kind": "portfolio",
        "capabilities": ["static", "marketing", "portfolio"],
        "package_manager": "pnpm",
        "build_command":   "pnpm install && pnpm build",
        "start_command":   "pnpm start",
        "preview_command": "pnpm dev",
        "env_vars":        [],
        "files": {
            "package.json": _PKG_NEXTJS,
            "app/page.tsx": 'export default function Page() { return <main><h1>NXT1 Portfolio</h1></main>; }',
        },
        "notes": "Personal portfolio. Add MDX for blog/case studies.",
    },
    {
        "id": "landing",
        "label": "Landing Page",
        "framework": "React + Vite",
        "kind": "landing",
        "capabilities": ["marketing", "waitlist", "static"],
        "package_manager": "pnpm",
        "build_command":   "pnpm install && pnpm build",
        "start_command":   "pnpm preview",
        "preview_command": "pnpm dev",
        "env_vars":        [],
        "files": {
            "package.json": _PKG_REACT_VITE,
            "index.html":   '<!doctype html><html><head><meta charset="utf-8"><title>NXT1 Launch</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>',
            "src/main.jsx": 'import { createRoot } from "react-dom/client"; import App from "./App"; createRoot(document.getElementById("root")).render(<App />);',
            "src/App.jsx":  'export default function App() { return <main><h1>Launch your idea</h1></main>; }',
        },
        "notes": "Marketing-first. Add a waitlist form wired to your backend.",
    },
    {
        "id": "db-app",
        "label": "DB-Connected App",
        "framework": "FastAPI + React + Mongo",
        "kind": "db-app",
        "capabilities": ["database", "mongo", "full-stack"],
        "package_manager": "pnpm + pip",
        "build_command":   "cd frontend && pnpm install && pnpm build && cd ../backend && pip install -r requirements.txt",
        "start_command":   "cd backend && uvicorn main:app --host 0.0.0.0 --port 8080",
        "preview_command": "cd backend && uvicorn main:app --reload --port 8080",
        "env_vars":        ["MONGO_URL", "DB_NAME"],
        "files": {
            "backend/main.py":         _FASTAPI_MAIN + '\n# TODO: wire motor / pymongo using MONGO_URL + DB_NAME from env.\n',
            "backend/requirements.txt": _FASTAPI_REQS + 'motor==3.6.0\n',
            "frontend/package.json":   _PKG_REACT_VITE,
        },
        "notes": "Mongo via motor. Swap to Postgres by replacing motor + adding asyncpg.",
    },
]

# Index by kind for O(1) inference lookup.
SCAFFOLD_BY_KIND: Dict[str, Dict] = {s["kind"]: s for s in _SCAFFOLDS}


def list_scaffolds() -> List[Dict]:
    """Return a UX-shaped catalogue (no file bodies).

    UI/CLI surfaces consume this. File bodies stay server-side until
    a scaffold is actually picked.
    """
    out = []
    for s in _SCAFFOLDS:
        out.append({
            "id":              s["id"],
            "label":           s["label"],
            "framework":       s["framework"],
            "kind":            s["kind"],
            "capabilities":    s["capabilities"],
            "package_manager": s["package_manager"],
            "build_command":   s["build_command"],
            "start_command":   s["start_command"],
            "env_vars":        s["env_vars"],
            "file_count":      len(s["files"]),
            "notes":           s["notes"],
        })
    return out


def get_scaffold(scaffold_id: str) -> Optional[Dict]:
    """Return the full scaffold (including file bodies) by id."""
    for s in _SCAFFOLDS:
        if s["id"] == scaffold_id:
            return dict(s)
    return None


def pick_scaffold(kind: str) -> Optional[Dict]:
    """Map an inference kind to a scaffold. Returns the full scaffold dict.

    The inference engine sometimes returns kinds that don't have a direct
    1:1 scaffold (e.g. `web-static` as a default fallback). We alias those
    to the closest scaffold so the catalogue + import flow can always
    surface something useful.
    """
    aliases = {
        "web-static":           "landing",
        "marketing":            "landing",
        "saas":                 "nextjs-tailwind",
        "fullstack":            "fullstack-fastapi-react",
        "api":                  "fastapi-backend",
        "mobile":               "expo-rn",
        "extension":            "browser-extension",
        "tauri-desktop":        "react-vite",     # closest match until a Tauri scaffold lands
        "turborepo-monorepo":   "nextjs-tailwind",
    }
    resolved = aliases.get(kind, kind)
    s = SCAFFOLD_BY_KIND.get(resolved) or SCAFFOLD_BY_KIND.get(kind)
    return dict(s) if s else None


def enrich_kind_with_scaffold(kind: str) -> Dict:
    """Attach scaffold-summary metadata to an inferred kind (for the UI).

    Returns the same shape `list_scaffolds()` entries use (no file bodies)
    or an empty dict when no scaffold matches.
    """
    s = pick_scaffold(kind)
    if not s:
        return {}
    return {
        "id":              s["id"],
        "label":           s["label"],
        "framework":       s["framework"],
        "capabilities":    s["capabilities"],
        "package_manager": s["package_manager"],
        "build_command":   s["build_command"],
        "start_command":   s["start_command"],
        "env_vars":        s["env_vars"],
        "notes":           s["notes"],
    }
