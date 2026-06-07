"""API client for JD Smart."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from urllib.parse import quote, urlencode

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import (
    APP_KEY,
CONTROL_PATH,
    DEFAULT_APP_VERSION,
    DEFAULT_CHANNEL,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_PLATFORM,
    DEFAULT_PLATFORM_VERSION,
    DEFAULT_USER_AGENT,
    HMAC_KEY,
    JD_SMART_BASE_URL,
    LOGGER,
    SNAPSHOT_PATH,
)

WJLOGIN_REFRESH_URL = "https://wlogin.m.jd.com/applogin_v2"
WJLOGIN_APP_ID = 1421
WJLOGIN_APP_NAME = "jdsmart"
WJLOGIN_SDK_VERSION = "12.0.10"
WJLOGIN_RANDOM_KEY_ALPHABET = (
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


class JdSmartError(Exception):
    """Base JD Smart error."""


class JdSmartAuthError(JdSmartError):
    """Raised on authentication errors."""


class JdSmartCannotConnectError(JdSmartError):
    """Raised when the cloud cannot be reached."""


class JdSmartControlError(JdSmartError):
    """Raised when control fails."""


class JdSmartTokenRefreshError(JdSmartAuthError):
    """Raised when JD login token refresh fails."""


@dataclass(slots=True)
class JdSmartCredentials:
    """JD Smart credentials."""

    cookie: str
    tgt: str
    pin: str | None = None
    sgm_context: str | None = None


@dataclass(slots=True)
class JdSmartDeviceProfile:
    """JD Smart device profile."""

    device_id: str
    app_version: str = DEFAULT_APP_VERSION
    platform: str = DEFAULT_PLATFORM
    device_model: str = DEFAULT_DEVICE_MODEL
    platform_version: str = DEFAULT_PLATFORM_VERSION
    channel: str = DEFAULT_CHANNEL
    user_agent: str = DEFAULT_USER_AGENT


@dataclass(slots=True)
class JdSmartSnapshot:
    """JD Smart device snapshot."""

    digest: str
    status: str
    from_device_success: bool
    streams: dict[str, str]

    @classmethod
    def from_result(cls, result: str | dict[str, Any]) -> JdSmartSnapshot:
        """Create snapshot from API result."""
        data = json.loads(result) if isinstance(result, str) else result
        streams = {
            item["stream_id"]: str(item.get("current_value", ""))
            for item in data.get("streams", [])
        }
        return cls(
            digest=str(data.get("digest", "")),
            status=str(data.get("status", "")),
            from_device_success=bool(data.get("fromDeviceSuccess", False)),
            streams=streams,
        )


def _json_dumps(data: Any) -> str:
    """Dump compact JSON."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _day_of_year(now: datetime) -> int:
    """Return day of year."""
    return int(now.strftime("%j"))


def _timestamp(now: datetime) -> str:
    """Return API timestamp."""
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def build_authorization(
    method: str,
    raw_body: str,
    profile: JdSmartDeviceProfile,
    now: datetime | None = None,
) -> str:
    """Build JD Smart Authorization header."""
    now = now or datetime.now()
    timestamp = _timestamp(now)
    device_md5 = hashlib.md5(
        (
            f"{profile.platform}{profile.app_version}{profile.device_model}"
            f"{profile.platform_version}:{_day_of_year(now)}"
        ).encode()
    ).hexdigest()
    source = (
        device_md5
        + method.lower()
        + "json_body"
        + raw_body
        + timestamp
        + APP_KEY
        + device_md5
    )
    signature = hmac.new(HMAC_KEY.encode(), source.encode(), hashlib.sha1).digest()
    return f"smart {APP_KEY}:::{base64.b64encode(signature).decode()}:::{timestamp}"


def _u32(value: int) -> int:
    """Return value as an unsigned 32-bit integer."""
    return value & 0xFFFFFFFF


def _tea_encrypt_block(block: bytes, key: bytes) -> bytes:
    """Encrypt one TEA block using the JD WJLogin variant."""
    y = int.from_bytes(block[0:4], "big")
    z = int.from_bytes(block[4:8], "big")
    a = int.from_bytes(key[0:4], "big")
    b = int.from_bytes(key[4:8], "big")
    c = int.from_bytes(key[8:12], "big")
    d = int.from_bytes(key[12:16], "big")
    total = 0
    for _ in range(16):
        total = _u32(total + 0x9E3779B9)
        y = _u32(y + _u32(((z << 4) + a) ^ (z + total) ^ ((z >> 5) + b)))
        z = _u32(z + _u32(((y << 4) + c) ^ (y + total) ^ ((y >> 5) + d)))
    return y.to_bytes(4, "big") + z.to_bytes(4, "big")


def _tea_decrypt_block(block: bytes, key: bytes) -> bytes:
    """Decrypt one TEA block using the JD WJLogin variant."""
    y = int.from_bytes(block[0:4], "big")
    z = int.from_bytes(block[4:8], "big")
    a = int.from_bytes(key[0:4], "big")
    b = int.from_bytes(key[4:8], "big")
    c = int.from_bytes(key[8:12], "big")
    d = int.from_bytes(key[12:16], "big")
    total = 0xE3779B90
    for _ in range(16):
        z = _u32(z - _u32(((y << 4) + c) ^ (y + total) ^ ((y >> 5) + d)))
        y = _u32(y - _u32(((z << 4) + a) ^ (z + total) ^ ((z >> 5) + b)))
        total = _u32(total - 0x9E3779B9)
    return y.to_bytes(4, "big") + z.to_bytes(4, "big")


def _key16(key: str) -> bytes:
    """Return a 16-byte WJLogin key."""
    return key.encode()[:16].ljust(16, b"\x00")


def _qqtea_encrypt(data: bytes, key_string: str) -> bytes:
    """Encrypt bytes with the QQTEA mode used by WJLogin."""
    key = _key16(key_string)
    pad_len = (len(data) + 10) % 8
    if pad_len:
        pad_len = 8 - pad_len
    random_bytes = secrets.token_bytes(pad_len + 3)
    plain = bytearray(len(data) + pad_len + 10)
    plain[0] = (random_bytes[0] & 0xF8) | pad_len
    plain[1 : 1 + pad_len + 2] = random_bytes[1:]
    plain[1 + pad_len + 2 : 1 + pad_len + 2 + len(data)] = data

    out = bytearray(len(plain))
    previous_cipher = bytes(8)
    previous_plain = bytes(8)
    for offset in range(0, len(plain), 8):
        mixed = bytes(plain[offset + i] ^ previous_cipher[i] for i in range(8))
        encrypted = _tea_encrypt_block(mixed, key)
        block = bytes(encrypted[i] ^ previous_plain[i] for i in range(8))
        out[offset : offset + 8] = block
        previous_plain = mixed
        previous_cipher = block
    return bytes(out)


def _qqtea_decrypt(cipher: bytes, key_string: str) -> bytes | None:
    """Decrypt bytes with the QQTEA mode used by WJLogin."""
    if len(cipher) < 16 or len(cipher) % 8:
        return None
    key = _key16(key_string)
    plain = bytearray(len(cipher))
    previous_cipher = bytes(8)
    previous_plain = bytes(8)
    for offset in range(0, len(cipher), 8):
        block = bytes(cipher[offset + i] ^ previous_plain[i] for i in range(8))
        mixed = _tea_decrypt_block(block, key)
        plain[offset : offset + 8] = bytes(
            mixed[i] ^ previous_cipher[i] for i in range(8)
        )
        previous_plain = mixed
        previous_cipher = cipher[offset : offset + 8]

    pad_len = plain[0] & 0x07
    start = 1 + pad_len + 2
    end = len(plain) - 7
    if start > end or any(plain[end:]):
        return None
    return bytes(plain[start:end])


def _random_key16() -> str:
    """Generate a WJLogin random key."""
    return "".join(
        WJLOGIN_RANDOM_KEY_ALPHABET[byte % len(WJLOGIN_RANDOM_KEY_ALPHABET)]
        for byte in secrets.token_bytes(16)
    )


def _wj_encrypt_msg(tlv: bytes) -> tuple[str, str]:
    """Return WJLogin random key and encrypted request body."""
    key = _random_key16()
    encrypted = _qqtea_encrypt(tlv, key)
    return key, base64.b64encode(key.encode() + encrypted).decode()


def _wj_decrypt_msg(body: str, key: str) -> bytes | None:
    """Decrypt a WJLogin response body."""
    try:
        cipher = base64.b64decode(body)
    except ValueError:
        return None
    return _qqtea_decrypt(cipher, key)


class _PacketBuilder:
    """Build a WJLogin packet."""

    def __init__(self) -> None:
        """Initialize the builder."""
        self._chunks: list[bytes] = [bytes(2)]

    def short(self, value: int) -> None:
        """Append an unsigned short."""
        self._chunks.append((value & 0xFFFF).to_bytes(2, "big"))

    def byte(self, value: int) -> None:
        """Append one byte."""
        self._chunks.append(bytes([value & 0xFF]))

    def int(self, value: int) -> None:
        """Append a signed int."""
        self._chunks.append(int(value).to_bytes(4, "big", signed=True))

    def long(self, value: int) -> None:
        """Append a signed long."""
        self._chunks.append(int(value).to_bytes(8, "big", signed=True))

    def short_string(self, value: str | None) -> None:
        """Append a short-prefixed string."""
        raw = (value or "").encode()
        self.short(len(raw))
        self._chunks.append(raw)

    def short_bytes(self, value: bytes) -> None:
        """Append short-prefixed bytes."""
        self.short(len(value))
        self._chunks.append(value)

    def tlv(self, tag: int, value: bytes) -> None:
        """Append a TLV field."""
        self.short(tag)
        self.short(len(value))
        self._chunks.append(value)

    def finish(self) -> bytes:
        """Finish packet and write total length."""
        out = bytearray(b"".join(self._chunks))
        out[0:2] = len(out).to_bytes(2, "big")
        return bytes(out)


def _short_string(value: str | None) -> bytes:
    """Return short-prefixed bytes."""
    raw = (value or "").encode()
    return len(raw).to_bytes(2, "big") + raw


def _tlv_app_info(profile: JdSmartDeviceProfile) -> bytes:
    """Build WJLogin app info TLV."""
    builder = _PacketBuilder()
    builder.short(3)
    builder.short(WJLOGIN_APP_ID)
    builder.short_string("android")
    builder.short_string(profile.platform_version)
    builder.short_string(profile.app_version)
    builder.short_string("")
    builder.short_string(WJLOGIN_APP_NAME)
    builder.short_string("")
    builder.short_string("")
    builder.short_string(profile.device_id)
    builder.int(1)
    builder.short_string(WJLOGIN_SDK_VERSION)
    builder.short_string("")
    builder.short_string("")
    return builder.finish()[2:]


def _tlv_common_union(profile: JdSmartDeviceProfile) -> bytes:
    """Build WJLogin common union TLV."""
    return b"".join(
        [
            _short_string(profile.device_id),
            _short_string(""),
            _short_string(""),
            _short_string("{}"),
        ]
    )


def _tlv_device_101(profile: JdSmartDeviceProfile) -> bytes:
    """Build WJLogin device TLV 101."""
    return b"".join(
        [
            _short_string(""),
            _short_string(""),
            _short_string(""),
            _short_string(profile.device_id),
        ]
    )


def _a2_to_tlv_bytes(tgt: str) -> bytes:
    """Decode URL-safe A2 when possible, otherwise use raw UTF-8."""
    padded = tgt + "=" * ((4 - len(tgt) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded)
    except ValueError:
        return tgt.encode()
    round_trip = base64.urlsafe_b64encode(decoded).decode().rstrip("=")
    if decoded and round_trip == tgt.rstrip("="):
        return decoded
    return tgt.encode()


def _base64_url_no_padding(value: bytes) -> str:
    """Encode bytes as URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _build_refresh_a2_tlv(
    credentials: JdSmartCredentials,
    profile: JdSmartDeviceProfile,
) -> bytes:
    """Build a refreshA2 request packet."""
    builder = _PacketBuilder()
    builder.long(1)
    builder.int(1)
    builder.int(int(time.time()))
    builder.int(0)
    builder.short(3)
    builder.short(2)
    builder.short(WJLOGIN_APP_ID)
    builder.short(273)
    builder.byte(0)
    builder.tlv(8, _tlv_app_info(profile))
    builder.short(10)
    builder.short_bytes(_a2_to_tlv_bytes(credentials.tgt))
    builder.short(16)
    builder.short_string(credentials.pin or "")
    builder.tlv(72, _tlv_common_union(profile))
    builder.tlv(101, _tlv_device_101(profile))
    return builder.finish()


def _parse_refresh_a2_response(packet: bytes) -> str:
    """Parse refreshA2 response packet and return the refreshed TGT."""
    if len(packet) < 31:
        raise JdSmartTokenRefreshError("WJLogin response packet too short")
    reply_code = packet[30]
    if reply_code != 0:
        raise JdSmartTokenRefreshError(f"WJLogin reply code: {reply_code}")

    pos = 31
    while pos + 4 <= len(packet):
        tag = int.from_bytes(packet[pos : pos + 2], "big")
        length = int.from_bytes(packet[pos + 2 : pos + 4], "big")
        pos += 4
        if pos + length > len(packet):
            break
        value = packet[pos : pos + length]
        if tag == 10 and len(value) >= 2:
            return _base64_url_no_padding(value)
        pos += length
    raise JdSmartTokenRefreshError("WJLogin response did not include a new TGT")


def _parse_cookie(cookie: str) -> list[tuple[str, str]]:
    """Parse a Cookie header into key-value pairs."""
    items: list[tuple[str, str]] = []
    for part in cookie.split(";"):
        part = part.strip()
        if not part:
            continue
        key, separator, value = part.partition("=")
        items.append((key.strip(), value.strip() if separator else ""))
    return items


def _upsert_cookie(items: list[tuple[str, str]], key: str, value: str) -> None:
    """Insert or update a Cookie item."""
    for index, (item_key, _item_value) in enumerate(items):
        if item_key.lower() == key.lower():
            items[index] = (key, value)
            return
    items.append((key, value))


def _build_cookie_from_tgt(cookie: str, tgt: str, pin: str | None) -> str:
    """Update a Cookie header with the refreshed WJLogin token."""
    items = _parse_cookie(cookie)
    if pin:
        encoded_pin = quote(pin, safe="")
        _upsert_cookie(items, "pin", encoded_pin)
        _upsert_cookie(items, "pt_pin", encoded_pin)
        _upsert_cookie(items, "pwdt_id", encoded_pin)
    _upsert_cookie(items, "wskey", tgt)
    return "; ".join(f"{key}={value}" for key, value in items)


class JdSmartClient:
    """JD Smart client."""

    def __init__(
        self,
        session: ClientSession,
        credentials: JdSmartCredentials,
        profile: JdSmartDeviceProfile,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self.credentials = credentials
        self.profile = profile

    def _public_query(self) -> dict[str, str]:
        """Build public query parameters."""
        return {
            "plat": self.profile.platform,
            "hard_platform": self.profile.device_model,
            "app_version": self.profile.app_version,
            "plat_version": self.profile.platform_version,
            "device_id": self.profile.device_id,
            "channel": self.profile.channel,
        }

    def _headers(
        self, raw_body: str, *, content_type: str = "application/json"
    ) -> dict[str, str]:
        """Build common headers."""
        authorization = build_authorization("POST", raw_body, self.profile)
        headers = {
            "Content-Type": content_type,
            "Authorization": authorization,
            "Cookie": self.credentials.cookie,
            "tgt": self.credentials.tgt,
            "app_identity": "WL",
            "appversion": self.profile.app_version,
            "appplatform": self.profile.device_model,
            "appplatformversion": self.profile.platform_version,
            "User-Agent": self.profile.user_agent,
        }
        if self.credentials.sgm_context:
            headers["Sgm-Context"] = self.credentials.sgm_context
        return headers

    async def _request_json(
        self,
        url: str,
        raw_body: str,
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """POST JSON and parse response."""
        LOGGER.debug(
            "JD Smart request: path=%s, body_length=%s",
            url.split("?", 1)[0],
            len(raw_body),
        )
        try:
            async with self._session.post(
                url, data=raw_body, headers=headers
            ) as response:
                text = await response.text()
                LOGGER.debug(
                    "JD Smart response: path=%s, http_status=%s, body_length=%s",
                    url.split("?", 1)[0],
                    response.status,
                    len(text),
                )
                if response.status != HTTPStatus.OK:
                    LOGGER.warning(
                        "JD Smart HTTP error: path=%s, http_status=%s, body=%s",
                        url.split("?", 1)[0],
                        response.status,
                        _truncate(text),
                    )
                    raise ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=text,
                        headers=response.headers,
                    )
        except (ClientError, TimeoutError) as err:
            raise JdSmartCannotConnectError from err

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as err:
            raise JdSmartCannotConnectError("Invalid JSON response") from err

        error = payload.get("error")
        if error:
            error_code = str(error.get("errorCode", ""))
            error_info = error.get("errorInfo", "JD Smart API error")
            LOGGER.warning(
                "JD Smart API error: path=%s, code=%s, info=%s, status=%s",
                url.split("?", 1)[0],
                error_code,
                error_info,
                payload.get("status"),
            )
            if error_code == "401":
                raise JdSmartAuthError(error_info)
            raise JdSmartError(error_info)
        if payload.get("status") not in (0, "0"):
            LOGGER.warning(
                "JD Smart unexpected status: path=%s, status=%s, payload=%s",
                url.split("?", 1)[0],
                payload.get("status"),
                _truncate(json.dumps(payload, ensure_ascii=False)),
            )
            raise JdSmartError(f"Unexpected status: {payload.get('status')}")
        return payload

    async def async_refresh_token(self) -> tuple[str, str]:
        """Refresh the JD WJLogin A2 token and update local credentials."""
        tlv = _build_refresh_a2_tlv(self.credentials, self.profile)
        random_key, raw_body = _wj_encrypt_msg(tlv)
        LOGGER.info("JD Smart token refresh started")
        try:
            async with self._session.post(
                WJLOGIN_REFRESH_URL,
                data=raw_body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": f"Android WJLoginSDK {WJLOGIN_SDK_VERSION}",
                },
            ) as response:
                text = await response.text()
                if response.status != HTTPStatus.OK:
                    LOGGER.warning(
                        "JD Smart token refresh HTTP error: http_status=%s, "
                        "body_length=%s",
                        response.status,
                        len(text),
                    )
                    raise JdSmartTokenRefreshError(
                        f"WJLogin HTTP status: {response.status}"
                    )
        except (ClientError, TimeoutError) as err:
            raise JdSmartTokenRefreshError("Unable to reach WJLogin") from err

        packet = _wj_decrypt_msg(text, random_key)
        if packet is None:
            raise JdSmartTokenRefreshError("Unable to decrypt WJLogin response")

        new_tgt = _parse_refresh_a2_response(packet)
        new_cookie = _build_cookie_from_tgt(
            self.credentials.cookie,
            new_tgt,
            self.credentials.pin,
        )
        same_token = new_tgt == self.credentials.tgt
        self.credentials.tgt = new_tgt
        self.credentials.cookie = new_cookie
        LOGGER.info("JD Smart token refresh succeeded: same_token=%s", same_token)
        return new_tgt, new_cookie

    async def async_get_snapshot(
        self,
        feed_id: str,
        digest: str = "",
    ) -> JdSmartSnapshot:
        """Fetch a device snapshot using the plain iOS endpoint."""
        inner: dict[str, str | int] = {
            "feed_id": feed_id,
            "digest": digest,
            "pullMode": 0,
            "version": "2.0",
        }
        raw_body = _json_dumps({"json": inner})
        url = (
            f"{JD_SMART_BASE_URL}{SNAPSHOT_PATH}"
            f"?{urlencode(self._public_query())}"
        )
        payload = await self._request_json(
            url,
            raw_body,
            headers=self._headers(raw_body),
        )
        return JdSmartSnapshot.from_result(payload["result"])

    def _control_body(self, feed_id: str, commands: dict[str, Any]) -> str:
        """Build control business body."""
        inner = {
            "version": "2.0",
            "feed_id": feed_id,
            "command": [
                {"stream_id": stream_id, "current_value": value}
                for stream_id, value in commands.items()
            ],
        }
        return _json_dumps({"json": _json_dumps(inner)})

    async def async_control_streams(
        self,
        feed_id: str,
        commands: dict[str, Any],
    ) -> JdSmartSnapshot | None:
        """Control device streams."""
        raw_body = self._control_body(feed_id, commands)
        url = (
            f"{JD_SMART_BASE_URL}{CONTROL_PATH}"
            f"?{urlencode(self._public_query())}"
        )
        LOGGER.info(
            "JD Smart control command: feed_id=%s, commands=%s",
            feed_id,
            commands,
        )

        payload = await self._request_json(
            url,
            raw_body,
            headers=self._headers(raw_body),
        )
        result = json.loads(payload["result"])
        LOGGER.info(
            "JD Smart control result: feed_id=%s, control_ret=%s, "
            "status=%s, has_streams=%s, digest=%s",
            feed_id,
            result.get("control_ret"),
            result.get("status"),
            "streams" in result,
            result.get("digest"),
        )
        if "streams" in result:
            return JdSmartSnapshot.from_result(result)
        if result.get("control_ret") == "done":
            return None
        if result.get("status") in (1, "1"):
            return JdSmartSnapshot.from_result(result)
        LOGGER.warning(
            "JD Smart unexpected control result: feed_id=%s, result=%s",
            feed_id,
            _truncate(json.dumps(result, ensure_ascii=False)),
        )
        raise JdSmartControlError(f"Unexpected control result: {result}")


def _truncate(value: str, limit: int = 1000) -> str:
    """Truncate a log value."""
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."
