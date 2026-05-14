"""Caddy reverse-proxy + auto-SSL config generator (Track C).

NXT1 does NOT run Caddy inside this container. Instead, we generate a
Caddy `Caddyfile` snippet that the user can drop into their own Caddy
instance (Docker, systemd, edge box, etc.) to:

  * terminate TLS automatically (LetsEncrypt by default)
  * proxy `https://<custom-host>` to the NXT1 deployment URL
  * optionally inject security headers + HSTS

Why Caddy: it provisions SSL automatically via ACME with zero config,
unlike nginx where the operator hand-rolls certbot. This makes the
"one-click custom domain" flow believable end-to-end.

Public functions:
  generate_caddyfile(domains, upstream)  -> str (the Caddyfile)
  generate_compose_snippet()             -> str (docker-compose for Caddy)
  describe_install_steps()               -> dict (UX steps for the UI)
"""
from __future__ import annotations

from typing import Iterable, List, Optional


def _normalize_upstream(upstream: str) -> str:
    """Caddy upstreams must NOT include the scheme; strip http(s)://."""
    u = (upstream or "").strip()
    if u.startswith("https://"):
        u = u[len("https://"):]
    elif u.startswith("http://"):
        u = u[len("http://"):]
    return u.rstrip("/")


def generate_caddyfile(
    domains: Iterable[str],
    upstream: str,
    email: Optional[str] = None,
    include_hsts: bool = True,
) -> str:
    """Produce a Caddyfile that proxies all `domains` to `upstream` with auto SSL.

    `upstream` example: "deploy.nxt1.app" or "nxt1.onrender.com".
    `email` is optional — used by ACME for renewal notices.
    """
    host_list = " ".join(sorted({(d or "").strip().lower() for d in domains if d}))
    if not host_list:
        host_list = "example.invalid"
    up = _normalize_upstream(upstream) or "deploy.nxt1.app"
    lines: List[str] = []
    if email:
        lines.append("{")
        lines.append(f"\temail {email}")
        lines.append("}")
        lines.append("")
    lines.append(f"{host_list} {{")
    lines.append("\tencode zstd gzip")
    if include_hsts:
        lines.append("\theader {")
        lines.append("\t\tStrict-Transport-Security \"max-age=31536000; includeSubDomains\"")
        lines.append("\t\tX-Content-Type-Options nosniff")
        lines.append("\t\tReferrer-Policy strict-origin-when-cross-origin")
        lines.append("\t\tX-Frame-Options SAMEORIGIN")
        lines.append("\t}")
    lines.append(f"\treverse_proxy https://{up} {{")
    lines.append(f"\t\theader_up Host {up}")
    lines.append("\t\theader_up X-Forwarded-Host {host}")
    lines.append("\t\theader_up X-Real-IP {remote_host}")
    lines.append("\t}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_compose_snippet(caddyfile_path: str = "./Caddyfile",
                              http_port: int = 80,
                              https_port: int = 443) -> str:
    """Return a docker-compose snippet so the user can run Caddy with one
    `docker compose up -d`. Volumes persist ACME certs across restarts.
    """
    return (
        "services:\n"
        "  caddy:\n"
        "    image: caddy:2-alpine\n"
        "    restart: unless-stopped\n"
        "    ports:\n"
        f"      - \"{http_port}:80\"\n"
        f"      - \"{https_port}:443\"\n"
        "    volumes:\n"
        f"      - {caddyfile_path}:/etc/caddy/Caddyfile:ro\n"
        "      - caddy_data:/data\n"
        "      - caddy_config:/config\n"
        "\n"
        "volumes:\n"
        "  caddy_data:\n"
        "  caddy_config:\n"
    )


def describe_install_steps(domains: List[str], upstream: str) -> dict:
    """Step-by-step UX instructions the frontend can render."""
    return {
        "title": "Bring your own SSL with Caddy",
        "summary": (
            "Caddy auto-provisions LetsEncrypt SSL for any domain you point at it. "
            "Drop the Caddyfile below on your own server, point your DNS at that "
            "server, and Caddy handles the rest."
        ),
        "steps": [
            {
                "n": 1,
                "title": "Point your DNS",
                "detail": (
                    "Create an A record for each custom domain pointing at your "
                    "Caddy server's public IP. Or use the Cloudflare auto-attach "
                    "flow below."
                ),
            },
            {
                "n": 2,
                "title": "Drop the Caddyfile",
                "detail": "Save the generated Caddyfile on your Caddy server.",
            },
            {
                "n": 3,
                "title": "Run Caddy",
                "detail": (
                    "`docker compose up -d` using the snippet below, or "
                    "`sudo caddy run --config Caddyfile` if installed natively."
                ),
            },
            {
                "n": 4,
                "title": "Wait ~30s for ACME",
                "detail": "Caddy will fetch a LetsEncrypt cert automatically on first request.",
            },
        ],
        "caddyfile": generate_caddyfile(domains, upstream),
        "compose_snippet": generate_compose_snippet(),
    }
