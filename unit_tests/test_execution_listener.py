"""Verdict d'un run : ce que le listener compte, et ce qu'il transmet."""

from unittest.mock import Mock

import pytest

from robot_listeners.execution_listener import ExecutionListener


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Capte les notifications du listener sans réseau."""
    post = Mock(return_value=Mock())
    monkeypatch.setattr('robot_listeners.execution_listener.requests.post', post)
    return post


def _payloads(post: Mock, route: str) -> list[dict]:
    """Retourne les corps envoyés à une route donnée."""
    return [
        call.kwargs['json']
        for call in post.call_args_list
        if call.args[0].endswith(route)
    ]


def test_the_verdict_travels_as_numbers(sent: Mock) -> None:
    """Chercher « échoué » dans une phrase confond « 0 échoués » avec un échec."""
    listener = ExecutionListener('session-1')

    listener.end_test('A', {'status': 'PASS'})
    listener.end_test('B', {'status': 'FAIL', 'message': 'Timeout'})
    listener.end_test('C', {'status': 'PASS'})
    listener.end_suite('Suite', {'statistics': '3 tests, 2 passed, 1 failed'})

    status = _payloads(sent, '/final-status')[-1]
    assert (status['passed'], status['failed'], status['total']) == (2, 1, 3)


def test_a_skipped_test_is_not_counted_as_failed(sent: Mock) -> None:
    """Annoncer « a échoué » sur un test ignoré ferait chercher un défaut inexistant."""
    listener = ExecutionListener('session-1')

    listener.end_test('A', {'status': 'SKIP'})
    listener.end_suite('Suite', {'statistics': '1 test, 0 passed, 0 failed'})

    status = _payloads(sent, '/final-status')[-1]
    assert (status['passed'], status['failed'], status['skipped']) == (0, 0, 1)
    assert any('ignoré' in payload['message'] for payload in _payloads(sent, '/log'))


def test_progress_is_announced_after_each_test(sent: Mock) -> None:
    """Sans avancement, seul le chrono bouge : on ignore s'il reste un test ou dix."""
    listener = ExecutionListener('session-1')
    listener.start_suite('Racine', {'totaltests': 3})

    listener.end_test('A', {'status': 'PASS'})
    listener.end_test('B', {'status': 'FAIL'})

    assert _payloads(sent, '/progress') == [
        {'done': 1, 'total': 3, 'phase': 'run', 'session_id': 'session-1'},
        {'done': 2, 'total': 3, 'phase': 'run', 'session_id': 'session-1'},
    ]


def test_the_total_comes_from_the_root_suite(sent: Mock) -> None:
    """Les sous-suites annoncent leur propre compte : le total du run est le plus grand."""
    listener = ExecutionListener('session-1')
    listener.start_suite('Racine', {'totaltests': 5})
    listener.start_suite('Sous-suite', {'totaltests': 2})

    listener.end_test('A', {'status': 'PASS'})

    assert _payloads(sent, '/progress')[-1]['total'] == 5


def test_each_verdict_travels_with_its_full_name(sent: Mock) -> None:
    """La grille joint les configurations sur le nom complet : deux homonymes ne doivent pas fusionner."""
    listener = ExecutionListener('session-1')

    listener.end_test('Connexion', {
        'status': 'FAIL',
        'longname': 'Web.Saucedemo.00 Smoke.Connexion',
        'message': 'Timeout',
        'elapsedtime': 1200,
    })

    assert _payloads(sent, '/test-result') == [{
        'name': 'Connexion',
        'longname': 'Web.Saucedemo.00 Smoke.Connexion',
        'status': 'FAIL',
        'message': 'Timeout',
        'elapsed': 1200,
        'session_id': 'session-1',
    }]


def test_a_verdict_without_full_name_falls_back_on_the_test_name(sent: Mock) -> None:
    """Sans repli, un test dépourvu de nom complet n'aurait aucune clé de ligne."""
    listener = ExecutionListener('session-1')

    listener.end_test('Connexion', {'status': 'PASS'})

    assert _payloads(sent, '/test-result')[0]['longname'] == 'Connexion'


def test_a_skipped_test_travels_with_its_own_status(sent: Mock) -> None:
    """Confondre « ignoré » et « non joué » ferait passer une exclusion pour une absence."""
    listener = ExecutionListener('session-1')

    listener.end_test('A', {'status': 'SKIP', 'longname': 'Suite.A'})

    assert _payloads(sent, '/test-result')[0]['status'] == 'SKIP'


def test_the_run_name_stays_out_of_the_test_key(sent: Mock) -> None:
    """`-N` nomme le run d'après sa configuration : gardé dans la clé, chromium et
    firefox n'auraient jamais deux colonnes en face du même test."""
    listener = ExecutionListener('session-1')
    listener.start_suite('Smoke_Test_Firefox_Desktop', {
        'longname': 'Smoke_Test_Firefox_Desktop',
        'totaltests': 2,
    })

    listener.end_test('Connexion', {
        'status': 'PASS',
        'longname': 'Smoke_Test_Firefox_Desktop.Connexion',
    })

    assert _payloads(sent, '/test-result')[0]['longname'] == 'Connexion'


def test_the_key_keeps_the_suite_path_below_the_run(sent: Mock) -> None:
    """Seule la racine est retirée : le chemin restant sépare deux tests homonymes."""
    listener = ExecutionListener('session-1')
    listener.start_suite('Execution_Filtree_Chromium_Desktop', {
        'longname': 'Execution_Filtree_Chromium_Desktop',
    })
    listener.start_suite('02 Cart', {
        'longname': 'Execution_Filtree_Chromium_Desktop.Web.02 Cart',
    })

    listener.end_test('Panier', {
        'status': 'PASS',
        'longname': 'Execution_Filtree_Chromium_Desktop.Web.02 Cart.Panier',
    })

    assert _payloads(sent, '/test-result')[0]['longname'] == 'Web.02 Cart.Panier'


def _end(listener: ExecutionListener, name: str, **attrs) -> None:
    """Ferme un keyword comme Robot le ferait, avec ses attributs par defaut."""
    listener.end_keyword(name, {'kwname': name, 'type': 'KEYWORD', 'status': 'PASS', **attrs})


def _steps(post: Mock) -> list[tuple[str, str]]:
    return [
        (payload['message'], payload['level'])
        for payload in _payloads(post, '/log')
        if payload['level'].startswith('keyword')
    ]


def test_only_the_steps_written_in_the_test_are_reported(sent: Mock) -> None:
    """Chaque notification est un POST bloquant, et un test compte des milliers de
    keywords imbriques : remonter l'arbre entier ajouterait une minute au test."""
    listener = ExecutionListener('session-1')
    listener.start_test('Connexion', {})

    listener.start_keyword('Ouvrir le navigateur', {})
    _end(listener, 'Ouvrir le navigateur')

    # « Se connecter » appelle « Click », qui n'est pas ecrit dans le test.
    listener.start_keyword('Se connecter', {})
    listener.start_keyword('Click', {})
    _end(listener, 'Click')
    _end(listener, 'Se connecter', status='FAIL')

    assert _steps(sent) == [
        ('Ouvrir le navigateur', 'keyword'),
        ('Se connecter', 'keyword-failed'),
    ]


def test_control_structures_are_not_steps(sent: Mock) -> None:
    """Une boucle n'est pas une action : la compter noierait les etapes reelles."""
    listener = ExecutionListener('session-1')
    listener.start_test('Panier', {})

    listener.start_keyword('Ajouter au panier', {})
    _end(listener, 'Ajouter au panier')

    listener.start_keyword('FOR', {})
    _end(listener, '${article} IN @{articles}', type='FOR')

    assert _steps(sent) == [('Ajouter au panier', 'keyword')]


def test_a_keyword_outside_a_test_is_ignored(sent: Mock) -> None:
    """Le setup de suite se joue hors test : ses etapes n'appartiennent a aucun bloc."""
    listener = ExecutionListener('session-1')

    listener.start_keyword('Preparer la base', {})
    _end(listener, 'Preparer la base')

    assert _steps(sent) == []


def test_a_flood_of_steps_is_capped_once(sent: Mock) -> None:
    """Un test pathologique ne doit ni figer le run ni noyer l'ecran."""
    listener = ExecutionListener('session-1')
    listener.start_test('Long', {})

    for i in range(200):
        listener.start_keyword(f'Etape {i}', {})
        _end(listener, f'Etape {i}')

    steps = _steps(sent)
    assert len(steps) == 81
    assert steps[-1] == ('… etapes suivantes masquees', 'keyword')

