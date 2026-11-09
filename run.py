"""
EcoTrace Main Launcher
Runs the EcoTrace FastAPI Web Server & Profiler Engine.
"""

import uvicorn
import argparse
import sys
import io
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    parser = argparse.ArgumentParser(description="EcoTrace Server Launcher")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload")
    args = parser.parse_args()

    print("=" * 65)
    print("EcoTrace - Granular Cloud Carbon & Energy Footprint Profiler")
    print(f"Serving Web Dashboard & REST API at http://{args.host}:{args.port}")
    print("=" * 65)

    uvicorn.run("ecotrace.api.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
