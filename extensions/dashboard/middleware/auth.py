"""Authentication middleware for dashboard."""

import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED

security = HTTPBasic(auto_error=False)


def get_credentials() -> tuple[str, str]:
    """Get dashboard credentials from environment variables."""
    username = os.environ.get("DASHBOARD_USER", "")
    password = os.environ.get("DASHBOARD_PASS", "")
    return username, password


def verify_credentials(
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
) -> None:
    """Verify HTTP Basic Auth credentials.

    No-op if env vars not set (auth disabled).
    Raises HTTPException if credentials are invalid.
    """
    expected_user, expected_pass = get_credentials()

    # Auth not configured, allow all
    if not expected_user and not expected_pass:
        return

    if credentials is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    correct_user = secrets.compare_digest(credentials.username, expected_user)
    correct_pass = secrets.compare_digest(credentials.password, expected_pass)

    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
