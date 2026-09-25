"""Démarrage de TestOps : ce qui doit attendre, et ce qui ne doit pas."""

import time
from unittest.mock import Mock

import pytest

from api import app as app_module


def test_the_port_does_not_wait_for_the_mobile_preflight(monkeypatch) -> None:
    """Le préflight interroge Node et Appium : à froid, il retardait l'ouverture du port."""
    started = []

    def _slow_preflight():
        started.append(time.perf_counter())
        time.sleep(0.4)

    monkeypatch.setattr(app_module, "_log_mobile_preflight", _slow_preflight)

    begin = time.perf_counter()
    thread = app_module._start_mobile_preflight()
    elapsed = time.perf_counter() - begin

    assert elapsed < 0.2
    thread.join(timeout=2)
    assert started, "le préflight doit tout de même avoir lieu"


def test_the_preflight_thread_never_holds_the_shutdown(monkeypatch) -> None:
    """Un préflight encore en cours ne doit pas empêcher TestOps de s'arrêter."""
    monkeypatch.setattr(app_module, "_log_mobile_preflight", lambda: time.sleep(5))

    thread = app_module._start_mobile_preflight()

    assert thread.daemon is True


def test_a_broken_mobile_chain_stays_a_log_line(monkeypatch) -> None:
    """Le mobile est optionnel : son indisponibilité ne remonte jamais au démarrage."""
    monkeypatch.setattr(
        "services.mobile.preflight.check_mobile_env",
        Mock(side_effect=OSError("adb absent")),
    )

    app_module._log_mobile_preflight()


@pytest.mark.parametrize("platform", ["Android", "iOS"])
def test_the_summary_is_logged_for_each_platform(monkeypatch, caplog, platform) -> None:
    """Le résumé arrive dans le log, même s'il arrive après l'ouverture du port."""
    monkeypatch.setattr(
        "services.mobile.preflight.check_mobile_env",
        Mock(return_value={"ok": True, "platform": platform, "checks": []}),
    )

    with caplog.at_level("INFO"):
        app_module._log_mobile_preflight()

    assert any(platform in message for message in caplog.messages)
