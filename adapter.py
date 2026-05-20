"""Telnyx SMS/MMS platform adapter for Hermes Agent.

Plugin-first Hermes platform adapter that exposes Telnyx Messaging as
``telnyx_sms`` without modifying Hermes' built-in Twilio ``sms`` adapter.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any, Dict, Iterable, Optional

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)
from gateway.platforms.helpers import redact_phone, strip_markdown

logger = logging.getLogger(__name__)

TELNYX_API_BASE = "https://api.telnyx.com/v2"
TELNYX_MESSAGES_URL = f"{TELNYX_API_BASE}/messages"
DEFAULT_WEBHOOK_HOST = "127.0.0.1"
DEFAULT_WEBHOOK_PORT = 8087
DEFAULT_WEBHOOK_PATH = "/webhooks/telnyx/sms"
MAX_SMS_LENGTH = 1600
WEBHOOK_BODY_MAX_BYTES = 1_048_576
E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _split_csv(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = list(value)
    return [str(part).strip() for part in parts if str(part).strip()]


def _first_phone(value: Any) -> str:
    """Extract an E.164 number from Telnyx webhook-ish objects.

    Telnyx delivers ``from`` as a dict and ``to`` as a list of dicts.
    Handle str, dict, and list-of-dicts.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        if value:
            return _first_phone(value[0])
        return ""
    if isinstance(value, dict):
        for key in ("phone_number", "number", "address"):
            raw = value.get(key)
            if raw:
                return str(raw).strip()
    return ""


def _extract_media_urls(metadata: Optional[Dict[str, Any]]) -> list[str]:
    """Collect media URLs from common Hermes metadata shapes."""
    if not metadata:
        return []

    candidates: list[Any] = []
    for key in ("media_urls", "media", "attachments", "media_files"):
        if key in metadata:
            candidates.append(metadata[key])

    urls: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, str):
            urls.extend(_split_csv(candidate))
        elif isinstance(candidate, dict):
            raw = candidate.get("url") or candidate.get("media_url")
            if raw:
                urls.append(str(raw).strip())
        elif isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, str):
                    urls.append(item.strip())
                elif isinstance(item, dict):
                    raw = item.get("url") or item.get("media_url")
                    if raw:
                        urls.append(str(raw).strip())

    # Telnyx expects public URLs for MMS media; local files cannot be uploaded
    # through this adapter without a separate public file-serving layer.
    return [url for url in urls if url.startswith(("http://", "https://"))]


# Maximum size for inbound MMS media downloads (5 MB).
_MMS_DOWNLOAD_MAX_BYTES = 5 * 1024 * 1024
_MMS_DOWNLOAD_TIMEOUT = 15  # seconds
_MMS_ALLOWED_CONTENT_TYPES = frozenset({
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "video/mp4", "video/3gpp",
    "audio/mpeg", "audio/ogg", "audio/amr",
    "application/pdf",
})


def check_requirements() -> bool:
    """Return True when runtime deps and the minimum Telnyx credentials exist."""
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return False
    return bool(_env("TELNYX_API_KEY") and _env("TELNYX_SMS_FROM_NUMBER"))


def validate_config(config: PlatformConfig) -> bool:
    extra = getattr(config, "extra", {}) or {}
    api_key = _env("TELNYX_API_KEY") or str(extra.get("api_key", "")).strip()
    from_number = _env("TELNYX_SMS_FROM_NUMBER") or str(extra.get("from_number", "")).strip()
    return bool(api_key and from_number)


def is_connected(config: PlatformConfig) -> bool:
    return validate_config(config)


def _env_enablement() -> dict | None:
    api_key = _env("TELNYX_API_KEY")
    from_number = _env("TELNYX_SMS_FROM_NUMBER")
    if not (api_key and from_number):
        return None

    seed: dict[str, Any] = {
        "from_number": from_number,
        "webhook_host": _env("TELNYX_SMS_WEBHOOK_HOST", DEFAULT_WEBHOOK_HOST),
        "webhook_port": _env("TELNYX_SMS_WEBHOOK_PORT", str(DEFAULT_WEBHOOK_PORT)),
        "webhook_path": _env("TELNYX_SMS_WEBHOOK_PATH", DEFAULT_WEBHOOK_PATH),
    }
    profile_id = _env("TELNYX_MESSAGING_PROFILE_ID")
    if profile_id:
        seed["messaging_profile_id"] = profile_id
    home = _env("TELNYX_SMS_HOME_CHANNEL")
    if home:
        seed["home_channel"] = {"chat_id": home, "name": home}
    return seed


class TelnyxSmsAdapter(BasePlatformAdapter):
    """Telnyx SMS/MMS <-> Hermes gateway adapter."""

    MAX_MESSAGE_LENGTH = MAX_SMS_LENGTH

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform("telnyx_sms"))
        extra = getattr(config, "extra", {}) or {}
        self._api_key = _env("TELNYX_API_KEY") or str(extra.get("api_key", "")).strip()
        self._from_number = _env("TELNYX_SMS_FROM_NUMBER") or str(extra.get("from_number", "")).strip()
        self._messaging_profile_id = _env("TELNYX_MESSAGING_PROFILE_ID") or str(extra.get("messaging_profile_id", "")).strip()
        self._api_base = (_env("TELNYX_SMS_API_BASE") or str(extra.get("api_base", TELNYX_API_BASE))).rstrip("/")
        self._messages_url = f"{self._api_base}/messages"
        self._webhook_host = _env("TELNYX_SMS_WEBHOOK_HOST") or str(extra.get("webhook_host", DEFAULT_WEBHOOK_HOST))
        try:
            self._webhook_port = int(_env("TELNYX_SMS_WEBHOOK_PORT") or str(extra.get("webhook_port", DEFAULT_WEBHOOK_PORT)))
        except ValueError:
            raw_port = _env("TELNYX_SMS_WEBHOOK_PORT") or str(extra.get("webhook_port", ""))
            msg = f"[telnyx_sms] TELNYX_SMS_WEBHOOK_PORT is not a valid integer: {raw_port!r}"
            logger.error(msg)
            self._webhook_port = DEFAULT_WEBHOOK_PORT
        self._webhook_path = _env("TELNYX_SMS_WEBHOOK_PATH") or str(extra.get("webhook_path", DEFAULT_WEBHOOK_PATH))
        self._public_key = _env("TELNYX_PUBLIC_KEY") or str(extra.get("public_key", "")).strip()
        self._require_signature = _truthy(_env("TELNYX_SMS_REQUIRE_SIGNATURE") or str(extra.get("require_signature", "")))
        self._runner = None
        self._http_session: Optional["aiohttp.ClientSession"] = None

    async def connect(self) -> bool:
        import aiohttp
        from aiohttp import web

        if not self._api_key:
            msg = "[telnyx_sms] TELNYX_API_KEY not set"
            logger.error(msg)
            self._set_fatal_error("telnyx_sms_missing_api_key", msg, retryable=False)
            return False
        if not self._from_number:
            msg = "[telnyx_sms] TELNYX_SMS_FROM_NUMBER not set"
            logger.error(msg)
            self._set_fatal_error("telnyx_sms_missing_from_number", msg, retryable=False)
            return False
        if self._require_signature and not self._public_key:
            msg = "[telnyx_sms] TELNYX_SMS_REQUIRE_SIGNATURE=true but TELNYX_PUBLIC_KEY is not set"
            logger.error(msg)
            self._set_fatal_error("telnyx_sms_missing_public_key", msg, retryable=False)
            return False

        if self._public_key or self._require_signature:
            try:
                from nacl.signing import VerifyKey  # noqa: F401
            except ImportError:
                msg = (
                    "[telnyx_sms] PyNaCl is required for webhook signature validation but is not installed. "
                    "Install it with: pip install PyNaCl"
                )
                logger.error(msg)
                self._set_fatal_error("telnyx_sms_missing_pynacl", msg, retryable=False)
                return False

        app = web.Application(client_max_size=WEBHOOK_BODY_MAX_BYTES)
        app.router.add_post(self._webhook_path, self._handle_webhook)
        app.router.add_get("/health", lambda _: web.Response(text="ok"))

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._webhook_host, self._webhook_port)
        await site.start()
        self._http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self._mark_connected()
        logger.info(
            "[telnyx_sms] webhook server listening on %s:%d%s, from: %s",
            self._webhook_host,
            self._webhook_port,
            self._webhook_path,
            redact_phone(self._from_number),
        )
        return True

    async def disconnect(self) -> None:
        if self._http_session:
            await self._http_session.close()
            self._http_session = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._mark_disconnected()
        logger.info("[telnyx_sms] disconnected")

    def format_message(self, content: str) -> str:
        return strip_markdown(content or "")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        import aiohttp

        to_number = str(chat_id or "").strip()
        if not E164_RE.match(to_number):
            return SendResult(success=False, error=f"Invalid E.164 destination: {to_number}")

        formatted = self.format_message(content)
        chunks = self.truncate_message(formatted, self.MAX_MESSAGE_LENGTH)
        media_urls = _extract_media_urls(metadata)
        last_result = SendResult(success=True)

        session = self._http_session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            for index, chunk in enumerate(chunks):
                payload: dict[str, Any] = {
                    "from": self._from_number,
                    "to": to_number,
                    "text": chunk,
                }
                if self._messaging_profile_id:
                    payload["messaging_profile_id"] = self._messaging_profile_id
                # Attach MMS media only to the first chunk to avoid duplicating
                # images/files across split SMS segments.
                if index == 0 and media_urls:
                    payload["media_urls"] = media_urls

                try:
                    async with session.post(self._messages_url, json=payload, headers=headers) as resp:
                        body = await self._safe_json(resp)
                        if resp.status >= 400:
                            error_msg = self._error_message(body)
                            logger.error(
                                "[telnyx_sms] send failed to %s: %s %s",
                                redact_phone(to_number),
                                resp.status,
                                error_msg,
                            )
                            return SendResult(success=False, error=f"Telnyx {resp.status}: {error_msg}")
                        message_id = self._message_id(body)
                        last_result = SendResult(success=True, message_id=message_id, raw_response=body)
                except Exception as exc:
                    logger.error("[telnyx_sms] send error to %s: %s", redact_phone(to_number), exc)
                    return SendResult(success=False, error=str(exc), retryable=True)
        finally:
            if not self._http_session and session:
                await session.close()

        return last_result

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id, "type": "dm"}

    async def _safe_json(self, resp) -> Any:
        try:
            return await resp.json()
        except Exception:
            try:
                return {"text": await resp.text()}
            except Exception:
                return {}

    @staticmethod
    def _message_id(body: Any) -> str:
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, dict):
                return str(data.get("id") or data.get("record_id") or "")
            return str(body.get("id") or body.get("message_id") or "")
        return ""

    @staticmethod
    def _error_message(body: Any) -> str:
        if isinstance(body, dict):
            errors = body.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    return str(first.get("detail") or first.get("title") or first)
                return str(first)
            return str(body.get("message") or body.get("error") or body)
        return str(body)

    def _validate_telnyx_signature(self, body: bytes, headers: Dict[str, str]) -> bool:
        """Validate Telnyx Ed25519 webhook signature when PyNaCl is available.

        Telnyx signs ``timestamp + '|' + raw_body`` with the account public key.
        Validation is optional by default so local development can work without
        PyNaCl; set ``TELNYX_SMS_REQUIRE_SIGNATURE=true`` in production.
        """
        if not self._public_key:
            return not self._require_signature

        signature = headers.get("Telnyx-Signature-Ed25519") or headers.get("telnyx-signature-ed25519") or ""
        timestamp = headers.get("Telnyx-Timestamp") or headers.get("telnyx-timestamp") or ""
        if not signature or not timestamp:
            return False

        try:
            # Reject stale signatures by default; can be relaxed in tests/dev.
            tolerance = int(_env("TELNYX_SMS_SIGNATURE_TOLERANCE", "300"))
            if tolerance > 0 and abs(int(time.time()) - int(timestamp)) > tolerance:
                return False
        except ValueError:
            return False

        try:
            from nacl.signing import VerifyKey
        except ImportError:
            logger.warning("[telnyx_sms] PyNaCl not installed; cannot verify Telnyx webhook signature")
            return False

        try:
            import base64

            key_bytes = base64.b64decode(self._public_key)
            if len(key_bytes) != 32:
                logger.warning("[telnyx_sms] public key decoded to %d bytes, expected 32", len(key_bytes))
                return False
            sig_bytes = base64.b64decode(signature)
            if len(sig_bytes) != 64:
                logger.warning("[telnyx_sms] signature decoded to %d bytes, expected 64", len(sig_bytes))
                return False
            verify_key = VerifyKey(key_bytes)
            verify_key.verify(f"{timestamp}|".encode("utf-8") + body, sig_bytes)
            return True
        except Exception:
            return False

    async def _handle_webhook(self, request) -> "aiohttp.web.Response":
        from aiohttp import web

        raw = await request.read()
        if self._public_key or self._require_signature:
            if not self._validate_telnyx_signature(raw, dict(request.headers)):
                logger.warning("[telnyx_sms] rejected webhook: invalid Telnyx signature")
                return web.json_response({"ok": False}, status=403)

        try:
            payload = await request.json()
        except Exception as exc:
            logger.error("[telnyx_sms] webhook parse error: %s", exc)
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)

        event_type = str(payload.get("event_type") or payload.get("data", {}).get("event_type") or "")
        data = payload.get("data", payload)
        inner = data.get("payload", data) if isinstance(data, dict) else {}
        if not isinstance(inner, dict):
            return web.json_response({"ok": True})

        if event_type != "message.received":
            # Require explicit message.received; delivery receipts and other
            # lifecycle events should not trigger agent responses.  Payloads
            # that lack event_type entirely are also rejected.
            return web.json_response({"ok": True})

        from_number = _first_phone(inner.get("from")) or _first_phone(inner.get("from_number"))
        to_number = _first_phone(inner.get("to")) or _first_phone(inner.get("to_number"))
        text = str(inner.get("text") or inner.get("body") or "").strip()
        message_id = str(inner.get("id") or inner.get("message_id") or data.get("id") or "").strip()

        media_urls: list[str] = []
        media = inner.get("media") or inner.get("media_urls") or []
        if isinstance(media, list):
            for item in media:
                if isinstance(item, str):
                    media_urls.append(item)
                elif isinstance(item, dict):
                    raw_url = item.get("url") or item.get("media_url")
                    if raw_url:
                        media_urls.append(str(raw_url))

        if not from_number or (not text and not media_urls):
            return web.json_response({"ok": True})
        if from_number == self._from_number:
            logger.debug("[telnyx_sms] ignoring echo from own number %s", redact_phone(from_number))
            return web.json_response({"ok": True})

        logger.info(
            "[telnyx_sms] inbound from %s -> %s (%d chars, %d media)",
            redact_phone(from_number),
            redact_phone(to_number),
            len(text),
            len(media_urls),
        )
        source = self.build_source(
            chat_id=from_number,
            chat_name=from_number,
            chat_type="dm",
            user_id=from_number,
            user_name=from_number,
            message_id=message_id or None,
        )
        # Download inbound MMS media to bounded temp files so Hermes gets
        # local paths instead of remote Telnyx URLs that may expire or leak PII.
        local_media = await self._download_inbound_media(media_urls)

        event = MessageEvent(
            text=text or "[MMS attachment]",
            message_type=MessageType.TEXT,
            source=source,
            raw_message=payload,
            message_id=message_id or None,
            media_urls=local_media,
            media_types=["image" if path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")) else "document" for path in local_media],
        )

        task = asyncio.ensure_future(self._safe_handle_message(event))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return web.json_response({"ok": True})

    async def _safe_handle_message(self, event: MessageEvent) -> None:
        """Wrap handle_message with exception logging."""
        try:
            await self.handle_message(event)
        except Exception:
            logger.exception("[telnyx_sms] unhandled error in handle_message for %s", event.message_id)

    async def _download_inbound_media(self, urls: list[str]) -> list[str]:
        """Download remote MMS media to local temp files with size/type checks.

        Returns a list of local file paths.  Skips URLs that fail validation.
        """
        import tempfile
        import aiohttp as _aiohttp

        if not urls:
            return []

        local_paths: list[str] = []
        session = self._http_session or _aiohttp.ClientSession(
            timeout=_aiohttp.ClientTimeout(total=_MMS_DOWNLOAD_TIMEOUT)
        )
        own_session = session is not self._http_session
        try:
            for url in urls:
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.warning("[telnyx_sms] MMS download %s returned %d", url[:120], resp.status)
                            continue
                        content_type = (resp.content_type or "").split(";")[0].strip().lower()
                        if content_type and content_type not in _MMS_ALLOWED_CONTENT_TYPES:
                            logger.warning("[telnyx_sms] MMS download %s disallowed content-type: %s", url[:120], content_type)
                            continue
                        ext_map = {
                            "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                            "image/webp": ".webp", "video/mp4": ".mp4", "video/3gpp": ".3gp",
                            "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/amr": ".amr",
                            "application/pdf": ".pdf",
                        }
                        ext = ext_map.get(content_type, ".bin")
                        data = await resp.content.read(_MMS_DOWNLOAD_MAX_BYTES + 1)
                        if len(data) > _MMS_DOWNLOAD_MAX_BYTES:
                            logger.warning("[telnyx_sms] MMS download %s exceeds %d bytes, skipping", url[:120], _MMS_DOWNLOAD_MAX_BYTES)
                            continue
                        tmp = tempfile.NamedTemporaryFile(prefix="telnyx_mms_", suffix=ext, delete=False)
                        tmp.write(data)
                        tmp.close()
                        local_paths.append(tmp.name)
                except Exception as exc:
                    logger.warning("[telnyx_sms] MMS download failed for %s: %s", url[:120], exc)
        finally:
            if own_session:
                await session.close()
        return local_paths


async def _standalone_send(
    pconfig,
    chat_id: str,
    message: str,
    *,
    thread_id=None,
    media_files=None,
    force_document: bool = False,
) -> dict:
    """Out-of-process cron delivery support."""
    adapter = TelnyxSmsAdapter(pconfig)
    metadata = {"media_files": media_files or []}
    result = await adapter.send(chat_id, message, metadata=metadata)
    if result.success:
        return {"success": True, "message_id": result.message_id}
    return {"error": result.error or "Telnyx SMS send failed"}


def register(ctx) -> None:
    """Plugin entry point: called by the Hermes plugin system."""
    ctx.register_platform(
        name="telnyx_sms",
        label="Telnyx SMS",
        adapter_factory=lambda cfg: TelnyxSmsAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=["TELNYX_API_KEY", "TELNYX_SMS_FROM_NUMBER"],
        install_hint="pip install aiohttp pynacl (PyNaCl only required for signature validation)",
        env_enablement_fn=_env_enablement,
        cron_deliver_env_var="TELNYX_SMS_HOME_CHANNEL",
        standalone_sender_fn=_standalone_send,
        allowed_users_env="TELNYX_SMS_ALLOWED_USERS",
        allow_all_env="TELNYX_SMS_ALLOW_ALL_USERS",
        max_message_length=MAX_SMS_LENGTH,
        pii_safe=True,
        emoji="📱",
        allow_update_command=True,
        platform_hint=(
            "You are chatting via carrier SMS/MMS through Telnyx. SMS does not "
            "support Markdown; keep replies concise, plain-text, and useful. "
            "Long replies may be split into multiple SMS segments."
        ),
    )
