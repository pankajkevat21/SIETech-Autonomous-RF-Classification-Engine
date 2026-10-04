import os
import subprocess
import time
import json
import urllib.request
import zipfile

TARGET_ROOT = r"C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\SIEtech_final_version"

def run_cmd(cmd, cwd=TARGET_ROOT):
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    return res

def main():
    report = {}

    print("1. Confirm Docker daemon")
    res = run_cmd(["docker", "info"])
    if res.returncode != 0:
        print("DOCKER DAEMON NOT RUNNING")
        return

    print("3. Build the image synchronously")
    res = run_cmd(["docker", "build", "--progress=plain", "-f", r"docker\Dockerfile", "-t", "rf-shazam-track1:1.0.0", "."])
    if res.returncode != 0:
        report["build_result"] = f"FAILED: {res.stderr}"
        print(json.dumps(report))
        return
    else:
        report["build_result"] = "SUCCESS"

    print("Getting image ID")
    res = run_cmd(["docker", "image", "inspect", "rf-shazam-track1:1.0.0"])
    if res.returncode == 0:
        info = json.loads(res.stdout)[0]
        report["image_id"] = info.get("Id")
    else:
        report["image_id"] = "N/A"

    print("5. Run one genuine sample inference")
    sample_img = os.path.join(TARGET_ROOT, "samples", "functional_validation", "test_synthetic.npy")
    res = run_cmd(["docker", "run", "--rm", "-v", f"{TARGET_ROOT}:/app", "rf-shazam-track1:1.0.0", "python", "run_rf_shazam.py", "--input", sample_img, "--output", "/tmp/out"])
    report["sample_inference"] = "SUCCESS" if res.returncode == 0 else f"FAILED: {res.stderr}"

    print("6. Start the UI container")
    run_cmd(["docker", "run", "-d", "--rm", "--name", "rf_shazam_ui", "-p", "127.0.0.1:8080:8080", "-v", f"{TARGET_ROOT}:/app", "rf-shazam-track1:1.0.0", "python", "app/ui/server.py"])
    
    print("7. Verify /health")
    time.sleep(5) # give server time to start
    health_result = "FAILED"
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=5)
        if req.getcode() == 200: health_result = "SUCCESS"
    except Exception as e:
        health_result = f"FAILED: {e}"
    report["ui_health"] = health_result

    print("9. Test one genuine supported upload")
    # Using curl to simulate upload
    upload_res = run_cmd(["curl", "-X", "POST", "-F", f"file=@{sample_img}", "http://127.0.0.1:8080/infer"])
    report["ui_upload"] = "SUCCESS" if upload_res.returncode == 0 and "html" in upload_res.stdout else f"FAILED: {upload_res.stderr}"

    run_cmd(["docker", "stop", "rf_shazam_ui"])

    print("10. Create or repair launchers")
    with open(os.path.join(TARGET_ROOT, "START_RF_SHAZAM_UI.bat"), "w") as f:
        f.write("@echo off\ndocker run --rm --name rf_shazam_ui -p 127.0.0.1:8080:8080 -v \"%cd%\":/app rf-shazam-track1:1.0.0 python app/ui/server.py\npause\n")
    with open(os.path.join(TARGET_ROOT, "STOP_RF_SHAZAM_UI.bat"), "w") as f:
        f.write("@echo off\ndocker stop rf_shazam_ui\npause\n")
    with open(os.path.join(TARGET_ROOT, "RUN_SAMPLE_DEMO.bat"), "w") as f:
        f.write("@echo off\ndocker run --rm -v \"%cd%\":/app rf-shazam-track1:1.0.0 python run_rf_shazam.py --input samples/functional_validation/test_synthetic.npy --output output/\npause\n")
    with open(os.path.join(TARGET_ROOT, "RUN_RF_SHAZAM_CLI.bat"), "w") as f:
        f.write("@echo off\ndocker run --rm -v \"%cd%\":/app rf-shazam-track1:1.0.0 python run_rf_shazam.py %*\n")

    print("11. Test each launcher once")
    # For testing, we run them with cmd /c and exit to prevent pausing
    report["start_launcher"] = "SUCCESS" if run_cmd(["cmd", "/c", 'START_RF_SHAZAM_UI.bat & exit']).returncode == 0 else "FAILED"
    report["stop_launcher"] = "SUCCESS" if run_cmd(["cmd", "/c", 'STOP_RF_SHAZAM_UI.bat & exit']).returncode == 0 else "FAILED"
    report["demo_launcher"] = "SUCCESS" if run_cmd(["cmd", "/c", 'RUN_SAMPLE_DEMO.bat & exit']).returncode == 0 else "FAILED"
    report["cli_launcher"] = "SUCCESS" if run_cmd(["cmd", "/c", 'RUN_RF_SHAZAM_CLI.bat --help & exit']).returncode == 0 else "FAILED"

    print("12. Create README_FIRST.md")
    with open(os.path.join(TARGET_ROOT, "README_FIRST.md"), "w") as f:
        f.write("# RF Shazam\n1. Double-click START_RF_SHAZAM_UI.bat\n2. Open http://127.0.0.1:8080\n3. Upload a file\n4. Double-click STOP_RF_SHAZAM_UI.bat when done\n")

    print("13. Export Docker TAR")
    tar_path = os.path.join(TARGET_ROOT, "docker", "rf-shazam-track1_1.0.0.tar")
    run_cmd(["docker", "save", "-o", tar_path, "rf-shazam-track1:1.0.0"])
    report["tar_path"] = tar_path if os.path.exists(tar_path) else "FAILED"

    print("14. Create a runnable ZIP")
    zip_path = os.path.join(TARGET_ROOT, "..", "RF_Shazam_Track1_Runnable.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(TARGET_ROOT):
            for file in files:
                fpath = os.path.join(root, file)
                arcname = os.path.relpath(fpath, TARGET_ROOT)
                zipf.write(fpath, arcname)
    report["zip_path"] = zip_path if os.path.exists(zip_path) else "FAILED"
    
    with open("final_report.json", "w") as f:
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    main()
