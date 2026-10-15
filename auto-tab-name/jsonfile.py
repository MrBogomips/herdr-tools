"""One atomic JSON writer shared by the config and the state file."""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

JSON_INDENT = 2


def write_json_atomic(path: Path, document: Any) -> None:
    """Write `document` as indented JSON, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        try:
            output = os.fdopen(handle, "w", encoding="utf-8")
        except BaseException:
            os.close(handle)  # fdopen did not take ownership of the descriptor
            raise
        with output:
            json.dump(document, output, indent=JSON_INDENT)
            output.write("\n")
        os.replace(temporary, path)
    except BaseException:
        # A failed cleanup must not hide the error that got us here.
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
