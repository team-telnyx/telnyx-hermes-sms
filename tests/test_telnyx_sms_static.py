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
    import adapter

    assert adapter.TELNYX_API_BASE == 'https://api.telnyx.com/v2'
    assert adapter.TELNYX_MESSAGES_URL.endswith('/messages')
    assert adapter.DEFAULT_WEBHOOK_PATH == '/webhooks/telnyx/sms'
    assert adapter.MAX_SMS_LENGTH == 1600
