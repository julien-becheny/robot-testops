"""Tests des liens Robot et de l'ouverture sécurisée des dossiers de rapports."""

from pathlib import Path
from unittest.mock import Mock
from urllib.parse import quote

import pytest

from api.app import app
from api.routes import execution_routes


@pytest.fixture
def report_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isole la racine des rapports et le registre local de routes."""
    report_root = tmp_path / "reports"
    report_root.mkdir()
    monkeypatch.setattr(execution_routes.paths, "REPORTS", report_root)
    execution_routes._session_log_dirs.clear()
    yield app.test_client(), report_root
    execution_routes._session_log_dirs.clear()


def _write_report(path: Path, content: str) -> Path:
    """Crée un fichier de rapport temporaire accessible par le client Flask."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_log_directory_keeps_same_event_for_valid_report(
    monkeypatch: pytest.MonkeyPatch,
    report_context,
) -> None:
    """Un dossier valide est mémorisé et diffusé avec l'événement historique."""
    client, report_root = report_context
    report_dir = report_root / "2026_07_27-120000"
    report_dir.mkdir()
    emit = Mock()
    update = Mock()
    monkeypatch.setattr(execution_routes, "_emit_to_session", emit)
    monkeypatch.setattr(execution_routes.registry, "update", update)

    response = client.post('/log-directory', json={
        'session_id': 'session-1',
        'log_directory': str(report_dir),
    })

    canonical = str(report_dir.resolve())
    assert response.status_code == 200
    assert execution_routes._session_log_dirs['session-1'] == canonical
    update.assert_called_once_with('session-1', log_directory=canonical)
    emit.assert_called_once_with(
        'log-directory',
        {'log_directory': canonical},
        'session-1',
    )


def test_log_link_event_contract_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    report_context,
) -> None:
    """Le nom et le payload de l'événement utilisé par les liens restent identiques."""
    client, _report_root = report_context
    emit = Mock()
    monkeypatch.setattr(execution_routes, "_emit_to_session", emit)

    response = client.post('/log-link', json={
        'session_id': 'session-1',
        'log_link': 'log_merge.html',
        'is_merged': True,
        'has_rerun': True,
    })

    assert response.status_code == 200
    emit.assert_called_once_with(
        'log-link',
        {
            'log_link': 'log_merge.html',
            'is_merged': True,
            'has_rerun': True,
        },
        'session-1',
    )


@pytest.mark.parametrize("directory_kind,route,filename", [
    ('standard', '/logs/session-1/standard/', 'log.html'),
    ('Output_original', '/logs/session-1/original/', 'log_original.html'),
    ('Output_merge', '/logs/session-1/merged/', 'log_merge.html'),
])
def test_robot_report_links_remain_accessible(
    report_context,
    directory_kind: str,
    route: str,
    filename: str,
) -> None:
    """Les rapports standard, original et fusionné restent servis par les mêmes URLs."""
    client, report_root = report_context
    report_dir = report_root / "run"
    target_dir = report_dir if directory_kind == 'standard' else report_dir / directory_kind
    _write_report(target_dir / filename, f"rapport {directory_kind}")
    execution_routes._session_log_dirs['session-1'] = str(report_dir)

    response = client.get(f"{route}{quote(filename)}")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == f"rapport {directory_kind}"


def test_log_directory_rejects_path_outside_report_root(
    monkeypatch: pytest.MonkeyPatch,
    report_context,
    tmp_path: Path,
) -> None:
    """Un chemin extérieur n'est ni mémorisé ni diffusé au frontend."""
    client, _report_root = report_context
    outside = tmp_path / "outside"
    outside.mkdir()
    emit = Mock()
    monkeypatch.setattr(execution_routes, "_emit_to_session", emit)

    response = client.post('/log-directory', json={
        'session_id': 'session-1',
        'log_directory': str(outside),
    })

    assert response.status_code == 400
    assert 'session-1' not in execution_routes._session_log_dirs
    emit.assert_not_called()


def test_log_directory_rejects_missing_directory(report_context) -> None:
    """Un dossier inexistant ne peut pas activer le bouton Dossier."""
    client, report_root = report_context

    response = client.post('/log-directory', json={
        'session_id': 'session-1',
        'log_directory': str(report_root / "absent"),
    })

    assert response.status_code == 400


def test_report_file_cannot_escape_session_directory(report_context) -> None:
    """Le nom de fichier ne peut pas remonter vers un autre dossier de rapports."""
    client, report_root = report_context
    report_dir = report_root / "run"
    report_dir.mkdir()
    _write_report(report_root / "secret.txt", "hors session")
    execution_routes._session_log_dirs['session-1'] = str(report_dir)

    response = client.get('/logs/session-1/standard/%2E%2E%2Fsecret.txt')

    assert response.status_code == 404
    assert "hors session" not in response.get_data(as_text=True)


def test_last_run_serves_the_log_the_report_links_to(report_context) -> None:
    """Robot lie rapport, log et captures en relatif : une racine commune les garde vivants."""
    client, report_root = report_context
    run_dir = report_root / "2026_08_24-120000"
    _write_report(run_dir / "output.xml", "<robot><suite name='S'/></robot>")
    _write_report(run_dir / "log.html", "journal du run")
    _write_report(run_dir / "browser" / "screenshot" / "fail-1.png", "capture")

    assert client.get('/last-run/log.html').get_data(as_text=True) == "journal du run"
    assert client.get('/last-run/browser/screenshot/fail-1.png').status_code == 200


def test_last_run_file_cannot_escape_the_run_directory(report_context) -> None:
    """La route prend un nom venu du client : il ne doit ouvrir que ce dossier."""
    client, report_root = report_context
    _write_report(report_root / "2026_08_24-120000" / "output.xml", "<robot/>")
    _write_report(report_root / "secret.txt", "hors du run")

    response = client.get('/last-run/%2E%2E%2Fsecret.txt')

    assert response.status_code == 404
    assert "hors du run" not in response.get_data(as_text=True)


def test_last_run_file_without_any_run(report_context) -> None:
    """Sans run joué, il n'y a pas de dossier à servir : le dire plutôt que planter."""
    client, _report_root = report_context

    assert client.get('/last-run/log.html').status_code == 404


def test_open_directory_uses_validated_path_without_powershell(
    monkeypatch: pytest.MonkeyPatch,
    report_context,
) -> None:
    """La route conserve son payload mais délègue l'ouverture au helper natif."""
    client, report_root = report_context
    report_dir = report_root / "run"
    report_dir.mkdir()
    execution_routes._session_log_dirs['session-1'] = str(report_dir)
    open_report = Mock()
    monkeypatch.setattr(execution_routes, "_open_report_directory", open_report)

    response = client.post('/open-directory', json={'session_id': 'session-1'})

    assert response.status_code == 200
    assert response.get_json()['directory'] == str(report_dir.resolve())
    open_report.assert_called_once_with(report_dir.resolve())


def test_windows_open_uses_os_startfile_not_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Windows ouvre le dossier sans PowerShell ni chaîne interprétée."""
    startfile = Mock()
    run = Mock()
    monkeypatch.setattr(execution_routes.platform, "system", Mock(return_value='Windows'))
    monkeypatch.setattr(execution_routes.os, "startfile", startfile, raising=False)
    monkeypatch.setattr(execution_routes.subprocess, "run", run)

    execution_routes._open_report_directory(tmp_path)

    startfile.assert_called_once_with(str(tmp_path))
    run.assert_not_called()