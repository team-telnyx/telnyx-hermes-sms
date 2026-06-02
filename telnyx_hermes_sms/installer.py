from __future__ import annotations

import argparse
import importlib.resources as resources
from pathlib import Path
from typing import Sequence

PLUGIN_DIRNAME = "telnyx_sms"
DEFAULT_TARGET_DIR = Path.home() / ".hermes" / "plugins" / PLUGIN_DIRNAME
INIT_FILE = '''"""Telnyx SMS platform plugin entry point for Hermes Agent."""

def register(ctx):
    try:
        from .adapter import register as _register
    except ImportError:  # pragma: no cover - supports direct file/plugin loading
        from adapter import register as _register

    return _register(ctx)

__all__ = ["register"]
'''


def _package_file(name: str) -> str:
    return resources.files("telnyx_hermes_sms").joinpath(name).read_text()


def _adapter_source() -> str:
    adapter_path = Path(__file__).resolve().parents[1] / "adapter.py"
    if not adapter_path.exists():
        raise RuntimeError(f"Could not locate installed adapter.py source at {adapter_path}")
    return Path(adapter_path).read_text()


def install_plugin(target_dir: Path, *, force: bool = False) -> list[Path]:
    plugin_dir = Path(target_dir).expanduser().resolve()
    plugin_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "__init__.py": INIT_FILE,
        "adapter.py": _adapter_source(),
        "plugin.yaml": _package_file("plugin.yaml"),
        ".env.example": _package_file(".env.example"),
    }

    written: list[Path] = []
    for name, content in paths.items():
        destination = plugin_dir / name
        if destination.exists() and not force:
            raise FileExistsError(
                f"{destination} already exists. Re-run with --force to overwrite it."
            )
        destination.write_text(content)
        written.append(destination)

    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install the Telnyx Hermes SMS plugin into a Hermes plugins directory."
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=DEFAULT_TARGET_DIR,
        help=f"Plugin directory to populate (default: {DEFAULT_TARGET_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing plugin files in the target directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    written = install_plugin(args.target_dir, force=args.force)
    print(f"Installed Telnyx Hermes SMS plugin to {args.target_dir}")
    for path in written:
        print(f" - {path.name}")
    print("Next steps:")
    print(" - run: hermes plugins enable telnyx-sms-platform")
    print(" - append .env.example entries into ~/.hermes/.env and fill in Telnyx values")
    print(" - set gateway.platforms.telnyx_sms.enabled: true in ~/.hermes/config.yaml")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
