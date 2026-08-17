"""Generate the System Prompt deliverable PDF into docs/.

Usage:
    .venv/bin/python scripts/generate_system_prompt_pdf.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.api.docs import _build_pdf_bytes

OUT = Path(__file__).resolve().parent.parent / "docs" / "WOW_AI_Voice_Agent_System_Prompt.pdf"


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(_build_pdf_bytes())
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.1f} KiB)")


if __name__ == "__main__":
    main()