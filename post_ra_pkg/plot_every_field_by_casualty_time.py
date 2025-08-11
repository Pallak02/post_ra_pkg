import os
import json
import pandas as pd
import plotly.express as px
import argparse
import ast
from collections import defaultdict

# -----------------------------
# CLI Arguments
# -----------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--csv_dir", type=str, default="../outputs/csv")
parser.add_argument("--json_dir", type=str, default="../outputs/json")
parser.add_argument("--output_dir", type=str, default="../outputs/plots")
args = parser.parse_args()

# -----------------------------
# Constants / Config
# -----------------------------
RUN_START = 1753804554  # Hardcoded for now
MAX_ARRAY_ELEMS = 4     # how many numbers to show from long arrays in hover
MAX_TRANSCRIPT_CHARS = 160  # truncate long transcripts in hover
ROUND = 4               # decimal places for numbers in hover

# -----------------------------
# File paths
# -----------------------------
ASSESSMENTS_FILE = os.path.join(args.csv_dir, "assessments_with_time.csv")
OBSERVATIONS_FILE = os.path.join(args.json_dir, "observations.json")
DATA_SOURCES_FILE = os.path.join(args.json_dir, "observation_data_sources.json")
OUTPUT_DIR = args.output_dir

print("  Script started")
print("  Using paths:")
print("   CSV:", ASSESSMENTS_FILE)
print("   JSON (obs):", OBSERVATIONS_FILE)
print("   JSON (data sources):", DATA_SOURCES_FILE)
print("   Output plots dir:", OUTPUT_DIR)

# -----------------------------
# Load assessments CSV
# -----------------------------
df = pd.read_csv(ASSESSMENTS_FILE)

# Ensure relative time column
if "time_since_start" not in df.columns:
    if "timestamp_sec" not in df.columns:
        raise ValueError("CSV must contain either 'time_since_start' or 'timestamp_sec'.")
    df["time_since_start"] = df["timestamp_sec"] - RUN_START

# -----------------------------
# Load & index observations by data_source_id (many-to-one)
# -----------------------------
with open(OBSERVATIONS_FILE, "r") as f:
    observations = json.load(f)

obs_by_id = defaultdict(list)
for obs in observations:
    dsid = obs.get("data_source_id")
    if dsid is not None:
        obs_by_id[dsid].append(obs)

# -----------------------------
# Load data_sources (one-to-one expected)
# -----------------------------
with open(DATA_SOURCES_FILE, "r") as f:
    data_sources = json.load(f)

ds_dict = {}
for ds in data_sources:
    dsid = ds.get("data_source_id")
    if dsid is not None:
        ds_dict[dsid] = ds

# -----------------------------
# Fields to plot
# -----------------------------
LIST_FIELDS = [
    "severe_hemorrhage",
    "respiratory_distress",
    "hr_value",
    "rr_value",
    "trauma_head",
    "trauma_torso",
    "trauma_upper_ext",
    "trauma_lower_ext",
    "alertness_ocular",
    "alertness_verbal",
    "alertness_motor",
]

# -----------------------------
# Helpers
# -----------------------------
def safe_to_list(value):
    """Turn a scalar or stringified list into a real list."""
    if pd.isna(value):
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except Exception:
            # fallback: single token numbers or strings
            try:
                return [float(value)]
            except Exception:
                return [value]
    return None

def safe_ids(value):
    """Parse the data_source_ids column into a list of ints."""
    if pd.isna(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except Exception:
            # Try comma-separated string
            try:
                return [int(x.strip()) for x in value.split(",") if x.strip()]
            except Exception:
                return []
    try:
        return list(value)
    except Exception:
        return []

def _truncate_list(lst, max_elems=MAX_ARRAY_ELEMS):
    if not isinstance(lst, (list, tuple)):
        return lst
    if len(lst) <= max_elems:
        return [round(x, ROUND) if isinstance(x, (int, float)) else x for x in lst]
    head = [round(x, ROUND) if isinstance(x, (int, float)) else x for x in lst[:max_elems]]
    return head + ["…"]

def _truncate_text(txt, max_chars=MAX_TRANSCRIPT_CHARS):
    if not isinstance(txt, str):
        return txt
    txt = txt.strip()
    if len(txt) <= max_chars:
        return txt
    return txt[:max_chars - 1] + "…"

def _fmt_val(v):
    if isinstance(v, (int, float)):
        return str(round(v, ROUND))
    if isinstance(v, (list, tuple)):
        return str(_truncate_list(list(v)))
    return str(v)

def build_hover_for_active_ids(active_ids):
    """
    Build a clean, multi-line HTML hover text for Plotly.
    
    """
    if not active_ids:
        return "(no active IDs)"

    lines = []
    for dsid in active_ids:
        # Header for each Data Source ID
        lines.append(f"<b>=== Data Source ID {dsid} ===</b>")

        # --- OBSERVATIONS ---
        obs_list = obs_by_id.get(dsid, [])
        if obs_list:
            lines.append("<u>Observations:</u>")
            for ob in obs_list:
                platform = ob.get("platform_name", "")
                module = ob.get("observation_module", "")
                observation = _fmt_val(ob.get("observation", ""))
                lines.append(f"&nbsp;&nbsp;• {platform} | {module}: {observation}")
        else:
            lines.append("<u>Observations:</u> None found")

        # --- OBSERVATION DATA SOURCE META ---
        ds_meta = ds_dict.get(dsid, {})
        ds_platform = ds_meta.get("platform_name", "")
        ds_transcript = _truncate_text(ds_meta.get("transcript", "") or "")
        lines.append("<u>Data Source Meta:</u>")
        if ds_platform or ds_transcript:
            if ds_platform:
                lines.append(f"&nbsp;&nbsp;Platform: {ds_platform}")
            if ds_transcript:
                lines.append(f"&nbsp;&nbsp;Transcript: \"{ds_transcript}\"")
        else:
            lines.append("&nbsp;&nbsp;No meta available")

        # Blank line between IDs
        lines.append("")

    # Use <br> for Plotly line breaks
    return "<br>".join(lines)

# Plotting

os.makedirs(OUTPUT_DIR, exist_ok=True)

for field in LIST_FIELDS:
    print(f"\nProcessing field: {field}")
    skipped = 0

    for casualty_id in sorted(df["casualty_id"].unique()):
        df_cas = df[df["casualty_id"] == casualty_id].copy()

        # Sort assessments deterministically in time
        sort_cols = []
        if "timestamp_sec" in df_cas.columns:
            sort_cols.append("timestamp_sec")
        if "time_since_start" in df_cas.columns:
            sort_cols.append("time_since_start")
        sort_cols = sort_cols or df_cas.columns.tolist()
        df_cas = df_cas.sort_values(by=sort_cols)

        plot_rows = []

        # MEMORY for this casualty (length-based delta of data_source_ids)
        prev_len = 0
        active_ids_memory = []  # "new" IDs to show until length changes again

        for _, row in df_cas.iterrows():
            try:
                # Skip if the field is missing or NaN
                if field not in row or pd.isna(row[field]):
                    skipped += 1
                    continue

                # Parse data_source_ids for this assessment
                row_ids = safe_ids(row.get("data_source_ids"))
                cur_len = len(row_ids)

                # Update memory based on length change
                if cur_len > prev_len:
                    new_count = cur_len - prev_len
                    active_ids_memory = row_ids[-new_count:]  # last N are new
                elif cur_len == prev_len:
                    pass  # keep previous memory
                else:
                    # length shrank (reset) -> show whatever is present now
                    active_ids_memory = row_ids

                prev_len = cur_len

                values = safe_to_list(row[field])
                if not values:
                    skipped += 1
                    continue

                time_sec = row["time_since_start"]

                # Build a single hover block for this assessment (clean HTML)
                hover_text = build_hover_for_active_ids(active_ids_memory)

                # One point per component (so posteriors show as multiple points)
                for i, v in enumerate(values):
                    plot_rows.append(
                        {
                            "casualty_id": casualty_id,
                            "time": time_sec,
                            "value": v,
                            "stage": f"{field}_{i}",
                            "hover": hover_text,
                        }
                    )
            except Exception:
                skipped += 1

        if not plot_rows:
            print(f"  No data to plot for {field} (casualty {casualty_id})")
            continue

        plot_df = pd.DataFrame(plot_rows)

        # Use custom_data to control the hovertemplate cleanly
        fig = px.scatter(
            plot_df,
            x="time",
            y="value",
            color="stage",
            title=f"{field.replace('_', ' ').title()} - Casualty {casualty_id}",
            custom_data=["hover", "stage", "time", "value"],
        )

        # Build a readable hover template:
        #   - stage (bold)
        #   - time, value (inline)
        #   - the multi-line HTML hover text we constructed
        fig.update_traces(
            hovertemplate=(
                "<b>%{customdata[1]}</b>"
                "<br>time=%{x}s"
                "<br>value=%{y}"
                "<br>%{customdata[0]}"
                "<extra></extra>"
            )
        )

        # Axis labels
        if field == "hr_value":
            y_label = "Heart Rate (bpm)"
        elif field == "rr_value":
            y_label = "Respiratory Values"
        else:
            y_label = "Posterior Values"

        fig.update_layout(
            xaxis_title="Time Since Start (sec)",
            yaxis_title=y_label,
            xaxis=dict(tickmode="linear", tick0=0, dtick=300),
            legend_title_text="Component",
            margin=dict(l=60, r=20, t=60, b=60),
        )

        out_path = os.path.join(OUTPUT_DIR, field)
        os.makedirs(out_path, exist_ok=True)
        out_file = os.path.join(out_path, f"casualty_{casualty_id}.html")
        fig.write_html(out_file)
        print(f"  Wrote: {out_file}")

    print(f" {field} done. Skipped {skipped} rows.")

