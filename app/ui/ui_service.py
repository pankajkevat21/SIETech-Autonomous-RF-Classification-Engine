import os
import uuid
import shutil
import zipfile
import json
import traceback
import copy
from run_rf_shazam import run_inference, get_hash

ALLOWED_EXTENSIONS = {'.npy', '.npz', '.png', '.jpg', '.jpeg', '.bmp', '.webp'}
ALLOWED_META = {'.json'}

def is_safe_path(basedir, path, follow_symlinks=True):
    basedir = os.path.abspath(basedir)
    path = os.path.abspath(path)
    return path.startswith(basedir)

from datetime import datetime, timezone
from PIL import Image
import numpy as np

def create_request_context():
    req_id = str(uuid.uuid4())
    utc_time = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    unique_out_dir = f"run_{utc_time}_{req_id[:8]}"
    paths = {
        'input': os.path.join("runtime", "input", req_id),
        'output': os.path.join("output", unique_out_dir),
        'logs': os.path.join("runtime", "logs", req_id)
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return req_id, paths, unique_out_dir

def get_file_metadata(filepath):
    meta = {
        "filename": os.path.basename(filepath),
        "extension": os.path.splitext(filepath)[1].lower(),
        "file_size_bytes": os.path.getsize(filepath),
        "dimensions": "N/A",
        "dtype": "N/A"
    }
    try:
        if meta["extension"] in ['.npy']:
            arr = np.load(filepath)
            meta["dimensions"] = str(arr.shape)
            meta["dtype"] = str(arr.dtype)
        elif meta["extension"] in ['.npz']:
            with np.load(filepath) as data:
                meta["dimensions"] = f"{len(data.files)} arrays"
        elif meta["extension"] in ['.png', '.jpg', '.jpeg']:
            with Image.open(filepath) as img:
                meta["dimensions"] = f"{img.width}x{img.height}"
    except Exception:
        pass
    return meta

def process_upload(files, form_data, app_args):
    req_id, paths, unique_out_dir = create_request_context()
    errors = []
    
    file_metadata_map = {}
    
    try:
        # Group files by stem to preserve NPY/JSON pairing
        temp_dir = os.path.join(paths['input'], '_raw_uploads')
        os.makedirs(temp_dir, exist_ok=True)
        
        raw_files = []
        for file in files:
            if not file.filename: continue
            
            ext = os.path.splitext(file.filename)[1].lower()
            if ext == '.zip':
                zip_path = os.path.join(temp_dir, f"upload_{uuid.uuid4().hex[:8]}.zip")
                file.save(zip_path)
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        for member in zf.namelist():
                            member_ext = os.path.splitext(member)[1].lower()
                            if member_ext in ALLOWED_EXTENSIONS or member_ext in ALLOWED_META:
                                target_path = os.path.abspath(os.path.join(temp_dir, os.path.basename(member)))
                                if is_safe_path(temp_dir, target_path):
                                    with open(target_path, 'wb') as f_out:
                                        f_out.write(zf.read(member))
                                    raw_files.append(target_path)
                except Exception as e:
                    errors.append(f"Invalid ZIP archive: {e}")
                os.remove(zip_path)
            elif ext in ALLOWED_EXTENSIONS or ext in ALLOWED_META:
                target_path = os.path.join(temp_dir, os.path.basename(file.filename))
                file.save(target_path)
                raw_files.append(target_path)
            else:
                errors.append(f"Unsupported file extension: {ext}")
                
        # Group by stem
        from collections import defaultdict
        groups = defaultdict(list)
        for rf in raw_files:
            stem = os.path.splitext(os.path.basename(rf))[0]
            groups[stem].append(rf)
            
        for stem, group_files in groups.items():
            group_uuid = uuid.uuid4().hex[:8]
            for rf in group_files:
                ext = os.path.splitext(rf)[1].lower()
                safe_name = f"upload_{group_uuid}_{stem}{ext}"
                target_path = os.path.join(paths['input'], safe_name)
                os.rename(rf, target_path)
                # We only want to track metadata for primary files in file_metadata_map
                if ext in ALLOWED_EXTENSIONS:
                    file_metadata_map[target_path] = get_file_metadata(target_path)
                
        shutil.rmtree(temp_dir, ignore_errors=True)

        # Remove orphaned JSON files (JSON without a matching primary file)
        # Actually rf_shazam_runner ignores them, so it's fine.

        if not os.listdir(paths['input']):
            return {"error": "No valid files uploaded", "errors": errors}
            
        # Clone args for this run
        run_args = copy.deepcopy(app_args)
        run_args.input = paths['input']
        run_args.output = paths['output']
        
        # Parse UI config
        lib_mode = form_data.get('library_mode', 'read')
        top_k = int(form_data.get('top_k', 3))
        
        run_args.library_mode = lib_mode
        run_args.top_k = top_k
        
        if lib_mode == 'off':
            run_args.disable_retrieval = True
        else:
            run_args.disable_retrieval = False
            
        # Run inference
        final_output, count = run_inference(run_args)
        
        # Map metadata back to final output
        for res in final_output:
            sp = res.get("source_path", "")
            if sp in file_metadata_map:
                res["file_metadata"] = file_metadata_map[sp]
            else:
                res["file_metadata"] = get_file_metadata(sp)
                
        # Cleanup input
        shutil.rmtree(paths['input'], ignore_errors=True)
        
        # Create Result ZIP
        result_zip_path = os.path.join(paths['output'], f"results_{req_id}.zip")
        with zipfile.ZipFile(result_zip_path, 'w') as zf:
            for root, dirs, files in os.walk(paths['output']):
                for f in files:
                    if f.endswith('.zip'): continue
                    file_path = os.path.join(root, f)
                    arcname = os.path.relpath(file_path, paths['output'])
                    zf.write(file_path, arcname)
        
        # Calculate totals
        total_events = sum(len(r.get('events', [])) for r in final_output)
        bne_count = sum(1 for r in final_output if r.get('overall_classification') == 'Background_No_Event')
        
        with open(run_args.config) as f:
            cfg = json.load(f)
            
        return {
            "req_id": req_id,
            "results": final_output,
            "summary": {
                "run_id": unique_out_dir,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "library_mode": lib_mode.capitalize(),
                "top_k_requested": top_k if lib_mode != 'off' else 'N/A',
                "output_directory": paths['output'],
                "total_inputs": count,
                "successfully_processed": count,
                "rejected_files": len(errors),
                "total_events": total_events,
                "bne_count": bne_count,
                "runtime_sec": final_output[0].get("processing_seconds", 0) if final_output else 0,
                "model_name": cfg["model"]["weights_path"],
                "model_hash": get_hash(os.path.join("models", "best.pt"))[:8],
                "conf_thresh": cfg["model"]["confidence_threshold"],
                "nms_iou": cfg["model"]["nms_iou"],
                "imgsz": cfg["model"]["imgsz"],
                "run_status": "COMPLETED"
            },
            "errors": errors
        }
        
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e), "errors": errors}
