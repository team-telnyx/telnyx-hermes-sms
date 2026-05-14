from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from gateway.config import PlatformConfig

import adapter


class FakeResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return {'data': {'id': 'msg-123'}}


class FakeSession:
    def __init__(self):
        self.posts = []
        self.closed = False

    def post(self, url, json=None, headers=None):
        self.posts.append({'url': url, 'json': json, 'headers': headers})
        return FakeResponse()

    async def close(self):
        self.closed = True


def make_adapter(monkeypatch):
    monkeypatch.setenv('TELNYX_API_KEY', 'KEY_test')
    monkeypatch.setenv('TELNYX_SMS_FROM_NUMBER', '+15550000001')
    # Hermes only allows dynamic Platform("...") values after the plugin has
    # registered. Runtime does this before adapter_factory runs; tests mirror it.
    from gateway.platform_registry import PlatformEntry, platform_registry

    if not platform_registry.is_registered('telnyx_sms'):
        platform_registry.register(PlatformEntry(
            name='telnyx_sms',
            label='Telnyx SMS',
            adapter_factory=lambda cfg: None,
            check_fn=lambda: True,
        ))
    cfg = PlatformConfig(enabled=True, extra={})
    return adapter.TelnyxSmsAdapter(cfg)


@pytest.mark.asyncio
async def test_send_posts_to_telnyx_messages(monkeypatch):
    sms = make_adapter(monkeypatch)
    fake = FakeSession()
    sms._http_session = fake

    result = await sms.send(
        '+15550000002',
        '**Hello** [docs](https://example.com)',
        metadata={'media_urls': ['https://example.com/image.png', '/tmp/local.png']},
    )

    assert result.success is True
    assert result.message_id == 'msg-123'
    assert len(fake.posts) == 1
    post = fake.posts[0]
    assert post['url'] == 'https://api.telnyx.com/v2/messages'
    assert post['headers']['Authorization'] == 'Bearer KEY_test'
    assert post['json']['from'] == '+15550000001'
    assert post['json']['to'] == '+15550000002'
    assert post['json']['text'] == 'Hello docs'
    assert post['json']['media_urls'] == ['https://example.com/image.png']


@pytest.mark.asyncio
async def test_send_rejects_non_e164(monkeypatch):
    sms = make_adapter(monkeypatch)
    result = await sms.send('not-a-number', 'hello')
    assert result.success is False
    assert 'Invalid E.164' in result.error


@pytest.mark.asyncio
async def test_handle_webhook_creates_message_event(monkeypatch):
    sms = make_adapter(monkeypatch)
    captured = []

    async def fake_handle(event):
        captured.append(event)

    sms.handle_message = fake_handle
    payload = {
        'data': {
            'event_type': 'message.received',
            'id': 'evt-1',
            'payload': {
                'id': 'msg-in-1',
                'from': {'phone_number': '+15550000002'},
                'to': {'phone_number': '+15550000001'},
                'text': 'hello from telnyx',
                'media': [{'url': 'https://example.com/cat.jpg'}],
            },
        }
    }
    request = make_mocked_request('POST', '/webhooks/telnyx/sms', headers={'Content-Type': 'application/json'})
    request._read_bytes = __import__('json').dumps(payload).encode()

    response = await sms._handle_webhook(request)
    await __import__('asyncio').sleep(0)

    assert response.status == 200
    assert len(captured) == 1
    event = captured[0]
    assert event.text == 'hello from telnyx'
    assert event.message_id == 'msg-in-1'
    assert event.source.chat_id == '+15550000002'
    assert event.media_urls == ['https://example.com/cat.jpg']


@pytest.mark.asyncio
@pytest.mark.parametrize('event_type', ['message.sent', 'message.finalized', 'message.delivered'])
async def test_handle_webhook_ignores_lifecycle_events(monkeypatch, event_type):
    sms = make_adapter(monkeypatch)
    called = False

    async def fake_handle(event):
        nonlocal called
        called = True

    sms.handle_message = fake_handle
    payload = {'data': {'event_type': event_type, 'payload': {'id': 'x'}}}
    request = make_mocked_request('POST', '/webhooks/telnyx/sms', headers={'Content-Type': 'application/json'})
    request._read_bytes = __import__('json').dumps(payload).encode()

    response = await sms._handle_webhook(request)
    await __import__('asyncio').sleep(0)

    assert response.status == 200
    assert called is False


def test_env_enablement(monkeypatch):
    monkeypatch.setenv('TELNYX_API_KEY', 'KEY_test')
    monkeypatch.setenv('TELNYX_SMS_FROM_NUMBER', '+15550000001')
    monkeypatch.setenv('TELNYX_SMS_HOME_CHANNEL', '+15550000002')
    seed = adapter._env_enablement()
    assert seed['from_number'] == '+15550000001'
    assert seed['home_channel']['chat_id'] == '+15550000002'


def test_validate_config_accepts_env_without_extra(monkeypatch):
    monkeypatch.setenv('TELNYX_API_KEY', 'KEY_test')
    monkeypatch.setenv('TELNYX_SMS_FROM_NUMBER', '+15550000001')
    assert adapter.validate_config(PlatformConfig(enabled=True, extra={})) is True


def test_signature_required_without_public_key_is_invalid(monkeypatch):
    sms = make_adapter(monkeypatch)
    sms._require_signature = True
    sms._public_key = ''
    assert sms._validate_telnyx_signature(b'{}', {}) is False
