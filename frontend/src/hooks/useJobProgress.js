/**
 * useJobProgress — persistent job poller.
 *
 * Polls `/api/jobs/{id}` every 1.5s until status leaves {queued, running}.
 * Survives:
 *   • component remounts (lookup by job_id stored in localStorage scope key)
 *   • browser refresh — the page can re-attach to any in-flight job_id
 *   • tab backgrounding (we keep polling regardless of visibility)
 *
 * Backend jobs run as detached asyncio tasks so closing the browser doesn't
 * stop them — we just resume polling when the user returns.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { getJob } from "@/lib/api";

const SCOPE_PREFIX = "nxt1:job:";

export function rememberJob(scope, jobId) {
  try {
    localStorage.setItem(`${SCOPE_PREFIX}${scope}`, jobId);
  } catch {}
}
export function forgetJob(scope) {
  try {
    localStorage.removeItem(`${SCOPE_PREFIX}${scope}`);
  } catch {}
}
export function recallJob(scope) {
  try {
    return localStorage.getItem(`${SCOPE_PREFIX}${scope}`) || "";
  } catch {
    return "";
  }
}

export default function useJobProgress(jobId, { intervalMs = 1500, onDone } = {}) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);
  const stoppedRef = useRef(false);

  const stop = useCallback(() => {
    stoppedRef.current = true;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!jobId) return;
    stoppedRef.current = false;

    const tick = async () => {
      if (stoppedRef.current) return;
      try {
        const { data } = await getJob(jobId);
        setJob(data);
        const status = data?.status;
        if (status && !["queued", "running"].includes(status)) {
          stoppedRef.current = true;
          if (onDone) onDone(data);
          return;
        }
      } catch (e) {
        // Job may have just been created — keep retrying briefly.
        if (e?.response?.status === 404) {
          // pretend still queued
        } else {
          setError(e?.response?.data?.detail || e?.message || "Job poll failed");
        }
      }
      timerRef.current = setTimeout(tick, intervalMs);
    };

    tick();
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, intervalMs]);

  return { job, error, stop };
}
