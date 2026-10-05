"""Admin commands.

python -m app.cli load-content     Load / refresh frameworks, controls, mappings and policy templates
python -m app.cli check-content    Validate content mapping coverage without touching the database
"""
import sys

from app.db import system_session
from app.services.content import load_content, read_controls, read_frameworks, validate_content


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "load-content":
        with system_session() as db:
            print(load_content(db))
    elif cmd == "check-content":
        validate_content(read_frameworks(), read_controls())
        print("Content OK: every requirement maps to at least one control.")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
