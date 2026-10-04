@echo off
docker run --rm -v "%cd%":/workspace -w /workspace -v "%cd%\output":/app/output -v "%cd%\data\library":/app/runtime/library rf-shazam-track1:1.0.0 python /app/run_rf_shazam.py %*
