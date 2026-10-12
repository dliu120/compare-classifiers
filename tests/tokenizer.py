"""tiktoken fetches the ``o200k_base`` BPE file from the network on first use and caches it in
the OS temp dir (or ``TIKTOKEN_CACHE_DIR``). The suite is otherwise offline: the tests that count
tokens skip, rather than fail, on a machine where that one download has not happened."""

from __future__ import annotations

import pytest

from bakeoff.datasets import tokens


def _available() -> bool:
    try:
        tokens._encoding()
    except Exception:  # noqa: BLE001 - whatever stopped the download or the cache read
        return False
    return True


needs_tokenizer = pytest.mark.skipif(
    not _available(),
    reason="the o200k_base BPE file is not cached; tiktoken downloads it once (tests/tokenizer.py)",
)
