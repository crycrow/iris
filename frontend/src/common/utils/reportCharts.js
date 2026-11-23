export const palette = {
  blue: "var(--accent)",
  teal: "var(--success)",
  violet: "var(--secondary)",
  amber: "var(--warning)",
  rose: "var(--warning)",
  info: "var(--info)",
  red: "var(--danger)",
  slate: "var(--muted)",
};
export const severityColors = {
  critical: palette.red,
  high: palette.rose,
  medium: "var(--risk-medium)",
  low: palette.teal,
};
export const statusColors = {
  new: palette.red,
  reviewing: palette.info,
  in_progress: palette.blue,
  closed: palette.teal,
  rejected: palette.slate,
};
export const taskColors = {
  backlog: "color-mix(in srgb, var(--muted) 55%, var(--card))",
  todo: "color-mix(in srgb, var(--muted) 35%, var(--card))",
  dev: palette.blue,
  review: palette.violet,
  testing: palette.slate,
  release_wait: palette.rose,
  done: palette.teal,
  cancelled: "var(--border)",
};

export function finite(value) {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    typeof value === "boolean"
  )
    return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
export function chartNumber(value, digits = 2) {
  const n = finite(value);
  return n === null
    ? "Нет данных"
    : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(
        n,
      );
}
export function axisDomain(values, divisions = 4, integer = false) {
  const valid = values.map(finite).filter((v) => v !== null);
  const low = Math.min(0, ...valid),
    high = Math.max(0, ...valid);
  if (!low && !high) return { min: 0, max: 1, ticks: [0, 1] };
  const raw = (high - low) / divisions;
  const base = 10 ** Math.floor(Math.log10(raw));
  const candidate = [1, 2, 2.5, 5, 10].find((x) => x * base >= raw) * base;
  const step = integer ? Math.max(1, Math.ceil(candidate)) : candidate;
  const min = Math.floor(low / step) * step,
    max = Math.ceil(high / step) * step;
  const ticks = Array.from(
    { length: Math.round((max - min) / step) + 1 },
    (_, i) => Number((min + i * step).toPrecision(12)),
  );
  return { min, max, ticks };
}
export function lineSegments(values, x, y) {
  const segments = [];
  let current = [];
  values.forEach((value, i) => {
    const n = finite(value);
    if (n === null) {
      if (current.length) segments.push(current);
      current = [];
    } else current.push(`${x(i)},${y(n)}`);
  });
  if (current.length) segments.push(current);
  return segments.map((s) => s.join(" "));
}
export function groupedCounts(items, key, labels = {}, colors = {}) {
  const counts = new Map();
  items.forEach((item) => {
    const value = item[key] || "Не указано";
    counts.set(value, (counts.get(value) || 0) + 1);
  });
  const keys = [
    ...Object.keys(labels),
    ...Array.from(counts.keys()).filter((k) => !(k in labels)),
  ];
  return keys.map((key, i) => ({
    key,
    label: labels[key] || (Object.keys(labels).length ? "Неизвестная категория" : key),
    value: counts.get(key) || 0,
    color: colors[key] || (i === 0 ? palette.blue : palette.slate),
  }));
}
export function monthlyLabel(value) {
  const [year, month] = String(value).split("-").map(Number);
  return year && month
    ? new Intl.DateTimeFormat("ru-RU", {
        month: "short",
        year: "2-digit",
      }).format(new Date(year, month - 1, 1))
    : String(value);
}
