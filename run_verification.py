import os
import subprocess
import time
import urllib.request
import urllib.parse
import json
import shutil
import hashlib

def sha256_file(path):
    if not os.path.exists(path): return 'N/A'
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest().upper()

def run_tests():
    print("Building Docker image...")
    res = subprocess.run(['docker', 'build', '--progress=plain', '-f', 'docker/Dockerfile', '-t', 'rf-shazam-track1:1.0.0', '.'], capture_output=True, text=True, encoding='utf-8', errors='ignore')
    if res.returncode != 0:
        print("Build failed:", res.stderr)
        return False
    print("Build succeeded.")

    print("Starting UI container...")
    container = subprocess.Popen('cmd /c START_RF_SHAZAM_UI.bat < NUL', shell=True, encoding='utf-8', errors='ignore')
    time.sleep(5)

    print("Checking health...")
    try:
        r = urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)
        print("Health code:", r.getcode())
    except Exception as e:
        print("Health check failed:", e)

    # Test Upload (Event Producing)
    print("Testing upload (Update mode)...")
    try:
        import requests
        url = 'http://127.0.0.1:8080/analyze'
        files = {'files': open('samples/functional_validation/test_synthetic.npy', 'rb')}
        data = {'library_mode': 'update', 'top_k': 3}
        resp = requests.post(url, files=files, data=data)
        print("Upload status:", resp.status_code)
        if resp.status_code == 200:
            print("Response successfully rendered.")
        else:
            print("Response failed:", resp.text[:500])
    except Exception as e:
        print("Upload failed:", e)

    print("Stopping UI container...")
    subprocess.run('cmd /c STOP_RF_SHAZAM_UI.bat < NUL', shell=True, encoding='utf-8', errors='ignore')

    print("Done.")

if __name__ == '__main__':
    run_tests()
