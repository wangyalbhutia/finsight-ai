import { clsx, type ClassValue } from "clsx";
export function cn(...inputs: ClassValue[]) { return clsx(inputs); }
export function inr(n: number | undefined | null): string {
  const v = typeof n === "number" && Number.isFinite(n) ? n : 0;
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(v);
}
export function pct(n: number | undefined): string { return `${Math.round((n ?? 0) * (Math.abs(n ?? 0) <= 1 ? 100 : 1))}%`; }
