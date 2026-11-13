"""Exercise real Flask responses with network/game mutations replaced by mocks."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as web


class ProxyApiTests(unittest.TestCase):
    def test_start_returns_the_actual_failure(self):
        detail = 'El proxy terminó (código 7). Detalle: ModuleNotFoundError: mitmproxy'
        with patch.object(web.proxy_engine, 'start', return_value=False), patch.object(web.proxy_engine, 'last_error', detail), patch.object(web.proxy_engine, 'get_status', return_value={'running': False}):
            response = web.app.test_client().post('/api/proxy/start', json={}).get_json()
        self.assertFalse(response['ok'])
        self.assertEqual(response['error'], detail)

    def test_quick_start_returns_failure_without_launching_game(self):
        detail = 'No se puede usar el puerto local 8080'
        with patch.object(web.proxy_engine, 'get_payload', return_value='test payload'), patch.object(web.proxy_engine, 'log'), patch.object(web.trucador, 'cleanup_orphan_overrides', return_value=[]), patch.object(web.proxy_engine, 'get_status', return_value={'running': False}), patch.object(web.proxy_engine, 'start', return_value=False), patch.object(web.proxy_engine, 'last_error', detail), patch.object(web.game_launcher, 'wait_game_dead') as kill_game, patch.object(web.game_launcher, 'launch_game') as launch:
            response = web.app.test_client().post('/api/quick-start', json={}).get_json()
        self.assertFalse(response['ok'])
        self.assertEqual(response['error'], detail)
        kill_game.assert_not_called()
        launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
