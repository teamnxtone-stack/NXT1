/**
 * UsersPanel — admin-only list of public users with one-click access toggle
 * (approve / deny / pending). Surfaces email, name, status, and onboarding
 * answers when present.
 */
import { useEffect, useState } from "react";
import { Check, Loader2, Mail, RefreshCw, X, UserMinus } from "lucide-react";
import { toast } from "sonner";
import { listUsers, updateUserAccess } from "@/lib/api";

const STATUSES = [
  { id: "approved", label: "Approve", icon: Check, accent: "emerald" },
  { id: "denied", label: "Deny", icon: X, accent: "amber" },
  { id: "pending", label: "Pending", icon: UserMinus, accent: "zinc" },
];

const STATUS_PILL = {
  approved: "border-emerald-400/30 bg-emerald-500/10 text-emerald-200",
  pending: "border-amber-400/25 bg-amber-500/10 text-amber-200",
  denied: "border-red-400/25 bg-red-500/10 text-red-200",
};

export default function UsersPanel() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState({}); // userId -> bool

  const refresh = () => {
    setLoading(true);
    listUsers()
      .then(({ data }) => setUsers(data.items || []))
      .catch((e) => toast.error(e?.response?.data?.detail || "Couldn't load users"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  const update = async (userId, status) => {
    setPending((p) => ({ ...p, [userId]: true }));
    try {
      await updateUserAccess(userId, status);
      setUsers((arr) =>
        arr.map((u) => (u.user_id === userId ? { ...u, access_status: status } : u))
      );
      toast.success(`User ${status}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Update failed");
    } finally {
      setPending((p) => ({ ...p, [userId]: false }));
    }
  };

  return (
    <div className="p-4 sm:p-5" data-testid="users-tab">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500">
            Public users
          </div>
          <div className="text-[14px] text-white mt-0.5">
            Approve or deny new sign-ups
          </div>
        </div>
        <button
          onClick={refresh}
          className="h-8 w-8 flex items-center justify-center rounded-full text-zinc-400 hover:text-white hover:bg-white/5 transition"
          title="Refresh"
          data-testid="users-refresh"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {loading && (
        <div className="text-center py-10 text-zinc-500 text-[12px]">
          <Loader2 size={16} className="animate-spin inline mr-2" />
          Loading users…
        </div>
      )}

      {!loading && users.length === 0 && (
        <div className="text-[12px] text-zinc-500 py-6 text-center border border-dashed border-white/10 rounded-lg">
          No users yet.
        </div>
      )}

      <div className="space-y-2">
        {users.map((u) => {
          const status = u.access_status || "pending";
          const isAdmin = u.role === "admin";
          return (
            <div
              key={u.user_id}
              className="rounded-xl border border-white/8 surface-1 p-3"
              data-testid={`user-row-${u.user_id}`}
            >
              <div className="flex items-start gap-3">
                <span className="h-9 w-9 rounded-full bg-white/5 border border-white/10 flex items-center justify-center shrink-0 text-[12px] mono uppercase tracking-wider text-zinc-300">
                  {(u.name || u.email || "?").trim().charAt(0).toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[13px] text-white truncate">
                      {u.name || u.email}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-[10px] mono uppercase tracking-wider ${
                        isAdmin
                          ? "border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-200"
                          : STATUS_PILL[status] || STATUS_PILL.pending
                      }`}
                    >
                      {isAdmin ? "admin" : status}
                    </span>
                  </div>
                  <div className="text-[11px] mono text-zinc-500 truncate flex items-center gap-1 mt-0.5">
                    <Mail size={10} />
                    {u.email}
                  </div>
                </div>
              </div>
              {!isAdmin && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {STATUSES.map((s) => {
                    const active = status === s.id;
                    const isPending = pending[u.user_id];
                    return (
                      <button
                        key={s.id}
                        onClick={() => update(u.user_id, s.id)}
                        disabled={active || isPending}
                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] mono uppercase tracking-wider border transition ${
                          active
                            ? `border-${s.accent}-400/40 bg-${s.accent}-500/10 text-${s.accent}-200 cursor-default`
                            : "border-white/10 text-zinc-400 hover:border-white/30 hover:text-white"
                        } disabled:opacity-60`}
                        data-testid={`user-${u.user_id}-${s.id}`}
                      >
                        <s.icon size={10} />
                        {s.label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
