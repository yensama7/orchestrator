"""Secret-at-rest envelope (phases.md §Phase 5 — pay the `schema.sql` plaintext
debt). API keys the user enters in Settings are sealed before they touch the DB
and opened only at the moment a transport needs them, so a DB dump, a log of a
row, or a backup never carries a usable key.

One seam, one default impl (no interface-for-one-impl):

* ``seal(plaintext)`` → an opaque ``enc:v1:…`` token when a key is configured,
  else the plaintext unchanged.
* ``open_(stored)`` → plaintext; transparently passes through anything without
  the ``enc:v1:`` marker, so legacy plaintext rows and no-key dev both just work
  (no backfill migration needed).

The key comes from ``LINEAGE_SECRET_KEY`` (a Fernet urlsafe-base64 32-byte key;
generate one with ``python -m lineage.security.vault --keygen``). When it's
absent the module degrades to plaintext — dev stays runnable with zero config,
and the header of every Settings response still can't leak a stored key because
only ``open_`` ever reconstructs it.

ponytail: swap point for a real KMS — replace the two Fernet lines in ``_cipher``
with a KMS/Vault encrypt/decrypt and keep the ``enc:v1:`` envelope; callers don't
change. Authenticated encryption is not hand-rolled — that's the one thing you
never get lazy about.
"""

from __future__ import annotations

import os
from functools import lru_cache

_MARKER = "enc:v1:"


@lru_cache(maxsize=1)
def _cipher():
    key = os.getenv("LINEAGE_SECRET_KEY")
    if not key:
        return None
    from cryptography.fernet import Fernet  # deferred: dev w/o a key imports nothing
    return Fernet(key.encode())


def configured() -> bool:
    return _cipher() is not None


def seal(plaintext: str | None) -> str | None:
    """Encrypt for storage. No key configured → plaintext (dev). None → None."""
    if plaintext is None or plaintext == "":
        return plaintext
    c = _cipher()
    if c is None:
        return plaintext
    return _MARKER + c.encrypt(plaintext.encode()).decode()


def open_(stored: str | None) -> str | None:
    """Decrypt a stored value. A value without the marker is returned as-is —
    that's legacy plaintext or a dev row, not an error. A sealed value with no
    key configured is unrecoverable and raises (fail closed, never silently wrong)."""
    if not stored or not stored.startswith(_MARKER):
        return stored
    c = _cipher()
    if c is None:
        raise RuntimeError("LINEAGE_SECRET_KEY unset but a sealed key was stored")
    return c.decrypt(stored[len(_MARKER):].encode()).decode()


def demo() -> None:
    # no key → plaintext passthrough both ways (dev default).
    os.environ.pop("LINEAGE_SECRET_KEY", None)
    _cipher.cache_clear()
    assert seal("sk-abc") == "sk-abc"
    assert open_("sk-abc") == "sk-abc"   # legacy plaintext opens unchanged
    assert seal(None) is None and seal("") == ""

    # with a key → round-trips, and the stored form is opaque (not the key).
    from cryptography.fernet import Fernet
    os.environ["LINEAGE_SECRET_KEY"] = Fernet.generate_key().decode()
    _cipher.cache_clear()
    sealed = seal("sk-secret-123")
    assert sealed and sealed.startswith(_MARKER) and "sk-secret" not in sealed
    assert open_(sealed) == "sk-secret-123"
    assert open_("sk-plain") == "sk-plain"   # still passes legacy plaintext through

    # a sealed value with no key must fail closed, never return garbage.
    os.environ.pop("LINEAGE_SECRET_KEY", None)
    _cipher.cache_clear()
    try:
        open_(sealed)
        raise AssertionError("must refuse to open a sealed value with no key")
    except RuntimeError:
        pass
    print("vault.demo ok")


if __name__ == "__main__":
    import sys

    if "--keygen" in sys.argv:
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
    else:
        demo()
