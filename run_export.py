import os, hashlib, zipfile, subprocess, shutil

def sha256_file(path):
    if not os.path.exists(path): return 'N/A'
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest().upper()

print('=== EXPORTING DOCKER TAR ===')
subprocess.run(['docker', 'save', '-o', r'docker\rf-shazam-track1_1.0.0.tar', 'rf-shazam-track1:1.0.0'])

print('=== CREATING ZIP ===')
zip_path = r'C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\RF_Shazam_Track1_Runnable.zip'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk('.'):
        if '.git' in root or '__pycache__' in root or 'node_modules' in root:
            continue
        for f in files:
            p_file = os.path.join(root, f)
            zf.write(p_file, os.path.relpath(p_file, '.'))

print('=== EXTRACTING ZIP ===')
ext_dir = r'C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\SIEtech_test_extract'
if os.path.exists(ext_dir): shutil.rmtree(ext_dir, ignore_errors=True)
os.makedirs(ext_dir, exist_ok=True)
with zipfile.ZipFile(zip_path, 'r') as zf:
    zf.extractall(ext_dir)

print('=== HASHES ===')
print('Model:', sha256_file('models/best.pt'))
print('Runner:', sha256_file('app/runners/rf_shazam_runner.py'))
print('Policy:', sha256_file('config/final_policy.json'))
print('TAR Size:', os.path.getsize(r'docker\rf-shazam-track1_1.0.0.tar'), 'SHA:', sha256_file(r'docker\rf-shazam-track1_1.0.0.tar'))
print('ZIP Size:', os.path.getsize(zip_path), 'SHA:', sha256_file(zip_path))
