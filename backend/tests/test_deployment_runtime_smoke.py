from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.main import app


def test_deployments_runtime_lifespan_smoke() -> None:
    prev_enable = os.environ.get("ST_ENABLE_DEPLOYMENTS_RUNTIME")
    prev_allow = os.environ.get("ST_ENABLE_DEPLOYMENTS_RUNTIME_UNDER_PYTEST")
    prev_mode = os.environ.get("ST_DEPLOYMENTS_RUNTIME_MODE")
    try:
        os.environ["ST_ENABLE_DEPLOYMENTS_RUNTIME"] = "1"
        os.environ["ST_ENABLE_DEPLOYMENTS_RUNTIME_UNDER_PYTEST"] = "1"
        os.environ["ST_DEPLOYMENTS_RUNTIME_MODE"] = "once"
        with TestClient(app) as client:
            res = client.get("/health")
            assert res.status_code == 200
    finally:
        if prev_enable is None:
            os.environ.pop("ST_ENABLE_DEPLOYMENTS_RUNTIME", None)
        else:
            os.environ["ST_ENABLE_DEPLOYMENTS_RUNTIME"] = prev_enable
        if prev_allow is None:
            os.environ.pop("ST_ENABLE_DEPLOYMENTS_RUNTIME_UNDER_PYTEST", None)
        else:
            os.environ["ST_ENABLE_DEPLOYMENTS_RUNTIME_UNDER_PYTEST"] = prev_allow
        if prev_mode is None:
            os.environ.pop("ST_DEPLOYMENTS_RUNTIME_MODE", None)
        else:
            os.environ["ST_DEPLOYMENTS_RUNTIME_MODE"] = prev_mode
