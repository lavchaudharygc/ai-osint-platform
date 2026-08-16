"""
Root Launcher for UP Police Cyber Cell OSINT Platform (Beta-v2 SOC)
Delegates execution to Beta-v2/run.py.
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BETA_V2_RUN = BASE_DIR / "Beta-v2" / "run.py"


def main():
    print("=====================================================================")
    print("   UP POLICE CYBER CELL OSINT SOC PLATFORM (Beta-v2 Active)")
    print("=====================================================================")
    print("Notice: Active codebase is located in ./Beta-v2.")
    print("Launching Beta-v2 servers...\n")

    if not BETA_V2_RUN.exists():
        print(f"Error: Could not locate Beta-v2 launcher at {BETA_V2_RUN}")
        sys.exit(1)

    try:
        subprocess.run([sys.executable, str(BETA_V2_RUN)], check=True)
    except KeyboardInterrupt:
        print("\nShutdown complete.")
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
