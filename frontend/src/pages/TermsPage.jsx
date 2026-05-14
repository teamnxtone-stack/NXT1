import LegalPage, { Section, Bullets } from "./LegalPage";

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      lastUpdated="May 12, 2026"
      body={
        <>
          <p>
            By using <strong className="text-white">NXT1</strong> (operated by Jwood Technologies),
            you agree to these Terms of Service. NXT1 is an AI software platform that lets you build,
            preview, and ship applications generated from natural-language prompts. These terms cover
            access, acceptable use, intellectual property, and termination.
          </p>

          <Section title="Account & access">
            <Bullets
              items={[
                "You are responsible for maintaining the confidentiality of your credentials.",
                "Accounts are personal; team and enterprise plans have their own seat terms.",
                "We may suspend accounts that abuse the platform, our partners' APIs, or other users.",
              ]}
            />
          </Section>

          <Section title="Acceptable use">
            <Bullets
              items={[
                "Don't generate or deploy content that violates law, third-party rights, or the policies of the model providers we route to.",
                "Don't reverse-engineer rate-limited APIs, exploit credit systems, or attempt to extract internal prompts.",
                "Don't use NXT1 to create services that compete by direct-mirroring our generated output or visual identity.",
              ]}
            />
          </Section>

          <Section title="Your content & IP">
            <p>
              Code, designs, and project files you generate on NXT1 are <strong className="text-white">yours</strong>. You
              grant us a limited license only to host, transmit, and stream those files back to you and your collaborators,
              and to operate provider integrations on your behalf. You may export at any time via ZIP or GitHub sync.
            </p>
          </Section>

          <Section title="AI output disclaimer">
            <p>
              AI-generated code, copy, and design suggestions are provided as-is. You are responsible
              for reviewing, testing, and securing anything you ship to production. NXT1 is not liable
              for damages arising from generated output that you deploy without review.
            </p>
          </Section>

          <Section title="Payment & cancellation">
            <p>
              Paid plans renew on the cadence you select unless cancelled before the renewal date.
              Cancellation stops future billing and retains your data through the end of the paid
              period. Refunds are evaluated case-by-case via <a className="text-white hover:underline" href="/contact">Contact</a>.
            </p>
          </Section>

          <Section title="Termination">
            <p>
              You may delete your account from Settings at any time. We may terminate accounts that
              materially breach these terms or that pose risk to other users or our infrastructure.
            </p>
          </Section>

          <Section title="Changes">
            <p>
              We may update these terms as the product evolves. Material changes will be announced in
              the workspace or via email at least seven (7) days before they take effect.
            </p>
          </Section>

          <Section title="Contact">
            <p>
              Questions about these terms? Reach us via the{" "}
              <a className="text-white hover:underline" href="/contact">Contact</a> page or at{" "}
              <a className="text-white hover:underline" href="mailto:legal@jwoodtech.io">
                legal@jwoodtech.io
              </a>.
            </p>
          </Section>
        </>
      }
    />
  );
}
