"""PyInstaller entry point for the Pett Agent runner binary. This file is used to create the agent_runner_bin binary."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the project root is importable when PyInstaller runs the stub. This is necessary because the run.py file is not in the same directory as the pyinstaller/agent_runner_entry.py file.
PROJ_ROOT = Path(__file__).resolve().parent.parent
if str(PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJ_ROOT))

from run import get_version, main as run_main, parse_args  # noqa: E402


def _print_version() -> None:
    """Print the version string."""
    print(f"Pett Agent Runner {get_version()}")


def main() -> None:
    """Entrypoint used by PyInstaller."""
    args = parse_args()
    if args.version:
        _print_version()
        return

    try:
        asyncio.run(run_main(password=args.password))
    except KeyboardInterrupt:
        print("\n🛑 Agent stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
