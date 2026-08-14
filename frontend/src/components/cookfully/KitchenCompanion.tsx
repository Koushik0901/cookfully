import "./KitchenCompanion.css";

type KitchenCompanionMoment = "loading" | "empty" | "success" | "milestone" | "error";
type KitchenCompanionSize = "sm" | "md" | "lg";

export function KitchenCompanion({
  moment,
  size = "md",
  className = "",
}: {
  moment: KitchenCompanionMoment;
  size?: KitchenCompanionSize;
  className?: string;
}) {
  return (
    <span
      className={`kitchen-companion kitchen-companion--${moment} kitchen-companion--${size} ${className}`.trim()}
      data-companion-moment={moment}
      aria-hidden="true"
    >
      <svg viewBox="0 0 160 128" focusable="false">
        <ellipse className="kitchen-companion__shadow" cx="80" cy="111" rx="45" ry="7" />

        <g className="kitchen-companion__bowl">
          <path className="kitchen-companion__saucer" d="M44 101c10 10 62 10 72 0" />
          <path className="kitchen-companion__body" d="M36 55h88c-2 29-19 48-44 48S38 84 36 55Z" />
          <path className="kitchen-companion__rim" d="M34 55c0-6 20-11 46-11s46 5 46 11-20 10-46 10-46-4-46-10Z" />
          <g className="kitchen-companion__face">
            <circle cx="68" cy="78" r="2" />
            <circle cx="92" cy="78" r="2" />
            <path className="kitchen-companion__mouth kitchen-companion__mouth--smile" d="M72 86c5 5 11 5 16 0" />
            <path className="kitchen-companion__mouth kitchen-companion__mouth--rest" d="M74 88h12" />
          </g>
        </g>

        <g className="kitchen-companion__sprig">
          <path className="kitchen-companion__stem" d="M80 47c0-12 3-20 10-28" />
          <path className="kitchen-companion__leaf kitchen-companion__leaf--left" d="M83 32c-10 0-15-5-15-12 9-1 15 3 15 12Z" />
          <path className="kitchen-companion__leaf kitchen-companion__leaf--right" d="M87 25c2-9 8-13 16-11 0 8-6 13-16 11Z" />
        </g>

        {moment === "loading" ? (
          <g className="kitchen-companion__loading-marks">
            <g className="kitchen-companion__whisk">
              <path d="M107 20 87 51" />
              <path d="M83 55c-8-5-10-13-5-17 5-4 12 1 12 10 0-9 5-15 10-12 5 4 1 13-8 19" />
            </g>
            <path className="kitchen-companion__steam kitchen-companion__steam--one" d="M56 43c-5-6 4-8 0-15" />
            <path className="kitchen-companion__steam kitchen-companion__steam--two" d="M69 39c-4-5 3-7 0-12" />
          </g>
        ) : null}

        {moment === "empty" ? (
          <g className="kitchen-companion__seeds">
            <circle cx="45" cy="38" r="2.5" />
            <circle cx="117" cy="33" r="2" />
            <circle cx="126" cy="76" r="2.5" />
          </g>
        ) : null}

        {moment === "success" || moment === "milestone" ? (
          <g className="kitchen-companion__badge">
            <circle cx="120" cy="37" r="17" />
            <path className="kitchen-companion__check" d="m111 37 6 6 12-13" />
          </g>
        ) : null}

        {moment === "milestone" ? (
          <g className="kitchen-companion__celebration">
            <path d="m35 33-6-5" />
            <path d="m31 47-9-1" />
            <path d="m123 76 9 3" />
            <circle cx="42" cy="24" r="2.5" />
            <circle cx="136" cy="61" r="2.5" />
          </g>
        ) : null}

        {moment === "error" ? (
          <g className="kitchen-companion__error-mark">
            <circle cx="121" cy="39" r="15" />
            <path d="M121 31v10" />
            <circle cx="121" cy="47" r="1.5" />
          </g>
        ) : null}
      </svg>
    </span>
  );
}
