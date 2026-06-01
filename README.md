# Telnyx SMS — Hermes Agent Contribution

This repository contains the Telnyx SMS/MMS platform adapter for
[Hermes Agent](https://github.com/NousResearch/hermes-agent).

It is a **plugin-first platform adapter**. Hermes already has a built-in
`gateway/platforms/sms.py`, but that adapter is Twilio-based. This contribution
keeps Twilio untouched and adds Telnyx as `telnyx_sms` so the integration is
safe, reversible, and consistent with Hermes' platform-plugin architecture.

## What's inside

| File | Purpose |
|------|---------|
| `__init__.py` | Hermes directory-plugin entry point that exposes `register(ctx)` |
| `adapter.py` | Hermes platform adapter implementation |
| `plugin.yaml` | Platform plugin metadata and config UI env var definitions |
| `.env.example` | Copyable environment variable template |
| `tests/test_telnyx_sms_static.py` | Manifest/static/API shape checks |
| `tests/test_telnyx_sms_runtime.py` | Mocked outbound send and inbound webhook runtime tests |
| `tests/test_telnyx_sms_live.py` | Optional live SMS send test, gated by `TELNYX_SMS_LIVE_TEST=1` |

## Fresh clone setup

Requirements:

- Python 3.10+; Python 3.12 is recommended because local Hermes checkouts may
  use modern typing syntax.
- A local Hermes Agent checkout for tests that import `gateway.*` modules.
  Set `HERMES_AGENT_ROOT` if it is not at `~/.hermes/hermes-agent`.
- `uv` is recommended for reproducible local test dependencies.

```bash
git clone https://github.com/team-telnyx/telnyx-hermes-sms.git
cd telnyx-hermes-sms
export HERMES_AGENT_ROOT="$HOME/.hermes/hermes-agent"  # adjust if needed
uv run --extra test python -m pytest tests/test_telnyx_sms_static.py tests/test_telnyx_sms_runtime.py tests/test_telnyx_sms_plugin_loading.py -q
```

Without `uv`, use any Python 3.10+ virtualenv:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
export HERMES_AGENT_ROOT="$HOME/.hermes/hermes-agent"
python -m pytest tests/test_telnyx_sms_static.py tests/test_telnyx_sms_runtime.py tests/test_telnyx_sms_plugin_loading.py -q
```

## Integration into hermes-agent

### User plugin install

The repository now ships an installer CLI, so you can install the plugin from a
tagged Git ref instead of manually copying files.

Quickest downloadable path today:

```bash
pipx install --python python3.12 "git+https://github.com/team-telnyx/telnyx-hermes-sms.git"
telnyx-hermes-sms-install
```

If your machine's default `python3` is older than 3.10, do not use the generic
`python3 -m pip ...` examples below unchanged. On macOS in particular,
`python3 --version` may still be 3.9.x, which will fail because this package
requires Python 3.10+.

Recommended stable path once a Git tag/release exists:

```bash
pipx install --python python3.12 "git+https://github.com/team-telnyx/telnyx-hermes-sms.git@v0.2.0"
telnyx-hermes-sms-install
```

Install directly from the current default branch today:

```bash
pipx install --python python3.12 "git+https://github.com/team-telnyx/telnyx-hermes-sms.git"
telnyx-hermes-sms-install
```

Local checkout / pre-release validation path:

```bash
git clone https://github.com/team-telnyx/telnyx-hermes-sms.git
cd telnyx-hermes-sms
python3.12 -m pip install .
telnyx-hermes-sms-install
```

If you prefer `uv`, this also works without mutating your global Python setup:

```bash
uv tool install --python 3.12 "git+https://github.com/team-telnyx/telnyx-hermes-sms.git"
telnyx-hermes-sms-install
```

By default the installer writes the Hermes plugin directory at:

```text
~/.hermes/plugins/telnyx_sms/
  plugin.yaml
  __init__.py
  adapter.py
  .env.example
```

Use `telnyx-hermes-sms-install --target-dir /custom/path/telnyx_sms` to install
somewhere else, or `--force` to refresh an existing plugin checkout.

Enable the plugin in Hermes. Depending on the Hermes CLI version, use the
plugin manifest name/key shown by `hermes plugins list`; for this plugin that is
usually `telnyx-sms-platform` or the directory key `telnyx_sms`:

```bash
hermes plugins list
hermes plugins enable telnyx-sms-platform  # or: hermes plugins enable telnyx_sms
```

Then configure credentials and enable the platform:

```bash
# Append the installed template to your existing Hermes .env (do NOT overwrite):
cat ~/.hermes/plugins/telnyx_sms/.env.example >> ~/.hermes/.env
# Then edit ~/.hermes/.env — remove duplicates, fill in your Telnyx values.
```

```yaml
# ~/.hermes/config.yaml
gateway:
  platforms:
    telnyx_sms:
      enabled: true
```

Restart the Hermes gateway after installing/enabling the plugin so the platform
registry can discover `telnyx_sms`.

### Packaging and release notes

- `pyproject.toml` now declares a real setuptools build backend, so wheels and
  sdists can be built and tagged cleanly.
- The CLI entry point is `telnyx-hermes-sms-install`.
- As of 2026-05-31, the public GitHub repo has no tags or releases yet, so use
  the default-branch install command above until a release is cut.
- To publish the documented stable install command, tag and release `v0.2.0`
  (or the final chosen version) after review.

### Bundled upstream plugin path

For an upstream Hermes contribution, copy the plugin under:

```text
plugins/platforms/telnyx_sms/
  plugin.yaml
  __init__.py
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
| Plugin manifest name | `telnyx-sms-platform` |
| Outbound API | `POST https://api.telnyx.com/v2/messages` |
| Inbound webhook | `/webhooks/telnyx/sms` |
| Auth | `TELNYX_API_KEY` Bearer token |
| Sender | `TELNYX_SMS_FROM_NUMBER` |
| Optional profile | `TELNYX_MESSAGING_PROFILE_ID` |
| Message limit | 1600 chars per chunk |
| MMS outbound | Public `media_urls` only (no local file upload) |
| MMS inbound | Media auto-downloaded to local temp files (5 MB / file limit) |

## Environment variables

Required:

```bash
export TELNYX_API_KEY="KEY..."
export TELNYX_SMS_FROM_NUMBER="+15551234567"
```

Required for inbound SMS — set **at least one** so Hermes knows who can talk to
your bot:

```bash
# Allowlist specific numbers (recommended):
export TELNYX_SMS_ALLOWED_USERS="+15551230001,+15551230002"
# OR allow any sender (dev/testing only):
export TELNYX_SMS_ALLOW_ALL_USERS=true
```

Recommended production hardening:

```bash
# Get your public key: https://portal.telnyx.com → Account Settings → Public Key
export TELNYX_PUBLIC_KEY="<base64 Ed25519 public key from GET /v2/public_key>"
export TELNYX_SMS_REQUIRE_SIGNATURE=true
```

Optional:

```bash
export TELNYX_MESSAGING_PROFILE_ID="400..."
export TELNYX_SMS_API_BASE="https://api.telnyx.com/v2"
export TELNYX_SMS_WEBHOOK_HOST="0.0.0.0"      # default: 127.0.0.1
export TELNYX_SMS_WEBHOOK_PORT=8087           # default: 8087
export TELNYX_SMS_WEBHOOK_PATH="/webhooks/telnyx/sms"
export TELNYX_SMS_HOME_CHANNEL="+15551230001" # cron/default delivery
export TELNYX_SMS_SIGNATURE_TOLERANCE=300      # seconds; 0 disables freshness check
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

For local development, expose the webhook listener with a tunnel such as
Cloudflare Tunnel or ngrok and set `TELNYX_SMS_WEBHOOK_HOST=0.0.0.0` if the
listener must bind beyond localhost.

The adapter processes inbound `message.received` events and ignores other
message lifecycle webhooks so delivery receipts do not trigger agent replies.

## Security notes

- Use `TELNYX_SMS_ALLOWED_USERS` in production unless every sender should be
  allowed.
- Use `TELNYX_PUBLIC_KEY` + `TELNYX_SMS_REQUIRE_SIGNATURE=true` in production.
- If `TELNYX_PUBLIC_KEY` is set, incoming webhooks are signature-checked. If
  `TELNYX_SMS_REQUIRE_SIGNATURE=true`, invalid/missing signatures are rejected.
- PyNaCl is only required when signature validation is enabled.
- Phone numbers are redacted in logs where Hermes' helpers support it.

## Running tests

```bash
# No credentials needed; does not send SMS
uv run --extra test python -m pytest tests/test_telnyx_sms_static.py tests/test_telnyx_sms_runtime.py tests/test_telnyx_sms_plugin_loading.py -q

# Full suite; live test skips unless explicitly enabled
uv run --extra test python -m pytest -q
```

Live SMS send test requires an explicit safety flag and sends a real SMS:

```bash
export TELNYX_API_KEY="KEY..."
export TELNYX_SMS_FROM_NUMBER="+15551234567"
export TELNYX_SMS_TEST_TO="+15557654321"
export TELNYX_SMS_LIVE_TEST=1
uv run --extra test python -m pytest tests/test_telnyx_sms_live.py -q -m live
```

## Linear

AIF-206

OpenClaw equivalent: AIF-125 — Telnyx SMS Channel.

## References

- [Telnyx Messaging API](https://developers.telnyx.com/docs/api/v2/messaging)
- [Telnyx Messaging webhooks](https://developers.telnyx.com/docs/messaging/messages/webhooks)
- [Hermes platform adapter guide](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/adding-platform-adapters.md)
