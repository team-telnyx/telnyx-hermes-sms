import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_manifest_is_platform():
    manifest = yaml.safe_load((ROOT / 'plugin.yaml').read_text())
    assert manifest['name'] == 'telnyx-sms-platform'
    assert manifest['label'] == 'Telnyx SMS'
    assert manifest['kind'] == 'platform'
    required = {item['name'] for item in manifest['requires_env']}
    assert {'TELNYX_API_KEY', 'TELNYX_SMS_FROM_NUMBER'} <= required
    optional = {item['name'] for item in manifest['optional_env']}
    assert 'TELNYX_SMS_ALLOWED_USERS' in optional
    assert 'TELNYX_SMS_HOME_CHANNEL' in optional


def test_register_platform_shape():
    tree = ast.parse((ROOT / 'adapter.py').read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    register_calls = [
        call for call in calls
        if isinstance(call.func, ast.Attribute) and call.func.attr == 'register_platform'
    ]
    assert register_calls, 'adapter must call ctx.register_platform(...)'
    keywords = {kw.arg: kw.value for kw in register_calls[0].keywords}
    assert keywords['name'].value == 'telnyx_sms'
    assert keywords['label'].value == 'Telnyx SMS'
    assert keywords['allowed_users_env'].value == 'TELNYX_SMS_ALLOWED_USERS'
    assert keywords['allow_all_env'].value == 'TELNYX_SMS_ALLOW_ALL_USERS'
    assert keywords['cron_deliver_env_var'].value == 'TELNYX_SMS_HOME_CHANNEL'
    assert keywords['pii_safe'].value is True


def test_api_constants():
    tree = ast.parse((ROOT / 'adapter.py').read_text())
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except Exception:
                continue

    assert constants['TELNYX_API_BASE'] == 'https://api.telnyx.com/v2'
    assert constants['DEFAULT_WEBHOOK_PATH'] == '/webhooks/telnyx/sms'
    assert constants['MAX_SMS_LENGTH'] == 1600
    assert "TELNYX_MESSAGES_URL = f\"{TELNYX_API_BASE}/messages\"" in (ROOT / 'adapter.py').read_text()


def test_plugin_package_entrypoint_exists():
    init_file = ROOT / '__init__.py'
    assert init_file.exists(), 'Hermes directory plugins require __init__.py'
    text = init_file.read_text()
    assert 'register' in text


def test_manifest_documents_code_supported_env_vars():
    manifest = yaml.safe_load((ROOT / 'plugin.yaml').read_text())
    env_names = {item['name'] for block in ('requires_env', 'optional_env') for item in manifest.get(block, [])}
    assert 'TELNYX_SMS_API_BASE' in env_names
    assert 'TELNYX_SMS_SIGNATURE_TOLERANCE' in env_names


def test_env_example_includes_live_test_guard():
    env_example = (ROOT / '.env.example').read_text()
    assert 'TELNYX_SMS_LIVE_TEST=0' in env_example
    assert 'TELNYX_SMS_TEST_TO=' in env_example
