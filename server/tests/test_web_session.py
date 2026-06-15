"""Web auth helper coverage."""

from __future__ import annotations

import pytest

from app.web import _session_from_auth


def test_session_from_auth_missing_token():
    from fastapi import HTTPException

    with pytest.raises(HTTPException, match="認証トークン"):
        _session_from_auth({}, email="u@example.com")
