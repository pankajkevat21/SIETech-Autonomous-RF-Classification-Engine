import subprocess
import sys
import os

print("Running test inside docker container...")

cmd = [
    "docker", "run", "--rm",
    "-v", f"{os.path.abspath('.')}:/workspace",
    "-w", "/workspace",
    "rf-shazam-track1:1.0.0",
    "python", "run_metadata_tests.py"
]

res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stdout)
if res.returncode != 0:
    print(res.stderr)
    sys.exit(1)
else:
    print("Docker test successful.")
