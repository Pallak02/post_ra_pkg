import os
import json
import pandas as pd
import plotly.express as px

# Constants
RUN_START = 1753804554  # epoch time of /run/start message
ASSESSMENTS_FILE = "assessments_with_time.csv"
OBSERVATIONS_FILE = "observations.json"
DATA_SOURCES_FILE = "observation_data_sources.json"
OUTPUT_DIR = "smart_field_plots_time"

# Injury fields to process
LIST_FIELDS = [
    "severe_hemorrhage", "trauma_head", "trauma_upper_ext",
    "trauma_lower_ext", "respiratory_distress"
]

# Load CSV
df = pd.read_csv(ASSESSMENTS_FILE)
df["time_since_start"] = df["timestamp_sec"] - RUN_START

# Load observations
with open(OBSERVATIONS_FILE, 'r') as f:
    observations = json.load(f)
obs_dict = {obs["data_source_id"]: obs for obs in observations}

# Load data sources
with open(DATA_SOURCES_FILE, 'r') as f:
    data_sources = json.load(f)
ds_dict = {ds["data_source_id"]: ds for ds in data_sources}

# Plot each field
for field in LIST_FIELDS:
    print(f"Plotting field: {field}")
    os.makedirs(f"{OUTPUT_DIR}/{field}", exist_ok=True)

    for casualty_id in sorted(df["casualty_id"].unique()):
        df_cas = df[df["casualty_id"] == casualty_id]

        plot_rows = []

        for _, row in df_cas.iterrows():
            try:
                source_ids = eval(row["data_source_ids"])
                last_id = source_ids[-1]
                values = eval(row[field])
                time_sec = row["time_since_start"]

                obs = obs_dict.get(last_id, {})
                ds = ds_dict.get(last_id, {})

                hover_text = (
                    f"From observations<br>"
                    f"Platform: {obs.get('platform_name', '')}<br>"
                    f"Module: {obs.get('observation_module', '')}<br>"
                    f"Observation: {obs.get('observation', '')}<br><br>"
                    f"From observation_data_sources<br>"
                    f"Platform: {ds.get('platform_name', '')}<br>"
                    f"Transcript: {ds.get('transcript', '')}"
                )

                for i, v in enumerate(values):
                    plot_rows.append({
                        "casualty_id": casualty_id,
                        "time": time_sec,
                        "value": v,
                        "stage": f"stage_{i}",
                        "hover": hover_text
                    })

            except Exception as e:
                print(f"Skipping row due to error: {e}")

        if not plot_rows:
            continue

        plot_df = pd.DataFrame(plot_rows)
        fig = px.scatter(
            plot_df,
            x="time",
            y="value",
            color="stage",
            hover_data={"hover": True, "time": False, "value": False, "stage": False},
            title=f"{field.replace('_', ' ').title()} - Casualty {casualty_id}"
        )
        fig.update_layout(
            xaxis_title="Time Since Start (s)",
            yaxis_title="Posterior Values",
            xaxis=dict(dtick=300),  # Set ticks every 300 seconds
            legend_title="Stage"
        )

        output_path = f"{OUTPUT_DIR}/{field}/casualty_{casualty_id}.html"
        fig.write_html(output_path)

print("All plots generated.")

