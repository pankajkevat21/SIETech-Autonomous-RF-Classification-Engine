import os, subprocess, hashlib, shutil, zipfile, time, urllib.request

def sha256_file(path):
    if not os.path.exists(path): return 'N/A'
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest().upper()

log_file = r'C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\SIEtech_final_version\evidence\final_validation\docker_dependency_repair_build.log'
build_cmd = 'docker build --no-cache --progress=plain -f docker\Dockerfile -t rf-shazam-track1:1.0.0 .'
with open(log_file, 'w') as f:
    res_build = subprocess.run(build_cmd, shell=True, stdout=f, stderr=subprocess.STDOUT)

build_code = res_build.returncode

img_id = 'N/A'
img_size = 'N/A'
import_res = 'N/A'
sample_res = 'N/A'
ui_health = 'N/A'
launcher_res = 'N/A'
tar_sha = 'N/A'
tar_size = 'N/A'
zip_sha = 'N/A'
zip_size = 'N/A'
status = 'FAILED_AT_BUILD'

if build_code == 0:
    res_img = subprocess.run('docker images rf-shazam-track1:1.0.0 --format "{{.ID}}|{{.Size}}"', shell=True, capture_output=True, text=True)
    if res_img.stdout.strip():
        img_id, img_size = res_img.stdout.strip().split('\n')[0].split('|')
    
    res_import = subprocess.run('docker run --rm rf-shazam-track1:1.0.0 python -c "import cv2, pandas, numpy, torch, ultralytics; print(\'ALL_RUNTIME_IMPORTS_PASS\'); print(cv2.__version__); print(pandas.__version__)"', shell=True, capture_output=True, text=True)
    if res_import.returncode == 0:
        import_res = res_import.stdout.strip().replace('\n', ', ')
        
        # Step 7
        res_sample = subprocess.run('cmd /c RUN_SAMPLE_DEMO.bat < NUL', shell=True, capture_output=True, text=True)
        sample_res = 'SUCCESS' if res_sample.returncode == 0 else 'FAILED'
        
        # UI
        subprocess.Popen('cmd /c START_RF_SHAZAM_UI.bat < NUL', shell=True)
        time.sleep(5)
        try:
            req = urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)
            ui_health = req.getcode()
        except Exception as e:
            ui_health = f'FAILED_{e}'
        
        res_stop = subprocess.run('cmd /c STOP_RF_SHAZAM_UI.bat < NUL', shell=True, capture_output=True, text=True)
        
        if sample_res == 'SUCCESS' and str(ui_health) == '200' and res_stop.returncode == 0:
            launcher_res = 'ALL_PASS'
            
            # Step 8
            tar_path = r'C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\SIEtech_final_version\docker\rf-shazam-track1_1.0.0.tar'
            if os.path.exists(tar_path): os.remove(tar_path)
            subprocess.run(f'docker save -o {tar_path} rf-shazam-track1:1.0.0', shell=True)
            tar_size = os.path.getsize(tar_path)
            tar_sha = sha256_file(tar_path)
            
            zip_dir = r'C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\SIEtech_final_version'
            zip_out = r'C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\RF_Shazam_Track1_Runnable'
            if os.path.exists(zip_out + '.zip'): os.remove(zip_out + '.zip')
            shutil.make_archive(zip_out, 'zip', zip_dir)
            
            zip_file = zip_out + '.zip'
            zip_size = os.path.getsize(zip_file)
            zip_sha = sha256_file(zip_file)
            
            # Extraction Test
            ext_dir = r'C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\EXTRACT_FINAL'
            if os.path.exists(ext_dir): shutil.rmtree(ext_dir)
            os.makedirs(ext_dir)
            with zipfile.ZipFile(zip_file, 'r') as z: z.extractall(ext_dir)
            
            m_h = sha256_file(os.path.join(ext_dir, 'models', 'best.pt'))
            r_h = sha256_file(os.path.join(ext_dir, 'app', 'runners', 'rf_shazam_runner.py'))
            p_h = sha256_file(os.path.join(ext_dir, 'config', 'final_policy.json'))
            
            if m_h == 'B47AB2A7B0131A3FE8CDC650F7D1418D1C2E5974A30DEC42B2835F062E14072A' and r_h == 'ED3183909CF56CC066EB95C2AD7D0FF031B30191CDE9C59EB58355D908ACE1F9':
                subprocess.Popen('cmd /c START_RF_SHAZAM_UI.bat < NUL', shell=True, cwd=ext_dir)
                time.sleep(5)
                try:
                    r2 = urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)
                    if r2.getcode() == 200:
                        status = 'RUNNABLE_PACKAGE_READY'
                except: pass
                subprocess.run('cmd /c STOP_RF_SHAZAM_UI.bat < NUL', shell=True, cwd=ext_dir)
    else:
        import_res = res_import.stderr.strip()

print(f'BUILD_CODE:{build_code}')
print(f'IMG_ID:{img_id}')
print(f'IMG_SIZE:{img_size}')
print(f'IMPORT_RES:{import_res}')
print(f'SAMPLE:{sample_res}')
print(f'UI:{ui_health}')
print(f'LAUNCH:{launcher_res}')
print(f'TAR_SHA:{tar_sha}|{tar_size}')
print(f'ZIP_SHA:{zip_sha}|{zip_size}')
print(f'STATUS:{status}')
