#!/usr/bin/env python3
import argparse, json, os, re
from pathlib import Path
from typing import Dict, Any, List

FNAME_RE = re.compile(r"^frame_(\d+)_(\d+)\.(jpg|jpeg|png)$", re.IGNORECASE)

def load_json(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(p: Path, obj):
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    tmp.replace(p)

def read_run_start_epoch_seconds(bag_dir: Path) -> float:
    """Read starting_time.nanoseconds_since_epoch from metadata.yaml."""
    y = (bag_dir / "metadata.yaml").read_text(encoding="utf-8")
    ns = None
    for line in y.splitlines():
        line = line.strip()
        if line.startswith("nanoseconds_since_epoch:"):
            # e.g. nanoseconds_since_epoch: 1754576997347721159
            ns = int(line.split(":", 1)[1].strip())
            break
        # Newer metadata can store it nested under 'starting_time:'; the flat search above still finds it.
    if ns is None:
        raise FileNotFoundError("nanoseconds_since_epoch not found in metadata.yaml")
    return ns / 1e9

def collect_images_with_t(indir: Path) -> List[Dict[str, Any]]:
    out = []
    for p in sorted(indir.iterdir()):
        if not p.is_file():
            continue
        m = FNAME_RE.match(p.name)
        if not m:
            continue
        sec = int(m.group(1))
        nsec = int(m.group(2))
        out.append({"path": p, "sec": sec, "nsec": nsec, "t_abs": sec + nsec/1e9})
    return out

def main():
    ap = argparse.ArgumentParser(description="Write image_url into ODS by nearest time match")
    ap.add_argument("--bag_dir", required=True, help="Folder that contains metadata.yaml (the bag's directory)")
    ap.add_argument("--indir", required=True, help="Folder with observation_data_sources.json")
    ap.add_argument("--images", required=True, help="Folder with extracted casualty images (frame_<sec>_<nsec>.jpg)")
    ap.add_argument("--tol", type=float, default=1.0, help="Tolerance in seconds for nearest match")
    ap.add_argument("--image_field", default="image_url", help="ODS field name to write")
    args = ap.parse_args()

    bag_dir = Path(args.bag_dir)
    json_dir = Path(args.indir)
    img_dir = Path(args.images)

    ods_path = json_dir / "observation_data_sources.json"
    if not ods_path.exists():
        raise FileNotFoundError(f"Missing {ods_path}")

    # 1) run start epoch
    run_start_epoch_s = read_run_start_epoch_seconds(bag_dir)

    # 2) load ODS
    ods = load_json(ods_path)
    if not isinstance(ods, list):
        raise ValueError("observation_data_sources.json must be a list")

    # 3) collect images and compute time_since_start for each
    imgs = collect_images_with_t(img_dir)
    for im in imgs:
        im["t_rel"] = im["t_abs"] - run_start_epoch_s

    # 4) index ODS by t
    odst = []
    for i, r in enumerate(ods):
        t = r.get("time_since_start")
        if t is None:
            continue
        try:
            tt = float(t)
        except Exception:
            continue
        odst.append((i, tt))

    # 5) match
    wrote = 0
    for im in imgs:
        t = im["t_rel"]
        best = None
        best_dt = None
        for i, tt in odst:
            dt = abs(tt - t)
            if dt <= args.tol and (best_dt is None or dt < best_dt):
                best_dt = dt
                best = i
        if best is not None:
            # write image URL relative to JSON folder, so the HTML can load it
            rel = os.path.relpath(im["path"], json_dir)
            ods[best][args.image_field] = rel
            wrote += 1

    # 6) save (with backup)
    bak = ods_path.with_suffix(".json.bak")
    if not bak.exists():
        bak.write_text((ods_path.read_text(encoding="utf-8")), encoding="utf-8")
    save_json(ods_path, ods)

    print(f"[stitch] wrote {args.image_field} into {wrote} ODS rows (tol={args.tol:.1f}s)")
    print(f"[stitch] backup saved to {bak}")

if __name__ == "__main__":
    main()

