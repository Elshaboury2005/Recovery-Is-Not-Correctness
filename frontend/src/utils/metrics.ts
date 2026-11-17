/** Keep absent measurements distinct from an observed zero, including legacy aliases. */
export function measuredNumber(record: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = record[key];
    if (value === undefined) continue;
    if (value === null || (typeof value !== 'number' && typeof value !== 'string')) return null;
    if (typeof value === 'string' && !value.trim()) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }
  return null;
}
