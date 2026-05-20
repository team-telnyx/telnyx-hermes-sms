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
    # Platform is pre-registered by conftest._ensure_telnyx_sms_registered().
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
    # Stub _download_inbound_media so the test doesn't make real HTTP requests.
    async def fake_download(urls):
        return [f'/tmp/fake_{i}.jpg' for i, _ in enumerate(urls)]
    sms._download_inbound_media = fake_download

    payload = {
        'data': {
            'event_type': 'message.received',
            'id': 'evt-1',
            'payload': {
                'id': 'msg-in-1',
                'from': {'phone_number': '+15550000002'},
                'to': [{'phone_number': '+15550000001', 'status': 'webhook_delivered'}],
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
    assert event.media_urls == ['/tmp/fake_0.jpg']


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


def test_signature_verification_with_base64_keypair(monkeypatch):
    """Verify base64-encoded Ed25519 key/signature (Telnyx's actual format)."""
    pytest.importorskip('nacl')
    import base64
    import time as _time
    from nacl.signing import SigningKey

    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    public_key_b64 = base64.b64encode(bytes(verify_key)).decode()

    body = b'{"data":{"event_type":"message.received"}}'
    timestamp = str(int(_time.time()))
    signed = signing_key.sign(f"{timestamp}|".encode() + body)
    signature_b64 = base64.b64encode(signed.signature).decode()

    sms = make_adapter(monkeypatch)
    sms._public_key = public_key_b64
    sms._require_signature = True

    result = sms._validate_telnyx_signature(body, {
        'Telnyx-Signature-Ed25519': signature_b64,
        'Telnyx-Timestamp': timestamp,
    })
    assert result is True, 'base64 key + base64 signature must validate'



@pytest.mark.asyncio
async def test_handle_webhook_rejects_missing_event_type(monkeypatch):
    """Payloads without event_type should be rejected (not processed)."""
    sms = make_adapter(monkeypatch)
    called = False

    async def fake_handle(event):
        nonlocal called
        called = True

    sms.handle_message = fake_handle
    # No event_type field at all
    payload = {'data': {'payload': {'id': 'x', 'from': {'phone_number': '+15550000099'}, 'text': 'sneaky'}}}
    request = make_mocked_request('POST', '/webhooks/telnyx/sms', headers={'Content-Type': 'application/json'})
    request._read_bytes = __import__('json').dumps(payload).encode()

    response = await sms._handle_webhook(request)
    await __import__('asyncio').sleep(0)

    assert response.status == 200
    assert called is False


def test_signature_rejects_wrong_key(monkeypatch):
    """Verify that a valid signature from a different key is rejected."""
    pytest.importorskip('nacl')
    import base64
    import time as _time
    from nacl.signing import SigningKey

    signing_key = SigningKey.generate()
    wrong_key = SigningKey.generate().verify_key
    public_key_b64 = base64.b64encode(bytes(wrong_key)).decode()

    body = b'{"test": true}'
    timestamp = str(int(_time.time()))
    signed = signing_key.sign(f"{timestamp}|".encode() + body)
    signature_b64 = base64.b64encode(signed.signature).decode()

    sms = make_adapter(monkeypatch)
    sms._public_key = public_key_b64
    sms._require_signature = True

    result = sms._validate_telnyx_signature(body, {
        'Telnyx-Signature-Ed25519': signature_b64,
        'Telnyx-Timestamp': timestamp,
    })
    assert result is False, 'wrong key must reject'
