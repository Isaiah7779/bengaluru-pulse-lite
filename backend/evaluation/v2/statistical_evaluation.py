"""Create chronological, baseline-inclusive evaluation outputs for real research data.

Run from the backend directory with ``python -m evaluation.v2.statistical_evaluation``.
This report path is deliberately separate from model registration and activation.
"""

from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from core.settings import get_settings
from forecasting.pipeline import (
    RESEARCH,
    candidates,
    chronological_split,
    feature_columns,
    historical_average_table,
    load_research,
    metrics,
    model_matrix,
    predict_historical,
    supervised,
    to_grid,
)

MIN_GROUP_SAMPLES = 30
COLORS = {
    "persistence": "#64748b",
    "seasonal_naive": "#0f766e",
    "historical_average": "#d97706",
    "ridge": "#2563eb",
    "histogram_gradient_boosting": "#9333ea",
}
LABELS = {
    "persistence": "Persistence",
    "seasonal_naive": "Seasonal naive",
    "historical_average": "Historical average",
    "ridge": "Ridge",
    "histogram_gradient_boosting": "Histogram Gradient Boosting",
}


def calculate_metrics(actual: Iterable[float], predicted: Iterable[float]) -> Dict:
    """Return regression metrics, with R² omitted when it is mathematically undefined."""
    y = np.asarray(list(actual), dtype=float)
    p = np.asarray(list(predicted), dtype=float)
    if len(y) != len(p) or not len(y):
        raise ValueError("Actual and predicted values must have the same nonzero length")
    measured = metrics(y, p)
    r2 = measured["r2"]
    return {
        "mae": float(measured["mae"]),
        "rmse": float(measured["rmse"]),
        "r2": float(r2) if math.isfinite(r2) and len(y) >= 2 else None,
        "n": int(len(y)),
    }


def _svg(path: Path, title: str, body: str, width: int = 1100, height: int = 650) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<title>{html.escape(title)}</title><rect width="100%" height="100%" fill="white"/>'
        f'<text x="{width/2:.0f}" y="32" text-anchor="middle" font-family="sans-serif" font-size="20">{html.escape(title)}</text>'
        f'{body}</svg>',
        encoding="utf-8",
    )


def _line(x1, y1, x2, y2, color="#cbd5e1", width=1, dash="") -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"{dash_attr}/>'


def _legend(items: List[Tuple[str, str]], x: int, y: int, step: int = 22) -> str:
    parts = []
    for i, (name, color) in enumerate(items):
        yy = y + i * step
        parts.append(_line(x, yy, x + 22, yy, color, 3))
        parts.append(f'<text x="{x+30}" y="{yy+5}" font-family="sans-serif" font-size="13">{html.escape(name)}</text>')
    return "".join(parts)


def _comparison_plot(comparison: pd.DataFrame, path: Path) -> None:
    width, height, left, right, top, bottom = 1100, 650, 280, 70, 90, 90
    plot_w = width - left - right
    max_value = max(float(comparison["mae"].max()), float(comparison["rmse"].max()), 1e-9)
    max_value *= 1.12
    body = []
    for tick in range(6):
        value = max_value * tick / 5
        x = left + plot_w * tick / 5
        body += [_line(x, top, x, height-bottom, "#e2e8f0"),
                 f'<text x="{x:.1f}" y="{height-bottom+24}" text-anchor="middle" font-family="sans-serif" font-size="12">{value:.1f}</text>']
    group_h = (height - top - bottom) / len(comparison)
    for i, row in comparison.reset_index(drop=True).iterrows():
        y = top + i * group_h
        label = html.escape(LABELS.get(row.model, row.model))
        body.append(f'<text x="{left-12}" y="{y+group_h*.55:.1f}" text-anchor="end" font-family="sans-serif" font-size="14">{label}</text>')
        for j, metric_name in enumerate(("mae", "rmse")):
            yy = y + 6 + j * 22
            bar_w = plot_w * float(row[metric_name]) / max_value
            body.append(f'<rect x="{left}" y="{yy:.1f}" width="{bar_w:.1f}" height="16" fill="{COLORS[row.model]}" opacity="{1 if j == 0 else .55}"/>')
            body.append(f'<text x="{left+bar_w+6:.1f}" y="{yy+13:.1f}" font-family="sans-serif" font-size="11">{row[metric_name]:.3f}</text>')
    body.extend([_line(left, top, left, height-bottom, "#334155"), _line(left, height-bottom, width-right, height-bottom, "#334155")])
    body.append(f'<text x="{width-250}" y="58" font-family="sans-serif" font-size="12">Solid bars: MAE · faded bars: RMSE</text>')
    _svg(path, "Test-set model comparison (lower is better)", "".join(body), width, height)


def _series_path(values: np.ndarray, x0: float, y0: float, w: float, h: float, low: float, high: float) -> str:
    if len(values) > 1400:
        values = values[np.linspace(0, len(values)-1, 1400, dtype=int)]
    span = high - low or 1.0
    coords = [f"{x0 + i* w/max(len(values)-1,1):.1f},{y0+h-(v-low)*h/span:.1f}" for i, v in enumerate(values)]
    return " ".join(coords)


def _time_plot(predictions: pd.DataFrame, path: Path, columns: List[str], residual: bool = False) -> None:
    width, height, left, right, top, bottom = 1150, 620, 80, 40, 70, 80
    value_columns = ["actual"] if not residual else []
    value_columns += [f"{key}_residual" if residual else f"{key}_prediction" for key in columns]
    # Aggregate same-time road observations before drawing a time line; this avoids
    # connecting different roads as though they were consecutive observations.
    frame = predictions.groupby("target_time", as_index=False)[value_columns].mean().sort_values("target_time")
    series = {"actual": frame.actual.to_numpy(dtype=float)} if not residual else {}
    for key in columns:
        series[key] = frame[f"{key}_residual" if residual else f"{key}_prediction"].to_numpy(dtype=float)
    vals = np.concatenate(list(series.values()))
    low, high = float(np.nanmin(vals)), float(np.nanmax(vals))
    pad = (high-low)*.06 or 1.0
    low, high = low-pad, high+pad
    plot_w, plot_h = width-left-right, height-top-bottom
    body = []
    for tick in range(5):
        value = low+(high-low)*tick/4
        y = top+plot_h-plot_h*tick/4
        body.extend([_line(left,y,width-right,y,"#e2e8f0"),
                     f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="12">{value:.1f}</text>'])
    for key, values in series.items():
        color = "#111827" if key == "actual" else COLORS[key]
        dash = ' stroke-dasharray="6 4"' if residual else ""
        body.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.8"{dash} points="{_series_path(values,left,top,plot_w,plot_h,low,high)}"/>')
    body.extend([_line(left,top,left,height-bottom,"#334155"),_line(left,height-bottom,width-right,height-bottom,"#334155")])
    items = ([ ("Actual", "#111827") ] if not residual else []) + [(LABELS[k], COLORS[k]) for k in columns]
    body.append(_legend(items, left+8, height-45, 19))
    body.append(f'<text x="{left}" y="{height-14}" font-family="sans-serif" font-size="12">{html.escape(str(frame.target_time.min())[:10])}</text>')
    body.append(f'<text x="{width-right}" y="{height-14}" text-anchor="end" font-family="sans-serif" font-size="12">{html.escape(str(frame.target_time.max())[:10])}</text>')
    title = "Daily mean residual (prediction − actual) across roads" if residual else "Daily mean held-out actual and predicted values across roads"
    _svg(path,title,"".join(body),width,height)


def _histogram_plot(predictions: pd.DataFrame, path: Path, columns: List[str], value_columns: Dict[str, str], title: str, xlabel: str) -> None:
    width,height,left,right,top,bottom=1100,620,75,40,70,80
    values={key: predictions[col].to_numpy(dtype=float) for key,col in value_columns.items()}
    all_values=np.concatenate(list(values.values())); low,high=float(np.nanmin(all_values)),float(np.nanmax(all_values))
    if low == high: low,high=low-.5,high+.5
    bins=32; edges=np.linspace(low,high,bins+1); counts={k:np.histogram(v,bins=edges)[0] for k,v in values.items()}
    ymax=max(int(c.max()) for c in counts.values()) or 1; pw=width-left-right; ph=height-top-bottom; body=[]
    for t in range(5):
        v=ymax*t/4; y=top+ph-ph*t/4
        body.extend([_line(left,y,width-right,y,"#e2e8f0"),f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="12">{v:.0f}</text>'])
    binw=pw/bins
    for key,arr in counts.items():
        opacity=.34 if len(columns)>1 else .72
        for i,n in enumerate(arr):
            if n:
                x=left+i*binw; h=ph*n/ymax
                body.append(f'<rect x="{x:.1f}" y="{top+ph-h:.1f}" width="{max(binw-1,1):.1f}" height="{h:.1f}" fill="{COLORS[key]}" opacity="{opacity}"/>')
    body.extend([_line(left,top,left,height-bottom,"#334155"),_line(left,height-bottom,width-right,height-bottom,"#334155"),
                 f'<text x="{width/2:.0f}" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="14">{html.escape(xlabel)}</text>',
                 _legend([(LABELS[k],COLORS[k]) for k in columns],left+10,top+5)])
    _svg(path,title,"".join(body),width,height)


def _scatter_plot(predictions: pd.DataFrame, path: Path, columns: List[str]) -> None:
    width,height,left,right,top,bottom=800,700,80,40,65,80
    actual=predictions.actual.to_numpy(dtype=float); vals=np.concatenate([actual]+[predictions[f"{k}_prediction"].to_numpy(dtype=float) for k in columns])
    low,high=float(vals.min()),float(vals.max()); pad=(high-low)*.04 or 1; low-=pad;high+=pad
    pw,ph=width-left-right,height-top-bottom; body=[_line(left,top+ph,left+pw,top,"#64748b",2,"8 5")]
    for t in range(6):
        v=low+(high-low)*t/5; x=left+pw*t/5; y=top+ph-ph*t/5
        body.extend([_line(x,top,x,top+ph,"#e2e8f0"),_line(left,y,left+pw,y,"#e2e8f0"),
                     f'<text x="{x:.1f}" y="{top+ph+22}" text-anchor="middle" font-family="sans-serif" font-size="11">{v:.1f}</text>',
                     f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{v:.1f}</text>'])
    for key in columns:
        pred=predictions[f"{key}_prediction"].to_numpy(dtype=float); step=max(1,len(actual)//1200)
        for a,p in zip(actual[::step],pred[::step]):
            x=left+(a-low)*pw/(high-low); y=top+ph-(p-low)*ph/(high-low)
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="{COLORS[key]}" fill-opacity=".48"/>')
    body.extend([_line(left,top,left,top+ph,"#334155"),_line(left,top+ph,left+pw,top+ph,"#334155"),_legend([(LABELS[k],COLORS[k]) for k in columns],left+10,top+12)])
    body.append(f'<text x="{width/2:.0f}" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="14">Actual</text>')
    body.append(f'<text transform="translate(20 {height/2}) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="14">Predicted</text>')
    _svg(path,"Held-out predictions versus actual values","".join(body),width,height)


def _series_errors(predictions: pd.DataFrame, columns: List[str], path: Path) -> pd.DataFrame:
    rows=[]
    for series,group in predictions.groupby("series"):
        for key in columns:
            m=calculate_metrics(group.actual,group[f"{key}_prediction"])
            if m["n"] >= MIN_GROUP_SAMPLES:
                rows.append({"series":str(series),"model":key,**m})
    result=pd.DataFrame(rows,columns=["series","model","mae","rmse","r2","n"])
    result.to_csv(path,index=False)
    return result


def _series_plot(by_series: pd.DataFrame, path: Path) -> None:
    if by_series.empty:
        return
    names=list(by_series.series.drop_duplicates()); keys=list(by_series.model.drop_duplicates())
    width=max(1100,80+len(names)*90);height=700;left,right,top,bottom=80,30,70,220
    maxv=float(by_series.mae.max())*1.12 or 1;pw=width-left-right;ph=height-top-bottom;body=[]
    for t in range(6):
        v=maxv*t/5;y=top+ph-ph*t/5
        body.extend([_line(left,y,width-right,y,"#e2e8f0"),f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{v:.1f}</text>'])
    groupw=pw/len(names); barw=min(14,groupw/(len(keys)+1))
    for i,name in enumerate(names):
        for j,key in enumerate(keys):
            row=by_series[(by_series.series==name)&(by_series.model==key)]
            if row.empty: continue
            v=float(row.iloc[0].mae);x=left+i*groupw+(j+.5)*groupw/(len(keys)+1);h=ph*v/maxv
            body.append(f'<rect x="{x-barw/2:.1f}" y="{top+ph-h:.1f}" width="{barw:.1f}" height="{h:.1f}" fill="{COLORS[key]}"/>')
        x=left+(i+.5)*groupw
        body.append(f'<text transform="translate({x:.1f} {top+ph+12}) rotate(55)" font-family="sans-serif" font-size="10">{html.escape(name)}</text>')
    body.append(_legend([(LABELS[k],COLORS[k]) for k in keys],left+10,36,18))
    body.append(f'<text x="{width/2:.0f}" y="{height-14}" text-anchor="middle" font-family="sans-serif" font-size="13">Series (only groups with n ≥ {MIN_GROUP_SAMPLES})</text>')
    _svg(path,"Test MAE by road series (supported sample sizes only)","".join(body),width,height)


def write_horizon_outputs(output_dir: Path, label: str, comparison: pd.DataFrame,
                          predictions: pd.DataFrame, z_scores: np.ndarray,
                          z_metadata: Dict) -> Dict:
    """Write measured tables, summary and plots for a shared test population."""
    output_dir.mkdir(parents=True,exist_ok=True)
    comparison.to_csv(output_dir/"model_comparison.csv",index=False)
    predictions.to_csv(output_dir/"test_predictions.csv",index=False)
    columns=list(comparison.model)
    value_columns={k:f"{k}_residual" for k in columns}
    _comparison_plot(comparison,output_dir/"model_comparison.svg")
    _time_plot(predictions,output_dir/"actual_and_predicted_over_time.svg",columns)
    _histogram_plot(predictions,output_dir/"residual_distribution.svg",columns,value_columns,"Held-out residual distribution","Residual (prediction − actual)")
    _time_plot(predictions,output_dir/"residuals_over_time.svg",columns,residual=True)
    _scatter_plot(predictions,output_dir/"prediction_vs_actual.svg",columns)
    zframe=pd.DataFrame({"last_value_z_score":z_scores})
    zframe.to_csv(output_dir/"z_score_distribution.csv",index=False)
    _histogram_plot(zframe,output_dir/"z_score_distribution.svg",["ridge"],{"ridge":"last_value_z_score"},
                    f"Z-score distribution: {z_metadata['feature']}","Z-score")
    by_series=_series_errors(predictions,columns,output_dir/"error_by_series.csv")
    if not by_series.empty:
        _series_plot(by_series,output_dir/"error_by_series.svg")
    summary={
        "horizon":label,
        "population": {"n_rows_per_model":int(len(predictions)),"unique_test_timestamps":int(predictions.target_time.nunique()),
                       "start":str(predictions.target_time.min()),"end":str(predictions.target_time.max()),
                       "target_definition":RESEARCH.target},
        "models":{row.model:{"mae":float(row.mae),"rmse":float(row.rmse),"r2":None if pd.isna(row.r2) else float(row.r2),"n":int(row.n),
                              "configuration":row.configuration}
                  for row in comparison.itertuples(index=False)},
        "z_score":z_metadata,
        "error_by_series": {"minimum_group_samples":MIN_GROUP_SAMPLES,"supported_series":int(by_series.series.nunique()) if not by_series.empty else 0,
                            "plot_generated":bool(not by_series.empty)},
    }
    (output_dir/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False),encoding="utf-8")
    return summary


def _evaluate_horizon(grid: pd.DataFrame, label: str, steps: int, output_dir: Path) -> Dict:
    data=supervised(grid,RESEARCH,steps)
    train,val,test,splits=chronological_split(data,RESEARCH)
    if train.empty or val.empty or test.empty:
        raise ValueError(f"Horizon {label} does not have nonempty chronological train, validation, and test splits")
    cols=feature_columns(data)
    table_train=historical_average_table(train,RESEARCH)
    x_train=model_matrix(train,cols,table_train,RESEARCH)
    x_val=model_matrix(val,cols,table_train,RESEARCH)
    model_candidates=candidates(); ridge=next(c for c in model_candidates if c.name=="ridge")
    hgb_candidates=[c for c in model_candidates if c.name.startswith("hgb_")]
    validation=[]
    for candidate in hgb_candidates:
        model=candidate.factory();model.fit(x_train,train.target)
        prediction=model.predict(x_val)
        validation.append((calculate_metrics(val.target,np.clip(prediction,*RESEARCH.clip))["mae"],candidate))
    if not validation:
        raise RuntimeError("No Histogram Gradient Boosting candidates are configured")
    _,selected_hgb=min(validation,key=lambda pair:pair[0])

    trainval=pd.concat([train,val]).sort_values("target_time")
    table_tv=historical_average_table(trainval,RESEARCH)
    x_trainval=model_matrix(trainval,cols,table_tv,RESEARCH)
    x_test=model_matrix(test,cols,table_tv,RESEARCH)
    fitted={}
    for key,candidate in (("ridge",ridge),("histogram_gradient_boosting",selected_hgb)):
        estimator=candidate.factory();estimator.fit(x_trainval,trainval.target)
        fitted[key]=estimator
    frame=pd.DataFrame({"target_time":test.target_time.to_numpy(),"series":test.series.to_numpy(),
                        "actual":test.target.to_numpy(dtype=float)})
    frame["persistence_prediction"]=test.last_value.to_numpy(dtype=float)
    seasonal=test.seasonal_value.fillna(test.last_value).to_numpy(dtype=float)
    frame["seasonal_naive_prediction"]=seasonal
    frame["historical_average_prediction"]=np.clip(predict_historical(test,RESEARCH,table_tv),*RESEARCH.clip)
    configurations={
        "persistence":"latest observed value at the forecast origin",
        "seasonal_naive":f"same weekly slot ({RESEARCH.season}-step season)",
        "historical_average":"series and weekday means, estimated from train + validation",
        "ridge":"Ridge(alpha=1.0)",
        "histogram_gradient_boosting":selected_hgb.name,
    }
    for key,estimator in fitted.items():
        frame[f"{key}_prediction"]=np.clip(estimator.predict(x_test),*RESEARCH.clip)
    columns=["persistence","seasonal_naive","historical_average","ridge","histogram_gradient_boosting"]
    rows=[]
    for key in columns:
        prediction=frame[f"{key}_prediction"]
        frame[f"{key}_residual"]=prediction-frame.actual
        rows.append({"model":key,"configuration":configurations.get(key,""),**calculate_metrics(frame.actual,prediction)})
    comparison=pd.DataFrame(rows)

    ridge_pipe=fitted["ridge"]
    imputed=ridge_pipe.named_steps["simpleimputer"].transform(x_test)
    scaler=ridge_pipe.named_steps["standardscaler"]
    feature_index=cols.index("last_value")
    z_scores=scaler.transform(imputed)[:,feature_index]
    z_metadata={"feature":"last_value (latest observed congestion at forecast origin)",
                "population":"test rows with target_time in the held-out period",
                "scaler_fit_population":"training + validation predictor rows only",
                "scaler":"StandardScaler from the Ridge preprocessing pipeline; median imputation precedes scaling",
                "n":int(len(z_scores)),"mean":float(np.mean(z_scores)),"standard_deviation_population":float(np.std(z_scores))}
    summary=write_horizon_outputs(output_dir,label,comparison,frame,z_scores,z_metadata)
    summary["chronological_splits"]=splits
    summary["selected_gradient_boosting_configuration_on_validation"]=selected_hgb.name
    (output_dir/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False),encoding="utf-8")
    return summary


def run_research_evaluation(dataset_path: Path | None = None, output_dir: Path | None = None) -> Dict:
    settings=get_settings()
    dataset_path=dataset_path or settings.dataset_path
    output_dir=output_dir or Path(__file__).resolve().parent/"statistical"
    data,validation=load_research(dataset_path)
    if data.empty:
        raise ValueError("No valid research observations remain after preprocessing")
    times=pd.date_range(data.time.min(),data.time.max(),freq=RESEARCH.freq)
    expected=int(len(times)*data.series.nunique())
    coverage={"series":int(data.series.nunique()),"observed_rows_after_preprocessing":int(len(data)),
              "expected_series_time_cells":expected,"missing_series_time_cells":max(0,expected-len(data)),
              "coverage_fraction":float(len(data)/expected) if expected else 0.0,
              "dataset_start":str(data.time.min()),"dataset_end":str(data.time.max()),"span_days":float((data.time.max()-data.time.min()).total_seconds()/86400)}
    report={"generated_at":datetime.now(timezone.utc).isoformat(),"dataset":str(dataset_path),"target":RESEARCH.target,
            "task":"chronological baseline and regression comparison","data_validation":validation,
            "preprocessing_exclusion_counts_are_overlapping_issue_counts":True,
            "rows_after_preprocessing":int(len(data)),"coverage":coverage,"horizons":{}}
    if coverage["span_days"]<RESEARCH.min_span_days:
        report["status"]="insufficient_data";report["reason"]=f"Requires at least {RESEARCH.min_span_days} days; observed {coverage['span_days']:.2f}"
    else:
        grid=to_grid(data,RESEARCH)
        for label,steps in RESEARCH.horizons.items():
            report["horizons"][label]=_evaluate_horizon(grid,label,steps,output_dir/label)
        report["status"]="evaluated"
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"summary.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    return report


def main() -> None:
    report=run_research_evaluation()
    print(json.dumps({"status":report["status"],"coverage":report["coverage"],
                      "horizons":{h:{m:vals["mae"] for m,vals in result["models"].items()}
                                  for h,result in report.get("horizons",{}).items()}},indent=2))


if __name__ == "__main__":
    main()
