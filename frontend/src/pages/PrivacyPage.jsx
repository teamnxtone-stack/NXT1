import LegalPage, { Section, Bullets } from "./LegalPage";

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      lastUpdated="May 12, 2026"
      body={
        <>
          <p>
            NXT1 is operated by <strong className="text-white">Jwood Technologies</strong>. This Privacy
            Policy explains what data we collect when you use the platform, why we collect it, how it
            is stored, and the choices you have. We collect the minimum necessary to operate the
            service and we do not sell personal data — ever.
          </p>

          <Section title="What we collect">
            <Bullets
              items={[
                "Account info: name, email, hashed password (or OAuth identifiers).",
                "Workspace content: prompts, projects, generated files, uploaded assets.",
                "Operational telemetry: feature usage, error logs, performance metrics — used only to keep the platform stable.",
                "Optional billing data handled by our payment processor; we never store full card details.",
              ]}
            />
          </Section>

          <Section title="Why we collect it">
            <Bullets
              items={[
                "Run the workspace, deliver streamed AI generations, and persist your projects.",
                "Diagnose and prevent abuse, fraud, or service degradation.",
                "Improve the product through aggregated, de-identified analytics.",
              ]}
            />
          </Section>

          <Section title="Third-party model providers">
            <p>
              Your prompts and project context may be transmitted to AI providers (Anthropic, OpenAI,
              Google, Groq, DeepSeek and similar) under their respective enterprise terms. We choose
              providers that offer no-retention or zero-data-training configurations wherever possible
              and we route by the provider you select in the model picker.
            </p>
          </Section>

          <Section title="Storage & retention">
            <p>
              Project files are stored in project-scoped storage and accessible only to the
              authenticated owner. Backups are encrypted at rest. You may request deletion of your
              account, individual projects, or chat history at any time and we will action the request
              within thirty (30) days.
            </p>
          </Section>

          <Section title="Your rights">
            <Bullets
              items={[
                "Access — request a copy of your stored data.",
                "Correction — update or correct anything in your profile or projects.",
                "Deletion — close your account and remove personal data.",
                "Portability — export your projects as ZIP or to a connected GitHub repo.",
                "Objection — opt out of optional product analytics from Settings.",
              ]}
            />
          </Section>

          <Section title="Contact">
            <p>
              Privacy questions, deletion requests, or compliance inquiries can be sent to{" "}
              <a className="text-white hover:underline" href="mailto:privacy@jwoodtech.io">
                privacy@jwoodtech.io
              </a>{" "}
              or via the <a className="text-white hover:underline" href="/contact">Contact</a> page.
            </p>
          </Section>
        </>
      }
    />
  );
}
