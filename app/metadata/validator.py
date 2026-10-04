import json
import math
import os

ALIAS_MAP = {
    "sample_rate": "sample_rate_hz",
    "fs_hz": "sample_rate_hz",
    "center_frequency": "center_frequency_hz",
    "fc_hz": "center_frequency_hz",
    "frequency_start": "frequency_start_hz",
    "f_start": "frequency_start_hz",
    "frequency_stop": "frequency_stop_hz",
    "f_stop": "frequency_stop_hz",
    "frequency_span": "frequency_span_hz",
    "span_hz": "frequency_span_hz",
    "time_start": "time_start_s",
    "t_start": "time_start_s",
    "time_end": "time_end_s",
    "t_end": "time_end_s",
    "duration": "duration_s",
    "time_step": "time_step_s",
    "frequency_step": "frequency_step_hz"
}

def is_finite_number(val):
    if not isinstance(val, (int, float)):
        return False
    if math.isnan(val) or math.isinf(val):
        return False
    return True

def parse_and_validate_metadata(filepath):
    # Returns (canonical_metadata, status, errors, warnings)
    errors = []
    warnings = []
    canonical = {}
    
    if not os.path.exists(filepath):
        return None, "Metadata not supplied", ["File not found"], []
        
    if os.path.getsize(filepath) > 5 * 1024 * 1024:
        return None, "Metadata invalid", ["File too large (exceeds 5MB)"], []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except json.JSONDecodeError as e:
        return None, "Metadata invalid", [f"Invalid JSON syntax: {e}"], []
    except UnicodeDecodeError:
        return None, "Metadata invalid", ["File is not valid UTF-8"], []
    except Exception as e:
        return None, "Metadata invalid", [f"Read error: {e}"], []

    if not isinstance(raw_data, dict):
        return None, "Metadata invalid", ["JSON must contain a top-level object (dict)"], []

    # Map aliases and collect values
    for k, v in raw_data.items():
        if isinstance(v, (dict, list)):
            if len(str(v)) > 100000: # rough check for huge nested objects
                errors.append(f"Nested object '{k}' is too large.")
                continue
                
        canonical_key = ALIAS_MAP.get(k, k)
        
        # Only preserve allowed types (numbers, strings, bools, small structures)
        # For canonical physical fields, strictly enforce numbers
        numeric_fields = {
            "sample_rate_hz", "center_frequency_hz", "frequency_start_hz",
            "frequency_stop_hz", "frequency_span_hz", "time_start_s", "time_end_s",
            "duration_s", "time_step_s", "frequency_step_hz", "fft_size",
            "hop_length", "overlap_samples", "overlap_ratio"
        }
        
        if canonical_key in numeric_fields:
            if not is_finite_number(v):
                errors.append(f"Field '{k}' must be a finite number.")
                continue
            v = float(v)
            
            if canonical_key == "sample_rate_hz" and v <= 0:
                errors.append("sample_rate_hz must be positive.")
                continue
            if canonical_key in ["duration_s", "frequency_span_hz", "fft_size", "hop_length", "overlap_samples", "overlap_ratio"] and v < 0:
                errors.append(f"{canonical_key} must be non-negative.")
                continue
            
        canonical[canonical_key] = v

    if "overlap_samples" in canonical and "fft_size" in canonical:
        if canonical["overlap_samples"] >= canonical["fft_size"]:
            errors.append("overlap_samples cannot be greater than or equal to fft_size.")
            
    if "frequency_start_hz" in canonical and "frequency_stop_hz" in canonical:
        if canonical["frequency_start_hz"] >= canonical["frequency_stop_hz"]:
            errors.append("frequency_start_hz must be less than frequency_stop_hz (for absolute bounds).")

    if errors:
        return None, "Metadata invalid", errors, warnings

    if not canonical:
        return canonical, "Metadata incomplete", [], ["No recognized metadata fields found."]
        
    return canonical, "Metadata loaded", [], warnings

def calculate_physical_coordinates(canonical, bbox_xyxy_px, img_w, img_h):
    """
    Given a canonical metadata object and pixel coordinates, compute physical mapping.
    bbox_xyxy_px: [x1, y1, x2, y2]
    img_w, img_h: original array dimensions (e.g., from spectrogram shape)
    """
    x1, y1, x2, y2 = bbox_xyxy_px
    
    res = {
        "start_time_s": None,
        "end_time_s": None,
        "duration_s": None,
        "frequency_low_hz": None,
        "frequency_high_hz": None,
        "event_center_frequency_hz": None,
        "bandwidth_hz": None,
        "physical_mapping_status": "Unavailable"
    }

    if not canonical or not isinstance(canonical, dict):
        return res

    # 1. Time Mapping
    # Needs a valid t0 and a valid t1 to map x coordinates
    t0 = canonical.get("time_start_s")
    t1 = canonical.get("time_end_s")
    dur = canonical.get("duration_s")
    t_step = canonical.get("time_step_s")

    if t0 is None:
        t0 = 0.0

    if t1 is None:
        if dur is not None:
            t1 = t0 + dur
        elif t_step is not None and img_w > 0:
            t1 = t0 + (img_w * t_step)
            
    if t1 is not None and img_w > 0:
        # We have a valid time span [t0, t1]
        x1_norm = x1 / img_w
        x2_norm = x2 / img_w
        res["start_time_s"] = t0 + x1_norm * (t1 - t0)
        res["end_time_s"] = t0 + x2_norm * (t1 - t0)
        res["duration_s"] = res["end_time_s"] - res["start_time_s"]

    # 2. Frequency Mapping
    f_start = canonical.get("frequency_start_hz")
    f_stop = canonical.get("frequency_stop_hz")
    f_center = canonical.get("center_frequency_hz")
    f_span = canonical.get("frequency_span_hz")
    fs = canonical.get("sample_rate_hz")
    
    f0, f1 = None, None
    if f_start is not None and f_stop is not None:
        f0, f1 = f_start, f_stop
    elif f_center is not None and f_span is not None:
        f0 = f_center - f_span / 2.0
        f1 = f_center + f_span / 2.0
    elif f_center is not None and fs is not None:
        # Assuming spectrogram covers exactly the nyquist band [-fs/2, fs/2] centered around fc
        f0 = f_center - fs / 2.0
        f1 = f_center + fs / 2.0
        
    if f0 is not None and f1 is not None and img_h > 0:
        # The direction of the frequency axis in the image
        # Default in many spectrograms: low freq at bottom (y=H), high freq at top (y=0)
        axis_dir = canonical.get("frequency_axis_direction", "low_at_bottom").lower()
        
        y1_norm = y1 / img_h
        y2_norm = y2 / img_h
        
        if axis_dir == "low_at_top":
            # y=0 is f0, y=H is f1
            freq1 = f0 + y1_norm * (f1 - f0)
            freq2 = f0 + y2_norm * (f1 - f0)
        else:
            # y=0 is f1, y=H is f0 (standard)
            freq1 = f1 - y1_norm * (f1 - f0)
            freq2 = f1 - y2_norm * (f1 - f0)
            
        res["frequency_low_hz"] = min(freq1, freq2)
        res["frequency_high_hz"] = max(freq1, freq2)
        res["event_center_frequency_hz"] = (res["frequency_high_hz"] + res["frequency_low_hz"]) / 2.0
        res["bandwidth_hz"] = res["frequency_high_hz"] - res["frequency_low_hz"]

    if res["start_time_s"] is not None and res["frequency_low_hz"] is not None:
        res["physical_mapping_status"] = "Complete"
    elif res["start_time_s"] is not None:
        res["physical_mapping_status"] = "Time only"
    elif res["frequency_low_hz"] is not None:
        res["physical_mapping_status"] = "Frequency only"
        
    return res
