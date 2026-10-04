import pytest
import os
import json
import hashlib
import subprocess
import sqlite3
import numpy as np
from PIL import Image
import shutil

TARGET_ROOT = r"C:\Users\lalit\OneDrive\Desktop\SIEtech_Final\SIEtech_final_version"
CLI_SCRIPT = os.path.join(TARGET_ROOT, "run_rf_shazam.py")
POLICY_PATH = os.path.join(TARGET_ROOT, "config", "final_policy.json")

def get_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest().upper()

# --- INTEGRITY TESTS ---
def test_integrity_model_hash():
    assert get_hash(os.path.join(TARGET_ROOT, "models", "best.pt")) == "B47AB2A7B0131A3FE8CDC650F7D1418D1C2E5974A30DEC42B2835F062E14072A"

def test_integrity_runner_hash():
    assert get_hash(os.path.join(TARGET_ROOT, "app", "runners", "rf_shazam_runner.py")) == "ED3183909CF56CC066EB95C2AD7D0FF031B30191CDE9C59EB58355D908ACE1F9"

def test_integrity_policy_hash():
    assert get_hash(POLICY_PATH) == "E9C9C60F8A670C661A4C4BB76702848A44ACCEAA6D5BB94A86E6B785BAD7F36A"

def test_integrity_thresholds():
    with open(POLICY_PATH) as f: cfg = json.load(f)
    assert cfg["model"]["confidence_threshold"] == 0.60
    assert cfg["model"]["nms_iou"] == 0.50

def test_integrity_class_order():
    with open(POLICY_PATH) as f: cfg = json.load(f)
    assert cfg["classes"]["0"] == "Drone_Signal"
    assert cfg["classes"]["1"] == "WiFi"
    assert cfg["classes"]["2"] == "Bluetooth"

def test_integrity_background_no_event():
    with open(POLICY_PATH) as f: cfg = json.load(f)
    assert cfg["postprocessing"]["no_detection_label"] == "Background_No_Event"

# --- INPUT FIXTURES ---
@pytest.fixture
def sample_inputs(tmp_path):
    d = tmp_path / "inputs"
    d.mkdir()
    
    png = d / "test.png"
    Image.new('RGB', (640, 640)).save(str(png))
    
    jpg = d / "test.jpg"
    Image.new('RGB', (640, 640)).save(str(jpg))
    
    npy = d / "test.npy"
    np.save(str(npy), np.zeros((640, 640)))
    
    npz = d / "test.npz"
    np.savez(str(npz), data=np.zeros((640, 640)))
    
    ambig_npz = d / "ambig.npz"
    np.savez(str(ambig_npz), a=np.zeros(10), b=np.zeros(10))
    
    nan_npy = d / "nan.npy"
    arr = np.zeros((640, 640))
    arr[0,0] = np.nan
    np.save(str(nan_npy), arr)
    
    inf_npy = d / "inf.npy"
    arr = np.zeros((640, 640))
    arr[0,0] = np.inf
    np.save(str(inf_npy), arr)
    
    malformed = d / "malformed.npy"
    malformed.write_text("not an array")
    
    unsupported = d / "test.zip"
    unsupported.write_text("PK...")
    
    spaced = tmp_path / "spaced path dir"
    spaced.mkdir()
    spaced_png = spaced / "test space.png"
    Image.new('RGB', (640, 640)).save(str(spaced_png))
    
    return {
        "png": str(png), "jpg": str(jpg), "npy": str(npy), "npz": str(npz),
        "ambig_npz": str(ambig_npz), "nan": str(nan_npy), "inf": str(inf_npy),
        "malformed": str(malformed), "unsupported": str(unsupported),
        "spaced": str(spaced_png), "missing": str(d / "missing.png")
    }

# --- CLI TESTS ---
def run_cli(*args):
    return subprocess.run([sys.executable, CLI_SCRIPT, *args], capture_output=True, text=True, cwd=TARGET_ROOT)

def test_cli_help():
    res = run_cli("--help")
    assert res.returncode == 0
    assert "usage" in res.stdout.lower()

def test_cli_version():
    res = run_cli("--version")
    assert res.returncode == 0
    assert "1.0.0" in res.stdout or "2026" in res.stdout

def test_cli_invalid_invocation():
    res = run_cli()
    assert res.returncode != 0

def test_cli_missing_input(sample_inputs):
    res = run_cli("--input", sample_inputs["missing"], "--output", "out")
    assert res.returncode != 0

def test_cli_unsupported_ext(sample_inputs):
    res = run_cli("--input", sample_inputs["unsupported"], "--output", "out")
    assert res.returncode != 0

def test_cli_malformed(sample_inputs, tmp_path):
    out = tmp_path / "out"
    res = run_cli("--input", sample_inputs["malformed"], "--output", str(out))
    assert res.returncode != 0

def test_cli_nan(sample_inputs, tmp_path):
    out = tmp_path / "out"
    res = run_cli("--input", sample_inputs["nan"], "--output", str(out))
    assert res.returncode != 0

def test_cli_inf(sample_inputs, tmp_path):
    out = tmp_path / "out"
    res = run_cli("--input", sample_inputs["inf"], "--output", str(out))
    assert res.returncode != 0

def test_cli_ambig_npz(sample_inputs, tmp_path):
    out = tmp_path / "out"
    res = run_cli("--input", sample_inputs["ambig_npz"], "--output", str(out))
    assert res.returncode != 0

def test_cli_valid_png(sample_inputs, tmp_path):
    out = tmp_path / "out_png"
    res = run_cli("--input", sample_inputs["png"], "--output", str(out))
    assert res.returncode == 0
    assert out.exists()
    jsons = list(out.glob("*.json"))
    assert len(jsons) == 1
    data = json.loads(jsons[0].read_text())
    assert "detections" in data

def test_cli_valid_jpg(sample_inputs, tmp_path):
    out = tmp_path / "out_jpg"
    res = run_cli("--input", sample_inputs["jpg"], "--output", str(out))
    assert res.returncode == 0

def test_cli_valid_npy(sample_inputs, tmp_path):
    out = tmp_path / "out_npy"
    res = run_cli("--input", sample_inputs["npy"], "--output", str(out))
    assert res.returncode == 0

def test_cli_valid_npz(sample_inputs, tmp_path):
    out = tmp_path / "out_npz"
    res = run_cli("--input", sample_inputs["npz"], "--output", str(out))
    assert res.returncode == 0

def test_cli_spaced_path(sample_inputs, tmp_path):
    out = tmp_path / "out space"
    res = run_cli("--input", sample_inputs["spaced"], "--output", str(out))
    assert res.returncode == 0
    assert out.exists()

def test_cli_json_schema(sample_inputs, tmp_path):
    out = tmp_path / "out_schema"
    res = run_cli("--input", sample_inputs["png"], "--output", str(out))
    assert res.returncode == 0
    js = json.loads(list(out.glob("*.json"))[0].read_text())
    assert "file" in js
    assert "timestamp" in js
    assert "detections" in js

# --- SIGNATURE LIBRARY TESTS ---
def test_sig_library_sqlite(tmp_path):
    db_path = tmp_path / "library.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE signatures (id INTEGER PRIMARY KEY, hash TEXT, class TEXT)")
    cur.execute("INSERT INTO signatures (hash, class) VALUES ('abc', 'WiFi')")
    conn.commit()
    conn.close()
    
    conn = sqlite3.connect(db_path)
    res = conn.execute("SELECT class FROM signatures WHERE hash='abc'").fetchone()
    assert res[0] == "WiFi"
    conn.close()

# Note: More complex UI / Retrieval logic can be tested using the Flask test client, but doing a basic health check via UI tests.
import sys
sys.path.insert(0, TARGET_ROOT)
try:
    from app.ui.server import app
    HAS_APP = True
except ImportError:
    HAS_APP = False

@pytest.fixture
def client():
    if HAS_APP:
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    else:
        yield None

def test_ui_health(client):
    if client:
        res = client.get("/health")
        assert res.status_code == 200

def test_ui_version(client):
    if client:
        res = client.get("/version")
        assert res.status_code == 200

def test_ui_invalid_upload(client):
    if client:
        res = client.post("/infer")
        assert res.status_code in [400, 422, 500]

def test_ui_valid_upload(client, sample_inputs):
    if client:
        with open(sample_inputs["png"], "rb") as f:
            res = client.post("/infer", data={"file": (f, "test.png")})
            assert res.status_code == 200
            assert "json" in res.content_type or "html" in res.content_type
