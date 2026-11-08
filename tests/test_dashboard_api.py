import json
import subprocess
import threading
import time
from http.client import HTTPConnection
from urllib.parse import urlparse

import matplotlib
matplotlib.use('Agg')

from dashboard.app import Handler, ThreadingHTTPServer, ROOT
import ml_builder.ml_data as ml
from engine.plot import plot_data


def start_server():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def stop_server(server):
    server.shutdown(); server.server_close()


def test_ml_api_endpoints(tmp_path):
    # isolate dataset
    original = ml.DATA_FILE
    ml.DATA_FILE = tmp_path / 'dataset.jsonl'
    server, port = start_server()
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        # append
        payload = {"symbol": "API_TEST", "predicted_label": "up"}
        conn.request('POST', '/api/ml-data', body=json.dumps(payload), headers={'Content-Type': 'application/json'})
        resp = conn.getresponse(); assert resp.status == 200
        data = json.loads(resp.read())
        assert data.get('ok') is True
        rec = data.get('record')
        assert rec and rec.get('symbol') == 'API_TEST'

        # list
        conn.request('GET', '/api/ml-data')
        resp = conn.getresponse(); assert resp.status == 200
        lst = json.loads(resp.read())
        assert isinstance(lst, list)

        # export
        conn.request('GET', '/api/ml-data/export')
        resp = conn.getresponse(); assert resp.status == 200
        exported = json.loads(resp.read())
        assert 'records' in exported

        # update
        rid = rec.get('id')
        upd = {'id': rid, 'updates': {'ground_truth': 'up'}}
        conn.request('POST', '/api/ml-data/update', body=json.dumps(upd), headers={'Content-Type': 'application/json'})
        resp = conn.getresponse(); assert resp.status == 200
        ud = json.loads(resp.read())
        assert ud.get('ok') is True

    finally:
        conn.close()
        stop_server(server)
        ml.DATA_FILE = original


def test_dashboard_can_use_selected_symbol_from_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / 'request.json').write_text(json.dumps({
        'symbol': 'BTCUSDT',
        'time_frame': '1h',
        'llm_payload': {'market': {'symbol': 'BTCUSDT', 'current_time_frame': '1h'}, 'price_history': []},
    }), encoding='utf-8')
    (cache_dir / 'crypto_ETHUSDT.json').write_text(json.dumps({
        'symbol': 'ETHUSDT',
        'time_frame': '1h',
        'candles': [{'time': '2026-08-03 00:00:00', 'close': 123.45}],
    }), encoding='utf-8')

    monkeypatch.setattr('dashboard.app.ROOT', tmp_path)
    import dashboard.app as dashboard_app

    monkeypatch.setattr(dashboard_app, '_build_live_symbol_payload', lambda symbol, interval=None: {
        'symbol': symbol,
        'time_frame': interval or '1m',
        'candles': [],
        'market': {'symbol': symbol, 'current_time_frame': interval or '1m', 'current_price': None, 'price': None},
        'latest': {},
    })

    data = dashboard_app.dashboard_data('ETHUSDT')

    assert data['market']['symbol'] == 'ETHUSDT'
    assert data['market']['price'] == 123.45
    assert 'ETHUSDT' in data['available_symbols']


def test_dashboard_falls_back_to_live_payload_when_cache_missing(tmp_path, monkeypatch):
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / 'request.json').write_text(json.dumps({
        'symbol': 'BTCUSDT',
        'time_frame': '1h',
        'llm_payload': {'market': {'symbol': 'BTCUSDT', 'current_time_frame': '1h'}, 'price_history': []},
    }), encoding='utf-8')

    monkeypatch.setattr('dashboard.app.ROOT', tmp_path)
    import dashboard.app as dashboard_app

    monkeypatch.setattr(dashboard_app, '_build_live_symbol_payload', lambda symbol, interval=None: {
        'symbol': symbol,
        'time_frame': interval or '1h',
        'candles': [{'time': '2026-08-03 00:00:00', 'close': 99.0, 'rsi': 55.5, 'macd_hist': 1.2}],
        'market': {'symbol': symbol, 'current_time_frame': interval or '1h', 'current_price': 99.0, 'price': 99.0},
        'latest': {'time': '2026-08-03 00:00:00', 'close': 99.0, 'rsi': 55.5, 'macd_hist': 1.2},
    })

    data = dashboard_app.dashboard_data('ETHUSDT')

    assert data['market']['symbol'] == 'ETHUSDT'
    assert data['market']['price'] == 99.0
    assert data['market']['rsi'] == 55.5
    assert data['market']['macd'] == 1.2


def test_dashboard_uses_one_minute_live_interval_for_live_market_data(tmp_path, monkeypatch):
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / 'request.json').write_text(json.dumps({
        'symbol': 'BTCUSDT',
        'time_frame': '1h',
        'llm_payload': {'market': {'symbol': 'BTCUSDT', 'current_time_frame': '1h'}, 'price_history': []},
    }), encoding='utf-8')

    monkeypatch.setattr('dashboard.app.ROOT', tmp_path)
    import dashboard.app as dashboard_app

    calls = []

    def fake_build(symbol, interval=None):
        calls.append((symbol, interval))
        return {
            'symbol': symbol,
            'time_frame': interval or '1m',
            'candles': [{'time': '2026-08-03 00:00:00', 'close': 11.25, 'rsi': 60.0, 'macd_hist': 0.4}],
            'market': {'symbol': symbol, 'current_time_frame': interval or '1m', 'current_price': 11.25, 'price': 11.25},
            'latest': {'time': '2026-08-03 00:00:00', 'close': 11.25, 'rsi': 60.0, 'macd_hist': 0.4},
        }

    monkeypatch.setattr(dashboard_app, '_build_live_symbol_payload', fake_build)

    data = dashboard_app.dashboard_data('ETHUSDT')

    assert calls == [('ETHUSDT', '1m')]
    assert data['market']['interval'] == '1m'
    assert data['market']['price'] == 11.25


def test_dashboard_does_not_fetch_when_symbol_is_not_configured(tmp_path, monkeypatch):
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / 'request.json').write_text(json.dumps({
        'llm_payload': {'market': {}, 'price_history': []},
    }), encoding='utf-8')

    monkeypatch.setattr('dashboard.app.ROOT', tmp_path)
    import dashboard.app as dashboard_app

    def fail_live_fetch(*args, **kwargs):
        raise AssertionError('live fetch should be skipped without a symbol')

    monkeypatch.setattr(dashboard_app, '_build_live_symbol_payload', fail_live_fetch)
    monkeypatch.setattr(dashboard_app, '_refresh_web_context', fail_live_fetch)

    data = dashboard_app.dashboard_data(refresh=True)

    assert data['market']['symbol'] == '-'
    assert data['news'] == []


def test_dashboard_exposes_latest_telegram_message_from_run_output(tmp_path, monkeypatch):
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / 'request.json').write_text(json.dumps({
        'symbol': 'BTCUSDT',
        'time_frame': '1h',
        'llm_payload': {'market': {'symbol': 'BTCUSDT', 'current_time_frame': '1h'}, 'price_history': []},
    }), encoding='utf-8')

    monkeypatch.setattr('dashboard.app.ROOT', tmp_path)
    import dashboard.app as dashboard_app

    original_run = dashboard_app.RUN.copy()
    dashboard_app.RUN = {
        **original_run,
        'mode': 'live',
        'status': 'Completed',
        'output': [
            '[TELEGRAM_MESSAGE] {"status": "sent", "message": "<b>BTCUSDT</b>\n🟢 <b>UP</b> | Conf: <b>0.87</b>"}'
        ],
    }

    try:
        data = dashboard_app.dashboard_data('BTCUSDT')
        assert data['telegram']['status'] == 'sent'
        assert '<b>BTCUSDT</b>' in data['telegram']['message']
        assert '🟢' in data['telegram']['message']
    finally:
        dashboard_app.RUN = original_run


def test_plot_data_handles_nested_llm_payload_cache(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    request_payload = {
        'symbol': 'BTCUSDT',
        'time_frame': '1h',
        'llm_payload': {
            'market': {'symbol': 'BTCUSDT'},
            'price_history': [
                {'time': '2024-01-01T00:00:00Z', 'open': 100.0, 'high': 105.0, 'low': 99.0, 'close': 103.0, 'volume': 50.0},
                {'time': '2024-01-01T01:00:00Z', 'open': 103.0, 'high': 106.0, 'low': 101.0, 'close': 104.0, 'volume': 60.0},
                {'time': '2024-01-01T02:00:00Z', 'open': 104.0, 'high': 108.0, 'low': 102.0, 'close': 107.0, 'volume': 70.0},
                {'time': '2024-01-01T03:00:00Z', 'open': 107.0, 'high': 110.0, 'low': 105.0, 'close': 109.0, 'volume': 75.0},
            ],
        },
    }
    (cache_dir / 'request.json').write_text(json.dumps(request_payload), encoding='utf-8')

    output = plot_data(111.0, 90.0, 2, '1h', 'BTCUSDT')

    assert output.endswith('BTCUSDT_1h_price.png')
    assert (cache_dir / 'BTCUSDT_1h_price.png').exists()


def test_dashboard_defaults_cover_backtest_cli_surface():
    server, port = start_server()
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        conn.request('GET', '/api/defaults')
        resp = conn.getresponse()
        assert resp.status == 200
        defaults = json.loads(resp.read())

        expected = {
            'symbols', 'lookback', 'limit', 'interval', 'step', 'iterations',
            'model_names', 'prompt_files', 'n', 'higher_timeframes', 'indicators',
            'inference_plugin', 'inference_skill',
            'preprocessors',
            'max_expected_time', 'token_limit', 'input_token_price', 'output_token_price',
            'max_cost', 'output_dir', 'quant_enabled', 'quant_input_data', 'quant_indicators', 'quant_model',
            'quant_models', 'quant_target_mode', 'quant_direction_threshold',
            'quant_transform', 'quant_output_target', 'quant_shift', 'quant_predict_rows',
            'web_search_enabled', 'web_search_aspects', 'web_search_extra_terms',
            'web_search_topics', 'web_search_max_results', 'web_search_sites'
        }
        missing = sorted(expected - defaults.keys())
        assert not missing, f'Missing dashboard defaults: {missing}'
        assert defaults['lookback'] == defaults['limit']
        assert defaults['preprocessors'] == ['none']
    finally:
        conn.close()
        stop_server(server)


def test_dashboard_settings_store_direct_typesafe_key(tmp_path, monkeypatch):
    import dashboard.app as dashboard_app

    monkeypatch.setattr(dashboard_app, 'ENV_PATH', tmp_path / '.env')
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    server, port = start_server()
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        body = json.dumps({'typesafe_api_key': 'typesafe-test-key'}).encode()
        conn.request(
            'POST',
            '/api/settings',
            body=body,
            headers={'Content-Type': 'application/json'},
        )
        response = conn.getresponse()
        assert response.status == 200
        response.read()
        assert 'TYPESAFE_API_KEY=typesafe-test-key' in (tmp_path / '.env').read_text()

        conn.request('GET', '/api/settings')
        response = conn.getresponse()
        settings = json.loads(response.read())
        assert settings['typesafe_api_key'] == 'typesafe-test-key'
    finally:
        conn.close()
        stop_server(server)


def test_live_run_command_uses_unbuffered_python_output():
    import dashboard.app as dashboard_app

    payload = {'symbols': 'BTCUSDT', 'interval': '1h', 'limit': 400}
    command = dashboard_app.build_live(payload)

    assert command[:3] == [dashboard_app.sys.executable, '-u', 'main.py']


def test_dashboard_model_plugin_requires_openrouter_key(monkeypatch):
    import dashboard.app as dashboard_app

    monkeypatch.setattr(dashboard_app, 'has_openrouter_key', lambda: False)
    payload = {
        'symbols': 'BTCUSDT',
        'inference_plugin': 'model',
        'inference_skill': 'default',
    }

    assert 'OpenRouter API key is required' in dashboard_app.validate_run_payload(payload, 'live')
    monkeypatch.setattr(dashboard_app, 'has_openrouter_key', lambda: True)
    assert dashboard_app.validate_run_payload(payload, 'live') is None
    live_command = dashboard_app.build_live(payload)
    backtest_command = dashboard_app.build_backtest(payload)
    assert live_command[live_command.index('--inference-plugin') + 1] == 'model'
    assert live_command[live_command.index('--inference-skill') + 1] == 'default'
    assert backtest_command[backtest_command.index('--inference-plugin') + 1] == 'model'
    assert backtest_command[backtest_command.index('--inference-skill') + 1] == 'default'


def test_dashboard_direct_jev_uses_typesafe_key_automatically(monkeypatch):
    import dashboard.app as dashboard_app

    monkeypatch.setattr(dashboard_app, 'has_openrouter_key', lambda: False)
    monkeypatch.setattr(dashboard_app, 'has_typesafe_key', lambda: True)
    payload = {
        'symbols': 'BTCUSDT',
        'inference_plugin': 'model',
        'model_names': 'typesafe/jev-1.13',
    }

    assert dashboard_app.validate_run_payload(payload, 'live') is None
    live_command = dashboard_app.build_live(payload)
    backtest_command = dashboard_app.build_backtest(payload)
    for command in (live_command, backtest_command):
        assert '--jev-provider' not in command


def test_dashboard_commands_include_preprocessor_selection():
    import dashboard.app as dashboard_app

    payload = {
        'symbols': 'BTCUSDT',
        'inference_plugin': 'model',
        'preprocessors': 'fibonacci, none',
    }
    live_command = dashboard_app.build_live(payload)
    backtest_command = dashboard_app.build_backtest(payload)
    for command in (live_command, backtest_command):
        index = command.index('--preprocessors')
        assert command[index + 1:index + 3] == ['fibonacci', 'none']


def test_dashboard_launch_message_reports_selected_extensions(monkeypatch):
    import dashboard.app as dashboard_app

    class DummyProcess:
        def poll(self):
            return None

    class DummyThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(dashboard_app, 'RUN', {'process': None})
    monkeypatch.setattr(dashboard_app.subprocess, 'Popen', lambda *args, **kwargs: DummyProcess())
    monkeypatch.setattr(dashboard_app.threading, 'Thread', DummyThread)
    monkeypatch.setattr(dashboard_app, 'set_stop_request', lambda *args: None)
    monkeypatch.setattr(dashboard_app, 'has_openrouter_key', lambda: True)

    ok, message = dashboard_app.launch({
        'symbols': ['BTCUSDT'],
        'inference_plugin': 'model',
        'inference_skill': 'risk_first',
        'preprocessors': 'fibonacci, none',
    }, 'live')

    assert ok is True
    assert (
        '[extensions] Inference plugin: model | Inference skill: risk_first | '
        'Preprocessors: fibonacci, none | Prompt: default | Provider: OpenRouter'
    ) in message


def test_dashboard_launch_message_reports_prompt_and_automatic_jev_provider(monkeypatch):
    import dashboard.app as dashboard_app

    class DummyProcess:
        def poll(self):
            return None

    class DummyThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(dashboard_app, 'RUN', {'process': None})
    monkeypatch.setattr(dashboard_app.subprocess, 'Popen', lambda *args, **kwargs: DummyProcess())
    monkeypatch.setattr(dashboard_app.threading, 'Thread', DummyThread)
    monkeypatch.setattr(dashboard_app, 'set_stop_request', lambda *args: None)
    monkeypatch.setattr(dashboard_app, 'has_typesafe_key', lambda: True)
    monkeypatch.setattr(dashboard_app, 'has_openrouter_key', lambda: False)

    ok, message = dashboard_app.launch({
        'symbols': ['BTCUSDT'],
        'inference_plugin': 'model',
        'model_names': 'typesafe/jev-1.13',
        'prompt_files': 'prompts/fibonacci_decision.txt',
        'preprocessors': 'fibonacci',
    }, 'live')

    assert ok is True
    assert 'Prompt: prompts/fibonacci_decision.txt' in message
    assert 'Provider: TypeSafe direct API' in message


def test_extension_catalog_lists_plugins_and_documented_skills():
    server, port = start_server()
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        conn.request('GET', '/api/extensions')
        response = conn.getresponse()
        assert response.status == 200
        catalog = json.loads(response.read())['extensions']
        entries = {(item['kind'], item['name']): item for item in catalog}

        assert ('inference', 'model') in entries
        assert {name for kind, name in entries if kind == 'inference'} == {'model'}
        assert ('preprocessor', 'fibonacci') in entries
        assert ('preprocessor', 'price_change') in entries
        assert {name for kind, name in entries if kind == 'preprocessor'} == {
            'none', 'fibonacci', 'price_change'
        }
        assert ('skill', 'default') in entries
        assert 'General market-analysis guidance' in entries[('skill', 'default')]['description']
        assert ('skill', 'risk_first') in entries
        assert ('skill', 'market_structure') in entries
        assert ('skill', 'test') not in entries
        assert 'Jev via TypeSafe/OpenRouter decisions' in entries[('inference', 'model')]['compatibility']
        assert 'GenAI' in entries[('skill', 'risk_first')]['compatibility']
        assert 'Model-agnostic' in entries[('preprocessor', 'fibonacci')]['compatibility']
        assert 'Fibonacci' in entries[('preprocessor', 'fibonacci')]['readme']
        assert 'price_change' in entries[('preprocessor', 'price_change')]['readme']
    finally:
        conn.close()
        stop_server(server)


def test_saved_configs_are_persisted_on_disk(tmp_path, monkeypatch):
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr('dashboard.app.ROOT', tmp_path)
    import dashboard.app as dashboard_app

    dashboard_app.SAVED_CONFIGS_PATH = tmp_path / 'cache' / 'saved_configs.json'
    server, port = start_server()
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        payload = {'configs': [{'name': 'persisted-config', 'symbols': 'BTCUSDT', 'interval': '1h'}]}
        conn.request('POST', '/api/saved-configs', body=json.dumps(payload), headers={'Content-Type': 'application/json'})
        resp = conn.getresponse()
        assert resp.status == 200
        body = json.loads(resp.read())
        assert body['ok'] is True
        assert body['configs'][0]['name'] == 'persisted-config'

        conn.request('GET', '/api/saved-configs')
        resp = conn.getresponse()
        assert resp.status == 200
        stored = json.loads(resp.read())
        assert stored['configs'][0]['name'] == 'persisted-config'
        assert dashboard_app.SAVED_CONFIGS_PATH.exists()
        on_disk = json.loads(dashboard_app.SAVED_CONFIGS_PATH.read_text(encoding='utf-8'))
        assert on_disk[0]['symbols'] == 'BTCUSDT'
    finally:
        conn.close()
        stop_server(server)


def test_cap_stopped_backtest_is_reported_as_stopped_not_failed(monkeypatch):
    import dashboard.app as dashboard_app

    original_run = dashboard_app.RUN.copy()
    dashboard_app.RUN = {
        'process': None,
        'mode': 'backtest',
        'status': 'Running',
        'started_at': '2026-01-01T00:00:00+00:00',
        'finished_at': None,
        'command': [],
        'output': [],
        'error': None,
        'exit_code': None,
        'progress': {'current': 0, 'total': 0, 'percent': 0.0},
        'stopped_reason': None,
    }

    class DummyProcess:
        stdout = iter([
            '[progress] BTCUSDT 3/3\n',
            'Token limit (1500000) exceeded, stopping backtest.\n',
        ])

        def wait(self):
            return 0

    try:
        dashboard_app.consume(DummyProcess())
        assert dashboard_app.RUN['status'] == 'Stopped'
        assert 'token limit' in (dashboard_app.RUN['error'] or '').lower()
    finally:
        dashboard_app.RUN = original_run


def test_stop_active_process_marks_run_as_stopping_before_exit():
    import dashboard.app as dashboard_app

    original_run = dashboard_app.RUN.copy()

    class DummyProcess:
        def __init__(self):
            self.calls = []
            self._poll = None
        def poll(self):
            return self._poll
        def terminate(self):
            self.calls.append('terminate')
        def kill(self):
            self.calls.append('kill')
            self._poll = 0

    process = DummyProcess()
    dashboard_app.RUN = {
        'process': process,
        'mode': 'live',
        'status': 'Running',
        'started_at': '2026-01-01T00:00:00+00:00',
        'finished_at': None,
        'command': [],
        'output': [],
        'error': None,
        'exit_code': None,
        'progress': {'current': 0, 'total': 0, 'percent': 0.0},
        'symbol_progress': {},
        'total_progress_seen': False,
    }

    try:
        ok, message = dashboard_app.stop_active_process()
        assert ok is True
        assert message == 'Stop signal sent.'
        assert dashboard_app.RUN['status'] == 'Stopping'
        assert dashboard_app.RUN['error'] in {None, 'Stopping…'} or 'stopp' in (dashboard_app.RUN['error'] or '').lower()
        assert process.calls == []
    finally:
        dashboard_app.RUN = original_run


def test_stop_active_process_uses_loop_exit_signal_without_killing_process():
    import dashboard.app as dashboard_app

    original_run = dashboard_app.RUN.copy()

    class DummyProcess:
        def __init__(self):
            self.calls = []
            self._poll = None
        def poll(self):
            return self._poll
        def terminate(self):
            self.calls.append('terminate')
        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd='dummy', timeout=timeout)
            return 0
        def kill(self):
            self.calls.append('kill')
            self._poll = 0

    process = DummyProcess()
    dashboard_app.RUN = {
        'process': process,
        'mode': 'backtest',
        'status': 'Running',
        'started_at': '2026-01-01T00:00:00+00:00',
        'finished_at': None,
        'command': [],
        'output': [],
        'error': None,
        'exit_code': None,
        'progress': {'current': 0, 'total': 0, 'percent': 0.0},
        'symbol_progress': {},
        'total_progress_seen': False,
    }

    try:
        ok, message = dashboard_app.stop_active_process()
        assert ok is True
        assert message == 'Stop signal sent.'
        assert dashboard_app.RUN['status'] == 'Stopping'
        assert process.calls == []
    finally:
        dashboard_app.RUN = original_run


def test_backtest_progress_aggregates_all_symbols_total_steps():
    import dashboard.app as dashboard_app

    original_run = dashboard_app.RUN.copy()
    dashboard_app.RUN = {
        'process': None,
        'mode': 'backtest',
        'status': 'Running',
        'started_at': '2026-01-01T00:00:00+00:00',
        'finished_at': None,
        'command': [],
        'output': [],
        'error': None,
        'exit_code': None,
        'progress': {'current': 0, 'total': 0, 'percent': 0.0},
        'symbol_progress': {},
        'total_progress_seen': False,
    }

    try:
        dashboard_app.log('[progress] TOTAL 5/10')
        dashboard_app.log('[progress] BTCUSDT 2/5')
        dashboard_app.log('[progress] ETHUSDT 3/5')
        assert dashboard_app.RUN['progress'] == {'current': 5, 'total': 10, 'percent': 50.0}
    finally:
        dashboard_app.RUN = original_run


def test_backtest_progress_total_is_stable_for_multi_symbol_runs():
    import dashboard.app as dashboard_app

    original_run = dashboard_app.RUN.copy()
    dashboard_app.RUN = {
        'process': None,
        'mode': 'backtest',
        'status': 'Running',
        'started_at': '2026-01-01T00:00:00+00:00',
        'finished_at': None,
        'command': [],
        'output': [],
        'error': None,
        'exit_code': None,
        'progress': {'current': 0, 'total': 0, 'percent': 0.0},
        'symbol_progress': {},
        'total_progress_seen': False,
    }

    try:
        dashboard_app.log('[progress] TOTAL 2/10')
        dashboard_app.log('[progress] BTCUSDT 2/5')
        dashboard_app.log('[progress] ETHUSDT 0/5')
        assert dashboard_app.RUN['progress'] == {'current': 2, 'total': 10, 'percent': 20.0}
        dashboard_app.log('[progress] TOTAL 4/10')
        dashboard_app.log('[progress] BTCUSDT 4/5')
        dashboard_app.log('[progress] ETHUSDT 0/5')
        assert dashboard_app.RUN['progress'] == {'current': 4, 'total': 10, 'percent': 40.0}
    finally:
        dashboard_app.RUN = original_run


def test_backtest_progress_prefers_total_progress_over_symbol_progress():
    import dashboard.app as dashboard_app

    original_run = dashboard_app.RUN.copy()
    dashboard_app.RUN = {
        'process': None,
        'mode': 'backtest',
        'status': 'Running',
        'started_at': '2026-01-01T00:00:00+00:00',
        'finished_at': None,
        'command': [],
        'output': [],
        'error': None,
        'exit_code': None,
        'progress': {'current': 2, 'total': 10, 'percent': 20.0},
        'symbol_progress': {'BTCUSDT': {'current': 3, 'total': 5}, 'ETHUSDT': {'current': 2, 'total': 5}},
        'total_progress_seen': True,
    }

    try:
        dashboard_app.log('[progress] TOTAL 2/10')
        dashboard_app.log('[progress] BTCUSDT 3/5')
        dashboard_app.log('[progress] ETHUSDT 2/5')
        assert dashboard_app.RUN['progress'] == {'current': 2, 'total': 10, 'percent': 20.0}
    finally:
        dashboard_app.RUN = original_run


def test_launch_resets_total_progress_at_start_of_new_test():
    import dashboard.app as dashboard_app

    original_run = dashboard_app.RUN.copy()
    dashboard_app.RUN = {
        'process': None,
        'mode': 'backtest',
        'status': 'Completed',
        'started_at': '2026-01-01T00:00:00+00:00',
        'finished_at': '2026-01-01T00:05:00+00:00',
        'command': [],
        'output': ['old output'],
        'error': None,
        'exit_code': 0,
        'progress': {'current': 9, 'total': 10, 'percent': 90.0},
        'symbol_progress': {'BTCUSDT': {'current': 9, 'total': 10}},
        'total_progress_seen': True,
    }

    class DummyProcess:
        stdout = iter([])

        def poll(self):
            return None

        def wait(self):
            return 0

    def fake_popen(command, cwd, text, stdout, stderr, env, encoding, errors):
        return DummyProcess()

    try:
        monkeypatch = __import__('pytest').MonkeyPatch()
        monkeypatch.setattr(dashboard_app.subprocess, 'Popen', fake_popen)
        result, _ = dashboard_app.launch({
            'symbols': 'BTCUSDT,ETHUSDT',
            'lookback': 50,
            'interval': '1m',
            'step': 5,
            'n': 10,
            'max_expected_time': 5,
            'token_limit': 1000,
            'input_token_price': 0.0,
            'output_token_price': 0.0,
            'max_cost': 0.0,
            'output_dir': 'backtest_results',
            'quant_shift': 1,
            'quant_predict_rows': 1,
            'quant_direction_threshold': 0.0,
        }, 'backtest')
        assert result is True
        assert dashboard_app.RUN['progress'] == {'current': 0, 'total': 0, 'percent': 0.0}
        assert dashboard_app.RUN['symbol_progress'] == {}
        assert dashboard_app.RUN['total_progress_seen'] is False
        monkeypatch.undo()
    finally:
        dashboard_app.RUN = original_run
