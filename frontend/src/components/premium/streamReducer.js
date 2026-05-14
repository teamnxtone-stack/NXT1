/**
 * NXT1 — SSE event → ActivityStream step mapper.
 *
 * Translates raw backend events into a curated, human-readable orchestration
 * feed. The mapper is intentionally opinionated: it merges duplicates,
 * combines low-value events, and inserts subtle DISCOVER · DEVELOP · DELIVER
 * identity beats so the stream reads like a real OS process rather than
 * a developer log.
 *
 * API:
 *   const r = createStreamReducer();
 *   r.push(event);          // ingest an SSE event payload
 *   r.complete();           // mark current active step done + final "ready"
 *   r.reset();              // start over for a new build
 *   r.snapshot();           // current step array (for ActivityStream)
 *
 * Each step:
 *   { id, label, detail?, note?, state: "pending"|"active"|"done" }
 */

function nid(seed) {
  return `${seed}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function createStreamReducer() {
  const steps = [];
  // Track which canonical phases we've already emitted so we don't dupe.
  const seenPhases = new Set();
  let scaffoldCount = 0;
  let toolWriteCount = 0;
  let toolEditCount = 0;
  let finalized = false;

  function activateNew(label, detail, note, agent) {
    // Mark previous active steps as done.
    for (const s of steps) if (s.state === "active") s.state = "done";
    const step = { id: nid(label), label, detail, note, agent, state: "active" };
    steps.push(step);
    return step;
  }

  function maybeAdd(canonicalId, label, detail, note, agent) {
    if (seenPhases.has(canonicalId)) {
      // Update detail on the existing matching step (most recent first).
      for (let i = steps.length - 1; i >= 0; i--) {
        if (steps[i].id.startsWith(canonicalId + "-")) {
          if (detail) steps[i].detail = detail;
          if (note) steps[i].note = note;
          if (agent && !steps[i].agent) steps[i].agent = agent;
          return steps[i];
        }
      }
    }
    seenPhases.add(canonicalId);
    return activateNew(label, detail, note, agent);
  }

  function push(ev) {
    if (!ev || finalized) return;
    const type = ev.type;

    if (type === "phase") {
      const label = String(ev.label || "").trim();
      if (!label) return;
      // Normalize the most common backend phases to our human labels.
      // Each step carries an `agent` identity so the UI can color-code who
      // is currently working — analyst, architect, coder, tester, devops, etc.
      if (/^inferring foundation/i.test(label)) {
        const fw = ev.inference?.framework;
        maybeAdd("inferring", "Inferring architecture", fw || null, "DISCOVER", "analyst");
      } else if (/^foundation loaded/i.test(label)) {
        const fw = ev.inference?.framework;
        const inf = steps.find((s) => s.id.startsWith("inferring-"));
        if (inf) inf.state = "done";
        maybeAdd("foundation", "Loading foundation", fw || null, null, "scaffold");
      } else if (/^planning/i.test(label) || /architect/i.test(label)) {
        maybeAdd("planning", "Planning app structure", null, "DEVELOP", "architect");
      } else if (/^editing/i.test(label) || /^writing/i.test(label) || /generating/i.test(label)) {
        maybeAdd("editing", "Generating UI & code", null, null, "coder");
      } else if (/route|api|wiring/i.test(label)) {
        maybeAdd("routes", "Wiring routes & APIs", null, null, "integrator");
      } else if (/validat|test|check/i.test(label)) {
        maybeAdd("validating", "Testing build", null, null, "tester");
      } else if (/fix|repair|debug|patch/i.test(label)) {
        maybeAdd("repairing", "Debugging & repairing", null, null, "debugger");
      } else if (/finaliz|preparing preview|preview ready/i.test(label)) {
        maybeAdd("preview", "Preparing preview", null, "DELIVER", "preview");
      } else if (/deploy/i.test(label)) {
        maybeAdd("deploy", "Deploying", null, "DELIVER", "devops");
      } else {
        // Unknown phase — surface its raw label, capped.
        maybeAdd(`phase-${label.slice(0, 24)}`, label, null, null, "coder");
      }
    } else if (type === "tool") {
      const action = ev.action || "";
      const path = ev.path || "";
      if (action === "scaffold") {
        scaffoldCount += 1;
        maybeAdd("foundation", "Loading foundation", `${scaffoldCount} files prepared`, null, "scaffold");
      } else if (action === "created" || action === "edited") {
        if (action === "created") toolWriteCount += 1;
        else toolEditCount += 1;
        const detail = path
          ? `${path}`
          : `${toolWriteCount} new · ${toolEditCount} edited`;
        maybeAdd("editing", "Generating UI & code", detail, null, "coder");
      } else if (action === "viewed") {
        const editStep = steps.find((s) => s.id.startsWith("editing-"));
        if (editStep && path) editStep.detail = `inspecting ${path}`;
      }
    } else if (type === "narration") {
      // Narration lines are prose; we don't add them as steps but use them as
      // detail context on the active step. Keep it short.
      const line = String(ev.text || "").slice(0, 96);
      const active = [...steps].reverse().find((s) => s.state === "active");
      if (active && line) active.detail = line;
    } else if (type === "user_message") {
      // Brand-new build kickoff. Start with "Reading your request".
      if (!seenPhases.has("reading")) {
        seenPhases.add("reading");
        activateNew("Reading your request", null, "DISCOVER", "router");
      }
    } else if (type === "info") {
      // Quiet informational events — only surface if they look important.
      const msg = String(ev.message || "").trim();
      if (/deploy/i.test(msg)) maybeAdd("deploy", "Deployment ready", null, "DELIVER", "devops");
    }
  }

  function complete(finalLabel = "Ready to preview") {
    if (finalized) return;
    finalized = true;
    for (const s of steps) if (s.state === "active") s.state = "done";
    activateNew(finalLabel, null, "DELIVER", "preview");
  }

  function reset() {
    steps.length = 0;
    seenPhases.clear();
    scaffoldCount = 0;
    toolWriteCount = 0;
    toolEditCount = 0;
    finalized = false;
  }

  function snapshot() {
    // Return a stable copy.
    return steps.map((s) => ({ ...s }));
  }

  return { push, complete, reset, snapshot };
}
