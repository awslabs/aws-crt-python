# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from typing import TYPE_CHECKING

__all__ = ["deprecated"]

if TYPE_CHECKING:
    # Make type checkers happy with a real symbol
    from typing_extensions import deprecated as deprecated  # type: ignore[assignment]
else:
    _impl = None
    try:
        # prefer typing_extensions for widest runtime support
        from typing_extensions import deprecated as _impl
    except Exception:
        try:
            # Python 3.13+
            from typing import deprecated as _impl  # type: ignore[attr-defined]
        except Exception:
            _impl = None

    def deprecated(msg=None, *, since=None):
        """Decorator recognized by type checkers; a no-op at runtime if unsupported."""
        if _impl is None:
            def _noop(obj): return obj
            return _noop
        if since is not None:
            try:
                return _impl(msg, since=since)
            except TypeError:
                # older typing_extensions doesn't support the 'since' kwarg
                pass
        return _impl(msg)