import os
import sys
import tempfile
from pathlib import Path

TMP = Path(
    tempfile.mkdtemp(
        prefix="infographic-tests-"
    )
)

os.environ.setdefault(
    "PROJECTS_DIR",
    str(
        TMP
        / "projects"
    )
)

os.environ.setdefault(
    "OUTPUT_DIR",
    str(
        TMP
        / "output"
    )
)

os.environ.setdefault(
    "TASKS_DIR",
    str(
        TMP
        / "tasks"
    )
)

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / "app"
    )
)
