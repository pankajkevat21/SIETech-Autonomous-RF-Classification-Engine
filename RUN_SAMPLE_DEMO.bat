@echo off
docker run --rm -v "%cd%\output":/app/output -v "%cd%\data\library":/app/runtime/library rf-shazam-track1:1.0.0 python run_rf_shazam.py --input samples/functional_validation/test_synthetic.npy --output output/
pause
