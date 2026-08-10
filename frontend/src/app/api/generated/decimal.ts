import { z } from "zod";

const decimal6Pattern = /^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/;
const signedDecimal6Pattern = /^-?(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/;
const servingDecimalPattern = /^(?!0(?:\.0{1,3})?$)(?:0|[1-9][0-9]*)(?:\.[0-9]{1,3})?$/;

export const decimal6 = z.string().regex(decimal6Pattern);
export const signedDecimal6 = z.string().regex(signedDecimal6Pattern);
export const servingDecimal = z.string().regex(servingDecimalPattern);

export type DecimalString = z.infer<typeof decimal6>;

export function canonicalDecimal(value: string): DecimalString {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match || (match[2]?.length ?? 0) > 6) {
    throw new Error("Decimal must be non-negative with at most six fractional places.");
  }
  const whole = (match[1] ?? "0").replace(/^0+(?=\d)/u, "");
  const fraction = (match[2] ?? "").replace(/0+$/u, "");
  return decimal6.parse(fraction ? `${whole}.${fraction}` : whole);
}
