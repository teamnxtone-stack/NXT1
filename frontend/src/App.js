import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import ThemedToaster from "@/components/ThemedToaster";
import LandingPage from "@/pages/LandingPage";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import BuilderPage from "@/pages/BuilderPage";
import AdminWorkspace from "@/pages/AdminWorkspace";
import OnboardingPage from "@/pages/OnboardingPage";
import PrivacyPage from "@/pages/PrivacyPage";
import PreviewSharePage from "@/pages/PreviewSharePage";
import RequestAccessWall from "@/pages/RequestAccessWall";
import SignInPage from "@/pages/SignInPage";
import SignUpPage from "@/pages/SignUpPage";
import SiteEditorPage from "@/pages/SiteEditorPage";
import TermsPage from "@/pages/TermsPage";
import ContactPage from "@/pages/ContactPage";
import AuthGate from "@/components/AuthGate";
import OAuthCallbackInterceptor from "@/components/auth/OAuthCallback";
import ThemeProvider from "@/components/theme/ThemeProvider";
import WorkspaceShell from "@/components/workspace/WorkspaceShell";
import WorkspaceHome from "@/pages/workspace/WorkspaceHome";
import WorkspaceApps from "@/pages/workspace/WorkspaceApps";
import WorkspaceAccount from "@/pages/workspace/WorkspaceAccount";
import WorkspaceOperations from "@/pages/workspace/WorkspaceOperations";
import AgentOSDashboard from "@/pages/AgentOSDashboard";
import AgentsPage from "@/pages/AgentsPage";
import AgentOSPage from "@/pages/AgentOSPage";
import { useAgentActivityWatcher } from "@/lib/agentActivity";
import {
  WorkspaceDeployments,
  WorkspaceDomains,
  WorkspaceProviders,
  WorkspaceSettings,
  WorkspaceEditor,
} from "@/pages/workspace/WorkspaceModules";
import "@/App.css";

function App() {
  useAgentActivityWatcher(true);
  return (
    <ThemeProvider>
    <BrowserRouter>
      <ThemedToaster />
      <Routes>
        {/* Public */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/access" element={<LoginPage />} />
        <Route path="/signup" element={<SignUpPage />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/contact" element={<ContactPage />} />
        <Route path="/agentos" element={
          <AuthGate>
            <AgentOSDashboard />
          </AuthGate>
        } />
        <Route path="/p/:slug" element={<PreviewSharePage />} />

        {/* Authenticated app — gated by AuthGate which handles
            (a) no token → /signin, (b) pending/denied → access wall,
            (c) approved or admin → render. */}
        <Route
          path="/onboarding"
          element={
            <AuthGate>
              <OnboardingPage />
            </AuthGate>
          }
        />
        <Route
          path="/dashboard"
          element={
            <AuthGate>
              <DashboardPage />
            </AuthGate>
          }
        />
        <Route
          path="/workspace"
          element={
            <AuthGate>
              <OAuthCallbackInterceptor>
                <WorkspaceShell />
              </OAuthCallbackInterceptor>
            </AuthGate>
          }
        >
          <Route index element={<WorkspaceHome />} />
          <Route path="apps" element={<WorkspaceApps />} />
          {/* /workspace/live now redirects to /workspace/apps?segment=live for a single Apps surface. */}
          <Route path="live" element={<Navigate to="/workspace/apps?segment=live" replace />} />
          <Route path="drafts" element={<Navigate to="/workspace/apps?segment=drafts" replace />} />
          <Route path="deployments" element={<WorkspaceDeployments />} />
          <Route path="domains" element={<WorkspaceDomains />} />
          <Route path="providers" element={<WorkspaceProviders />} />
          <Route path="settings" element={<WorkspaceSettings />} />
          <Route path="editor" element={<WorkspaceEditor />} />
          <Route path="account" element={<WorkspaceAccount />} />
          <Route path="operations" element={<WorkspaceOperations />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="agentos" element={<AgentOSPage />} />
        </Route>
        <Route
          path="/builder/:projectId"
          element={
            <AuthGate>
              <BuilderPage />
            </AuthGate>
          }
        />
        <Route
          path="/admin"
          element={
            <AuthGate requireAdmin>
              <AdminWorkspace />
            </AuthGate>
          }
        />
        <Route
          path="/admin/site-editor"
          element={
            <AuthGate requireAdmin>
              <SiteEditorPage />
            </AuthGate>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
