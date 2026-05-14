import axios from "axios";
import { getToken, clearToken } from "@/lib/auth";
import { parseErrorMessage } from "@/lib/errors";

// Resolve backend URL from env (preview / production / local) with a sensible
// fallback to the production Render host. Never hardcoded — always env-first
// so deploys reconnect cleanly across Emergent preview, Render, Vercel, etc.
const RAW_BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const BACKEND_URL = (RAW_BACKEND_URL || "https://nxt1.onrender.com").replace(/\/+$/, "");
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    // GLOBAL ERROR NORMALISATION — Pydantic v2 returns 422 errors as arrays
    // of objects { type, loc, msg, input, url }. Components that pass
    // `err.response.data.detail` straight into JSX (or toast) would crash
    // with "Objects are not valid as a React child". We pre-flatten the
    // detail to a readable string here so ALL downstream consumers see a
    // string, regardless of provider/route.
    if (err?.response?.data) {
      const raw = err.response.data.detail;
      const isObjectLike = raw && typeof raw === "object";
      if (isObjectLike) {
        err.response.data.__detail_raw = raw;
        err.response.data.detail = parseErrorMessage({ response: err.response });
      }
    }
    if (err?.response?.status === 401) {
      clearToken();
      const path = window.location.pathname;
      // Public users go through /signin. The admin gate at /access still
      // works for admin recovery — but we send users with expired/missing
      // tokens to /signin so they don't need to know about the admin path.
      const skip = ["/", "/access", "/signin", "/signup", "/privacy", "/terms"];
      if (!skip.includes(path) && !path.startsWith("/p/")) {
        window.location.href = "/signin";
      }
    }
    return Promise.reject(err);
  }
);

// Auth & system
export const login = (password) => api.post("/auth/login", { password });
export const verifyAuth = () => api.get("/auth/verify");

// User accounts (email + password)
export const userSignup = (payload) => api.post("/users/signup", payload);
export const userSignin = (payload) => api.post("/users/signin", payload);
export const userMe = () => api.get("/users/me");
export const submitOnboarding = (payload) => api.post("/users/me/onboarding", payload);

// Admin: user management
export const listUsers = () => api.get("/users");
export const updateUserAccess = (userId, status) =>
  api.post(`/users/${userId}/access`, { access_status: status });

// Admin: AI Site Editor
export const siteEditorListFiles = () => api.get("/site-editor/files");
export const siteEditorPropose = (prompt, paths) =>
  api.post("/site-editor/propose", { prompt, paths });
export const siteEditorApply = (edit_id, opts = {}) =>
  api.post("/site-editor/apply", { edit_id, push_to_github: true, ...opts });
export const siteEditorHistory = () => api.get("/site-editor/history");
export const siteEditorRollback = (edit_id) =>
  api.post(`/site-editor/rollback/${edit_id}`);

// Admin: workspace
export const adminGithubStatus = () => api.get("/admin/github/status");
export const adminOverview = () => api.get("/admin/overview");
export const adminUpdateBrand = (payload) => api.post("/admin/brand", payload);
export const adminListSecrets = () => api.get("/admin/secrets");
export const adminUpdateSecrets = (updates) => api.post("/admin/secrets", { updates });
export const adminReloadEnv = () => api.post("/admin/restart");
export const adminAuditList = (params = {}) => api.get("/audit", { params });
export const adminAuditRollback = (id) => api.post(`/audit/${id}/rollback`);
export const detectDomain = (host) => api.get("/domains/detect", { params: { host } });
export const getProviders = () => api.get("/system/providers");
export const getSecretsStatus = () => api.get("/system/secrets");
export const setPublishOnSave = (id, on) =>
  api.post(`/projects/${id}/publish-on-save`, { publish_on_save: on });
export const getProjectState = (id) => api.get(`/projects/${id}/state`);

// Public access requests (no auth)
export const submitAccessRequest = (payload) =>
  axios.post(`${API}/access/request`, payload);

// Admin access requests inbox
export const listAccessRequests = () => api.get("/access/requests");
export const updateAccessRequest = (id, patch) =>
  api.patch(`/access/requests/${id}`, patch);
export const deleteAccessRequest = (id) =>
  api.delete(`/access/requests/${id}`);

// Streaming chat URL (use fetch + EventSource pattern in client).
// `protocol` (optional): "auto" | "tag" | "json"
//   - auto (default)  → server decides: tag for incremental edits (>5 files),
//                       JSON for blank-start full builds
//   - tag             → force the streaming-tag protocol (cheaper, surgical)
//   - json            → force the JSON-blob protocol (legacy, full-rewrites)
export const chatStreamUrl = (id, protocol = "auto") => {
  const t = encodeURIComponent(getToken());
  const p = protocol && protocol !== "auto"
    ? `&protocol=${encodeURIComponent(protocol)}`
    : "";
  return `${API}/projects/${id}/chat/stream?auth=${t}${p}`;
};

// Versions detail (files snapshot)
export const getVersion = (id, vid) =>
  api.get(`/projects/${id}/versions/${vid}`);

// Projects
export const listProjects = () => api.get("/projects");
// Accepts either:
//   createProject("My App", "desc")           → legacy positional
//   createProject({ name, prompt, mode, scaffold_id, framework, description })
//                                               → full FE payload (preferred)
// Without this overload, an object first-arg got `str()`-coerced on the
// backend and persisted as `{'name': 'Build …', 'prompt': '…'}` (visible
// in the dashboard as garbage project names).
export const createProject = (arg, description = "") => {
  if (arg && typeof arg === "object") {
    return api.post("/projects", arg);
  }
  return api.post("/projects", { name: arg, description });
};
export const getProject = (id) => api.get(`/projects/${id}`);
export const deleteProject = (id) => api.delete(`/projects/${id}`);

// Files
export const upsertFile = (id, path, content) =>
  api.put(`/projects/${id}/files/${path}`, { content });
export const deleteFile = (id, path) =>
  api.delete(`/projects/${id}/files/${path}`);

// Chat
export const getMessages = (id) => api.get(`/projects/${id}/messages`);
export const sendChat = (id, message, provider) =>
  api.post(`/projects/${id}/chat`, { message, provider });

// Versions
export const listVersions = (id) => api.get(`/projects/${id}/versions`);
export const restoreVersion = (id, versionId) =>
  api.post(`/projects/${id}/versions/${versionId}/restore`);

// Assets
export const listAssets = (id) => api.get(`/projects/${id}/assets`);
export const uploadAsset = (id, file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post(`/projects/${id}/upload`, fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const deleteAsset = (id, assetId) =>
  api.delete(`/projects/${id}/assets/${assetId}`);
export const assetUrl = (id, filename) =>
  `${API}/projects/${id}/assets/${filename}?auth=${encodeURIComponent(getToken())}`;

// Deployments (new)
export const createDeployment = (id, provider = "internal") =>
  api.post(`/projects/${id}/deployments`, { provider });
export const listDeployments = (id) => api.get(`/projects/${id}/deployments`);
export const getDeployment = (id, depId) =>
  api.get(`/projects/${id}/deployments/${depId}`);
export const cancelDeployment = (id, depId) =>
  api.post(`/projects/${id}/deployments/${depId}/cancel`);

// Legacy quick deploy (still works)
export const deployProject = (id) => api.post(`/projects/${id}/deploy`);

// Download
export const downloadZipUrl = (id) =>
  `${API}/projects/${id}/download?auth=${encodeURIComponent(getToken())}`;

// Public deploy URL (for live link)
export const deployUrl = (slug) => `${API}/deploy/${slug}`;

// Domains (new)
export const addDomain = (id, hostname) =>
  api.post(`/projects/${id}/domains`, { hostname });
export const listDomains = (id) => api.get(`/projects/${id}/domains`);
export const removeDomain = (id, domainId) =>
  api.delete(`/projects/${id}/domains/${domainId}`);
export const verifyDomain = (id, domainId) =>
  api.post(`/projects/${id}/domains/${domainId}/verify`);
export const setPrimaryDomain = (id, domainId) =>
  api.post(`/projects/${id}/domains/${domainId}/primary`);

// File rename
export const renameFile = (id, path, newPath) =>
  api.post(`/projects/${id}/files/${path}/rename`, { new_path: newPath });

// Env vars
export const listEnv = (id) => api.get(`/projects/${id}/env`);
export const upsertEnv = (id, key, value, scope = "runtime") =>
  api.post(`/projects/${id}/env`, { key, value, scope });
export const deleteEnv = (id, key) => api.delete(`/projects/${id}/env/${key}`);

// Commits / version timeline
export const listCommits = (id, q = "") =>
  api.get(`/projects/${id}/commits`, { params: q ? { q } : {} });
export const labelVersion = (id, vid, label, message = "") =>
  api.post(`/projects/${id}/versions/${vid}/label`, { label, message });

// Project memory
export const getMemory = (id) => api.get(`/projects/${id}/memory`);

// 3rd-party integrations
export const saveToGithub = (id, payload = {}) =>
  api.post(`/projects/${id}/github/save`, payload);
export const getGithubStatus = (id) => api.get(`/projects/${id}/github`);

// Shareable previews
export const createPreview = (id, payload = {}) =>
  api.post(`/projects/${id}/preview`, payload);
export const getPreview = (id) => api.get(`/projects/${id}/preview`);
export const deletePreview = (id) => api.delete(`/projects/${id}/preview`);
export const previewPublicUrl = (slug) =>
  `${BACKEND_URL}/p/${slug}`;

// AI debugging
export const aiDebug = (id, errorText, note = "") =>
  api.post(`/projects/${id}/debug`, { error_text: errorText, note });

// Runtime sandbox
export const runtimeStart = (id) => api.post(`/projects/${id}/runtime/start`);
export const runtimeStop = (id) => api.post(`/projects/${id}/runtime/stop`);
export const runtimeRestart = (id) => api.post(`/projects/${id}/runtime/restart`);
export const runtimeStatus = (id) => api.get(`/projects/${id}/runtime`);
export const runtimeLogs = (id, since = 0) =>
  api.get(`/projects/${id}/runtime/logs`, { params: { since } });
export const runtimeProxyUrl = (id) => `${API}/runtime/${id}`;
export const runtimeHealth = (id, path = "/api/health") =>
  api.post(`/projects/${id}/runtime/health`, null, { params: { path } });
export const runtimeTry = (id, payload) =>
  api.post(`/projects/${id}/runtime/try`, payload);

// Backend scaffold (one-click starters)
export const scaffoldBackend = (id, kind, autoStart = true) =>
  api.post(`/projects/${id}/scaffold`, { kind, auto_start: autoStart });

// Database connections
export const listDatabases = (id) => api.get(`/projects/${id}/databases`);
export const addDatabase = (id, kind, name, url, notes = "") =>
  api.post(`/projects/${id}/databases`, { kind, name, url, notes });
export const removeDatabase = (id, dbId) =>
  api.delete(`/projects/${id}/databases/${dbId}`);
export const dbSchemaTemplate = (id, dbId) =>
  api.get(`/projects/${id}/databases/${dbId}/schema-template`);
// Real provisioning + migrations (Phase 15)
export const dbProviders = () => api.get(`/databases/providers`);
export const provisionDatabase = (id, payload) =>
  api.post(`/projects/${id}/databases/provision`, payload);
export const dbMigrate = (id, dbId, sql, label = "manual") =>
  api.post(`/projects/${id}/databases/${dbId}/migrate`, { sql, label });
export const dbTest = (id, dbId) =>
  api.post(`/projects/${id}/databases/${dbId}/test`);
export const dbGenerateSchema = (id, dbId, prompt) =>
  api.post(`/projects/${id}/databases/${dbId}/generate-schema`, { prompt });

// Saved requests (Postman-lite)
export const listSavedRequests = (id) => api.get(`/projects/${id}/requests`);
export const saveRequest = (id, payload) => api.post(`/projects/${id}/requests`, payload);
export const deleteSavedRequest = (id, reqId) => api.delete(`/projects/${id}/requests/${reqId}`);

// Project import + analysis
export const importZipUrl = `${API}/projects/import/zip`;
export const importGithub = (repoUrl, branch = null, projectName = "") =>
  api.post(`/projects/import/github`, { repo_url: repoUrl, branch, project_name: projectName });
export const getAnalysis = (id) => api.get(`/projects/${id}/analysis`);
export const refreshAnalysis = (id) => api.post(`/projects/${id}/analysis/refresh`);

// Scaffolds / templates catalogue
export const listScaffolds = () => api.get("/scaffolds");
export const getScaffold = (id) => api.get(`/scaffolds/${id}`);
export const inferScaffold = (prompt) => api.post("/scaffolds/infer", { prompt });

// Generate frontend page that calls a backend route
export const generatePageFromRoute = (id, payload) =>
  api.post(`/projects/${id}/generate-page-from-route`, payload);

// Autonomous debugging loop
export const runtimeAutoFix = (id, errorText = "", note = "") =>
  api.post(`/projects/${id}/runtime/auto-fix`, { error_text: errorText, note });
export const runtimeAutoFixApply = (id, payload) =>
  api.post(`/projects/${id}/runtime/auto-fix/apply`, payload);
export const deployAutoFix = (id, deploymentId = null, note = "") =>
  api.post(`/projects/${id}/deploy/auto-fix`, { deployment_id: deploymentId, note });
export const deployAutoFixApply = (id, payload) =>
  api.post(`/projects/${id}/deploy/auto-fix/apply`, payload);

// Multi-agent foundation
export const listAgents = () => api.get(`/agents`);
export const runAgent = (role, prompt, provider = null) =>
  api.post(`/agents/run`, { role, prompt, provider });
export const routeAgent = (prompt) => api.post(`/agents/route`, { prompt });

// Product / readiness
export const getReadiness = (id) => api.get(`/projects/${id}/readiness`);
export const generateProductPlan = (id, brief, provider = null) =>
  api.post(`/projects/${id}/product-plan`, { brief, provider });

// ===== 2026-01-15: Tracks A/B/C/D =====
// Track A — Premium UI registry
export const getUIRegistry = (filters = {}) =>
  api.get(`/ui-registry`, { params: filters });
export const getUIBlock = (blockId) => api.get(`/ui-registry/blocks/${blockId}`);
export const getUIDirective = () => api.get(`/ui-registry/directive`);

// Track B — Durable workflows
export const startWorkflow = (projectId, prompt, deployTarget = "internal") =>
  api.post(`/workflows/start`, { project_id: projectId, prompt, deploy_target: deployTarget });
export const listWorkflows = (params = {}) =>
  api.get(`/workflows/list`, { params });
export const getWorkflow = (workflowId) => api.get(`/workflows/${workflowId}`);
export const resumeWorkflow = (workflowId, approval = true) =>
  api.post(`/workflows/${workflowId}/resume`, { approval });
export const cancelWorkflow = (workflowId) =>
  api.post(`/workflows/${workflowId}/cancel`);

// Track C — Hosting: Caddy + Cloudflare connect
export const generateCaddyfile = (domains, opts = {}) =>
  api.post(`/hosting/caddy/generate`, { domains, ...opts });
export const caddyInstallGuide = (domain) =>
  api.get(`/hosting/caddy/install-guide`, { params: { domain } });
export const cfConnect = (token) => api.post(`/hosting/cloudflare/connect`, { token });
export const cfStatus = () => api.get(`/hosting/cloudflare/status`);
export const cfZones = () => api.get(`/hosting/cloudflare/zones`);
export const cfAttachDNS = (hostname, zoneId, target = null) =>
  api.post(`/hosting/cloudflare/dns`, { hostname, zone_id: zoneId, target });
export const cfDisconnect = () => api.post(`/hosting/cloudflare/disconnect`);
export const hostingReadiness = () => api.get(`/hosting/readiness`);

// Track D — Sandboxed runner + self-heal
export const runnerConfig = () => api.get(`/runner/config`);
export const runnerQuickBuild = (projectId) =>
  api.post(`/runner/projects/${projectId}/quick-build`);
export const runnerSelfHealUrl = (projectId) => {
  const t = encodeURIComponent(getToken());
  return `${API}/runner/projects/${projectId}/self-heal?auth=${t}`;
};

// ─────────────────────────────────────────────────────────────────────────
// Social Content Agent (2026-05-14)
// ─────────────────────────────────────────────────────────────────────────
export const socialGetProfile = () => api.get("/social/profile");
export const socialSaveProfile = (payload) => api.post("/social/profile", payload);
export const socialUploadLogo = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post("/social/profile/logo", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const socialGenerate = (payload) => api.post("/social/generate", payload);
export const socialListJobs = (limit = 20) => api.get("/social/jobs", { params: { limit } });
export const socialListPosts = (params = {}) => api.get("/social/posts", { params });
export const socialGetPost = (id) => api.get(`/social/posts/${id}`);
export const socialUpdatePost = (id, patch) => api.patch(`/social/posts/${id}`, patch);
export const socialDeletePost = (id) => api.delete(`/social/posts/${id}`);
export const socialRegeneratePost = (id) => api.post(`/social/posts/${id}/regenerate`);

// ─────────────────────────────────────────────────────────────────────────
// Video Studio (2026-05-14)
// ─────────────────────────────────────────────────────────────────────────
export const videoHealth = () => api.get("/video/health");
export const videoGenerate = (payload) => api.post("/video/generate", payload);
export const videoUpload = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post("/video/upload", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const videoListClips = () => api.get("/video/clips");
export const videoDeleteClip = (id) => api.delete(`/video/clips/${id}`);
export const videoListJobs = (limit = 20) => api.get("/video/jobs", { params: { limit } });
export const videoSaveTimeline = (payload) => api.post("/video/timeline", payload);
export const videoListTimelines = () => api.get("/video/timelines");
export const videoGetTimeline = (id) => api.get(`/video/timeline/${id}`);
export const videoPostToSocial = (payload) => api.post("/video/post-to-social", payload);

// Generic jobs polling
export const getJob = (jobId) => api.get(`/jobs/${jobId}`);

// Absolute URL helper for media served by the backend
export const mediaUrl = (path) => {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return path.startsWith("/api/") ? `${BACKEND_URL}${path}` : path;
};

export default api;
