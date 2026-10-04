#!/usr/bin/env python3
import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
import hashlib
import time
import shutil
import pandas as pd
from app.retrieval.retrieval_interface import RetrievalInterface

def get_hash(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def build_argument_parser():
    parser = argparse.ArgumentParser(description="RF Shazam Wrapper")
    parser.add_argument("--input", required=False)
    parser.add_argument("--output", required=False)
    parser.add_argument("--metadata", required=False, help="Explicit path to JSON metadata sidecar")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--save-visualizations", action="store_true")
    parser.add_argument("--disable-retrieval", action="store_true")
    parser.add_argument("--config", default="config/final_policy.json")
    parser.add_argument("--version", action="store_true")
    
    # New UI mode arguments
    parser.add_argument("--ui", action="store_true", help="Launch the local offline UI")
    parser.add_argument("--host", default="127.0.0.1", help="Host binding for UI")
    parser.add_argument("--port", type=int, default=8080, help="Port for UI")
    parser.add_argument("--library-path", default=None, help="Path to SQLite library for UI")
    parser.add_argument("--library-mode", default="update", help="Read, Update, Off")
    parser.add_argument("--top-k", type=int, default=3, help="Top K matches")
    return parser

def validate_runtime_contract(args, parser):
    if args.version:
        print("rf-shazam-final 20260715")
        sys.exit(0)
    if not args.ui:
        if not args.input or not args.output:
            parser.error("the following arguments are required: --input, --output")

def run_inference(args):
    os.makedirs(args.output, exist_ok=True)
    if os.path.isfile(args.input):
        temp_input = os.path.join(args.output, "_temp_input_dir")
        os.makedirs(temp_input, exist_ok=True)
        # copy the input file
        shutil.copy(args.input, temp_input)
        
        # Explicit metadata support
        if args.metadata and os.path.isfile(args.metadata):
            stem = os.path.splitext(os.path.basename(args.input))[0]
            explicit_meta_path = os.path.join(temp_input, f"{stem}.json")
            shutil.copy(args.metadata, explicit_meta_path)
            
        input_dir = temp_input
    else:
        input_dir = args.input

    runner_path = os.path.join(os.path.dirname(__file__), "app", "runners", "rf_shazam_runner.py")
    cmd = [
        sys.executable,
        runner_path,
        "--input", input_dir,
        "--output", args.output,
        "--config", args.config
    ]
    
    t0 = time.time()
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Runner failed:")
        print(result.stderr)
        raise RuntimeError(f"Runner failed with code {result.returncode}:\n{result.stderr}")

    run_summary_path = os.path.join(args.output, "run_summary.json")
    event_log_path = os.path.join(args.output, "event_log.json")

    with open(event_log_path, "r") as f:
        event_log = json.load(f)

    with open(args.config, "r") as f:
        config_data = json.load(f)

    model_hash = get_hash(os.path.join(os.path.dirname(__file__), "models", "best.pt"))
    policy_hash = get_hash(args.config)

    retrieval = RetrievalInterface(mode=args.library_mode, top_k=args.top_k)

    final_output = []
    
    # Process inputs based on manifest to handle Background_No_Event
    manifest_path = os.path.join(args.output, "processed_input_manifest.csv")
    manifest = pd.read_csv(manifest_path)
    
    # Import our new canonical metadata mapper
    import app.metadata.validator as md_val
    
    events_by_input = {}
    for evt in event_log.get("events", []):
        iid = evt.get("event_id", "").split("_evt")[0].split("input")[-1]
        try:
            iid = int(iid)
        except:
            iid = -1
        events_by_input.setdefault(iid, []).append(evt)

    for idx, row in manifest.iterrows():
        input_id = int(row["input_id"])
        source_path = row["source_path"]
        
        events = events_by_input.get(input_id, [])
        formatted_events = []
        
        if args.disable_retrieval:
            ret_results = []
            ret_status = "DISABLED"
            ret_stats = {
                "library_mode": args.library_mode,
                "database_path": "N/A",
                "records_before": 0,
                "records_searched": 0,
                "top_k_requested": args.top_k,
                "matches_returned": 0,
                "records_inserted": 0,
                "duplicates_skipped": 0,
                "records_after": 0,
                "database_modified": "No"
            }
        else:
            ret_results, ret_status, ret_stats = retrieval.query(events, None)
        
        # Canonical Metadata parsing for this input
        # rf_shazam_runner populates metadata_path in manifest
        meta_path = row["metadata_path"]
        if pd.isna(meta_path) or not meta_path:
            meta_path = None
        else:
            meta_path = str(meta_path)
            
        canonical, status, errs, warns = md_val.parse_and_validate_metadata(meta_path) if meta_path else (None, "Metadata not supplied", [], [])
        
        # Override metadata status if explicit metadata provided but mismatched
        if args.metadata and not meta_path:
            # Explicit metadata was supplied but the runner didn't find it
            status = "Metadata filename mismatch"
            
        if not events:
            # Background_No_Event logic
            formatted_events = []
        else:
            for i, evt in enumerate(events):
                ret_info = ret_results[i] if not args.disable_retrieval else {"retrieval_top3": [], "uncertainty": {}}
                
                # Perform mapping using the canonical validated metadata
                bbox_px = evt["bbox_xyxy_px"]
                img_w = row["image_width"]
                img_h = row["image_height"]
                phys = md_val.calculate_physical_coordinates(canonical, bbox_px, img_w, img_h)
                
                evt_status = status
                if evt_status == "Metadata loaded" and phys["physical_mapping_status"] != "Complete":
                    evt_status = "Metadata incomplete"
                    
                formatted_events.append({
                    "event_id": evt["event_id"],
                    "class_id": next((k for k,v in config_data["classes"].items() if v == evt["label"]), -1),
                    "class_name": evt["label"],
                    "confidence": evt["confidence"],
                    "bounding_box": evt["bbox_xyxy_px"],
                    "pixel_coordinates": evt["bbox_xyxy_px"],
                    "time_start": phys["start_time_s"],
                    "time_end": phys["end_time_s"],
                    "duration": phys["duration_s"],
                    "frequency_low": phys["frequency_low_hz"],
                    "frequency_high": phys["frequency_high_hz"],
                    "center_frequency": phys["event_center_frequency_hz"],
                    "bandwidth": phys["bandwidth_hz"],
                    "metadata_source": args.metadata if args.metadata else evt["metadata_path"],
                    "metadata_status": evt_status,
                    "metadata_warnings": warns,
                    "metadata_errors": errs,
                    "physical_mapping_status": phys["physical_mapping_status"],
                    "retrieval_top3": ret_info.get("retrieval_top3", []),
                    "uncertainty": ret_info.get("uncertainty", {})
                })

        # If at least one event was incomplete for mapping, mark file as incomplete
        final_file_status = status
        if formatted_events:
            for evt_dict in formatted_events:
                if evt_dict.get("metadata_status") == "Metadata incomplete":
                    final_file_status = "Metadata incomplete"
                    break
        elif status == "Metadata loaded":
            # If no events, just do a dummy mapping to check if it has the required fields
            dummy_phys = md_val.calculate_physical_coordinates(canonical, [0, 0, 10, 10], row["image_width"], row["image_height"])
            if dummy_phys["physical_mapping_status"] != "Complete":
                final_file_status = "Metadata incomplete"
                
        record = {
            "schema_version": "1.0",
            "input_id": input_id,
            "source_path": source_path,
            "metadata_source": meta_path,
            "metadata_status": final_file_status,
            "source_sha256": get_hash(source_path),
            "processing_status": "SUCCESS",
            "model_name": config_data["model"]["weights_path"],
            "model_sha256": model_hash,
            "policy_sha256": policy_hash,
            "class_order": config_data["classes"],
            "confidence_threshold": config_data["model"]["confidence_threshold"],
            "nms_iou_threshold": config_data["model"]["nms_iou"],
            "image_size": config_data["model"]["imgsz"],
            "device": event_log.get("runtime", {}).get("device", args.device),
            "processing_seconds": time.time() - t0,
            "events": formatted_events,
            "library_stats": ret_stats,
            "warnings": ["Retrieval is " + ret_status],
            "errors": []
        }
        if not formatted_events:
            record["overall_classification"] = "Background_No_Event"
            
        final_output.append(record)

    with open(os.path.join(args.output, "final_output.json"), "w") as f:
        json.dump(final_output, f, indent=2)

    return final_output, len(manifest)

def main():
    parser = build_argument_parser()
    args = parser.parse_args()
    validate_runtime_contract(args, parser)

    if args.ui:
        import app.ui.server
        app.ui.server.run(args)
    else:
        final_output, count = run_inference(args)
        print(f"Processed {count} files successfully.")

if __name__ == "__main__":
    main()
