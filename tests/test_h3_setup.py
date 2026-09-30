import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest
from dotenv import dotenv_values

from app.config import settings
from app.h3 import gate_reason

ROOT = Path(__file__).resolve().parents[1]


def setup(path, *args):
    return subprocess.run([sys.executable, str(ROOT / "scripts/setup_h3.py"),
                           "--config", str(path), *args], text=True, capture_output=True)


def test_china_preparation_never_accepts_license_or_enables_execution(tmp_path):
    path = tmp_path / "h3.env"
    result = setup(path, "--operator-country", "CN", "--deployment-country", "CN")
    assert result.returncode == 0, result.stderr
    saved = dotenv_values(path)
    assert saved["H3_OPERATOR_REGION"] == saved["H3_ALLOWED_REGION"] == "CN"
    assert saved["H3_ENABLED"] == saved["H3_LICENSE_AUTHORIZED"] == "false"
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(result.stdout)["execution_enabled"] is False


def test_preparation_preserves_connection_and_requires_actual_acceptance(tmp_path):
    path = tmp_path / "h3.env"
    result = setup(path, "--operator-country", "CN", "--deployment-country", "CN",
                   "--volume-id", "example-volume")
    assert result.returncode == 0
    result = setup(path, "--accept-community-license")
    assert result.returncode == 0, result.stderr
    saved = dotenv_values(path)
    assert saved["H3_NETWORK_VOLUME_ID"] == "example-volume"
    assert saved["H3_LICENSE_AUTHORIZED"] == "true"
    assert saved["H3_LICENSE_MODE"] == "community"
    assert saved["H3_ENABLED"] == "false"


def test_excluded_deployment_cannot_be_accepted_as_community(tmp_path):
    path = tmp_path / "h3.env"
    result = setup(path, "--operator-country", "CN", "--deployment-country", "US",
                   "--accept-community-license")
    assert result.returncode != 0
    assert not path.exists()


def test_china_community_gate(monkeypatch):
    for name, value in {"h3_enabled": True, "h3_license_authorized": True,
                        "h3_license_mode": "community", "h3_operator_region": "CN",
                        "h3_allowed_region": "CN"}.items():
        monkeypatch.setattr(settings, name, value)
    assert gate_reason() is None
    monkeypatch.setattr(settings, "h3_allowed_region", "US")
    assert "excludes" in gate_reason()


def test_h3_cannot_allocate_with_unprepared_worker_image(monkeypatch):
    sys.path.insert(0, str(ROOT / "launcher"))
    import runpod_launcher
    for name, value in {"h3_enabled": True, "h3_license_authorized": True,
                        "h3_license_mode": "community", "h3_operator_region": "CN",
                        "h3_allowed_region": "CN", "h3_worker_image": ""}.items():
        monkeypatch.setattr(settings, name, value)
    create = Mock()
    monkeypatch.setattr(runpod_launcher.runpod, "create_pod", create)
    with pytest.raises(ValueError, match="prepared H3 worker"):
        runpod_launcher.launch_pod(api_key="fixture", image="normal-wan-image", model="h3-fl2va")
    create.assert_not_called()
