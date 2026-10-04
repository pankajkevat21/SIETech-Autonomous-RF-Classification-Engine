# SIETech — RF Shazam Track-1

**Offline RF Spectrum Intelligence System**

![Python](https://img.shields.io/badge/Python-3.11-blue)
![PyTorch](https://img.shields.io/badge/PyTorch-2.x-red)
![Flask](https://img.shields.io/badge/Flask-3.1.3-green)
![Docker](https://img.shields.io/badge/Docker-verified-blue)

An offline, air-gapped RF spectrum intelligence system that detects and classifies **Drone, WiFi, and Bluetooth** signals from spectrogram images using a YOLO-based detector/classifier.

## Overview

**RF Shazam Track-1** is a passive RF/ESM spectrum intelligence prototype:

1. Detects RF events using a YOLO detector/classifier (models/best.pt)
2. Optionally enriches detections with physical coordinates (time, frequency, bandwidth) from JSON metadata sidecars
3. Matches detections against a SQLite-backed signature library (top-K retrieval with uncertainty scoring)
4. Emits structured JSON, CSV, and ZIP outputs — fully offline

### Supported Classes

| Class ID | Label              |
|----------|--------------------|
| 0        | Drone_Signal       |
| 1        | WiFi               |
| 2        | Bluetooth          |
| —        | Background_No_Event |

## Features

- Multi-format input: PNG, JPG/JPEG, NPY, NPZ
- YOLO-based detection: confidence 0.6, NMS IoU 0.5, imgsz 640
- Physical coordinate mapping: pixel bbox to time (s), frequency (Hz), bandwidth (Hz)
- Signature retrieval library: SQLite-backed, modes read / update / off
- Top-K matching with uncertainty scoring
- Dual interface: CLI + Flask-based offline operator UI
- SHA256 integrity verification for model, runner, and policy
- Fully offline / air-gapped operation
- Docker containerized (verified build, CPU-only PyTorch)
- Cross-platform: Linux, macOS, Windows

## Architecture


## Quick Start

### 1. Clone

    git clone https://github.com/pankajkevat21/SIETech-Autonomous-RF-Classification-Engine.git
    cd SIETech-Autonomous-RF-Classification-Engine

### 2. Virtual Environment

    python3 -m venv venv
    source venv/bin/activate          # macOS / Linux
    # venv\Scripts\activate           # Windows

### 3. Install Dependencies

    pip install --upgrade pip
    pip install -r requirements.txt

### 4. Run CLI

    mkdir -p output
    python3 run_rf_shazam.py --input samples/functional_validation/test_synthetic.npy --output output/ --disable-retrieval

### 5. Run Web UI

    python3 run_rf_shazam.py --ui --host 127.0.0.1 --port 5000

Open http://127.0.0.1:5000 in your browser.

## Docker (Verified)

Tested on macOS (Apple Silicon) with Docker Desktop.

### Build

    docker build --platform linux/amd64 -f docker/Dockerfile -t rf-shazam-track1:2.0.0 .

### Run CLI

    docker run --rm --platform linux/amd64 -v "$PWD:/app" -w /app rf-shazam-track1:2.0.0 python run_rf_shazam.py --input samples/functional_validation/test_synthetic.npy --output output/ --disable-retrieval

### Run Web UI

    docker run --rm -it --platform linux/amd64 -p 5001:5000 -v "$PWD:/app" -w /app rf-shazam-track1:2.0.0 python run_rf_shazam.py --ui --host 0.0.0.0 --port 5000

Open http://127.0.0.1:5001 in your browser.

**Note:** On macOS, port 5000 may be taken by the AirPlay Receiver. Use 5001 instead.

### Save / Load Image

    # Save
    docker save -o rf-shazam-track1_2.0.0.tar rf-shazam-track1:2.0.0

    # Load on another machine
    docker load -i rf-shazam-track1_2.0.0.tar

## CLI Usage

| Option                  | Description                                     | Default                    |
|-------------------------|-------------------------------------------------|----------------------------|
| --input PATH            | Input file or directory (CLI mode)              | —                          |
| --output PATH           | Output directory (CLI mode)                     | —                          |
| --metadata PATH         | Explicit JSON metadata sidecar path             | auto-detect                |
| --device DEVICE         | auto / cpu / cuda                               | auto                       |
| --recursive             | Recurse into subdirectories                     | off                        |
| --overwrite             | Overwrite existing outputs                      | off                        |
| --save-visualizations   | Save annotated images                           | off                        |
| --disable-retrieval     | Skip signature library retrieval                | off                        |
| --config PATH           | Path to policy config                           | config/final_policy.json   |
| --version               | Print version and exit                          | —                          |
| --ui                    | Launch local web UI                             | off                        |
| --host HOST             | UI host binding                                 | 127.0.0.1                  |
| --port PORT             | UI port                                         | 8080                       |
| --library-mode MODE     | read / update / off                             | update                     |
| --top-k K               | Number of top matches to retrieve               | 3                          |

## Web UI

| Endpoint             | Method | Description                          |
|----------------------|--------|--------------------------------------|
| /                    | GET    | Operator UI                          |
| /analyze             | POST   | Process uploaded files               |
| /download/<path>     | GET    | Download result artifacts            |
| /health              | GET    | Health check (model/library status)  |
| /version             | GET    | Version + config hashes              |

## Input / Output Schema

### Inputs

| Format      | Accepted         | Notes                                       |
|-------------|------------------|---------------------------------------------|
| Images      | PNG, JPG / JPEG  | Auto-resized to 640x640                     |
| Arrays      | NPY, NPZ         | 2D spectrogram arrays                       |
| Metadata    | JSON (same stem) | Optional canonical metadata sidecar         |
| Bundle      | ZIP              | Multiple inputs + sidecars                  |

### Outputs (per run)

| File                            | Description                                  |
|---------------------------------|----------------------------------------------|
| final_output.json               | Structured per-input records with events     |
| event_log.json                  | Raw YOLO detections                          |
| events.csv                      | Tabular event summary                        |
| processed_input_manifest.csv    | Per-input file hashes + dimensions           |
| run_summary.json                | Run metadata, model/policy hashes, timings   |
| signature_library.json          | Library state after retrieval                |
| results_<req_id>.zip            | Bundle of artifacts (UI mode)                |

## Configuration

config/final_policy.json controls the runtime policy:

    {
      "model": {
        "weights_path": "models/best.pt",
        "confidence_threshold": 0.6,
        "nms_iou": 0.5,
        "imgsz": 640
      },
      "classes": {
        "0": "Drone_Signal",
        "1": "WiFi",
        "2": "Bluetooth"
      }
    }

## Integrity Verification

Every inference run records SHA256 hashes of:

| Artifact                    | Purpose          |
|-----------------------------|------------------|
| models/best.pt              | Model weights    |
| rf_shazam_runner.py         | Inference runner |
| config/final_policy.json    | Runtime policy   |

Hashes are embedded in final_output.json and exposed via /version on the UI.

## Testing

    pytest tests/ -v

The suite covers CLI contract, input edge cases (missing, unsupported, malformed, NaN/Inf, ambiguous NPZ), valid inputs, JSON schema validation, SQLite operations, UI endpoints, and integrity hashes.

## Documentation

| Document                                | Description                    |
|-----------------------------------------|--------------------------------|
| docs/TECHNICAL_BRIEF.md                 | System architecture and design |
| docs/INPUT_OUTPUT_SCHEMA.md             | Full I/O contract              |
| docs/LIMITATIONS.md                     | Known limitations              |
| docs/README_FIRST.md                    | Quick-start guide              |
| docs/STANDARDIZED_TEST_COMMAND.md       | Test procedure                 |

## Safety Scope

This project performs **passive RF/ESM analysis only**.

- No transmission
- No jamming
- No illegal interception
- Offline processing of provided spectrograms

## Limitations

- Prototype / research build — not production-hardened
- CPU-only inference by default
- No real-time streaming (batch / file-based)
- Model trained on a limited class set (3 classes)
- Metadata sidecar is optional; physical mapping requires it
