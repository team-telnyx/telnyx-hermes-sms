# Telnyx SMS — Hermes Agent Contribution

This repository contains the Telnyx SMS/MMS platform adapter for
[Hermes Agent](https://github.com/team-telnyx/hermes-agent).

It is a **plugin-first platform adapter**. Hermes already has a built-in
`gateway/platforms/sms.py`, but that adapter is Twilio-based. This contribution
keeps Twilio untouched and adds Telnyx as `telnyx_sms` so the integration is
safe, reversible, and consistent with Hermes' platform-plugin architecture.

## What's inside

| File | Purpose |
|------|---------|
| `adapter.py` | Hermes platform adapter + `register(ctx)` plugin entry point |
| `plugin.yaml` | Platform plugin metadata and config UI env var definitions |
| `tests/test_telnyx_sms_static.py` | Manifest/static/API shape checks |
| `tests/test_telnyx_sms_runtime.py` | Mocked outbound send and inbound webhook runtime tests |
| `tests/test_telnyx_sms_live.py` | Optional live SMS send test |

## Integration into hermes-agent

### Plugin path

Copy this repository's plugin files into a Hermes plugin directory:

```text
~/.hermes/plugins/telnyx_sms/
  plugin.yaml
  adapter.py
```

Or contribute upstream as a bundled platform plugin:

```text
plugins/platforms/telnyx_sms/
  plugin.yaml
  adapter.py
```

No core Hermes code changes are required. Hermes' platform registry handles:

- adapter creation via `ctx.register_platform(...)`
- dynamic `Platform("telnyx_sms")` enum support
- env-driven enablement
- allowed-user / allow-all auth checks
- cron/home-channel delivery
- standalone out-of-process sends
- `hermes status` / setup UI display
- platform prompt hints
- SMS message chunking

## Provider details

| Field | Value |
|-------|-------|
| Platform ID | `telnyx_sms` |
| Outbound API | `POST https://api.telnyx.com/v2/messages` |
| Inbound webhook | `/webhooks/telnyx/sms` |
| Auth | `TELNYX_API_KEY` Bearer token |
| Sender | `TELNYX_SMS_FROM_NUMBER` |
| Optional profile | `TELNYX_MESSAGING_PROFILE_ID` |
| Message limit | 1600 chars per chunk |
| MMS | Public `media_urls` only |

## Environment variables

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
export TELNYX_SMS_WEBHOOK_HOST="0.0.0.0"      # default: 127.0.0.1
export TELNYX_SMS_WEBHOOK_PORT=8087           # default: 8087
export TELNYX_SMS_WEBHOOK_PATH="/webhooks/telnyx/sms"
export TELNYX_SMS_HOME_CHANNEL="+15551230001" # cron/default delivery
export TELNYX_SMS_API_BASE="https://api.telnyx.com/v2"
```

## Hermes configuration

```yaml
gateway:
  platforms:
    telnyx_sms:
      enabled: true
      extra:
        from_number: "+15551234567"
        webhook_host: "0.0.0.0"
        webhook_port: 8087
        webhook_path: "/webhooks/telnyx/sms"
```

The plugin also supports env-driven auto-enablement when
`TELNYX_API_KEY` and `TELNYX_SMS_FROM_NUMBER` are present.

## Webhook setup

Configure the Telnyx Messaging Profile inbound webhook URL to:

```text
https://your-public-host.example/webhooks/telnyx/sms
```

The adapter processes `message.received` events and ignores delivery receipts
or other lifecycle webhooks so they do not trigger agent replies.

## Security notes

- Use `TELNYX_SMS_ALLOWED_USERS` in production unless every sender should be
  allowed.
- Use `TELNYX_PUBLIC_KEY` + `TELNYX_SMS_REQUIRE_SIGNATURE=true` in production.
- PyNaCl is only required when signature validation is enabled.
- Phone numbers are redacted in logs where Hermes' helpers support it.

## Running tests

```bash
# No credentials needed
python -m pytest tests/test_telnyx_sms_static.py tests/test_telnyx_sms_runtime.py -q

# Live test (sends a real SMS)
export TELNYX_API_KEY="KEY..."
export TELNYX_SMS_FROM_NUMBER="+15551234567"
export TELNYX_SMS_TEST_TO="+15557654321"
python -m pytest tests/test_telnyx_sms_live.py -q -m live
```

## Linear

AI-2323

OpenClaw equivalent: AIF-125 — Telnyx SMS Channel.

## References

- [Telnyx Messaging API](https://developers.telnyx.com/docs/api/v2/messaging)
- [Telnyx Messaging webhooks](https://developers.telnyx.com/docs/messaging/messages/webhooks)
- [Hermes platform adapter guide](https://github.com/team-telnyx/hermes-agent/blob/main/website/docs/developer-guide/adding-platform-adapters.md)
