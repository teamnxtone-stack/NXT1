/**
 * Premium UI block — card.aceternity.3d-pin
 *
 * Card tilts in 3D on hover with a perspective pin.
 */
import { motion, useMotionValue, useTransform } from "framer-motion";

export default function ThreeDPinCard({
  title = "Product showcase",
  description = "Tilt me — perspective pin reacts to cursor.",
  imageSrc = null,
  imageAlt = "",
  href = "#",
}) {
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const rotateX = useTransform(my, [-50, 50], [10, -10]);
  const rotateY = useTransform(mx, [-50, 50], [-10, 10]);

  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    mx.set(e.clientX - r.left - r.width / 2);
    my.set(e.clientY - r.top - r.height / 2);
  };
  const onLeave = () => { mx.set(0); my.set(0); };

  return (
    <a
      href={href}
      data-testid="block-card-3d-pin"
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      className="block"
      style={{ perspective: "900px" }}
    >
      <motion.div
        style={{
          rotateX,
          rotateY,
          transformStyle: "preserve-3d",
          background: "#0a0a0f",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
        className="rounded-2xl overflow-hidden text-white p-6 transition-shadow hover:shadow-[0_30px_60px_-20px_rgba(139,92,246,0.4)]"
      >
        {imageSrc && (
          <div
            className="rounded-xl mb-4 aspect-[16/9] bg-cover bg-center"
            style={{
              backgroundImage: `url(${imageSrc})`,
              boxShadow: "inset 0 0 60px rgba(0,0,0,0.6)",
            }}
            aria-label={imageAlt}
          />
        )}
        <div className="text-[16px] font-semibold mb-1">{title}</div>
        <div className="text-[13px]" style={{ color: "rgba(255,255,255,0.55)" }}>
          {description}
        </div>
      </motion.div>
    </a>
  );
}
