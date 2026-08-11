const RING_RADIUS = 46;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

const SEGMENTS = [
  { key: "protein", pct: 41, color: "var(--macro-protein)" },
  { key: "carbohydrate", pct: 26, color: "var(--macro-carbohydrate)" },
  { key: "fat", pct: 15, color: "var(--macro-fat)" },
] as const;

const BARS = [
  { key: "protein", label: "Protein", value: "164 / 180 g", pct: 91, color: "var(--macro-protein)" },
  { key: "carbohydrate", label: "Carbs", value: "206 / 220 g", pct: 94, color: "var(--macro-carbohydrate)" },
  { key: "fat", label: "Fat", value: "61 / 65 g", pct: 94, color: "var(--macro-fat)" },
] as const;

export function MacroRing({ className = "" }: { className?: string }) {
  let rotation = 0;
  const segments = SEGMENTS.map((segment) => {
    const start = rotation;
    rotation += (segment.pct / 100) * 360;
    const dash = (segment.pct / 100) * RING_CIRCUMFERENCE;
    return (
      <circle
        key={segment.key}
        className={`macro-ring__segment macro-ring__segment--${segment.key}`}
        cx="50"
        cy="50"
        r={RING_RADIUS}
        fill="none"
        strokeWidth="3.5"
        strokeDasharray={`${dash} ${RING_CIRCUMFERENCE - dash}`}
        transform={`rotate(${start - 90} 50 50)`}
      />
    );
  });

  return (
    <svg className={`macro-ring ${className}`} viewBox="0 0 100 100" aria-hidden="true">
      <circle className="macro-ring__track" cx="50" cy="50" r={RING_RADIUS} fill="none" strokeWidth="3.5" />
      {segments}
    </svg>
  );
}

export function MacroPreview({ className = "" }: { className?: string }) {
  return (
    <figure className={`macro-preview ${className}`} aria-hidden="true">
      <div className="macro-preview__plate">
        <MacroRing />
        <div className="macro-preview__plate-core">
          <span className="macro-preview__plate-label">Today</span>
          <span className="macro-preview__plate-value data-value">2,210</span>
          <span className="macro-preview__plate-target data-value">of 2,200 kcal</span>
        </div>
      </div>
      <dl className="macro-preview__bars">
        {BARS.map((bar) => (
          <div className={`macro-preview__bar macro-preview__bar--${bar.key}`} key={bar.key}>
            <dt>{bar.label}</dt>
            <dd className="data-value">{bar.value}</dd>
            <span className="macro-preview__track">
              <span style={{ width: `${bar.pct}%`, background: bar.color }} />
            </span>
          </div>
        ))}
      </dl>
    </figure>
  );
}
