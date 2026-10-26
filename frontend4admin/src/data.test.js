import { elapsedLabel, modelRows, numericBins, predictionSeries, residualBins } from "./data";

test("model rows map generated metrics without embedding scores", () => {
  const rows = modelRows({ ensemble: { horizons: { "1d": { test_metrics: [{ model: "ridge", mae: 2, rmse: 3, n: 9 }] } } } }, "1d");
  expect(rows[0]).toMatchObject({ label: "Ridge regression", mae: 2, rmse: 3, n: 9 });
});

test("prediction transforms ignore missing and nonnumeric output", () => {
  const rows = predictionSeries([{ target_time: "2024-01-01", actual: "4", ridge_prediction: "5" }, { actual: "2", ridge_prediction: "bad" }], "ridge");
  expect(rows).toEqual([{ time: "2024-01-01", actual: 4, predicted: 5, residual: 1, series: undefined }]);
});

test("residual histogram and freshness labels are bounded and honest", () => {
  expect(residualBins([{ actual: 10, ridge_prediction: 15 }, { actual: 20, ridge_prediction: 5 }], "ridge").reduce((n, b) => n + b.count, 0)).toBe(2);
  expect(elapsedLabel(null)).toBe("Unavailable");
  expect(elapsedLabel(65)).toBe("1 min");
  expect(numericBins([-0.1, 0.1, 1.4], 0.5).reduce((n, b) => n + b.count, 0)).toBe(3);
});
