"""AI chat (streaming) + Tailwind scaffold — SSE-ready foundation."""
from typing import List


def files(project_name: str = "NXT1 Project") -> List[dict]:
    return [
        {"path": "index.html", "content": _INDEX_HTML.replace("{{name}}", project_name)},
        {"path": "styles/main.css", "content": _STYLES_CSS},
        {"path": "scripts/chat.js", "content": _CHAT_JS},
        {"path": "backend/server.py", "content": _SERVER_PY},
        {"path": "backend/requirements.txt", "content": _REQS},
        {"path": "README.md", "content": _README.replace("{{name}}", project_name)},
    ]


_INDEX_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"/>
  <title>{{name}}</title>
  <link rel=\"stylesheet\" href=\"styles/main.css\" />
</head>
<body>
  <main class=\"chat-shell\">
    <header class=\"chat-header\">
      <span class=\"pill\">NXT1 // AI CHAT</span>
      <h1>{{name}}</h1>
    </header>
    <section id=\"messages\" class=\"messages\"></section>
    <form id=\"composer\" class=\"composer\">
      <input id=\"prompt\" placeholder=\"Ask anything…\" autocomplete=\"off\" />
      <button type=\"submit\">Send</button>
    </form>
  </main>
  <script src=\"scripts/chat.js\"></script>
</body>
</html>
"""

_STYLES_CSS = """:root {
  --bg: #1F1F23;
  --panel: #242428;
  --fg: #FAFAFA;
  --muted: #8A8A93;
  --accent: #5EEAD4;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  font-family: 'Inter', system-ui, sans-serif;
  background: var(--bg);
  color: var(--fg);
  display: grid;
  place-items: center;
}
.chat-shell {
  width: min(720px, 100%);
  height: 100vh;
  display: grid;
  grid-template-rows: auto 1fr auto;
  padding: 16px;
  gap: 12px;
}
.chat-header { padding: 12px 16px; }
.pill {
  display: inline-block;
  font-family: monospace;
  font-size: 10px;
  letter-spacing: 2.4px;
  color: var(--muted);
  border: 1px solid rgba(255,255,255,0.12);
  padding: 4px 8px;
  border-radius: 4px;
  margin-bottom: 8px;
}
h1 { font-size: 22px; letter-spacing: -0.4px; font-weight: 600; }
.messages {
  overflow-y: auto;
  background: var(--panel);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 16px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.msg { padding: 10px 14px; border-radius: 12px; max-width: 80%; font-size: 14.5px; line-height: 1.5; }
.msg.user { align-self: flex-end; background: #2F2F37; }
.msg.bot  { align-self: flex-start; background: transparent; color: var(--muted); }
.composer { display: flex; gap: 8px; }
.composer input {
  flex: 1;
  padding: 12px 16px;
  background: var(--panel);
  color: var(--fg);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 14px;
  outline: none;
  font-size: 15px;
}
.composer input:focus { border-color: rgba(94,234,212,0.35); }
.composer button {
  padding: 0 18px;
  background: var(--accent);
  color: #1F1F23;
  border: 0;
  border-radius: 14px;
  font-weight: 600;
  cursor: pointer;
}
"""

_CHAT_JS = """const messages = document.getElementById('messages');
const form = document.getElementById('composer');
const input = document.getElementById('prompt');

function appendMsg(text, who) {
  const el = document.createElement('div');
  el.className = `msg ${who}`;
  el.textContent = text;
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
  return el;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  appendMsg(q, 'user');
  input.value = '';
  const bubble = appendMsg('…', 'bot');
  try {
    const r = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: q }),
    });
    if (!r.body) throw new Error('no stream');
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    bubble.textContent = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bubble.textContent += decoder.decode(value, { stream: true });
      messages.scrollTop = messages.scrollHeight;
    }
  } catch (err) {
    bubble.textContent = 'Stream failed: ' + err.message;
  }
});
"""

_SERVER_PY = """\"\"\"Streaming chat backend stub (FastAPI). Replace the echo with your LLM call.\"\"\"
import asyncio
import os
from fastapi import FastAPI, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title=\"NXT1 chat starter\")
app.add_middleware(CORSMiddleware, allow_origins=[\"*\"], allow_methods=[\"*\"], allow_headers=[\"*\"])

@app.get(\"/api/health\")
def health(): return {\"status\": \"ok\"}

@app.post(\"/api/chat/stream\")
async def chat_stream(body: dict = Body(default={})):
    msg = (body or {}).get(\"message\", \"\")
    async def gen():
        reply = f\"You said: {msg}\\n\\nThis is a placeholder stream. Wire your LLM provider here.\"
        for tok in reply.split():
            yield tok + \" \"
            await asyncio.sleep(0.04)
    return StreamingResponse(gen(), media_type=\"text/plain\")

if __name__ == \"__main__\":
    import uvicorn
    uvicorn.run(app, host=\"127.0.0.1\", port=int(os.environ.get(\"PORT\", 8000)))
"""

_REQS = "fastapi==0.110.1\nuvicorn==0.30.1\n"

_README = """# {{name}}

AI chat (streaming) foundation generated by NXT1. Streams plain-text tokens
from `/api/chat/stream`. Replace the echo stub with your LLM provider call.

Frontend: vanilla HTML + JS (no framework dependency).
Backend: FastAPI with SSE-friendly StreamingResponse.
"""
