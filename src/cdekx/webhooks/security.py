"""Hardening the webhook receiver endpoint.

The platform limitations matter here:

* **CDEK does not sign the webhook body** with an HMAC signature (unlike, say,
  Telegram or Stripe). The only built-in defences are checking the sender IP and
  your own "secret path" in the subscription URL.
* The recommended layout is therefore ``https://example.com/webhooks/cdek/{secret}``,
  where ``secret`` is a random string of 32+ characters known only to you.
  An HMAC helper is provided below for the case where you proxy events through
  your own service that signs them.

CDEK IP ranges change from time to time: check ``CDEK_IP_RANGES`` against the
documentation or support before enabling strict verification.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from collections.abc import Iterable, Sequence

__all__ = [
    "CDEK_IP_RANGES",
    "compare_signature",
    "is_cdek_ip",
    "verify_ip",
]

#: Address ranges CDEK sends webhooks from.
#:
#: The list is **deliberately empty**: CDEK does not publish a stable list of IP
#: addresses in its public documentation (apidoc.cdek.ru), and a stale allowlist
#: is more dangerous than none — it silently drops legitimate events and the
#: subscription dies without a trace. An empty list means "IP verification is
#: off": :func:`is_cdek_ip` returns ``False``, :func:`verify_ip` does not raise,
#: and ``WebhookApp`` accepts requests from any address.
#:
#: CDEK support (integrator@cdek.ru) provides the current ranges. Once you have
#: them, pass the list explicitly — do not edit this constant in your own copy
#: of the library::
#:
#:     WebhookApp(on_event=handler, ip_ranges=("2001:db8::/32", "192.0.2.0/24"))
#:
#: The secret in the subscription path remains the primary defence: CDEK does
#: not sign the webhook body, so a URL like ``/webhooks/cdek/{secret}`` is the
#: only mechanism that cannot be bypassed by forging headers.
CDEK_IP_RANGES: tuple[str, ...] = ()


def is_cdek_ip(ip: str | None, ranges: Sequence[str] = CDEK_IP_RANGES) -> bool:
    """Check whether an IP falls into the known CDEK ranges.

    Returns ``False`` when the range list is empty (verification not configured)
    so that traffic is not blocked by default.
    """
    if not ip or not ranges:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(r, strict=False) for r in ranges)


def verify_ip(ip: str | None, ranges: Sequence[str] = CDEK_IP_RANGES) -> None:
    """Raise ``PermissionError`` if the IP is outside the CDEK ranges."""
    if ranges and not is_cdek_ip(ip, ranges):
        raise PermissionError(f"webhook request from untrusted IP: {ip}")


def compare_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Verify an HMAC-SHA256 signature of the body (for your own proxy layer).

    Args:
        body: raw request body bytes.
        signature: value of the signature header (hex or ``sha256=<hex>``).
        secret: your shared secret.

    """
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, provided)


def allowed_types(event_types: Iterable[str] | None) -> frozenset[str] | None:
    """Normalise the list of allowed event types (``None`` means all)."""
    if event_types is None:
        return None
    return frozenset(str(t) for t in event_types)
