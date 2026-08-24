export function daysLeft(expiresOn: string, todayStr: string): number {
  const e = new Date(expiresOn + "T00:00:00Z");
  const t = new Date(todayStr + "T00:00:00Z");
  return Math.round((e.getTime() - t.getTime()) / 86400000);
}

export function expiryBadge(expiresOn: string, todayStr: string): { label: string; tone: "mint" | "amber" | "danger" } {
  const d = daysLeft(expiresOn, todayStr);
  if (d < 0) return { label: `Expired ${Math.abs(d)}d ago`, tone: "danger" };
  if (d <= 1) return { label: `Use soon — ${d}d left`, tone: "amber" };
  if (d <= 3) return { label: `Expires in ${d}d`, tone: "amber" };
  return { label: `Expires ${expiresOn}`, tone: "mint" };
}
