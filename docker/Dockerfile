# RF Shazam Dockerfile
# Passive RF Spectrum Intelligence Prototype

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY docker/requirements_runtime.txt /tmp/requirements_runtime.txt

RUN python -m pip install --no-cache-dir --upgrade pip

RUN python -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements_runtime.txt

RUN python -m pip uninstall -y opencv-python opencv-contrib-python || true

RUN python -m pip install --no-cache-dir --no-deps opencv-python-headless==4.10.0.84

RUN python -c "import cv2, pandas, numpy, torch, ultralytics; print('cv2', cv2.__version__); print('pandas', pandas.__version__); print('numpy', numpy.__version__); print('torch', torch.__version__); print('ultralytics', ultralytics.__version__)"

COPY . /app

CMD ["python", "rf_shazam_runner.py", "--input", "/input", "--output", "/output", "--config", "config/final_policy.json"]
