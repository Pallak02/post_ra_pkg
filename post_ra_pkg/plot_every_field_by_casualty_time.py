import os
import json
import pandas as pd
import plotly.express as px
import argparse
import ast

# CLI Arguments
parser = argparse.ArgumentParser()
parser.add_argument("--csv_dir", type=str, default="../outputs/csv")
parser.add_argument("--json_dir", type=str, default="../outputs/json")
parser.add_argument("--output_dir", type=str, default="../outputs/plots")
args = parser.parse_args()

# Constants
RUN_START = 1753804554  # Hardcoded for now

# File paths
ASSESSMENTS_FILE = os.path.join(args.csv_dir, "assessments_with_time.csv")
OBSERVATIONS_FILE = os.path.join(args.json_dir, "observations.json")
DATA_SOURCES_FILE = os.path.join(args.json_dir, "observation_data_sources.json")
OUTPUT_DIR = args.output_dir

print("  Script started")
print("  Using paths:")
print("  CSV:", ASSESSMENTS_FILE)
print("  JSON (obs):", OBSERVATIONS_FILE)
print("  JSON (data sources):", DATA_SOURCES_FILE)
print("  Output plots dir:", OUTPUT_DIR)

# Load assessments CSV
df = pd.read_csv(ASSESSMENTS_FILE)
df["time_since_start"] = df["timestamp_sec"] - RUN_START

# Load observations JSON
with open(OBSERVATIONS_FILE, 'r') as f:
    observations = json.load(f)
obs_dict = {obs["data_source_id"]: obs for obs in observations}

# Load data sources JSON
with open(DATA_SOURCES_FILE, 'r') as f:
    data_sources = json.load(f)
ds_dict = {ds["data_source_id"]: ds for ds in data_sources}

# Injury/metric fields to plot
LIST_FIELDS = [
    "severe_hemorrhage",
    "trauma_head",
    "trauma_upper_ext",
    "trauma_lower_ext",
    "respiratory_distress",
    "hr_value",
    "rr_value",
    "alertness_verbal",
    "alertness_motor",
    "alertness_eye"
]

# Expected posterior vector lengths for each field
EXPECTED_LENGTHS = {
    "severe_hemorrhage": 2,
    "trauma_head": 2,
    "trauma_upper_ext": 3,
    "trauma_lower_ext": 3,
    "respiratory_distress": 2,
    "alertness_eye": 4,
    "alertness_verbal": 5,
    "alertness_motor": 6,
    "hr_value": 1,
    "rr_value": 1
}

for field in LIST_FIELDS:
    print(f"\nProcessing field: {field}")
    skipped = 0

    for casualty_id in sorted(df["casualty_id"].unique()):
        df_cas = df[df["casualty_id"] == casualty_id]
        plot_rows = []

        for _, row in df_cas.iterrows():
            try:
                if field not in row or pd.isna(row[field]):
                    skipped += 1
                    continue

                source_ids = eval(row["data_source_ids"])
                last_id = source_ids[-1]

                raw_value = row[field]
                if isinstance(raw_value, str):
                    values = ast.literal_eval(raw_value)
                else:
                    values = raw_value

                if not isinstance(values, list):
                    values = [values]

                expected_len = EXPECTED_LENGTHS.get(field)
                if expected_len is not None and len(values) != expected_len:
                    print(f" Warning: Skipping row with unexpected length for {field}. Got {len(values)}, expected {expected_len}")
                    skipped += 1
                    continue

                time_sec = row["time_since_start"]
                obs = obs_dict.get(last_id, {})
                ds = ds_dict.get(last_id, {})

                for i, v in enumerate(values):
                    hover_text = f"""
From observations<br>
Platform: {obs.get('platform_name', '')}<br>
Module: {obs.get('observation_module', '')}<br>
Observation: {obs.get('observation', '')}<br><br>
From observation_data_sources<br>
 Platform: {ds.get('platform_name', '')}<br>
 Transcript: {ds.get('transcript', '')}
 """.strip()

                    plot_rows.append({
                        "casualty_id": casualty_id,
                        "time": time_sec,
                        "value": v,
                        "stage": f"{field}_{i}",
                        "hover": hover_text
                    })

            except Exception as e:
                skipped += 1

        if not plot_rows:
            print(f" No data to plot for {field}")
            continue

        plot_df = pd.DataFrame(plot_rows)
        fig = px.scatter(
            plot_df, x="time", y="value", color="stage",
            hover_name="hover",
            title=f"{field.replace('_', ' ').title()} - Casualty {casualty_id}"
        )
        if field == "hr_value":
            y_label = "Heart Rate (bpm)"
        elif field == "rr_value":
            y_label = "Respiratory Values"
        else:
            y_label = "Posterior Values"    
                
        fig.update_layout(
            xaxis_title="Time Since Start (sec)",
            yaxis_title=y_label,
            xaxis=dict(tickmode='linear', tick0=0, dtick=300)
        )

        out_path = os.path.join(OUTPUT_DIR, field)
        os.makedirs(out_path, exist_ok=True)
        fig.write_html(f"{out_path}/casualty_{casualty_id}.html")

    print(f" {field} done. Skipped {skipped} rows.")

