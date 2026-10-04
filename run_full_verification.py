import urllib.request, time, subprocess, json, os, shutil, hashlib

def sha256_file(path):
    if not os.path.exists(path): return 'N/A'
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest().upper()

def test_upload(mode, filename, expected_events=None):
    import requests
    url = 'http://127.0.0.1:8080/analyze'
    files = {'files': open(f'samples/functional_validation/{filename}', 'rb')}
    data = {'library_mode': mode, 'top_k': 3}
    resp = requests.post(url, files=files, data=data)
    print(f"[{mode.upper()} MODE] Upload {filename}: {resp.status_code}")
    if resp.status_code == 200:
        html = resp.text
        if "Analysis Results" in html:
            print("   -> HTML Rendered Successfully")
        else:
            print("   -> Missing Expected HTML Header")
        
        # very simple grep of the html for logging
        for line in html.split('\n'):
            if "Run ID:" in line: print("   ->", line.strip().replace('<p>', '').replace('</p>', ''))
            if "Total Accepted Events:" in line: print("   ->", line.strip().replace('<p>', '').replace('</p>', ''))
            if "Library Mode:" in line: print("   ->", line.strip().replace('<p>', '').replace('</p>', ''))
            if "Database Modified" in line and "<td>Yes</td>" in line: print("   -> DB Modified: Yes")
    else:
        print("   -> Error:", resp.text[:200])

print('=== STARTING CONTAINER ===')
subprocess.run('docker rm -f rf_shazam_ui', shell=True, stderr=subprocess.DEVNULL)
p = subprocess.Popen('cmd /c START_RF_SHAZAM_UI.bat < NUL', shell=True)
time.sleep(6)

print('=== CHECKING HEALTH ===')
try:
    req = urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)
    print('Health:', req.getcode())
except Exception as e:
    print('Health failed:', e)

print('=== TESTING OFF MODE ===')
test_upload('off', 'test_synthetic.npy')

print('=== TESTING UPDATE MODE ===')
test_upload('update', 'test_synthetic.npy')

print('=== TESTING READ MODE (BACKGROUND) ===')
test_upload('read', 'test_synthetic.npy')

print('=== STOPPING CONTAINER ===')
subprocess.run('cmd /c STOP_RF_SHAZAM_UI.bat < NUL', shell=True)

print('=== TESTING PERSISTENCE ===')
p = subprocess.Popen('cmd /c START_RF_SHAZAM_UI.bat < NUL', shell=True)
time.sleep(6)
test_upload('read', 'test_synthetic.npy')
subprocess.run('cmd /c STOP_RF_SHAZAM_UI.bat < NUL', shell=True)

print('=== EXPORTING DOCKER TAR ===')
subprocess.run(['docker', 'save', '-o', r'docker\rf-shazam-track1_1.0.0.tar', 'rf-shazam-track1:1.0.0'])

print('=== CREATING ZIP ===')
import zipfile
zip_path = r'C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\RF_Shazam_Track1_Runnable.zip'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk('.'):
        if '.git' in root or '__pycache__' in root or 'node_modules' in root:
            continue
        for f in files:
            p_file = os.path.join(root, f)
            zf.write(p_file, os.path.relpath(p_file, '.'))

print('=== TEST EXTRACT ===')
ext_dir = r'C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\SIEtech_test_extract'
if os.path.exists(ext_dir): shutil.rmtree(ext_dir, ignore_errors=True)
os.makedirs(ext_dir, exist_ok=True)
with zipfile.ZipFile(zip_path, 'r') as zf:
    zf.extractall(ext_dir)

print('=== VERIFYING EXTRACTED RUN ===')
p_ext = subprocess.Popen('cmd /c START_RF_SHAZAM_UI.bat < NUL', shell=True, cwd=ext_dir)
time.sleep(6)
try:
    req = urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)
    print('Extracted Health:', req.getcode())
except Exception as e:
    print('Extracted Health failed:', e)
subprocess.run('cmd /c STOP_RF_SHAZAM_UI.bat < NUL', shell=True, cwd=ext_dir)

print('=== HASHES ===')
print('Model:', sha256_file('models/best.pt'))
print('Runner:', sha256_file('app/runners/rf_shazam_runner.py'))
print('Policy:', sha256_file('config/final_policy.json'))
print('TAR Size:', os.path.getsize(r'docker\rf-shazam-track1_1.0.0.tar'), 'SHA:', sha256_file(r'docker\rf-shazam-track1_1.0.0.tar'))
print('ZIP Size:', os.path.getsize(zip_path), 'SHA:', sha256_file(zip_path))
