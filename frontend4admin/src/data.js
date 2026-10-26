export const NAV = [
  ["overview", "Overview", "◫"], ["models", "Model laboratory", "⌁"], ["flow", "Data flow", "⇢"],
  ["quality", "Data quality", "◉"], ["routing", "Routing intelligence", "↗"], ["architecture", "Architecture", "⌘"],
  ["api", "API monitor", "⌘"], ["guide", "Project guide", "▤"], ["delivery", "Tests & deployment", "✓"],
];

export const MODEL_LABELS = {
  persistence: "Persistence", seasonal_naive: "Seasonal naive", historical_average: "Historical average",
  ridge: "Ridge regression", histogram_gradient_boosting: "Histogram gradient boosting", transformer: "Transformer",
  equal_weight_ensemble: "Equal-weight ensemble", weighted_ensemble: "Validation-selected ensemble",
};

export function modelRows(report, horizon) {
  const ensemble = report?.ensemble?.horizons?.[horizon]?.test_metrics;
  if (Array.isArray(ensemble) && ensemble.length) return ensemble.map((item) => ({ ...item, label: MODEL_LABELS[item.model] || item.model }));
  const stats = report?.statistical?.horizons?.[horizon]?.models || {};
  const transformer = report?.transformer?.horizons?.[horizon]?.metrics || [];
  return [...Object.entries(stats).map(([model, metrics]) => ({ model, ...metrics })), ...transformer.filter((m) => m.model === "transformer")]
    .map((item) => ({ ...item, label: MODEL_LABELS[item.model] || item.model }));
}

export function metricValue(row, metric) {
  const value = Number(row?.[metric]);
  return Number.isFinite(value) ? value : null;
}

export function predictionSeries(rows, model, limit = 250) {
  const stride = Math.max(1, Math.ceil(rows.length / limit));
  return rows.filter((_, index) => index % stride === 0).map((row) => ({
    time: String(row.target_time || "").slice(0, 10),
    actual: Number(row.actual),
    predicted: Number(row[`${model}_prediction`]),
    residual: Number(row[`${model}_prediction`]) - Number(row.actual),
    series: row.series,
  })).filter((row) => Number.isFinite(row.actual) && Number.isFinite(row.predicted));
}

export function residualBins(rows, model) {
  const errors = rows.map((row) => Number(row[`${model}_prediction`]) - Number(row.actual)).filter(Number.isFinite);
  if (!errors.length) return [];
  const lo = Math.floor(Math.min(...errors) / 10) * 10;
  const hi = Math.ceil(Math.max(...errors) / 10) * 10 || 10;
  const bins = [];
  for (let start = lo; start <= hi; start += 10) bins.push({ range: `${start}…${start + 10}`, count: 0 });
  errors.forEach((e) => { const i = Math.min(bins.length - 1, Math.max(0, Math.floor((e - lo) / 10))); bins[i].count += 1; });
  return bins;
}

export function numericBins(values, width = 0.5) {
  const valid = values.map(Number).filter(Number.isFinite);
  if (!valid.length) return [];
  const first = Math.floor(Math.min(...valid) / width) * width;
  const last = Math.ceil(Math.max(...valid) / width) * width;
  const bins = [];
  for (let x = first; x <= last; x += width) bins.push({ range: `${x.toFixed(1)}…${(x + width).toFixed(1)}`, count: 0 });
  valid.forEach((v) => { bins[Math.min(bins.length - 1, Math.max(0, Math.floor((v - first) / width)))].count += 1; });
  return bins;
}

export function elapsedLabel(seconds) {
  if (seconds === null || seconds === undefined) return "Unavailable";
  const n = Number(seconds);
  if (!Number.isFinite(n)) return "Unavailable";
  if (n < 60) return `${Math.round(n)} sec`;
  if (n < 3600) return `${Math.floor(n / 60)} min`;
  return `${Math.floor(n / 3600)} hr`;
}
