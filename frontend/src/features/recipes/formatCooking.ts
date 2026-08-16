export function formatCookingNumber(value: string | number | null | undefined, maximumFractionDigits = 3) {
  if (value == null || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(number);
}

export function formatCookingInput(value: string | number | null | undefined) {
  if (value == null || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toFixed(6).replace(/\.?0+$/, "");
}

export function formatCookingText(value: string) {
  return value.replace(/-?\d+\.\d+/g, (match) => formatCookingNumber(match));
}

export function servingLabel(quantity: string | number, unit: string) {
  const amount = Number(quantity);
  const friendlyUnit = amount === 1 && unit.toLowerCase() === "servings" ? "serving" : unit;
  return `${formatCookingNumber(quantity)} ${friendlyUnit}`;
}

export function sourceHost(url: string | null | undefined) {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}
