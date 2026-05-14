/**
 * NXT1 Carbon Shell — primitive page wrapper.
 * Use on any internal page (dashboard, builder, admin) that should sit on the
 * new carbon backdrop without the heavy public-landing orbs.
 */
import GradientBackdrop from "@/components/GradientBackdrop";

export default function CarbonShell({ children, variant = "workspace", intensity = "strong", className = "" }) {
  return (
    <div className={`relative min-h-screen w-full overflow-x-hidden text-white ${className}`}>
      <GradientBackdrop variant={variant} intensity={intensity} />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
