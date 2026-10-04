import os
import json
import shutil
import subprocess
import hashlib

TEST_DIR = "test_metadata_fixtures"
OUT_DIR = "test_metadata_output"

def setup():
    shutil.rmtree(TEST_DIR, ignore_errors=True)
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(TEST_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    base_npy = "samples/functional_validation/test_synthetic.npy"
    if not os.path.exists(base_npy):
        print(f"Error: Base test file {base_npy} not found")
        return False
        
    # 1. Valid NPY + JSON
    shutil.copy(base_npy, os.path.join(TEST_DIR, "capture_001.npy"))
    with open(os.path.join(TEST_DIR, "capture_001.json"), "w") as f:
        json.dump({"sample_rate_hz": 1e6, "center_frequency_hz": 2.4e9, "time_start_s": 0.0, "time_step_s": 1e-4}, f)

    # 3. NPY without JSON
    shutil.copy(base_npy, os.path.join(TEST_DIR, "capture_003.npy"))
    
    # 4. Valid JSON incomplete
    shutil.copy(base_npy, os.path.join(TEST_DIR, "capture_004.npy"))
    with open(os.path.join(TEST_DIR, "capture_004.json"), "w") as f:
        json.dump({"center_frequency_hz": 2.4e9}, f) # Missing BW or Sample rate
        
    # 5. Malformed JSON
    shutil.copy(base_npy, os.path.join(TEST_DIR, "capture_005.npy"))
    with open(os.path.join(TEST_DIR, "capture_005.json"), "w") as f:
        f.write("{ invalid json")

    # 6. Mismatch
    shutil.copy(base_npy, os.path.join(TEST_DIR, "capture_006.npy"))
    with open(os.path.join(TEST_DIR, "capture_007.json"), "w") as f: # Mismatch!
        json.dump({"sample_rate_hz": 1e6}, f)

    # 7. Invalid negative sample rate
    shutil.copy(base_npy, os.path.join(TEST_DIR, "capture_008.npy"))
    with open(os.path.join(TEST_DIR, "capture_008.json"), "w") as f:
        json.dump({"sample_rate_hz": -1e6, "center_frequency_hz": 2.4e9}, f)

    # 8. Overlap > FFT size
    shutil.copy(base_npy, os.path.join(TEST_DIR, "capture_009.npy"))
    with open(os.path.join(TEST_DIR, "capture_009.json"), "w") as f:
        json.dump({"fft_size": 1024, "overlap_samples": 1024}, f)
        
    return True

def run_tests():
    print("Running batch CLI inference...")
    res = subprocess.run([
        "python", "run_rf_shazam.py",
        "--input", TEST_DIR,
        "--output", OUT_DIR
    ], capture_output=True, text=True)
    
    if res.returncode != 0:
        print("CLI Failed:")
        print(res.stderr)
        return False
        
    with open(os.path.join(OUT_DIR, "final_output.json"), "r") as f:
        results = json.load(f)
        
    print(f"Processed {len(results)} files.")
    
    # Basic Checks
    for r in results:
        src = r["source_path"]
        status = r["metadata_status"]
        if "001" in src:
            assert status == "Metadata loaded", f"Expected loaded, got {status}"
            for evt in r.get("events", []):
                assert evt["physical_mapping_status"] == "Complete"
                assert evt["time_start"] >= 0.0
                assert evt["center_frequency"] == 2.4e9
        if "003" in src:
            assert status == "Metadata not supplied"
            for evt in r.get("events", []):
                assert evt["physical_mapping_status"] == "Unavailable"
        if "004" in src:
            print(f"DEBUG 004 status: {status}")
            assert status == "Metadata incomplete"
            for evt in r.get("events", []):
                assert evt["physical_mapping_status"] == "Frequency only"
        if "005" in src:
            assert status == "Metadata invalid"
        if "006" in src:
            assert status == "Metadata not supplied"
        if "008" in src:
            assert status == "Metadata invalid"
        if "009" in src:
            assert status == "Metadata invalid"
            
    print("All basic JSON metadata test statuses validated successfully.")
    
    # Check hashes
    h1 = hashlib.sha256(open("models/best.pt", "rb").read()).hexdigest().upper()
    h2 = hashlib.sha256(open("app/runners/rf_shazam_runner.py", "rb").read()).hexdigest().upper()
    h3 = hashlib.sha256(open("config/final_policy.json", "rb").read()).hexdigest().upper()
    print("Models hash:", h1)
    print("Runner hash:", h2)
    print("Policy hash:", h3)
    
    return True

if __name__ == "__main__":
    setup()
    run_tests()
