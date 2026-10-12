export const num = (value: string | number, digits = 0) => {
  const parsed = typeof value === "number" ? value : Number(String(value).replace(/,/g, ""));
  if (!Number.isFinite(parsed)) return String(value);
  return parsed.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

/** 金额在账本里带符号，展示时支出取绝对值，方向交给颜色和文案。 */
export const abs = (value: string | number, digits = 0) => num(Math.abs(Number(String(value).replace(/,/g, "")) || 0), digits);

export const pct = (part: number, whole: number) => (whole ? Math.min(100, (part / whole) * 100) : 0);

export const monthLabel = (iso: string) => `${iso.slice(5, 7)} 月`;

export const today = () => new Date().toISOString().slice(0, 10);

export function monthsBack(count: number): string {
  const now = new Date();
  now.setDate(1);
  now.setMonth(now.getMonth() - (count - 1));
  return now.toISOString().slice(0, 7);
}
