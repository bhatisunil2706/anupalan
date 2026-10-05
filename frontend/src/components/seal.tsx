/**
 * Readiness seal: a circular stamp-like ring showing the share of requirements met.
 * The inner tick ring fills in step with progress so it reads like an official seal; it turns marigold at 100%.
 */
export function Seal({
  percent,
  size = 112,
  label,
  sublabel,
}: {
  percent: number;
  size?: number;
  label: string;
  sublabel?: string;
}) {
  const stroke = size * 0.075;
  const r = size / 2 - stroke;
  const c = 2 * Math.PI * r;
  const done = Math.max(0, Math.min(100, percent));
  const ticks = Array.from({ length: 40 });
  const complete = done === 100;
  return (
    <figure className="flex flex-col items-center gap-2 text-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${done}% ready`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-ink-50)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={complete ? "var(--color-marigold)" : "var(--color-ink)"}
          strokeWidth={stroke}
          strokeDasharray={`${(c * done) / 100} ${c}`}
          strokeLinecap="butt"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        {ticks.map((_, i) => {
          const a = (i / ticks.length) * 2 * Math.PI;
          const r1 = r - stroke * 1.1;
          const r2 = r - stroke * (i % 5 === 0 ? 1.9 : 1.5);
          return (
            <line
              key={i}
              x1={size / 2 + r1 * Math.sin(a)}
              y1={size / 2 - r1 * Math.cos(a)}
              x2={size / 2 + r2 * Math.sin(a)}
              y2={size / 2 - r2 * Math.cos(a)}
              stroke={i / ticks.length < done / 100 ? "var(--color-ink)" : "var(--color-line)"}
              strokeWidth={1}
            />
          );
        })}
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          fontSize={size * 0.24}
          fontWeight={700}
          fill="var(--color-text)"
        >
          {done}%
        </text>
      </svg>
      <figcaption>
        <span className="block text-sm font-semibold">{label}</span>
        {sublabel && <span className="block text-xs text-muted">{sublabel}</span>}
      </figcaption>
    </figure>
  );
}
