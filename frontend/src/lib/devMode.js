/**
 * Developer Mode — when OFF (default), advanced developer tools (Files,
 * Runtime, Env, History) are hidden from the Tools drawer so the chat-first
 * experience stays clean. When ON, every advanced panel is exposed.
 *
 * Persistent in localStorage. Components subscribe via the `useDevMode`
 * hook so flipping the toggle updates every consumer instantly.
 */
import { useEffect, useState } from "react";

const KEY = "nxt1.devMode";
const EVENT = "nxt1:devModeChange";

export function getDevMode() {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setDevMode(on) {
  try {
    if (on) window.localStorage.setItem(KEY, "1");
    else window.localStorage.removeItem(KEY);
    window.dispatchEvent(new CustomEvent(EVENT, { detail: { on: !!on } }));
  } catch {
    /* ignore */
  }
}

export function useDevMode() {
  const [on, setOn] = useState(getDevMode());
  useEffect(() => {
    const handler = (ev) => setOn(!!ev?.detail?.on);
    window.addEventListener(EVENT, handler);
    return () => window.removeEventListener(EVENT, handler);
  }, []);
  return [on, setDevMode];
}
