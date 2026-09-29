"""urllib helpers for connecting to Pi APIs with a pinned self-signed TLS cert."""
from __future__ import annotations

import hashlib
import http.client
import ssl
import urllib.request


def build_pinned_opener(fingerprint: str) -> urllib.request.OpenerDirector:
    expected = fingerprint.replace(":", "").lower()
    if len(expected) != 64 or any(
        character not in "0123456789abcdef" for character in expected
    ):
        raise ValueError("Pi TLS certificate fingerprint is invalid")
    context = ssl._create_unverified_context()

    class PinnedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self) -> None:
            super().connect()
            if self.sock is None:
                raise ssl.SSLError("Pi API TLS socket was not established")
            actual = hashlib.sha256(
                self.sock.getpeercert(binary_form=True)
            ).hexdigest()
            if not __import__("hmac").compare_digest(actual, expected):
                self.close()
                raise ssl.SSLError("Pi API TLS certificate fingerprint changed")

    class PinnedHTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, request):
            def connection_factory(host, **kwargs):
                kwargs["context"] = context
                return PinnedHTTPSConnection(host, **kwargs)

            return self.do_open(
                connection_factory,
                request,
            )

    return urllib.request.build_opener(PinnedHTTPSHandler(context=context))


def open_request(request, *, timeout: float, fingerprint: str = ""):
    if request.full_url.lower().startswith("https://") and fingerprint:
        return build_pinned_opener(fingerprint).open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)
