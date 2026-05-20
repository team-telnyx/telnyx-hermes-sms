---
name: telnyx-hermes-sms
description: Telnyx SMS/MMS platform adapter for Hermes Agent
author: Telnyx AI FDE
version: 0.1.0
tags: [hermes, telnyx, sms, mms, platform]
---

# Telnyx Hermes SMS

Use Telnyx Messaging as a first-class Hermes platform adapter.

## Install into Hermes

```bash
mkdir -p ~/.hermes/plugins/telnyx_sms
cp __init__.py adapter.py plugin.yaml ~/.hermes/plugins/telnyx_sms/
hermes plugins list
hermes plugins enable telnyx-sms-platform  # or telnyx_sms depending on CLI key
```

Restart the Hermes gateway after enabling the plugin.

## Configuration

Required:

```bash
export TELNYX_API_KEY="KEY..."
export TELNYX_SMS_FROM_NUMBER="+15551234567"
```

Recommended production hardening:

```bash
export TELNYX_PUBLIC_KEY="<Telnyx webhook signing public key>"
export TELNYX_SMS_REQUIRE_SIGNATURE=true
export TELNYX_SMS_ALLOWED_USERS="+15551230001,+15551230002"
```

Optional:

```bash
export TELNYX_MESSAGING_PROFILE_ID="400..."
export TELNYX_SMS_API_BASE="https://api.telnyx.com/v2"
export TELNYX_SMS_WEBHOOK_HOST="0.0.0.0"
export TELNYX_SMS_WEBHOOK_PORT=8087
export TELNYX_SMS_WEBHOOK_PATH="/webhooks/telnyx/sms"
export TELNYX_SMS_HOME_CHANNEL="+15551230001"
export TELNYX_SMS_SIGNATURE_TOLERANCE=300
```

## Hermes config

```yaml
gateway:
  platforms:
    telnyx_sms:
      enabled: true
```

Or rely on env-driven enablement when `TELNYX_API_KEY` and
`TELNYX_SMS_FROM_NUMBER` are set and the plugin is enabled.

## Webhook

Configure the Telnyx Messaging Profile inbound webhook to:

```text
https://your-public-host.example/webhooks/telnyx/sms
```

The adapter accepts inbound `message.received` webhooks and ignores delivery
receipt lifecycle events.

## Tests

```bash
uv run --extra test python -m pytest tests/test_telnyx_sms_static.py tests/test_telnyx_sms_runtime.py -q
```

Live SMS send test requires an explicit safety flag and sends a real SMS:

```bash
export TELNYX_API_KEY="KEY..."
export TELNYX_SMS_FROM_NUMBER="+15551234567"
export TELNYX_SMS_TEST_TO="+15557654321"
export TELNYX_SMS_LIVE_TEST=1
uv run --extra test python -m pytest tests/test_telnyx_sms_live.py -q -m live
```
