@echo off
docker run --rm --name rf_shazam_ui -p 127.0.0.1:8080:8080 -v "%cd%\output":/app/output -v "%cd%\data\library":/app/runtime/library rf-shazam-track1:1.0.0 python run_rf_shazam.py --ui --host 0.0.0.0
pause
