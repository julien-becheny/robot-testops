"""Tests unitaires du parsing et des notifications du rerun Robot Framework."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
import requests

from services.execution import rerun

VALID_OUTPUT = """<?xml version="1.0" encoding="UTF-8"?>
<robot>
  <suite name="Suite Démo">
    <test name="Test réussi"><status status="PASS" /></test>
    <test name="Test échoué"><status status="FAIL" /></test>
  </suite>
  <statistics><total><stat pass="1" fail="1" /></total></statistics>
</robot>
"""


def _write_output(path: Path, content: str = VALID_OUTPUT) -> Path:
    """Écrit un résultat Robot minimal dans le dossier temporaire du test."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_merge_sources(report_folder: Path) -> tuple[Path, Path]:
    """Crée les deux fichiers XML requis pour démarrer une fusion Rebot."""
    original = _write_output(
        report_folder / "Output_original" / "output_original.xml",
    )
    replay = _write_output(
        report_folder / "Output_rerun" / "output_rerun.xml",
    )
    return original, replay


def test_extract_failed_tests_returns_only_failed_names(tmp_path: Path) -> None:
    """Seuls les tests dont le statut est FAIL sont retournés."""
    output = _write_output(tmp_path / "output.xml")

    assert rerun.extract_failed_tests(str(output)) == ["Test échoué"]


def test_extract_failed_tests_rejects_missing_output(tmp_path: Path) -> None:
    """Un résultat original absent est distingué d'une exécution sans échec."""
    with pytest.raises(rerun.RerunOutputError, match="introuvable"):
        rerun.extract_failed_tests(str(tmp_path / "absent.xml"))


def test_extract_failed_tests_rejects_malformed_output(tmp_path: Path) -> None:
    """Un XML mal formé provoque une erreur métier explicite."""
    output = _write_output(tmp_path / "output.xml", "<robot><suite>")

    with pytest.raises(rerun.RerunOutputError, match="invalide"):
        rerun.extract_failed_tests(str(output))


def test_extract_final_status_builds_readable_summary(tmp_path: Path) -> None:
    """Les statistiques Robot sont converties en résumé français."""
    output = _write_output(tmp_path / "output.xml")

    assert rerun.extract_final_status(str(output)) == "2 tests : 1 passés, 1 échoués"


def test_extract_final_status_reports_invalid_xml(tmp_path: Path) -> None:
    """Un résultat fusionné inutilisable produit un statut d'erreur explicite."""
    output = _write_output(tmp_path / "output.xml", "<robot>")

    assert rerun.extract_final_status(str(output)) == "Erreur statut"


def test_invalid_original_output_does_not_publish_original_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Un output invalide abandonne le rerun sans annoncer un rapport valide."""
    notify_original = Mock()
    monkeypatch.setattr(rerun, "_notify_original_only", notify_original)

    rerun.rerun_failed_tests(str(tmp_path), "timestamp")

    notify_original.assert_not_called()


def test_valid_output_without_failure_publishes_original_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Une exécution valide sans échec publie normalement son rapport original."""
    output = _write_output(
        tmp_path / "Output_original" / "output_original.xml",
        VALID_OUTPUT.replace('status="FAIL"', 'status="PASS"'),
    )
    notify_original = Mock()
    monkeypatch.setattr(rerun, "_notify_original_only", notify_original)

    rerun.rerun_failed_tests(str(tmp_path), "timestamp", session_id="session-1")

    assert output.exists()
    notify_original.assert_called_once_with(str(tmp_path), "session-1")


def test_post_notification_checks_http_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une notification vérifie aussi les réponses HTTP non réussies."""
    response = Mock()
    post = Mock(return_value=response)
    monkeypatch.setattr(rerun.requests, "post", post)

    rerun._post_notification("/log-link", {"session_id": "session-1"})

    post.assert_called_once_with(
        f"{rerun.API_BASE_URL}/log-link",
        json={"session_id": "session-1"},
        timeout=3,
    )
    response.raise_for_status.assert_called_once_with()


def test_original_notification_failure_does_not_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une API indisponible n'interrompt pas le traitement du rerun."""
    monkeypatch.setattr(
        rerun,
        "_post_notification",
        Mock(side_effect=requests.ConnectionError("API indisponible")),
    )

    rerun._notify_original_only("rapport", "session-1")


def test_merged_notifications_publish_links_directory_and_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le rapport fusionné publie ses quatre informations dans l'ordre attendu."""
    post_notification = Mock()
    monkeypatch.setattr(rerun, "_post_notification", post_notification)
    monkeypatch.setattr(
        rerun, "extract_final_status", Mock(return_value="2 tests : 2 passés, 0 échoués")
    )
    monkeypatch.setattr(
        rerun,
        "extract_counts",
        Mock(return_value={'passed': 2, 'failed': 0, 'skipped': 0, 'total': 2}),
    )

    rerun._notify_merged_results("rapport", "fusion", "session-1", rerun_count=1)

    assert post_notification.call_args_list == [
        call('/log-link', {
            'log_link': 'log_original.html',
            'is_merged': False,
            'has_rerun': True,
            'session_id': 'session-1',
        }),
        call('/log-link', {
            'log_link': 'log_merge.html',
            'is_merged': True,
            'session_id': 'session-1',
        }),
        call('/log-directory', {
            'log_directory': 'rapport',
            'session_id': 'session-1',
        }),
        call('/final-status', {
            'status': '2 tests : 2 passés, 0 échoués',
            'is_merged': True,
            'session_id': 'session-1',
            'rerun': 1,
            'passed': 2,
            'failed': 0,
            'skipped': 0,
            'total': 2,
        }),
    ]


def test_counts_travel_as_numbers_not_as_a_sentence(tmp_path: Path) -> None:
    """L'interface doit lire un verdict, pas chercher des mots dans une phrase."""
    output = _write_output(tmp_path / "output.xml")

    assert rerun.extract_counts(str(output)) == {
        'passed': 1,
        'failed': 1,
        'skipped': 0,
        'total': 2,
    }


def test_counts_stay_neutral_when_the_result_is_unreadable(tmp_path: Path) -> None:
    """Un résultat illisible ne doit pas se traduire par un faux verdict vert."""
    output = _write_output(tmp_path / "output.xml", "<robot")

    assert rerun.extract_counts(str(output))['total'] == 0


def test_rerun_uses_safe_formatter_and_merges_remaining_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Un rerun rouge utilise l'affichage masqué puis conserve la fusion."""
    _write_output(tmp_path / "Output_original" / "output_original.xml")
    formatter = Mock(return_value="commande masquée")
    merge_outputs = Mock()
    monkeypatch.setattr(rerun, "format_rf_command_for_log", formatter)
    monkeypatch.setattr(rerun, "run_rf_command", Mock(return_value=1))
    monkeypatch.setattr(rerun, "_merge_outputs", merge_outputs)

    rerun.rerun_failed_tests(str(tmp_path), "timestamp")

    formatter.assert_called_once()
    # Le nombre de tests rejoues suit jusqu'a l'interface : un vert au 2e essai se dit.
    merge_outputs.assert_called_once_with(str(tmp_path), None, 1)


def test_rerun_technical_error_keeps_original_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Une erreur technique Robot empêche la fusion et conserve l'original."""
    _write_output(tmp_path / "Output_original" / "output_original.xml")
    merge_outputs = Mock()
    notify_original = Mock()
    monkeypatch.setattr(rerun, "run_rf_command", Mock(return_value=252))
    monkeypatch.setattr(rerun, "_merge_outputs", merge_outputs)
    monkeypatch.setattr(rerun, "_notify_original_only", notify_original)

    rerun.rerun_failed_tests(str(tmp_path), "timestamp", session_id="session-1")

    merge_outputs.assert_not_called()
    notify_original.assert_called_once_with(str(tmp_path), "session-1")


def test_merge_missing_sources_keeps_original_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Une fusion sans ses deux sources n'est pas présentée comme réussie."""
    notify_original = Mock()
    monkeypatch.setattr(rerun, "_notify_original_only", notify_original)

    result = rerun._merge_outputs(str(tmp_path), "session-1")

    assert result is False
    notify_original.assert_called_once_with(str(tmp_path), "session-1")


def test_merge_runs_rebot_as_argument_list_and_publishes_stable_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Rebot reçoit une liste d'arguments et un résultat stable est publié."""
    original, replay = _write_merge_sources(tmp_path)
    run = Mock(return_value=SimpleNamespace(returncode=0))
    notify_merged = Mock()
    monkeypatch.setattr(rerun.subprocess, "run", run)
    monkeypatch.setattr(rerun, "_wait_for_stable_files", Mock(return_value=True))
    monkeypatch.setattr(rerun, "_notify_merged_results", notify_merged)

    result = rerun._merge_outputs(str(tmp_path), "session-1")

    assert result is True
    command = run.call_args.args[0]
    assert command[:3] == [rerun.sys.executable, "-m", "robot.rebot"]
    assert command[-2:] == [str(original), str(replay)]
    notify_merged.assert_called_once_with(
        str(tmp_path),
        str(tmp_path / "Output_merge"),
        "session-1",
        0,
    )


def test_rebot_test_failures_still_publish_merged_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Un code Rebot de 1 à 250 produit un rapport rouge mais exploitable."""
    _write_merge_sources(tmp_path)
    notify_merged = Mock()
    monkeypatch.setattr(
        rerun.subprocess,
        "run",
        Mock(return_value=SimpleNamespace(returncode=2)),
    )
    monkeypatch.setattr(rerun, "_wait_for_stable_files", Mock(return_value=True))
    monkeypatch.setattr(rerun, "_notify_merged_results", notify_merged)

    result = rerun._merge_outputs(str(tmp_path), "session-1")

    assert result is True
    notify_merged.assert_called_once()


def test_unstable_merged_files_keep_original_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Un timeout de stabilité interdit la publication du rapport fusionné."""
    _write_merge_sources(tmp_path)
    notify_original = Mock()
    notify_merged = Mock()
    monkeypatch.setattr(
        rerun.subprocess,
        "run",
        Mock(return_value=SimpleNamespace(returncode=0)),
    )
    monkeypatch.setattr(rerun, "_wait_for_stable_files", Mock(return_value=False))
    monkeypatch.setattr(rerun, "_notify_original_only", notify_original)
    monkeypatch.setattr(rerun, "_notify_merged_results", notify_merged)

    result = rerun._merge_outputs(str(tmp_path), "session-1")

    assert result is False
    notify_original.assert_called_once_with(str(tmp_path), "session-1")
    notify_merged.assert_not_called()


def test_wait_for_stable_files_returns_true_without_real_wait(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Deux fichiers non vides dont la taille ne change plus sont déclarés stables."""
    merge_dir = tmp_path / "Output_merge"
    _write_output(merge_dir / "output_merge.xml")
    (merge_dir / "log_merge.html").write_text("rapport", encoding="utf-8")
    monkeypatch.setattr(rerun.time, "sleep", Mock())

    assert rerun._wait_for_stable_files(str(merge_dir), max_wait=2) is True


def test_wait_for_stable_files_handles_read_error_until_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Une erreur système de lecture est réessayée puis se termine par un timeout."""
    merge_dir = tmp_path / "Output_merge"
    _write_output(merge_dir / "output_merge.xml")
    (merge_dir / "log_merge.html").write_text("rapport", encoding="utf-8")
    monkeypatch.setattr(rerun.os.path, "getsize", Mock(side_effect=OSError("lecture impossible")))
    monkeypatch.setattr(rerun.time, "sleep", Mock())

    assert rerun._wait_for_stable_files(str(merge_dir), max_wait=2) is False