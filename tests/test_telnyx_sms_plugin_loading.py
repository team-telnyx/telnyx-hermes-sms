import importlib.util
import sys
import types
from pathlib import Path


def test_directory_plugin_entrypoint_registers_platform(monkeypatch):
    """Mirror Hermes loading __init__.py from a directory plugin."""
    root = Path(__file__).resolve().parents[1]
    module_name = 'telnyx_sms_plugin_under_test'
    spec = importlib.util.spec_from_file_location(
        module_name,
        root / '__init__.py',
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    fake_adapter = types.ModuleType(f'{module_name}.adapter')
    fake_adapter.register = lambda ctx: ctx.register_platform(name='telnyx_sms', label='Telnyx SMS')
    sys.modules[f'{module_name}.adapter'] = fake_adapter
    assert spec.loader is not None
    spec.loader.exec_module(module)

    calls = []

    class Ctx:
        def register_platform(self, **kwargs):
            calls.append(kwargs)

    module.register(Ctx())
    assert calls
    assert calls[0]['name'] == 'telnyx_sms'
    assert calls[0]['label'] == 'Telnyx SMS'
