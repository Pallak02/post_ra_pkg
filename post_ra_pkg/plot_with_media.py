#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, csv, json, math, os
from collections import defaultdict, OrderedDict
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# ---------------- utils ----------------
def ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True)

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def is_number(x) -> bool:
    try:
        float(str(x).strip())
        return True
    except Exception:
        return False

def f2(v) -> str:
    try:
        return f"{float(v):.2f}"
    except Exception:
        return str(v)

def parse_dsid_list(s: Any) -> List[int]:
    if s is None:
        return []
    if isinstance(s, (list, tuple)):
        seq = s
    else:
        ss = str(s).strip()
        if ss.startswith("[") and ss.endswith("]"):
            try:
                seq = json.loads(ss)
            except Exception:
                ss = ss.strip("[]")
                seq = [p.strip() for p in ss.split(",") if p.strip()]
        else:
            seq = [ss]
    out: List[int] = []
    for v in seq:
        try:
            out.append(int(str(v).strip()))
        except Exception:
            pass
    return out

# ----------- vector helpers -----------
def try_parse_vector(s: Any) -> Optional[List[float]]:
    if s is None:
        return None
    if isinstance(s, (list, tuple)):
        vals = []
        for v in s:
            try:
                vals.append(float(v))
            except Exception:
                return None
        return vals if vals else None
    ss = str(s).strip()
    if not (ss.startswith("[") and ss.endswith("]")):
        return None
    try:
        arr = json.loads(ss)
        return [float(v) for v in arr]
    except Exception:
        try:
            ss = ss.strip("[]")
            parts = [p for p in ss.split(",") if p.strip()]
            return [float(p) for p in parts]
        except Exception:
            return None

def vector_to_scalar(vec: List[float], policy: str, index: int) -> Optional[float]:
    if not vec:
        return None
    if policy == "max":
        return max(vec)
    if policy == "take":
        if 0 <= index < len(vec):
            return vec[index]
        return None
    if policy == "argmax":
        return float(max(range(len(vec)), key=lambda i: vec[i]))
    if policy == "mean":
        return sum(vec) / len(vec)
    return None

def vector_argmax(vec: List[float]) -> Optional[int]:
    if not vec:
        return None
    return int(max(range(len(vec)), key=lambda i: vec[i]))

# ------------- time-link helper -------------
def nearest_row_by_time(rows: List[Dict[str, Any]], t: float, tol: float) -> Optional[Dict[str, Any]]:
    best = None
    best_dt = None
    for r in rows:
        ts = r.get("time_since_start")
        if ts is None:
            continue
        try:
            dt = abs(float(ts) - float(t))
        except Exception:
            continue
        if dt <= tol and (best_dt is None or dt < best_dt):
            best = r
            best_dt = dt
    return best

# ------------- Bag A (CSV) -------------
def _normalize_csv_row(row: Dict[str, Any]) -> Dict[str, Any]:
    r = dict(row)
    if "casualty" not in r and "casualty_id" in r:
        r["casualty"] = r["casualty_id"]
    if "time_since_start_s" not in r and "time_since_start" in r:
        r["time_since_start_s"] = r["time_since_start"]
    try:
        r["_casualty"] = int((r.get("casualty", 0) or 0))
    except Exception:
        r["_casualty"] = 0
    try:
        r["_t"] = float(r.get("time_since_start_s", "nan"))
    except Exception:
        r["_t"] = math.nan
    dsids = parse_dsid_list(r.get("data_source_ids"))
    r["_dsids"] = dsids
    r["_last_dsid"] = dsids[-1] if dsids else None
    return r

def load_assessments_csv(csv_path: Path):
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing CSV: {csv_path}")
    rows: List[Dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        if not rd.fieldnames:
            raise ValueError("CSV has no header row.")
        for raw in rd:
            r = _normalize_csv_row(raw)
            if "casualty" not in r or "time_since_start_s" not in r:
                raise ValueError("CSV must include 'casualty'/'casualty_id' and 'time_since_start_s'/'time_since_start'.")
            rows.append(r)

    fields_by_cas: Dict[int, List[str]] = {}
    by_cas: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_cas[r["_casualty"]].append(r)

    def looks_like_value_col(name: str) -> bool:
        n = name.lower()
        if n in ("casualty", "casualty_id", "time_since_start_s", "time_since_start", "topic", "timestamp_ns", "seq"):
            return False
        bad = (
            "stamp.sec", "stamp.nanosec", ".sec", ".nanosec", "header.", "status.", "_stamp", "stamp_",
            "position_covariance_type", "position_covariance", "num_observations",
            "times_submitted", "golden_window_period", "frame_id",
        )
        if any(b in n for b in bad):
            return False
        return True

    for cas, cas_rows in by_cas.items():
        keys = list(rows[0].keys())
        candidates: List[str] = []
        for k in keys:
            if k.startswith("_"): continue
            if not looks_like_value_col(k): continue
            vals: List[float] = []
            for r in cas_rows[:1000]:
                v = r.get(k)
                if is_number(v):
                    try: vals.append(float(v))
                    except Exception: pass
                else:
                    vec = try_parse_vector(v)
                    if vec is not None:
                        vals.append(sum(vec))  # detect variance
            if len(vals) >= 3 and (max(vals) - min(vals)) > 1e-4:
                candidates.append(k)
        preferred = [x for x in candidates if x in ("hr_value", "rr_value")]
        others = [x for x in candidates if x not in preferred]
        fields_by_cas[cas] = (preferred + others)[:50]
    return rows, fields_by_cas

# ------------- Bag B (ODS) -------------
TRANSCRIPT_KEYS = ("audio_transcript", "transcript", "stt_text")
AUDIO_KEYS      = ("audio_url", "media_url", "wav_url", "mp3_url", "raw_audio", "audio_file", "audio_path")
PLATFORM_KEYS   = ("platform_name", "platform", "source_platform")
IMAGE_KEYS_DEFAULT = ("image_url", "image_path", "frame_path")
ODS_DSID_KEYS   = ("data_source_id", "dataSourceId", "dsid", "source_id", "observation_id", "data_source_ids")
ODS_TIME_KEYS   = ("time_since_start", "time_since_start_s", "t", "time")

def _coerce_int(x):
    try: return int(str(x).strip())
    except Exception: return None

def _extract_first_int_from_listlike(v):
    if v is None: return None
    if isinstance(v, (list, tuple)):
        for item in v:
            ii = _coerce_int(item)
            if ii is not None: return ii
        return None
    return _coerce_int(v)

def load_ods_json(ods_path: Path, bagb_offset_s: float, force_ods_casualty: Optional[int]):
    if not ods_path.exists(): raise FileNotFoundError(f"Missing ODS JSON: {ods_path}")
    ods_rows = load_json(ods_path)

    dsid_index: Dict[int, Dict[str, Any]] = {}
    ods_by_cas: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    for r in ods_rows:
        t = None
        for tk in ODS_TIME_KEYS:
            if tk in r:
                try:
                    t = float(r[tk]); break
                except Exception:
                    t = None
        if t is not None and bagb_offset_s:
            t = t + float(bagb_offset_s)
        r["time_since_start"] = t

        if force_ods_casualty is not None:
            cas = int(force_ods_casualty)
        else:
            cas = _coerce_int(r.get("casualty")) or 0
        r["casualty"] = cas
        ods_by_cas[cas].append(r)

        dsid = None
        for dk in ODS_DSID_KEYS:
            if dk in r:
                dsid = _extract_first_int_from_listlike(r[dk])
                if dsid is not None: break
        if dsid is not None:
            dsid_index[dsid] = r

    return ods_rows, ods_by_cas, dsid_index

# ---------- media path resolution ----------
def resolve_media_path(
    candidate: str,
    page_dir: Path,
    image_path_root: Optional[str],
    indir: Path,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (src_for_html, debug_message_if_missing).
    If URL (http/https/file:) we pass through.
    If local file, return a relative path from page_dir if it exists.
    Otherwise try a few roots and report a debug string if none exist.
    """
    if not candidate:
        return None, "empty image path"

    s = str(candidate)

    # URLs / file scheme: pass through
    if s.startswith(("http://", "https://", "file://")):
        return s, None

    # Absolute filesystem path
    if s.startswith("/"):
        p = Path(s)
        if p.exists():
            try:
                return os.path.relpath(p, page_dir), None
            except Exception:
                return s, None  # fallback: absolute
        return None, f"not found: {s}"

    # Relative: try a few roots
    roots: List[Path] = []
    if image_path_root:
        roots.append(Path(image_path_root))
    roots.append(indir)
    roots.append(page_dir)

    for root in roots:
        p = root / s
        if p.exists():
            try:
                return os.path.relpath(p, page_dir), None
            except Exception:
                return str(p), None

    tried = [str(root / s) for root in roots]
    return None, "not found in roots: " + " | ".join(tried)

# ------------- staging helpers -------------
def quantile_edges(sorted_vals: List[float], q: int) -> List[float]:
    if q <= 1 or not sorted_vals: return []
    n = len(sorted_vals); edges = []
    for k in range(1, q):
        pos = k*(n-1)/q
        lo = int(math.floor(pos)); hi = int(math.ceil(pos))
        if lo == hi: v = sorted_vals[lo]
        else:
            a = sorted_vals[lo]; b = sorted_vals[hi]
            v = a + (b-a)*(pos-lo)
        edges.append(float(v))
    return edges

def assign_tertile_label(t: float, edges: List[float]) -> str:
    if not edges: return "all"
    if t <= edges[0]: return "stage 1 (early)"
    if len(edges) == 1: return "stage 2 (late)"
    if t <= edges[1]: return "stage 2 (mid)"
    return "stage 3 (late)"

def assign_quantile_label(idx: int, q: int) -> str:
    return f"stage {idx+1}"

# ------------- HTML builder -------------
def build_field_page(outdir: Path, cas: int, field: str, points: List[Dict[str, Any]],
                     ods_rows_for_cas: List[Dict[str, Any]], dsid_index: Dict[int, Dict[str, Any]],
                     link_tol: float, enable_images: bool, image_field: str,
                     image_path_root: Optional[str], banner: str, link_mode: str,
                     ods_all_rows: List[Dict[str, Any]], stage_mode: str,
                     stage_field: Optional[str], stage_quantiles: int,
                     indir: Path):
    """
    Returns (matched_by_dsid, matched_by_time, tx_count, audio_count, img_count, path)
    Builds one HTML with one or more traces (one per stage), plus media overlays.
    """
    ensure_dir(outdir)

    # group points into stages
    stage_groups: Dict[str, List[Dict[str, Any]]] = OrderedDict()

    if stage_mode == "by_field" and stage_field:
        for p in points:
            label = str(p["row"].get(stage_field, "") or "unknown")
            stage_groups.setdefault(label, []).append(p)
    elif stage_mode in ("tertiles", "quantiles"):
        q = 3 if stage_mode == "tertiles" else max(2, int(stage_quantiles))
        times = sorted([p["t"] for p in points])
        edges = quantile_edges(times, q)
        if stage_mode == "tertiles":
            for p in points:
                lab = assign_tertile_label(p["t"], edges)
                stage_groups.setdefault(lab, []).append(p)
        else:
            for p in points:
                idx = 0
                while idx < len(edges) and p["t"] > edges[idx]:
                    idx += 1
                lab = assign_quantile_label(idx, q)
                stage_groups.setdefault(lab, []).append(p)
    elif stage_mode == "vector":
        for p in points:
            lab = p.get("_stage_label", "unknown")
            stage_groups.setdefault(lab, []).append(p)
    else:
        stage_groups["all"] = points

    # Build traces + collect media overlay coords (+ customdata!)
    traces = []
    total_dsid = total_time = total_tx = total_audio = total_img = 0
    tx_x, tx_y, tx_cd = [], [], []
    au_x, au_y, au_cd = [], [], []
    im_x, im_y, im_cd = [], [], []

    for stage_label, pts in stage_groups.items():
        xs: List[float] = []; ys: List[float] = []; custom: List[List[Any]] = []
        c_dsid = c_time = c_tx = c_audio = c_img = 0

        for p in pts:
            t, y, last_dsid = p["t"], p["y"], p.get("last_dsid")
            ods = None

            if link_mode == "auto":
                if isinstance(last_dsid, int) and last_dsid in dsid_index:
                    ods = dsid_index[last_dsid]; c_dsid += 1
                if ods is None:
                    ods = nearest_row_by_time(ods_rows_for_cas, t, link_tol)
                    if ods is not None: c_time += 1
            else:
                ods = nearest_row_by_time(ods_all_rows, t, link_tol)
                if ods is not None: c_time += 1

            transcript = ""; audio_url = ""; image_url = ""; platform = ""; img_dbg = None
            dsid_text = str(last_dsid) if last_dsid is not None else ""
            if ods:
                for k in PLATFORM_KEYS:
                    if ods.get(k): platform = str(ods[k]); break
                if not dsid_text:
                    ds = ods.get("data_source_id")
                    if ds is not None: dsid_text = str(ds)
                # transcript
                for k in TRANSCRIPT_KEYS:
                    if ods.get(k): transcript = str(ods[k]); break
                # audio
                for k in AUDIO_KEYS:
                    if ods.get(k):
                        au = str(ods[k])
                        if image_path_root and not au.startswith(("http://","https://","file:/","/")):
                            abs_path = Path(image_path_root) / au
                            audio_url = os.path.relpath(abs_path, outdir)
                        else:
                            if au.startswith("/") and image_path_root:
                                try: audio_url = os.path.relpath(au, outdir)
                                except Exception: audio_url = au
                            else:
                                audio_url = au
                        break
                # image
                if enable_images:
                    candidates = [image_field] + [k for k in IMAGE_KEYS_DEFAULT if k != image_field]
                    for k in candidates:
                        if ods.get(k):
                            iu = str(ods[k])
                            image_url, img_dbg = resolve_media_path(iu, outdir, image_path_root, indir)
                            if image_url: break

            cd = [t, y, dsid_text, transcript, audio_url, image_url or "", platform, img_dbg or ""]
            xs.append(t); ys.append(y); custom.append(cd)

            if transcript:
                c_tx += 1; tx_x.append(t); tx_y.append(y); tx_cd.append(cd)
            if audio_url:
                c_audio += 1; au_x.append(t); au_y.append(y); au_cd.append(cd)
            if image_url:
                c_img += 1; im_x.append(t); im_y.append(y); im_cd.append(cd)

        total_dsid += c_dsid; total_time += c_time
        total_tx += c_tx; total_audio += c_audio; total_img += c_img

        traces.append({
            "x": xs, "y": ys, "type": "scatter", "mode": "markers",
            "name": stage_label, "marker": {"size": 8}, "customdata": custom,
            "hovertemplate": "<b>%{customdata[0]:.2f}s</b>  value: %{customdata[1]}<extra></extra>",
        })

    # Media overlay traces (with customdata so clicks work)
    overlay_traces = []
    if tx_x:
        overlay_traces.append({
            "x": tx_x, "y": tx_y, "type": "scatter", "mode": "markers",
            "name": "has transcript",
            "marker": {"size": 11, "symbol": "square-open", "line": {"width": 1.5}},
            "hoverinfo": "skip", "showlegend": True, "customdata": tx_cd,
        })
    if au_x:
        overlay_traces.append({
            "x": au_x, "y": au_y, "type": "scatter", "mode": "markers",
            "name": "has audio",
            "marker": {"size": 11, "symbol": "diamond-open", "line": {"width": 1.5}},
            "hoverinfo": "skip", "showlegend": True, "customdata": au_cd,
        })
    if im_x:
        overlay_traces.append({
            "x": im_x, "y": im_y, "type": "scatter", "mode": "markers",
            "name": "has image",
            "marker": {"size": 11, "symbol": "x"},
            "hoverinfo": "skip", "showlegend": True, "customdata": im_cd,
        })

    import json as pyjson
    traces_js = pyjson.dumps(traces + overlay_traces)
    layout_js = pyjson.dumps({
        "hovermode":"closest",
        "xaxis":{"title":"Time Since Start (s)"},
        "yaxis":{"title":field},
        "legend":{"title":{"text":"stage / media"}},
        "margin":{"l":50,"r":20,"t":60,"b":50},
    })

    title = f"{field.replace('_',' ').title()} — Casualty {cas}"
    img_if = """
      if (imageUrl) {
        html += '<img src="' + esc(imageUrl) + '" alt="image" />';
      } else if (imgDbg) {
        html += '<div class="meta" style="margin-top:6px;color:#b55">[image not found] ' + esc(imgDbg) + '</div>';
      }
    """

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/><title>{title}</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
 body {{ font-family: system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
 #wrap {{ max-width: 1080px; margin: 12px auto; padding: 8px 12px; }}
 #chart {{ width:100%; height:620px; }}
 #details {{ margin-top:12px; padding:10px 12px; border-top:1px solid #e0e0e0; background:#fafafa; }}
 #details .label {{ color:#444; font-weight:600; }}
 #details .meta {{ color:#666; }}
 #details img {{ max-width: 440px; border-radius:6px; display:block; margin-top:8px; }}
 #banner {{ font-size: 13px; color:#555; margin-bottom:8px; }}
</style>
</head>
<body>
<div id="wrap">
  <h2>{title}</h2>
  <div id="banner">{banner}</div>
  <div id="chart"></div>
  <div id="details"><div class="meta"><b>Click a point</b> to see transcript, audio{' and image' if enable_images else ''}.</div></div>
</div>
<script>
(function(){{
  const chart=document.getElementById('chart');
  const details=document.getElementById('details');
  const data={traces_js};
  const layout={layout_js};
  function esc(s){{return (s||'').toString().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
  Plotly.newPlot(chart, data, layout, {{displaylogo:false}});

  chart.on('plotly_click', function(evt){{
    if(!evt||!evt.points||!evt.points.length) return;
    const cd=evt.points[0].customdata||[];
    const t=cd[0]||0, val=cd[1], dsid=cd[2]||'', transcript=cd[3]||'',
          audioUrl=cd[4]||'', imageUrl=cd[5]||'', platform=cd[6]||'', imgDbg=cd[7]||'';
    let html='';
    html+='<div class="meta"><b>{field}</b>'+(platform?' — <span class="meta">'+esc(platform)+'</span>':'')+'</div>';
    html+='<div class="meta">time: '+Number(t).toFixed(2)+' s   value: '+esc(val)+(dsid?'   data_source_id: '+esc(dsid):'')+'</div>';
    html+='<div style="margin-top:8px"><span class="label">transcript:</span> '+(transcript?esc(transcript):'<i>none</i>')+'</div>';
    if(audioUrl){{ html+='<audio style="margin-top:6px" controls src="'+esc(audioUrl)+'"></audio>'; }}
    {img_if}
    details.innerHTML=html;
  }});
}})();
</script>
</body></html>"""
    out = outdir / f"{field}.html"
    out.write_text(html, encoding="utf-8")
    return total_dsid, total_time, total_tx, total_audio, total_img, out

def build_index(outdir: Path, generated: Dict[int, List[str]]):
    lines = [
        "<!doctype html><meta charset='utf-8'><title>Assessments × ODS Plots</title>",
        "<h1>Assessments × ODS Plots</h1>",
        "<p>Click a field under each casualty to open the plot.</p>",
    ]
    for cas in sorted(generated.keys()):
        lines.append(f"<h2>Casualty {cas}</h2><ul>")
        for f in sorted(generated[cas]):
            lines.append(f"<li><a href='./cas_{cas}/{f}.html'>{f}</a></li>")
        lines.append("</ul>")
    (outdir / "index.html").write_text("\n".join(lines), encoding="utf-8")

# ---------------- driver ----------------
def main():
    ap = argparse.ArgumentParser(
        description="Plot Bag A assessments and link Bag B ODS media/transcripts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--indir", required=True, help="Folder with Bag B JSONs (must contain observation_data_sources.json)")
    ap.add_argument("--assess_csv", required=True, help="Bag A CSV; accepts (casualty|casualty_id) and (time_since_start_s|time_since_start)")
    ap.add_argument("--outdir", required=True, help="Output folder for HTML plots")
    ap.add_argument("--fields", nargs="*", default=[], help="Specific fields to plot (default: auto-select per casualty)")
    ap.add_argument("--link_mode", choices=["auto","time_all"], default="auto", help="Linking strategy")
    ap.add_argument("--link_tol", type=float, default=3.0, help="Seconds tolerance for time linking")
    ap.add_argument("--bagb_offset_s", type=float, default=0.0, help="Shift ODS time_since_start by this many seconds")
    ap.add_argument("--force_ods_casualty", type=int, default=None, help="Treat all ODS rows as this casualty id")
    ap.add_argument("--enable_images", action="store_true", help="Render image in details panel if available")
    ap.add_argument("--image_field", default="image_url", help="ODS image field name (fallbacks tried automatically)")
    ap.add_argument("--image_path_root", default="", help="If ODS has relative media paths, prefix with this root; we store relpath from outdir")

    # vector handling
    ap.add_argument("--vector_policy", choices=["max","take","argmax","mean"], default="max",
                    help="How to turn vector-like CSV values (e.g., '[0.7,0.3]') into a scalar")
    ap.add_argument("--vector_index", type=int, default=1, help="Index to use when --vector_policy=take")

    # STAGES
    ap.add_argument("--stage_mode", choices=["none","tertiles","quantiles","by_field","vector"], default="none",
                    help="How to color points by stage")
    ap.add_argument("--stage_quantiles", type=int, default=3, help="Number of quantiles when --stage_mode=quantiles")
    ap.add_argument("--stage_field", default="", help="CSV column to use when --stage_mode=by_field")

    # labels for vector-class stages (repeatable: FIELD=l0,l1,...)
    ap.add_argument("--stage_labels", action="append", default=[],
                    help="Map field to class labels for --stage_mode=vector, e.g. severe_hemorrhage=mild,normal,severe")

    args = ap.parse_args()

    # parse stage_labels into dict[str, list[str]]
    label_map: Dict[str, List[str]] = {}
    for entry in args.stage_labels:
        if "=" in entry:
            field, labcsv = entry.split("=", 1)
            labels = [s.strip() for s in labcsv.split(",")]
            if field.strip():
                label_map[field.strip()] = labels

    indir = Path(args.indir); outdir = Path(args.outdir); ensure_dir(outdir)
    ods_path = indir / "observation_data_sources.json"
    if not ods_path.exists(): raise FileNotFoundError(f"Missing file: {ods_path}")

    assess_rows, auto_fields_by_cas = load_assessments_csv(Path(args.assess_csv))
    ods_rows, ods_by_cas, dsid_index = load_ods_json(ods_path, args.bagb_offset_s, args.force_ods_casualty)

    # choose fields per casualty
    if args.fields:
        requested = set(args.fields)
        csv_keys = set(assess_rows[0].keys())
        cas_to_fields: Dict[int, List[str]] = {}
        for cas, auto in auto_fields_by_cas.items():
            sel = [f for f in requested if f in csv_keys]
            cas_to_fields[cas] = sel if sel else auto
    else:
        cas_to_fields = auto_fields_by_cas

    casualties = sorted(k for k in cas_to_fields.keys() if cas_to_fields[k])
    diag = {cas: len(ods_by_cas.get(cas, [])) for cas in casualties}
    print(f"[diag] Link mode: {args.link_mode}  |  stage_mode: {args.stage_mode}{'('+args.stage_field+')' if args.stage_mode=='by_field' else ''}")
    print(f"[diag] Total ODS rows: {len(ods_rows)} | DSID index size: {len(dsid_index)}")
    print(f"[diag] ODS rows per casualty: {diag}")

    total_by_dsid = total_by_time = total_tx = total_audio = total_img = 0
    ods_all_rows = ods_rows
    generated: Dict[int, List[str]] = defaultdict(list)

    for cas in casualties:
        fields = cas_to_fields.get(cas, [])
        if not fields: continue
        cas_dir = outdir / f"cas_{cas}"; ensure_dir(cas_dir)
        cas_rows = [r for r in assess_rows if r["_casualty"] == cas and is_number(r.get("time_since_start_s", r.get("_t")))]
        ods_rows_for_cas = ods_by_cas.get(cas, [])

        for field in fields:
            pts: List[Dict[str, Any]] = []
            for r in cas_rows:
                raw = r.get(field); t = r.get("_t")
                y = None; stage_label_for_point = None

                if is_number(raw):
                    y = float(raw)
                else:
                    vec = try_parse_vector(raw)
                    if vec is not None:
                        y = vector_to_scalar(vec, args.vector_policy, args.vector_index)
                        if args.stage_mode == "vector":
                            idx = vector_argmax(vec)
                            if idx is not None:
                                labels = label_map.get(field)
                                stage_label_for_point = (labels[idx] if labels and 0 <= idx < len(labels) else f"{field}_{idx}")

                if y is not None and is_number(t):
                    d = {"t": float(t), "y": float(y), "row": r, "last_dsid": r.get("_last_dsid")}
                    if args.stage_mode == "vector" and stage_label_for_point is not None:
                        d["_stage_label"] = stage_label_for_point
                    pts.append(d)

            if not pts:
                print(f"[warn] No numeric points for field '{field}' casualty {cas}; skipping.")
                continue

            banner = (f"link_mode = {args.link_mode} &nbsp; | &nbsp; "
                      f"link_tol = {args.link_tol}s &nbsp; | &nbsp; "
                      f"bagb_offset_s = {f2(args.bagb_offset_s)} &nbsp; | &nbsp; "
                      f"ODS rows for cas {cas}: {len(ods_rows_for_cas)} / total {len(ods_all_rows)} "
                      f"&nbsp; | &nbsp; vector_policy={args.vector_policy}"
                      f"{'('+str(args.vector_index)+')' if args.vector_policy=='take' else ''}")

            by_dsid, by_time, tx, au, im, page = build_field_page(
                outdir=cas_dir, cas=cas, field=field, points=pts,
                ods_rows_for_cas=ods_rows_for_cas, dsid_index=dsid_index,
                link_tol=args.link_tol, enable_images=args.enable_images,
                image_field=args.image_field, image_path_root=(args.image_path_root or None),
                banner=banner, link_mode=args.link_mode, ods_all_rows=ods_all_rows,
                stage_mode=args.stage_mode, stage_field=(args.stage_field or None),
                stage_quantiles=args.stage_quantiles, indir=indir
            )
            total_by_dsid += by_dsid; total_by_time += by_time
            total_tx += tx; total_audio += au; total_img += im
            generated[cas].append(field)
            print(f"[ok] Wrote {page.as_posix()}  |  matched: dsid={by_dsid}, time={by_time} (tx={tx}, audio={au}, img={im})")

    build_index(outdir, generated)
    print(f"[media] linked by dsid: {total_by_dsid}, by time: {total_by_time}")
    print(f"[media] transcripts: {total_tx}, audio: {total_audio}" + (f", images: {total_img}" if args.enable_images else ""))
    print(f"[out] {(outdir / 'index.html').as_posix()}")

if __name__ == "__main__":
    main()

