import { type KeyboardEvent, useRef } from "react";

import type { PeriodTotal } from "./types";

function dayLabel(value: string): string {
  return new Intl.DateTimeFormat("en-CA", { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

export function DayTabs({ dates, selected, onSelect, totals, entryCounts = {} }: { dates: string[]; selected: string; onSelect: (date: string) => void; totals: Record<string, PeriodTotal>; entryCounts?: Record<string, number> }) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  function keyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!direction) return;
    event.preventDefault();
    refs.current[(index + direction + dates.length) % dates.length]?.focus();
  }
  return (
    <div className="day-tabs" role="tablist" aria-label="Days in planning week">
      {dates.map((date, index) => {
        const total = totals[date];
        const count = entryCounts[date] ?? (total ? 1 : 0);
        return <button key={date} ref={(node) => { refs.current[index] = node; }} className={`day-tab ${date === selected ? "day-tab--active" : ""}`} role="tab" aria-selected={date === selected} aria-label={dayLabel(date)} tabIndex={date === selected ? 0 : -1} onKeyDown={(event) => keyDown(event, index)} onClick={() => onSelect(date)}><span>{new Intl.DateTimeFormat("en-CA", { weekday: "short", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`))}</span><strong>{date.slice(-2)}</strong><small>{count ? `${count} ${count === 1 ? "meal" : "meals"}` : "Open"}</small></button>;
      })}
    </div>
  );
}

