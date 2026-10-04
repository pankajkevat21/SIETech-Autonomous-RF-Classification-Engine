# SIETech — RF Shazam Track-1

Offline RF Spectrum Intelligence System.

Detects and classifies Drone, WiFi, and Bluetooth signals from spectrogram images using a YOLO-based detector.

## Features

- Multi-format input: PNG, JPG/JPEG, NPY, NPZ
- 3-class detection: Drone_Signal, WiFi, Bluetooth
- Optional JSON metadata sidecar for physical coordinate mapping
- SQLite-backed signature retrieval library
- Flask-based offline UI + CLI
- SHA256 integrity verification
- Fully offline / air-gapped operation
- Docker containerized

## Quick Start

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

    # CLI
    python3 run_rf_shazam.py --input samples/ --output output/ --recursive

    # UI
    python3 run_rf_shazam.py --ui --host 127.0.0.1 --port 5000

## Safety Scope

Passive RF/ESM analysis only. No transmission, jamming, or illegal interception.

## Version

v1.0.0# SIETech — RF Shazam Track-1

**Offline RF Spectrum Intelligence System**

Detects and classifies **Drone, WiFi, and Bluetooth** signals from spectrogram images using a YOLO-based detector.

## Features

- Multi-format input: PNG, JPG/JPEG, NPY, NPZ
- 3-class detection: Drone_Signal, WiFi, Bluetooth
- Optional JSON metadata sidecar for physical coordinate mapping
- SQLite-backed signature retrieval library (Read / Update / Off)
- Flask-based offline operator UI + CLI
- SHA256 integrity verification (model, runner, policy)
- Fully offline / air-gapped operation
- Docker containerized

## Quick Start

```bash
git clone https://github.com/pankajkevat21/SIETech-Autonomous-RF-Classification-Engine.git
cd SIETech-Autonomous-RF-Classification-Engine

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

# CLI
python3 run_rf_shazam.py --input samples/ --output output/ --recursive

# UI
python3 run_rf_shazam.py --ui --host 127.0.0.1 --port 5000
# Open http://127.0.0.1:5000
