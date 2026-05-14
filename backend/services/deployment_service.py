"""Provider-based deployment service for NXT1.

Active:
  InternalProvider — slug-based public hosting served by NXT1 backend itself.
  VercelProvider — real Vercel API deployments (requires VERCEL_TOKEN).
  CloudflarePagesProvider — real CF Pages deployments (requires CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID).

Future stubs: RailwayProvider, RenderProvider, FlyProvider.

Each Deployment record:
  id, project_id, provider, status, slug, public_url, logs[], started_at,
  completed_at, files (snapshot), error?
Status: pending | building | deployed | failed | cancelled
"""
import os
import re
import uuid
import asyncio
import logging
import json
import base64
from datetime import datetime, timezone
from typing import List, Optional

import requests

logger = logging.getLogger("nxt1.deploy")

DEPLOY_STATUS = ("pending", "building", "deployed", "failed", "cancelled")


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:32] or "site"


class BaseDeployProvider:
    name: str = "base"
    requires_token_env: Optional[str] = None
    is_configured: bool = True

    async def deploy(self, project: dict, deployment: dict) -> dict:
        raise NotImplementedError


def _build_preview_shim(project: dict, entry_path: str) -> str:
    """Synthesize a tiny static landing page for projects whose real
    rendering pipeline (Next.js / React-Vite) needs a build step the
    internal provider doesn't perform. Lets the slug stay reachable
    so users can validate the deploy flow end-to-end.
    """
    name = (project.get("name") or "Untitled").replace("<", "&lt;")
    desc = (project.get("description") or project.get("prompt") or "")[:240].replace("<", "&lt;")
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
       background:#0a0a0f;color:#fff;min-height:100vh;
       display:flex;align-items:center;justify-content:center;padding:24px}}
  main{{max-width:560px;text-align:center}}
  .badge{{display:inline-block;font-size:10px;letter-spacing:0.3em;text-transform:uppercase;
         color:#a78bfa;margin-bottom:24px}}
  h1{{font-size:clamp(28px,6vw,52px);font-weight:600;line-height:1.05;margin-bottom:16px;
     background:linear-gradient(180deg,#fff 0%,rgba(255,255,255,0.55) 100%);
     -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
  p{{color:rgba(255,255,255,0.6);font-size:15px;margin-bottom:32px}}
  .info{{font-size:11px;color:rgba(255,255,255,0.4);padding:12px;border:1px solid rgba(255,255,255,0.08);
        border-radius:12px;background:rgba(255,255,255,0.02);text-align:left}}
  code{{font-family:ui-monospace,monospace;color:#67e8f9}}
</style>
</head><body><main>
  <div class="badge">NXT1 · Preview</div>
  <h1>{name}</h1>
  <p>{desc or "Live preview is ready."}</p>
  <div class="info">
    This project ships with <code>{entry_path}</code> (Next.js/React).
    The internal provider serves a static preview shim — for full client-side
    rendering, redeploy via Vercel or Cloudflare Pages.
  </div>
</main></body></html>"""


class InternalProvider(BaseDeployProvider):
    name = "internal"

    async def deploy(self, project: dict, deployment: dict) -> dict:
        files: List[dict] = deployment.get("files") or project.get("files") or []
        logs: List[dict] = deployment.setdefault("logs", [])

        def log(level: str, msg: str):
            logs.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": level, "msg": msg,
            })

        log("info", "› provider=internal target=public-url")
        log("info", f"› project={project.get('name')!r} files={len(files)}")

        # bug fix iter4 #4: the default scaffold is Next.js/React (app/page.jsx
        # or src/main.jsx) — no top-level index.html. Instead of failing the
        # deploy outright, synthesize a static index.html so the user still gets
        # a live URL for landing-page / preview purposes. For full SSR they
        # should pick the Vercel or CF Pages provider.
        has_index = any(f["path"].lower() == "index.html" for f in files)
        nextjs_entry = next((f for f in files if f["path"].lower() in
                             ("app/page.jsx", "app/page.tsx",
                              "src/app/page.jsx", "src/app/page.tsx")), None)
        react_entry = next((f for f in files if f["path"].lower() in
                            ("src/main.jsx", "src/main.tsx",
                             "src/index.jsx", "src/index.tsx")), None)
        if not has_index:
            if nextjs_entry or react_entry:
                entry_path = (nextjs_entry or react_entry)["path"]
                log("warn", f"› no static index.html — generating shim for {entry_path}")
                # Synthesize a minimal static index.html so the slug is reachable.
                # NOTE: this is a *preview* shim, not a real SSR/CSR build.
                files = list(files) + [{
                    "path": "index.html",
                    "content": _build_preview_shim(project, entry_path),
                }]
                deployment["preview_shim"] = True
                deployment["warning"] = (
                    "Internal provider served a preview shim. For real Next.js / "
                    "React routing, deploy with Vercel or Cloudflare Pages."
                )
            else:
                deployment["status"] = "failed"
                deployment["error"] = "No index.html or recognised React/Next entry"
                deployment["failure_reason"] = (
                    "Internal provider serves static HTML. Your scaffold has no "
                    "index.html and no app/page or src/main entry — pick a "
                    "static-html scaffold or deploy via Vercel / Cloudflare Pages."
                )
                log("error", "✗ no entry point found for static deploy")
                deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
                return deployment
        log("info", "› build: collecting static files…")
        for f in files:
            log("debug", f"  + {f['path']} ({len(f.get('content',''))} bytes)")
        log("info", "✓ build complete")
        n_assets = len(project.get("assets", []) or [])
        if n_assets:
            log("info", f"› bundling {n_assets} asset(s)")
        slug = project.get("deploy_slug") or deployment.get("slug")
        if not slug:
            slug = f"{slugify(project.get('name','site'))}-{uuid.uuid4().hex[:6]}"
        deployment["slug"] = slug
        log("info", f"› allocating slug: {slug}")
        log("info", "› publishing…")
        deploy_host = os.environ.get("DEPLOY_HOST", "").strip()
        deployment["public_url"] = (
            f"https://{deploy_host}/api/deploy/{slug}" if deploy_host else f"/api/deploy/{slug}"
        )
        log("info", f"✓ live: {deployment['public_url']}")
        deployment["status"] = "deployed"
        deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        return deployment


class VercelProvider(BaseDeployProvider):
    """Real Vercel deployment via Deployments API.

    Requires VERCEL_TOKEN in env. Project-name is derived from project.name.
    """
    name = "vercel"
    requires_token_env = "VERCEL_TOKEN"

    @property
    def is_configured(self) -> bool:
        return bool(os.environ.get("VERCEL_TOKEN", "").strip())

    async def deploy(self, project: dict, deployment: dict) -> dict:
        logs: List[dict] = deployment.setdefault("logs", [])

        def log(level: str, msg: str):
            logs.append({"ts": datetime.now(timezone.utc).isoformat(), "level": level, "msg": msg})

        token = os.environ.get("VERCEL_TOKEN", "").strip()
        if not token:
            log("error", "✗ VERCEL_TOKEN not set in backend env")
            deployment["status"] = "failed"
            deployment["error"] = "Vercel provider requires VERCEL_TOKEN. Add it to /app/backend/.env."
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
            return deployment

        files: List[dict] = deployment.get("files") or project.get("files") or []
        project_name = slugify(project.get("name", "nxt1-site"))
        log("info", f"› provider=vercel project={project_name}")
        log("info", f"› preparing {len(files)} files for upload…")

        # Vercel API: POST /v13/deployments with files inline (base64).
        payload_files = [
            {
                "file": f["path"],
                "data": base64.b64encode(f["content"].encode("utf-8")).decode("ascii"),
                "encoding": "base64",
            }
            for f in files
        ]
        body = {
            "name": project_name,
            "files": payload_files,
            "projectSettings": {"framework": None},
            "target": "production",
        }
        try:
            log("info", "› POST https://api.vercel.com/v13/deployments")
            resp = requests.post(
                "https://api.vercel.com/v13/deployments",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
            if resp.status_code >= 400:
                log("error", f"✗ Vercel API {resp.status_code}: {resp.text[:300]}")
                deployment["status"] = "failed"
                deployment["error"] = f"Vercel API error {resp.status_code}: {resp.text[:240]}"
                deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
                return deployment
            data = resp.json()
            dep_id = data.get("id") or data.get("uid")
            url = data.get("url") or (data.get("alias") or [None])[0]
            public_url = f"https://{url}" if url else None
            log("info", f"› deployment created id={dep_id} → {public_url}")
            deployment["public_url"] = public_url
            deployment["slug"] = dep_id or project_name

            # Poll until ready or failed (cap at ~3min)
            deadline = datetime.now(timezone.utc).timestamp() + 180
            ready_state = data.get("readyState") or "BUILDING"
            log("info", f"› polling readyState (initial={ready_state})")
            while ready_state not in ("READY", "ERROR", "CANCELED"):
                if datetime.now(timezone.utc).timestamp() > deadline:
                    log("warn", "✗ poll timeout (3min) — leaving as building")
                    deployment["status"] = "failed"
                    deployment["error"] = "Vercel build timed out after 3 minutes"
                    break
                await asyncio.sleep(4)
                pr = requests.get(
                    f"https://api.vercel.com/v13/deployments/{dep_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=20,
                )
                if pr.status_code >= 400:
                    log("warn", f"  poll {pr.status_code}: {pr.text[:180]}")
                    continue
                pdata = pr.json()
                new_state = pdata.get("readyState") or pdata.get("status") or ready_state
                if new_state != ready_state:
                    log("info", f"  → {new_state}")
                    ready_state = new_state
            if ready_state == "READY":
                log("info", f"✓ live: {public_url}")
                deployment["status"] = "deployed"
            elif ready_state == "ERROR":
                log("error", "✗ Vercel reported build error")
                deployment["status"] = "failed"
                deployment["error"] = "Vercel build failed"
            elif ready_state == "CANCELED":
                deployment["status"] = "cancelled"
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            log("error", f"✗ Vercel error: {e}")
            deployment["status"] = "failed"
            deployment["error"] = str(e)[:300]
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        return deployment


class CloudflarePagesProvider(BaseDeployProvider):
    """Real Cloudflare Pages deployment via wrangler CLI (Direct Upload).

    Cloudflare itself recommends wrangler over hand-rolled v4 API calls
    (the manifest/upload-token API is undocumented + changes frequently).
    We materialise the project's files into a tmpdir, then invoke
    `wrangler pages deploy <dir> --project-name <slug>` with the account
    token in env. Logs are tail-captured.

    Requires CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID. The token must
    have **Cloudflare Pages: Edit** permission scoped to the account.
    """
    name = "cloudflare-pages"
    requires_token_env = "CLOUDFLARE_API_TOKEN"

    @property
    def is_configured(self) -> bool:
        return bool(
            os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
            and os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        )

    async def deploy(self, project: dict, deployment: dict) -> dict:
        import shutil
        import subprocess
        import tempfile
        logs: List[dict] = deployment.setdefault("logs", [])

        def log(level: str, msg: str):
            logs.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": level, "msg": msg,
            })

        if not self.is_configured:
            log("error", "✗ Cloudflare Pages requires CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID")
            deployment["status"] = "failed"
            deployment["error"] = "Cloudflare Pages not configured."
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
            return deployment

        wrangler_bin = shutil.which("wrangler")
        if not wrangler_bin:
            log("error", "✗ wrangler CLI not found on this server")
            deployment["status"] = "failed"
            deployment["error"] = "wrangler CLI is required for CF Pages deploys"
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
            return deployment

        files: List[dict] = deployment.get("files") or project.get("files") or []
        project_name = (
            os.environ.get("CLOUDFLARE_PAGES_PROJECT", "").strip()
            or slugify(project.get("name", "nxt1-site"))
        )
        log("info", f"› provider=cloudflare-pages project={project_name}")
        log("info", f"› materialising {len(files)} files")

        tmp = tempfile.mkdtemp(prefix="nxt1-cfp-")
        try:
            from pathlib import Path
            for f in files:
                p = Path(tmp) / f["path"]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(f.get("content") or "", encoding="utf-8")

            # Ensure Pages project exists (wrangler doesn't auto-create)
            account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
            cf_token = os.environ["CLOUDFLARE_API_TOKEN"].strip()
            api_base = (
                f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
                f"/pages/projects"
            )
            cf_hdr = {"Authorization": f"Bearer {cf_token}",
                      "Content-Type": "application/json"}
            chk = await asyncio.to_thread(
                requests.get, f"{api_base}/{project_name}",
                headers=cf_hdr, timeout=20,
            )
            if chk.status_code == 404:
                log("info", "› creating Pages project (first deploy)")
                cr = await asyncio.to_thread(
                    requests.post, api_base,
                    headers=cf_hdr,
                    json={"name": project_name, "production_branch": "main"},
                    timeout=20,
                )
                if cr.status_code >= 400:
                    raise RuntimeError(
                        f"create project: {cr.status_code} {cr.text[:200]}"
                    )
            elif chk.status_code >= 400:
                raise RuntimeError(
                    f"check project: {chk.status_code} {chk.text[:200]}"
                )

            env = os.environ.copy()
            env["CLOUDFLARE_API_TOKEN"] = cf_token
            env["CLOUDFLARE_ACCOUNT_ID"] = account_id

            cmd = [
                wrangler_bin, "pages", "deploy", tmp,
                "--project-name", project_name,
                "--commit-message", f"NXT1 deploy {deployment['id'][:8]}",
                "--commit-dirty=true",
            ]
            log("info", f"› {' '.join(cmd[1:])}")

            def _run() -> subprocess.CompletedProcess:
                return subprocess.run(
                    cmd, env=env, capture_output=True, text=True, timeout=240,
                )

            proc = await asyncio.to_thread(_run)
            for line in (proc.stdout or "").splitlines()[-40:]:
                if line.strip():
                    log("info", f"  {line.strip()[:300]}")
            for line in (proc.stderr or "").splitlines()[-20:]:
                if line.strip():
                    log("warn", f"  {line.strip()[:300]}")

            if proc.returncode != 0:
                deployment["status"] = "failed"
                deployment["error"] = (proc.stderr or proc.stdout or "wrangler failed").strip()[:300]
                deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
                return deployment

            # Parse the deployed URL from wrangler output
            import re as _re
            m = _re.search(r"https://[a-z0-9.-]+\.pages\.dev[^\s]*", proc.stdout or "")
            url = m.group(0).rstrip(".") if m else None
            deployment["public_url"] = url
            deployment["slug"] = project_name
            log("info", f"✓ live: {url}")
            deployment["status"] = "deployed"
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        except subprocess.TimeoutExpired:
            log("error", "✗ wrangler timed out (4min)")
            deployment["status"] = "failed"
            deployment["error"] = "CF Pages deploy timed out"
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            log("error", f"✗ {e}")
            deployment["status"] = "failed"
            deployment["error"] = str(e)[:300]
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return deployment


class CloudflareWorkersProvider(BaseDeployProvider):
    """Real Cloudflare Workers deployment via wrangler CLI.

    Materialises the project's files into a tmpdir, generates a
    `wrangler.toml` on the fly (taking project name, env_vars, D1 + R2
    bindings into account), then runs `wrangler deploy`. Plain `[vars]`
    are inlined into the toml; secret-shaped keys (anything containing
    "TOKEN", "KEY", "SECRET") are pushed via `wrangler secret put`.

    Requires CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID + a server-side
    `wrangler` binary on PATH. Token must have `Workers Scripts: Edit`.
    """
    name = "cloudflare-workers"
    requires_token_env = "CLOUDFLARE_API_TOKEN"

    @property
    def is_configured(self) -> bool:
        return bool(
            os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
            and os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        )

    async def deploy(self, project: dict, deployment: dict) -> dict:
        import shutil
        import subprocess
        import tempfile
        logs: List[dict] = deployment.setdefault("logs", [])

        def log(level: str, msg: str):
            logs.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": level, "msg": msg,
            })

        if not self.is_configured:
            log("error", "✗ Workers requires CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID")
            deployment["status"] = "failed"
            deployment["error"] = "Cloudflare Workers not configured."
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
            return deployment

        wrangler_bin = shutil.which("wrangler")
        if not wrangler_bin:
            log("error", "✗ wrangler CLI not found on this server")
            deployment["status"] = "failed"
            deployment["error"] = (
                "wrangler CLI is required. Install with `npm i -g wrangler` on the deploy host."
            )
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
            return deployment

        files: List[dict] = deployment.get("files") or project.get("files") or []
        worker_name = slugify(project.get("name", "nxt1-worker"))

        # Find the entry file. Conventions: src/index.js > src/index.ts >
        # worker.js > index.js (top level). If none found, fail loud.
        candidates = ["src/index.ts", "src/index.js", "worker.ts", "worker.js", "index.js"]
        entry_path = next(
            (c for c in candidates if any(f.get("path") == c for f in files)),
            None,
        )
        if not entry_path:
            log("error", "✗ no Worker entry file found (looked for src/index.{ts,js}, worker.{ts,js}, index.js)")
            deployment["status"] = "failed"
            deployment["error"] = (
                "Workers deploy requires an entry file at src/index.js (or .ts), "
                "worker.js, or index.js. Add one — even a tiny `export default { fetch() {} }` works."
            )
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
            return deployment
        log("info", f"› entry: {entry_path}")

        # Split env_vars into plain vars vs secrets
        env_vars = (project.get("env_vars") or [])
        plain_vars: dict = {}
        secret_keys: list = []
        for ev in env_vars:
            k = ev.get("key", "")
            v = ev.get("value", "")
            if not k or v is None:
                continue
            if any(s in k for s in ("TOKEN", "SECRET", "KEY", "PASSWORD")):
                secret_keys.append(k)
            else:
                plain_vars[k] = v

        # D1 + R2 bindings — derived from the project's `databases` + R2 config.
        d1_bindings: list = []
        for d in (project.get("databases") or []):
            meta = d.get("provider_meta") or {}
            if d.get("kind") == "postgres" and meta.get("d1_database_id"):
                d1_bindings.append({
                    "binding": d.get("name", "DB").upper().replace("-", "_")[:32],
                    "database_name": meta.get("d1_database_name") or d.get("name"),
                    "database_id": meta["d1_database_id"],
                })

        r2_bindings: list = []
        if (os.environ.get("R2_BUCKET") or "").strip():
            r2_bindings.append({
                "binding": "ASSETS",
                "bucket_name": os.environ["R2_BUCKET"].strip(),
            })

        log("info", f"› provider=cloudflare-workers worker={worker_name}")
        log("info", f"› vars={len(plain_vars)} secrets={len(secret_keys)} d1={len(d1_bindings)} r2={len(r2_bindings)}")

        tmp = tempfile.mkdtemp(prefix="nxt1-cfw-")
        try:
            from pathlib import Path
            for f in files:
                p = Path(tmp) / f["path"]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(f.get("content") or "", encoding="utf-8")

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            toml_lines = [
                f'name = "{worker_name}"',
                f'main = "{entry_path}"',
                f'compatibility_date = "{today}"',
            ]
            if plain_vars:
                toml_lines.append("\n[vars]")
                for k, v in plain_vars.items():
                    safe = json.dumps(v)
                    toml_lines.append(f"{k} = {safe}")
            for d1 in d1_bindings:
                toml_lines.append("\n[[d1_databases]]")
                for k, v in d1.items():
                    toml_lines.append(f'{k} = "{v}"')
            for r2 in r2_bindings:
                toml_lines.append("\n[[r2_buckets]]")
                for k, v in r2.items():
                    toml_lines.append(f'{k} = "{v}"')
            (Path(tmp) / "wrangler.toml").write_text("\n".join(toml_lines), encoding="utf-8")

            account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
            cf_token = os.environ["CLOUDFLARE_API_TOKEN"].strip()
            env = os.environ.copy()
            env["CLOUDFLARE_API_TOKEN"] = cf_token
            env["CLOUDFLARE_ACCOUNT_ID"] = account_id

            cmd = [wrangler_bin, "deploy", "--config", str(Path(tmp) / "wrangler.toml")]
            log("info", f"› {' '.join(cmd[1:])}")

            def _run() -> subprocess.CompletedProcess:
                return subprocess.run(
                    cmd, env=env, capture_output=True, text=True, timeout=240, cwd=tmp,
                )

            proc = await asyncio.to_thread(_run)
            for line in (proc.stdout or "").splitlines()[-40:]:
                if line.strip():
                    log("info", f"  {line.strip()[:300]}")
            for line in (proc.stderr or "").splitlines()[-20:]:
                if line.strip():
                    log("warn", f"  {line.strip()[:300]}")

            if proc.returncode != 0:
                deployment["status"] = "failed"
                deployment["error"] = (proc.stderr or proc.stdout or "wrangler failed").strip()[:300]
                deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
                return deployment

            # Push secrets one-by-one — these don't go in wrangler.toml.
            for sk in secret_keys:
                sv = next((ev["value"] for ev in env_vars if ev.get("key") == sk), None)
                if sv is None or sv == "":
                    continue
                try:
                    def _push_secret(key=sk, val=sv):
                        return subprocess.run(
                            [wrangler_bin, "secret", "put", key, "--name", worker_name],
                            input=val, env=env, capture_output=True, text=True,
                            timeout=60, cwd=tmp,
                        )
                    sproc = await asyncio.to_thread(_push_secret)
                    if sproc.returncode == 0:
                        log("info", f"  + secret {sk}")
                    else:
                        log("warn", f"  ! secret {sk} failed: {(sproc.stderr or '').strip()[:160]}")
                except Exception as e:
                    log("warn", f"  ! secret {sk} push error: {e}")

            # Parse the deployed URL from wrangler output.
            import re as _re
            m = _re.search(r"https://[a-z0-9.-]+\.workers\.dev[^\s]*", proc.stdout or "")
            url = m.group(0).rstrip(".") if m else f"https://{worker_name}.workers.dev"
            deployment["public_url"] = url
            deployment["slug"] = worker_name
            log("info", f"✓ live: {url}")
            deployment["status"] = "deployed"
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        except subprocess.TimeoutExpired:
            log("error", "✗ wrangler timed out (4min)")
            deployment["status"] = "failed"
            deployment["error"] = "Workers deploy timed out"
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            log("error", f"✗ {e}")
            deployment["status"] = "failed"
            deployment["error"] = str(e)[:300]
            deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return deployment


class _StubProvider(BaseDeployProvider):
    def __init__(self, name: str):
        self.name = name
    @property
    def is_configured(self) -> bool:
        return False
    async def deploy(self, project: dict, deployment: dict) -> dict:
        deployment["status"] = "failed"
        deployment["error"] = f"Provider '{self.name}' not yet implemented"
        deployment.setdefault("logs", []).append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": "error", "msg": f"Provider '{self.name}' is a stub.",
        })
        deployment["completed_at"] = datetime.now(timezone.utc).isoformat()
        return deployment


PROVIDERS = {
    "internal": InternalProvider(),
    "vercel": VercelProvider(),
    "cloudflare-pages": CloudflarePagesProvider(),
    "cloudflare-workers": CloudflareWorkersProvider(),
    "railway": _StubProvider("railway"),
    "render": _StubProvider("render"),
    "fly": _StubProvider("fly"),
}


def get_provider(name: str = "internal") -> BaseDeployProvider:
    return PROVIDERS.get(name) or PROVIDERS["internal"]


def list_providers() -> list:
    """Return shape: [{name, configured, requires_token_env}]."""
    out = []
    for k, p in PROVIDERS.items():
        out.append({
            "name": k,
            "configured": bool(getattr(p, "is_configured", True)),
            "requires_token_env": getattr(p, "requires_token_env", None),
        })
    return out


def new_deployment_record(project: dict, files: List[dict], provider: str = "internal") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "project_id": project["id"],
        "provider": provider,
        "status": "pending",
        "slug": project.get("deploy_slug") if provider == "internal" else None,
        "public_url": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "logs": [],
        "files": files,
        "error": None,
        "trigger": "manual",
        "created_by": "admin",
    }
