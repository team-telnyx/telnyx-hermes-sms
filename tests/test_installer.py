from pathlib import Path

import pytest

from telnyx_hermes_sms import installer


def test_install_plugin_writes_expected_files(tmp_path):
    written = installer.install_plugin(tmp_path)

    assert [path.name for path in written] == [
        "__init__.py",
        "adapter.py",
        "plugin.yaml",
        ".env.example",
    ]
    assert (tmp_path / "__init__.py").read_text() == installer.INIT_FILE
    assert (tmp_path / "adapter.py").read_text() == (Path(__file__).resolve().parents[1] / "adapter.py").read_text()
    assert "name: telnyx-sms-platform" in (tmp_path / "plugin.yaml").read_text()
    assert "TELNYX_API_KEY" in (tmp_path / ".env.example").read_text()


def test_install_plugin_requires_force_for_existing_files(tmp_path):
    installer.install_plugin(tmp_path)

    with pytest.raises(FileExistsError):
        installer.install_plugin(tmp_path)


def test_install_plugin_force_overwrites_existing_files(tmp_path):
    installer.install_plugin(tmp_path)
    init_path = tmp_path / "__init__.py"
    init_path.write_text("stale")

    installer.install_plugin(tmp_path, force=True)

    assert init_path.read_text() == installer.INIT_FILE
