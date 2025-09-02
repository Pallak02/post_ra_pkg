# post_ra_pkg

ROS 2 package for **Post-Run Analysis** of casualty assessments from a ROS bag file, including injury classification plots, observation inspection, and data source tracking.

## 📁 Package Structure

post_ra_ws/
├── src/
│ └── post_ra_pkg/
│ ├── extract_assessments.py
│ ├── extract_observations.py
│ ├── extract_observation_data_sources.py
│ ├── extract_casualty_images.py
│ ├── stitch_images_into_ods.py
│ ├── unified_extract.py
│ ├── plot_with_media.py
│ └── outputs/ # ignored in Git (generated artifacts)
│
└── outputs/
├── csv/ # extracted assessment CSVs
├── json/ # extracted observation JSONs
├── casualty_images/ # images from observation sources
├── plots/ # basic plots
└── plots_fields_media/ # interactive HTML plots with media

---
1. **Extraction**
   - `extract_assessments.py`: Converts assessment ROS bag messages to CSV.
   - `extract_observations.py`: Extracts raw observation messages to JSON.
   - `extract_observation_data_sources.py`: Builds `observation_data_sources.json` containing transcripts, audio, and image metadata.
   - `extract_casualty_images.py`: Extracts casualty images for linking.

2. **Linking**
   - `stitch_images_into_ods.py`: Ensures images are linked into the ODS JSON.
   - `unified_extract.py`: Runs extraction pipelines end-to-end.

3. **Plotting**
   - `plot_with_media.py`: Generates interactive Plotly-based HTML plots of assessment fields.
     - Points are colored by stages (per-field stage labels).
     - Media indicators show presence of transcript, audio, and image.
     - Clicking a point displays transcript, audio playback, and image.

## Usage

### 1. Extract Data
From bag files, generate assessment CSVs and observation JSONs:
```bash
python3 src/post_ra_pkg/extract_assessments.py --bag <rosbag> --outdir outputs/csv
python3 src/post_ra_pkg/extract_observations.py --bag <rosbag> --outdir outputs/json
python3 src/post_ra_pkg/extract_observation_data_sources.py --bag <rosbag> --outdir outputs/json
python3 src/post_ra_pkg/extract_casualty_images.py --bag <rosbag> --outdir outputs/casualty_images

Generate plots:-
python3 src/post_ra_pkg/plot_with_media.py \
  --indir outputs/json \
  --assess_csv outputs/csv/assessments_with_time.csv \
  --outdir outputs/plots_fields_media \
  --link_mode time_all \
  --link_tol 10.0 \
  --enable_images \
  --image_field image_url \
  --image_path_root outputs/images \
  --stage_mode by_field
