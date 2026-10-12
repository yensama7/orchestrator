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
generate one with ``python -m lineage.security.vault --keygen``). When that env
var is absent we fall back to a key auto-generated once and persisted under
``LINEAGE_SECRET_DIR`` (default ``~/.lineage``) — so keys entered in Settings are
encrypted at rest with zero config and survive restarts, and the user never hits
a plaintext-refusal just to save a key. Only if that dir can't be written does
the module degrade: seal with ``require`` still fails closed rather than writing
plaintext. The header of every Settings response can't leak a stored key because
only ``open_`` ever reconstructs it.

Persist the key dir to keep stored keys openable across container restarts
(compose mounts a volume at ``~/.lineage``). Lose the key → sealed values are
unrecoverable, exactly like losing a KMS key.

ponytail: swap point for a real KMS — replace the two Fernet lines in ``_cipher``
with a KMS/Vault encrypt/decrypt and keep the ``enc:v1:`` envelope; callers don't
change. Authenticated encryption is not hand-rolled — that's the one thing you
never get lazy about.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_MARKER = "enc:v1:"


def _key_file() -> Path:
    base = os.getenv("LINEAGE_SECRET_DIR") or str(Path.home() / ".lineage")
    return Path(base) / "secret.key"


def _file_key() -> str | None:
    """Read, or first-time create, the persisted auto-key. Returns None only if
    the dir can't be created/written — then callers fall back to plaintext-refusal
    (fail closed), never a silent plaintext write."""
    from cryptography.fernet import Fernet

    path = _key_file()
    try:
        if path.exists():
            return path.read_text().strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key().decode()
        path.write_text(key)
        os.chmod(path, 0o600)
        return key
    except OSError:
        return None


@lru_cache(maxsize=1)
def _cipher():
    key = os.getenv("LINEAGE_SECRET_KEY") or _file_key()
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def configured() -> bool:
    return _cipher() is not None


def seal(plaintext: str | None, *, require: bool = False) -> str | None:
    """Encrypt for storage. None/"" → unchanged. No key configured → plaintext
    (dev convenience) — UNLESS `require` is set, in which case storing a real
    secret with no vault is a hard error (fail closed), never a silent plaintext
    write. Callers pass require=True for a live API key at the trust boundary."""
    if plaintext is None or plaintext == "":
        return plaintext
    c = _cipher()
    if c is None:
        if require:
            raise RuntimeError(
                "refusing to store an API key in plaintext: set LINEAGE_SECRET_KEY "
                "(generate one with `python -m lineage.security.vault --keygen`)")
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
    import tempfile
    from cryptography.fernet import Fernet

    tmp = tempfile.mkdtemp()

    # zero config: no env key, but a writable secret dir → auto-persisted key,
    # so values are ENCRYPTED by default (not plaintext) and round-trip.
    os.environ.pop("LINEAGE_SECRET_KEY", None)
    os.environ["LINEAGE_SECRET_DIR"] = tmp
    _cipher.cache_clear()
    assert configured()
    sealed = seal("sk-abc")
    assert sealed and sealed.startswith(_MARKER) and "sk-abc" not in sealed
    assert open_(sealed) == "sk-abc"
    assert seal(None) is None and seal("") == ""
    assert open_("sk-plain") == "sk-plain"   # legacy plaintext still opens unchanged
    # the key persists: a fresh cipher reads the same file and opens old values.
    _cipher.cache_clear()
    assert open_(sealed) == "sk-abc"

    # no writable dir AND no env key → fail closed, never a silent plaintext write.
    blocker = os.path.join(tmp, "not-a-dir")
    open(blocker, "w").close()
    os.environ["LINEAGE_SECRET_DIR"] = os.path.join(blocker, "nope")
    _cipher.cache_clear()
    assert not configured()
    assert seal("sk-abc") == "sk-abc"       # non-required value: passthrough ok
    try:
        seal("sk-live", require=True)
        raise AssertionError("must refuse to store a real key with no vault")
    except RuntimeError:
        pass
    try:
        open_(sealed)                       # a sealed value with no key is unrecoverable
        raise AssertionError("must refuse to open a sealed value with no key")
    except RuntimeError:
        pass

    # explicit env key overrides the file and round-trips.
    os.environ["LINEAGE_SECRET_KEY"] = Fernet.generate_key().decode()
    _cipher.cache_clear()
    s2 = seal("sk-secret-123")
    assert s2 and s2.startswith(_MARKER) and "sk-secret" not in s2
    assert open_(s2) == "sk-secret-123"
    print("vault.demo ok")


if __name__ == "__main__":
    import sys

    if "--keygen" in sys.argv:
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
    else:
        demo()
