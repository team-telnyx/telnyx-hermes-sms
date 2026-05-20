import os

import pytest

from gateway.config import PlatformConfig

import adapter


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_send_sms(monkeypatch):
    required = (
        os.getenv('TELNYX_SMS_LIVE_TEST') == '1'
        and os.getenv('TELNYX_API_KEY')
        and os.getenv('TELNYX_SMS_FROM_NUMBER')
        and os.getenv('TELNYX_SMS_TEST_TO')
    )
    if not required:
        pytest.skip(
            'Set TELNYX_SMS_LIVE_TEST=1 plus TELNYX_API_KEY, '
            'TELNYX_SMS_FROM_NUMBER, and TELNYX_SMS_TEST_TO to send a real SMS'
        )

    sms = adapter.TelnyxSmsAdapter(PlatformConfig(enabled=True, extra={}))
    result = await sms.send(os.environ['TELNYX_SMS_TEST_TO'], 'Hermes Telnyx SMS live test')
    assert result.success, result.error
    assert result.message_id
