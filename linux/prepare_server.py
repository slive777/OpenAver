import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import mutate_config  # noqa: E402
from core.data_layout import bootstrap_data_layout  # noqa: E402


def _enable_server_mode(cfg):
    cfg.setdefault("general", {})["server_mode"] = True


def main():
    try:
        bootstrap_data_layout()
        mutate_config(_enable_server_mode)
    except Exception as exc:
        sys.stderr.write(f"prepare_server: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
