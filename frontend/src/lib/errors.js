/**
 * NXT1 — Centralised error parsing.
 *
 * FastAPI returns 422 validation errors as Pydantic v2 arrays of objects:
 *   detail: [
 *     { type, loc: [..], msg, input, url },
 *     ...
 *   ]
 *
 * When components do `toast.error(err.response.data.detail)` they end up
 * either rendering "[object Object]" or — when React tries to flatten an
 * array of objects directly — throwing the
 *   "Objects are not valid as a React child"
 * uncaught runtime error we hit in the preview surface.
 *
 * This helper normalises ANY error / detail shape into a single readable
 * string suitable for toasts, banners, and React children.
 */

/**
 * Normalise a backend error response into a single readable string.
 * @param {unknown} err     Axios error / Response payload / detail body.
 * @param {string}  fallback Message to use when nothing useful is found.
 * @returns {string}
 */
export function parseErrorMessage(err, fallback = "Something went wrong.") {
  if (err == null) return fallback;
  if (typeof err === "string") return err;

  // Axios error: dig into response.data.detail first.
  const detail =
    err?.response?.data?.detail ??
    err?.data?.detail ??
    err?.detail ??
    err?.response?.data ??
    err?.data ??
    err?.message;

  return _flatten(detail) || fallback;
}

function _flatten(d) {
  if (d == null) return "";
  if (typeof d === "string") return d;

  // Pydantic v2 error array — each item is { type, loc, msg, input, url }.
  if (Array.isArray(d)) {
    return d
      .map((item) => {
        if (item == null) return "";
        if (typeof item === "string") return item;
        if (typeof item.msg === "string") {
          const path = Array.isArray(item.loc)
            ? item.loc.filter((p) => p !== "body").join(".")
            : "";
          return path ? `${path}: ${item.msg}` : item.msg;
        }
        return safeStringify(item);
      })
      .filter(Boolean)
      .join(" · ");
  }

  // Generic object with a message-ish key.
  if (typeof d === "object") {
    if (typeof d.msg === "string") return d.msg;
    if (typeof d.message === "string") return d.message;
    if (typeof d.error === "string") return d.error;
    if (typeof d.detail === "string") return d.detail;
    return safeStringify(d);
  }

  return String(d);
}

function safeStringify(obj) {
  try {
    return JSON.stringify(obj);
  } catch {
    return String(obj);
  }
}

/**
 * Safely render any value (string / number / object / Pydantic error array)
 * as a React child. Use this anywhere you suspect an error object could
 * accidentally end up in JSX — eg. <p>{errorState}</p>.
 *
 * Returns a string, never an object, so React reconciliation cannot throw.
 */
export function renderableMessage(value, fallback = "") {
  if (value == null) return fallback;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return _flatten(value) || fallback;
}


/**
 * NXT1 — Friendly error UX layer.
 *
 * The chat / stream pipeline can surface raw provider noise: LiteLLM
 * tracebacks, budget-exceeded JSON dumps, rate-limit verbiage, OpenRouter
 * stack traces, Anthropic 529 walls of text. Users should never see any of
 * that. `friendlyError` collapses anything coming off the wire into a
 * short, calm, human sentence + a category we can use to drive the UI
 * ("retry", "switch model", "out of budget", "rate limited").
 *
 * @param {unknown} input  Error / message / event payload.
 * @returns {{ title: string, hint: string, category: string }}
 */
export function friendlyError(input) {
  const raw = (renderableMessage(input) || "").toString();
  const text = raw.toLowerCase();

  // Budget / credits
  if (
    text.includes("budget") ||
    text.includes("credit") ||
    text.includes("insufficient_quota") ||
    text.includes("billing")
  ) {
    return {
      title: "Out of model budget",
      hint: "Top up your provider credits or switch to a different model and try again.",
      category: "budget",
    };
  }

  // Rate limit
  if (
    text.includes("rate limit") ||
    text.includes("rate_limit") ||
    text.includes("429") ||
    text.includes("too many requests")
  ) {
    return {
      title: "Model is rate-limited",
      hint: "Give it a few seconds and retry — or pick another provider in the model picker.",
      category: "rate_limit",
    };
  }

  // Provider auth / missing key
  if (
    text.includes("api key") ||
    text.includes("api_key") ||
    text.includes("unauthorized") ||
    text.includes("401") ||
    text.includes("invalid_api_key")
  ) {
    return {
      title: "Provider not connected",
      hint: "This model needs an API key. Switch model or connect one from Workspace · Providers.",
      category: "auth",
    };
  }

  // Network / aborted / connection
  if (
    text.includes("network") ||
    text.includes("fetch") ||
    text.includes("abort") ||
    text.includes("timeout") ||
    text.includes("econnreset")
  ) {
    return {
      title: "Connection hiccup",
      hint: "The build stream dropped mid-flight. Retry — your project state is safe.",
      category: "network",
    };
  }

  // LiteLLM / generic provider trace — never show raw
  if (
    text.includes("litellm") ||
    text.includes("traceback") ||
    text.includes("openrouter") ||
    text.includes("anthropic.") ||
    text.includes("openai.") ||
    text.includes("\n  at ") ||
    text.includes("{\"")
  ) {
    return {
      title: "Model run failed",
      hint: "We couldn't reach the model. Retry, or switch to another provider from the picker.",
      category: "provider",
    };
  }

  // Unknown — return a calm message, never the raw payload.
  if (raw && raw.length < 140) {
    return {
      title: "Something interrupted the build",
      hint: raw,
      category: "unknown",
    };
  }
  return {
    title: "Something interrupted the build",
    hint: "Retry when you're ready — we'll pick up where we left off.",
    category: "unknown",
  };
}
