/**
 * NXT1 — WorkspaceRouter (Phase 18)
 *
 * Authenticated workspace home. Per user direction:
 *   • Do NOT redirect into a generated app
 *   • Do NOT show admin cards / analytics
 *   • Show the Workspace Home: prompt-first, premium, calm
 *
 * This is simply DashboardPage rendered as the canonical workspace surface.
 * The Dashboard already implements: prompt cockpit + recent projects grid.
 * Top horizontal nav is provided by DashboardPage itself.
 */
import DashboardPage from "./DashboardPage";
import OAuthCallbackInterceptor from "@/components/auth/OAuthCallback";

export default function WorkspaceRouter() {
  return (
    <OAuthCallbackInterceptor>
      <DashboardPage />
    </OAuthCallbackInterceptor>
  );
}
