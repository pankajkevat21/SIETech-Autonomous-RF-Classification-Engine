# RF Shazam Dockerfile
# Passive RF Spectrum Intelligence Prototype

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

# System libraries needed by opencv-python-headless + ultralytics
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY docker/requirements_runtime.txt /tmp/requirements_runtime.txt

RUN python -m pip install --no-cache-dir --upgrade pip

RUN python -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements_runtime.txt

# Patch ultralytics for headless OpenCV (no GUI)
RUN sed -i 's/^_imshow = cv2\.imshow.*/_imshow = lambda *args, **kwargs: None/' /usr/local/lib/python3.11/site-packages/ultralytics/utils/patches.py

# Verify imports
RUN python -c "import cv2, pandas, numpy, torch, ultralytics; print('cv2', cv2.__version__); print('torch', torch.__version__); print('ultralytics', ultralytics.__version__)"

COPY . /app

CMD ["python", "rf_shazam_runner.py", "--input", "/input", "--output", "/output", "--config", "config/final_policy.json"]
