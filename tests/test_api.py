from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _auth() -> dict[str, str]:
    return {"X-Access-Token": "test-token"}


def test_mock_end_to_end_download_guard(tmp_path: Path) -> None:
    old = {
        "data_dir": settings.data_dir,
        "app_access_token": settings.app_access_token,
        "ugc_renderer_mode": settings.ugc_renderer_mode,
        "max_session_hours": settings.max_session_hours,
    }
    settings.data_dir = tmp_path / "data"
    settings.app_access_token = "test-token"
    settings.ugc_renderer_mode = "mock"
    settings.max_session_hours = 999.0

    try:
        with TestClient(app) as client:
            for owner in ("Mehmet", "Joshua"):
                response = client.post(
                    "/api/jobs",
                    headers=_auth(),
                    data={
                        "owner": owner,
                        "renderer": "ltx25",
                        "prompt": f"{owner} UGC smoke test",
                        "duration": "4",
                        "variations": "1",
                    },
                    files={"start_frame": ("start.png", b"mock-image", "image/png")},
                )
                assert response.status_code == 200, response.text

            deadline = time.time() + 20
            jobs = []
            while time.time() < deadline:
                jobs = client.get("/api/jobs", headers=_auth()).json()["jobs"]
                if len(jobs) >= 2 and all(j["status"] == "complete" for j in jobs[:2]):
                    break
                time.sleep(0.2)

            assert len(jobs) >= 2
            assert all(j["status"] == "complete" for j in jobs[:2])
            assert {j["owner"] for j in jobs[:2]} == {"Mehmet", "Joshua"}
            assert all(j["output_raw"] is None for j in jobs[:2])

            preview = client.get(
                f"/api/jobs/{jobs[0]['id']}/video", params={"token": "test-token"}
            )
            assert preview.status_code == 200
            assert preview.headers["content-type"].startswith("video/mp4")

            guarded = client.post("/api/session/terminate", headers=_auth())
            assert guarded.status_code == 409
            detail = guarded.json()["detail"]
            assert detail["active_jobs"] == 0
            assert detail["undownloaded_outputs"] >= 2

            ids = ",".join(j["id"] for j in jobs[:2])
            bundle = client.get(
                "/api/download.zip", params={"ids": ids, "token": "test-token"}
            )
            assert bundle.status_code == 200
            assert bundle.headers["content-type"] == "application/zip"
            assert len(bundle.content) > 1024

            session = client.get("/api/session", headers=_auth()).json()
            assert session["active_jobs"] == 0
            assert session["undownloaded_outputs"] == 0

            terminated = client.post("/api/session/terminate", headers=_auth())
            assert terminated.status_code == 200
            assert terminated.json()["mock"] is True
    finally:
        settings.data_dir = old["data_dir"]
        settings.app_access_token = old["app_access_token"]
        settings.ugc_renderer_mode = old["ugc_renderer_mode"]
        settings.max_session_hours = old["max_session_hours"]
