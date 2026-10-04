#!/usr/bin/env python3

import os
import sys
import json
import time
import argparse
import hashlib
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from PIL import Image

import cv2
import torch
from ultralytics import YOLO


ALLOWED_INPUT_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".npz", ".npy"}


def safe_hash_text(text, n=12):
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:n]


def normalize01(x, eps=1e-8):
    x = np.asarray(x)

    if np.iscomplexobj(x):
        x = np.abs(x)

    x = np.squeeze(x)
    x = np.nan_to_num(x.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)

    mn = float(np.min(x))
    mx = float(np.max(x))

    if mx - mn < eps:
        return np.zeros_like(x, dtype=np.float32)

    return ((x - mn) / (mx - mn + eps)).astype(np.float32)


def load_npz_array(path):
    data = np.load(path, allow_pickle=False)
    keys = list(data.keys())

    preferred = ["spectrogram", "log_power", "spec", "power", "arr_0", "data", "image", "S"]

    for k in preferred:
        if k in keys:
            arr = data[k]
            if isinstance(arr, np.ndarray) and arr.ndim >= 2:
                return arr, k, keys

    for k in keys:
        arr = data[k]
        if isinstance(arr, np.ndarray) and arr.ndim >= 2:
            return arr, k, keys

    raise ValueError("No usable 2D array found in NPZ. keys=" + str(keys))


def load_npy_array(path):
    arr = np.load(path, allow_pickle=False)
    return arr, "npy_array", ["npy_array"]


def array_to_rgb_image(arr):
    arr = np.asarray(arr)

    if np.iscomplexobj(arr):
        arr = np.abs(arr)

    arr = np.squeeze(arr)

    if arr.ndim == 3:
        if arr.shape[-1] in [3, 4]:
            arr01 = normalize01(arr[..., :3])
            img8 = (arr01 * 255).astype(np.uint8)
            return Image.fromarray(img8).convert("RGB"), str(arr.shape)
        arr = arr[..., 0]

    if arr.ndim != 2:
        raise ValueError("Unsupported array shape: " + str(arr.shape))

    arr01 = normalize01(arr)
    img8 = (arr01 * 255).astype(np.uint8)

    cm = cv2.applyColorMap(img8, cv2.COLORMAP_VIRIDIS)
    cm_rgb = cv2.cvtColor(cm, cv2.COLOR_BGR2RGB)

    return Image.fromarray(cm_rgb).convert("RGB"), str(arr.shape)


def convert_input_to_cached_image(src_path, out_path):
    src_path = Path(src_path)
    ext = src_path.suffix.lower()

    if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
        img = Image.open(src_path).convert("RGB")
        img.save(out_path)
        return {
            "cache_mode": "image_copied",
            "array_key": None,
            "array_keys_json": None,
            "array_shape": None,
            "width": img.size[0],
            "height": img.size[1],
        }

    if ext == ".npz":
        arr, used_key, keys = load_npz_array(src_path)
        img, arr_shape = array_to_rgb_image(arr)
        img.save(out_path)
        return {
            "cache_mode": "npz_converted_to_viridis_png",
            "array_key": used_key,
            "array_keys_json": json.dumps(keys),
            "array_shape": arr_shape,
            "width": img.size[0],
            "height": img.size[1],
        }

    if ext == ".npy":
        arr, used_key, keys = load_npy_array(src_path)
        img, arr_shape = array_to_rgb_image(arr)
        img.save(out_path)
        return {
            "cache_mode": "npy_converted_to_viridis_png",
            "array_key": used_key,
            "array_keys_json": json.dumps(keys),
            "array_shape": arr_shape,
            "width": img.size[0],
            "height": img.size[1],
        }

    raise ValueError("Unsupported input extension: " + ext)


def discover_input_files(input_dir, max_files=None):
    input_dir = Path(input_dir)
    files = []

    for p in input_dir.rglob("*"):
        if not p.is_file():
            continue

        ext = p.suffix.lower()
        if ext not in ALLOWED_INPUT_EXTS:
            continue

        s = str(p).replace("\\", "/").lower()

        if "/labels/" in s or "/reports/" in s or "/checkpoints/" in s or "/runs/" in s:
            continue

        files.append(p)

    files = sorted(files)

    if max_files is not None and len(files) > max_files:
        files = files[:max_files]

    return files


def find_metadata_for_input(src_path, input_root):
    src_path = Path(src_path)
    input_root = Path(input_root)

    candidates = [
        src_path.with_suffix(".json"),
        src_path.parent / (src_path.stem + "_metadata.json"),
        src_path.parent / (src_path.stem + ".metadata.json"),
        src_path.parent.parent / "metadata_json" / (src_path.stem + ".json"),
        input_root / "metadata_json" / (src_path.stem + ".json"),
        input_root / "metadata" / (src_path.stem + ".json"),
    ]

    stem = src_path.stem
    for suffix in ["_canonical_spectrogram", "_spectrogram", "_spec"]:
        if stem.endswith(suffix):
            base = stem[: -len(suffix)]
            candidates.extend([
                src_path.parent / (base + "_metadata.json"),
                input_root / "metadata_json" / (base + "_metadata.json"),
                input_root.parent / "metadata_json" / (base + "_metadata.json"),
                input_root.parent / "metadata_json" / (base + ".json"),
            ])

    for c in candidates:
        if c.exists():
            return c

    return None


def load_metadata_json(meta_path):
    if meta_path is None:
        return {}

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_meta_value(meta, keys, default=None):
    for k in keys:
        if k in meta:
            return meta[k]
    return default


def bbox_to_time_freq_estimate(x1, y1, x2, y2, img_w, img_h, meta):
    result = {
        "time_start_sec": None,
        "time_end_sec": None,
        "freq_low_hz": None,
        "freq_high_hz": None,
        "mapping_status": "metadata_missing_or_insufficient",
    }

    t0 = get_meta_value(meta, ["time_start_sec", "start_time_sec", "t_start", "start_sec"], None)
    t1 = get_meta_value(meta, ["time_end_sec", "end_time_sec", "t_end", "end_sec"], None)
    duration = get_meta_value(meta, ["duration_sec", "duration_s", "recording_duration_sec"], None)

    if t0 is None:
        t0 = 0.0

    if t1 is None and duration is not None:
        try:
            t1 = float(t0) + float(duration)
        except Exception:
            t1 = None

    fmin = get_meta_value(meta, ["freq_min_hz", "frequency_min_hz", "f_min_hz", "min_freq_hz"], None)
    fmax = get_meta_value(meta, ["freq_max_hz", "frequency_max_hz", "f_max_hz", "max_freq_hz"], None)

    center = get_meta_value(meta, ["center_freq_hz", "center_frequency_hz", "cf_hz"], None)
    bw = get_meta_value(meta, ["bandwidth_hz", "bw_hz", "sample_rate_hz", "sampling_rate_hz"], None)

    if (fmin is None or fmax is None) and center is not None and bw is not None:
        try:
            center = float(center)
            bw = float(bw)
            fmin = center - bw / 2.0
            fmax = center + bw / 2.0
        except Exception:
            fmin = None
            fmax = None

    try:
        if t1 is not None:
            t0 = float(t0)
            t1 = float(t1)
            result["time_start_sec"] = t0 + (float(x1) / img_w) * (t1 - t0)
            result["time_end_sec"] = t0 + (float(x2) / img_w) * (t1 - t0)

        if fmin is not None and fmax is not None:
            fmin = float(fmin)
            fmax = float(fmax)

            freq_high = fmax - (float(y1) / img_h) * (fmax - fmin)
            freq_low = fmax - (float(y2) / img_h) * (fmax - fmin)

            result["freq_low_hz"] = min(freq_low, freq_high)
            result["freq_high_hz"] = max(freq_low, freq_high)

        if result["time_start_sec"] is not None or result["freq_low_hz"] is not None:
            result["mapping_status"] = "estimated_from_metadata"

    except Exception:
        result["mapping_status"] = "mapping_failed"

    return result


def image_crop_feature_vector(image_path, bbox_xyxy):
    img = Image.open(image_path).convert("RGB")
    arr = np.asarray(img).astype(np.float32) / 255.0
    h, w = arr.shape[:2]

    x1, y1, x2, y2 = bbox_xyxy

    x1i = int(max(0, min(w - 1, round(x1))))
    x2i = int(max(0, min(w, round(x2))))
    y1i = int(max(0, min(h - 1, round(y1))))
    y2i = int(max(0, min(h, round(y2))))

    if x2i <= x1i or y2i <= y1i:
        crop = arr
    else:
        crop = arr[y1i:y2i, x1i:x2i, :]

    gray = crop.mean(axis=2)

    bw = max(1.0, float(x2 - x1))
    bh = max(1.0, float(y2 - y1))
    area = bw * bh

    return [
        float(x1 / w), float(y1 / h), float(x2 / w), float(y2 / h),
        float(bw / w), float(bh / h), float(area / (w * h)), float(bw / bh),
        float(gray.mean()), float(gray.std()),
        float(np.percentile(gray, 25)), float(np.percentile(gray, 50)), float(np.percentile(gray, 75)),
        float(crop[:, :, 0].mean()), float(crop[:, :, 1].mean()), float(crop[:, :, 2].mean()),
    ]


def run_pipeline(input_dir, output_dir, config_path, max_files=None):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    config_path = Path(config_path)

    output_dir.mkdir(parents=True, exist_ok=True)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    model_cfg = config["model"]
    weights_path = Path(model_cfg["weights_path"])

    # Resolve relative model paths from package root.
    # Expected package layout:
    #   rf_shazam_runner.py
    #   config/final_policy.json
    #   models/best.pt
    if not weights_path.is_absolute():
        config_parent = Path(config_path).resolve().parent
        package_root = config_parent.parent if config_parent.name == "config" else config_parent
        weights_path = package_root / weights_path

    if not weights_path.exists():
        raise FileNotFoundError("Model weights not found: " + str(weights_path))

    conf = float(model_cfg.get("confidence_threshold", 0.60))
    iou = float(model_cfg.get("nms_iou", 0.50))
    imgsz = int(model_cfg.get("imgsz", 640))
    max_det = int(model_cfg.get("max_det", 300))

    class_id_to_name = {int(k): v for k, v in config.get("classes", {}).items()}

    run_id = "rf_shazam_run_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    cache_dir = output_dir / "_cache_images"
    cache_dir.mkdir(parents=True, exist_ok=True)

    event_log_path = output_dir / config["output_files"].get("event_log", "event_log.json")
    siglib_path = output_dir / config["output_files"].get("signature_library", "signature_library.json")
    events_csv_path = output_dir / config["output_files"].get("events_csv", "events.csv")
    manifest_csv_path = output_dir / config["output_files"].get("input_manifest", "processed_input_manifest.csv")
    run_summary_path = output_dir / config["output_files"].get("run_summary", "run_summary.json")

    t0 = time.time()

    input_files = discover_input_files(input_dir, max_files=max_files)

    manifest_rows = []
    bad_rows = []

    for idx, src_path in enumerate(input_files):
        out_name = "input_%05d_%s_%s.png" % (idx, safe_hash_text(src_path), Path(src_path).stem)
        cached_img_path = cache_dir / out_name

        try:
            info = convert_input_to_cached_image(src_path, cached_img_path)
            meta_path = find_metadata_for_input(src_path, input_dir)

            manifest_rows.append({
                "input_id": int(idx),
                "source_path": str(src_path),
                "source_ext": Path(src_path).suffix.lower(),
                "cached_image_path": str(cached_img_path),
                "metadata_path": str(meta_path) if meta_path else None,
                "cache_mode": info["cache_mode"],
                "array_key": info["array_key"],
                "array_keys_json": info["array_keys_json"],
                "array_shape": info["array_shape"],
                "image_width": int(info["width"]),
                "image_height": int(info["height"]),
                "metadata_loaded": bool(meta_path is not None),
            })

        except Exception as e:
            bad_rows.append({
                "source_path": str(src_path),
                "error": repr(e),
            })

    manifest_df = pd.DataFrame(manifest_rows)
    manifest_df.to_csv(manifest_csv_path, index=False)

    if len(manifest_df) == 0:
        raise RuntimeError("No usable input files after conversion.")

    device = 0 if torch.cuda.is_available() else "cpu"
    model = YOLO(str(weights_path))

    event_rows = []
    signature_items = []

    t_infer_start = time.time()

    for _, row in manifest_df.iterrows():
        img_path = row["cached_image_path"]
        meta = load_metadata_json(row["metadata_path"]) if pd.notna(row["metadata_path"]) else {}

        results = model.predict(
            source=img_path,
            imgsz=imgsz,
            conf=conf,
            iou=iou,
            max_det=max_det,
            verbose=False,
            device=device,
        )

        boxes = results[0].boxes

        if boxes is None or len(boxes) == 0:
            continue

        xyxy = boxes.xyxy.detach().cpu().numpy()
        confs = boxes.conf.detach().cpu().numpy()
        clss = boxes.cls.detach().cpu().numpy().astype(int)

        img_w = int(row["image_width"])
        img_h = int(row["image_height"])

        for det_idx, item in enumerate(zip(xyxy, confs, clss)):
            bb, det_conf, cls_id = item
            cls_id = int(cls_id)

            if cls_id not in class_id_to_name:
                continue

            x1, y1, x2, y2 = [float(v) for v in bb]
            label = class_id_to_name[cls_id]

            tf_est = bbox_to_time_freq_estimate(x1, y1, x2, y2, img_w, img_h, meta)
            feature_vector = image_crop_feature_vector(img_path, [x1, y1, x2, y2])

            event_id = "%s_input%05d_evt%03d" % (run_id, int(row["input_id"]), det_idx)
            sig_id = "%s_sig_%s" % (run_id, safe_hash_text(event_id, n=16))

            event_rows.append({
                "event_id": event_id,
                "input_id": int(row["input_id"]),
                "source_path": row["source_path"],
                "cached_image_path": img_path,
                "metadata_path": row["metadata_path"],
                "label": label,
                "class_id": cls_id,
                "confidence": float(det_conf),
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width_px": float(x2 - x1),
                "height_px": float(y2 - y1),
                "area_px": float(max(0, x2 - x1) * max(0, y2 - y1)),
                "time_start_sec": tf_est["time_start_sec"],
                "time_end_sec": tf_est["time_end_sec"],
                "freq_low_hz": tf_est["freq_low_hz"],
                "freq_high_hz": tf_est["freq_high_hz"],
                "mapping_status": tf_est["mapping_status"],
                "signature_id": sig_id,
            })

            signature_items.append({
                "signature_id": sig_id,
                "event_id": event_id,
                "source_path": row["source_path"],
                "label": label,
                "confidence": float(det_conf),
                "bbox_xyxy_px": [x1, y1, x2, y2],
                "time_freq_estimate": tf_est,
                "feature_vector": feature_vector,
                "feature_description": [
                    "x1_norm", "y1_norm", "x2_norm", "y2_norm",
                    "width_norm", "height_norm", "area_norm", "aspect_ratio",
                    "gray_mean", "gray_std", "gray_p25", "gray_p50", "gray_p75",
                    "rgb_r_mean", "rgb_g_mean", "rgb_b_mean"
                ],
            })

    inference_seconds = time.time() - t_infer_start

    events_df = pd.DataFrame(event_rows)

    if len(events_df) == 0:
        events_df = pd.DataFrame(columns=[
            "event_id", "input_id", "source_path", "cached_image_path", "metadata_path",
            "label", "class_id", "confidence",
            "x1", "y1", "x2", "y2", "width_px", "height_px", "area_px",
            "time_start_sec", "time_end_sec", "freq_low_hz", "freq_high_hz",
            "mapping_status", "signature_id"
        ])

    events_df.to_csv(events_csv_path, index=False)

    event_log = {
        "schema_version": "rf_shazam_event_log_v1.0",
        "created_at": datetime.now().isoformat(),
        "run_id": run_id,
        "project": "RF Track-1 Spectrum Intelligence RF Shazam",
        "mode": "final_default_conservative",
        "safety_scope": config.get("safety_scope", "passive RF/ESM analysis only"),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "model": {
            "type": model_cfg.get("type", "YOLO-only detector/classifier"),
            "weights": str(weights_path),
            "confidence_threshold": conf,
            "nms_iou": iou,
            "imgsz": imgsz,
        },
        "num_inputs": int(len(manifest_df)),
        "num_events": int(len(events_df)),
        "events": [],
    }

    for _, r in events_df.iterrows():
        event_log["events"].append({
            "event_id": r["event_id"],
            "source_path": r["source_path"],
            "metadata_path": r["metadata_path"] if pd.notna(r["metadata_path"]) else None,
            "label": r["label"],
            "confidence": float(r["confidence"]),
            "bbox_xyxy_px": [float(r["x1"]), float(r["y1"]), float(r["x2"]), float(r["y2"])],
            "bbox_size_px": {
                "width": float(r["width_px"]),
                "height": float(r["height_px"]),
                "area": float(r["area_px"]),
            },
            "time_freq_estimate": {
                "time_start_sec": None if pd.isna(r["time_start_sec"]) else float(r["time_start_sec"]),
                "time_end_sec": None if pd.isna(r["time_end_sec"]) else float(r["time_end_sec"]),
                "freq_low_hz": None if pd.isna(r["freq_low_hz"]) else float(r["freq_low_hz"]),
                "freq_high_hz": None if pd.isna(r["freq_high_hz"]) else float(r["freq_high_hz"]),
                "mapping_status": r["mapping_status"],
            },
            "signature_id": r["signature_id"],
        })

    with open(event_log_path, "w", encoding="utf-8") as f:
        json.dump(event_log, f, indent=2)

    siglib = {
        "schema_version": "rf_shazam_signature_library_v1.0",
        "created_at": datetime.now().isoformat(),
        "run_id": run_id,
        "library_type": "event_signature_library",
        "feature_vector_type": "lightweight_bbox_crop_statistics_v1",
        "num_signatures": len(signature_items),
        "signatures": signature_items,
    }

    with open(siglib_path, "w", encoding="utf-8") as f:
        json.dump(siglib, f, indent=2)

    class_counts = events_df["label"].value_counts().to_dict() if len(events_df) > 0 else {}

    total_seconds = time.time() - t0
    sec_per_input = total_seconds / len(manifest_df) if len(manifest_df) else None

    run_summary = {
        "schema_version": "rf_shazam_run_summary_v1.0",
        "created_at": datetime.now().isoformat(),
        "run_id": run_id,
        "status": "completed",
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "num_input_files_discovered": int(len(input_files)),
        "num_input_files_processed": int(len(manifest_df)),
        "num_bad_inputs": int(len(bad_rows)),
        "num_events": int(len(events_df)),
        "event_class_counts": class_counts,
        "runtime": {
            "inference_seconds": float(round(inference_seconds, 6)),
            "total_seconds": float(round(total_seconds, 6)),
            "seconds_per_processed_input": float(round(sec_per_input, 6)) if sec_per_input else None,
            "device": str(device),
            "cuda_available": bool(torch.cuda.is_available()),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        },
        "final_policy": {
            "model": model_cfg.get("type", "YOLO-only"),
            "confidence_threshold": conf,
            "nms_iou": iou,
            "imgsz": imgsz,
        },
        "outputs": {
            "event_log_json": str(event_log_path),
            "signature_library_json": str(siglib_path),
            "events_csv": str(events_csv_path),
            "processed_input_manifest_csv": str(manifest_csv_path),
            "run_summary_json": str(run_summary_path),
        },
    }

    with open(run_summary_path, "w", encoding="utf-8") as f:
        json.dump(run_summary, f, indent=2)

    return run_summary


def main():
    parser = argparse.ArgumentParser(description="RF Shazam passive spectrum intelligence runner")
    parser.add_argument("--input", required=True, help="Input folder containing spectrogram .png/.npz/.npy files")
    parser.add_argument("--output", required=True, help="Output folder for event log and signature library")
    parser.add_argument("--config", required=True, help="Path to final_policy.json config")
    parser.add_argument("--max-files", type=int, default=None, help="Optional max files")

    args = parser.parse_args()

    summary = run_pipeline(
        input_dir=args.input,
        output_dir=args.output,
        config_path=args.config,
        max_files=args.max_files,
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
