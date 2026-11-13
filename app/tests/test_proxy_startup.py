"""Proxy regressions: loopback/temporary data only; never change Windows settings."""
import http.client
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import proxy_engine as module

POPEN = subprocess.Popen


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='naw proxy á 试 ')
        self.root = Path(self.temp.name)
        locations = {
            'DATA_DIR': self.root, 'OVERRIDES_DIR': self.root / 'overrides',
            'ACTIVE_PAYLOAD_PATH': self.root / 'payload.txt',
            'LOGS_FILE_PATH': self.root / 'logs.txt',
            'ADDON_SCRIPT_PATH': self.root / 'addon.py',
            'PAC_FILE_PATH': self.root / 'proxy.pac',
            'INTERCEPT_LIST_PATH': self.root / 'intercept.txt',
            'STATS_PATH': self.root / 'stats.json',
        }
        self.paths = patch.multiple(module, **locations)
        self.paths.start()
        self.engine = module.ProxyEngine(free_port())
        self.cert = patch.object(self.engine, 'ensure_cert', return_value=True)
        self.pac = patch.object(self.engine, 'set_system_proxy', return_value=True)
        self.diag = patch.object(self.engine, '_log_startup_diagnostics')
        self.cert.start()
        self.pac_mock = self.pac.start()
        self.diag.start()

    def tearDown(self):
        self.engine.stop()
        self.cert.stop()
        self.pac.stop()
        self.diag.stop()
        self.paths.stop()
        self.temp.cleanup()

    def child(self, code):
        def spawn(cmd, **kwargs):
            # Keep the real isolated/UTF-8 invocation, replace only its Python code.
            return POPEN(cmd[:cmd.index('-c') + 1] + [code], **kwargs)
        return patch.object(module.subprocess, 'Popen', side_effect=spawn)

    def listener(self, delay=0, lifetime=60):
        return (f'import socket,time; time.sleep({delay}); s=socket.socket(); '
                f's.bind(("127.0.0.1",{self.engine.port})); s.listen(); time.sleep({lifetime})')

    def test_occupied_port_does_not_change_network(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', self.engine.port))
            sock.listen()
            self.assertFalse(self.engine.start())
        self.assertIn(str(self.engine.port), self.engine.last_error)
        self.pac_mock.assert_not_called()

    def test_missing_dependency_error_reaches_user(self):
        with self.child('raise ModuleNotFoundError("No module named mitmproxy")'):
            self.assertFalse(self.engine.start())
        self.assertIn('mitmproxy', self.engine.last_error)
        self.assertIn('Instalar.bat', self.engine.last_error)
        self.assertIsNone(self.engine.process)
        self.pac_mock.assert_not_called()

    def test_utf8_error_is_preserved(self):
        with self.child('import sys; print("PermissionError: acceso denegado á 试",file=sys.stderr); sys.exit(7)'):
            self.assertFalse(self.engine.start())
        self.assertIn('á 试', self.engine.last_error)
        self.assertIn('7', self.engine.last_error)

    def test_no_output_has_exit_code(self):
        with self.child('import sys; sys.exit(9)'):
            self.assertFalse(self.engine.start())
        self.assertIn('9', self.engine.last_error)
        self.assertIn('No emitió detalles', self.engine.last_error)

    def test_slow_start_over_three_seconds(self):
        with self.child(self.listener(delay=3.3)):
            self.assertTrue(self.engine.start())
        self.assertTrue(self.engine.is_running)
        self.assertIsNone(self.engine.last_error)

    def test_timeout_is_not_reported_as_early_exit(self):
        # Advance only the deadline clock; process waits are real and bounded.
        with self.child('import time; time.sleep(60)'), patch.object(module.time, 'monotonic', side_effect=[0, 21]):
            self.assertFalse(self.engine.start())
        self.assertIn('20 segundos', self.engine.last_error)
        self.assertNotIn('código None', self.engine.last_error)
        self.assertIsNone(self.engine.process)

    def test_bad_addon_is_reported_before_child_starts(self):
        def invalid():
            module.ADDON_SCRIPT_PATH.write_text('def broken(', encoding='utf8')
        with patch.object(self.engine, '_write_addon_script', side_effect=invalid), patch.object(module.subprocess, 'Popen') as spawn:
            self.assertFalse(self.engine.start())
            spawn.assert_not_called()
        self.assertIn('SyntaxError', self.engine.last_error)

    def test_certificate_failure_does_not_apply_pac(self):
        with patch.object(self.engine, 'ensure_cert', return_value=False):
            self.assertFalse(self.engine.start())
        self.pac_mock.assert_not_called()
        self.assertIn('certificado', self.engine.last_error)

    def test_pac_failure_reaps_child(self):
        self.pac_mock.return_value = False
        with self.child(self.listener()):
            self.assertFalse(self.engine.start())
        self.assertFalse(self.engine.is_running)
        self.assertIsNone(self.engine.process)
        self.assertIn('PAC', self.engine.last_error)

    def test_crash_after_start_restores_network(self):
        with self.child(self.listener(lifetime=0.6)):
            self.assertTrue(self.engine.start())
        deadline = time.monotonic() + 5
        while self.engine.is_running and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(self.engine.is_running)
        self.assertIsNone(self.engine.process)
        self.assertIn('código', self.engine.last_error)
        self.pac_mock.assert_any_call(False)

    def test_repeated_start_uses_same_process(self):
        with self.child(self.listener()) as spawn:
            self.assertTrue(self.engine.start())
            first = self.engine.process
            self.assertTrue(self.engine.start())
            self.assertIs(self.engine.process, first)
            self.assertEqual(spawn.call_count, 1)

    def test_real_mitmproxy_passes_local_http(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                data = b'naw-loopback-ok'
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def spawn(cmd, **kwargs):
            return POPEN(cmd + ['--set', 'confdir=' + str(self.root / 'certs')], **kwargs)
        try:
            # A hostile inherited PYTHONPATH must not shadow mitmproxy.
            shadow = self.root / 'shadow'
            shadow.mkdir()
            (shadow / 'mitmproxy.py').write_text('raise RuntimeError("shadowed")')
            with patch.dict(module.os.environ, {'PYTHONPATH': str(shadow)}), patch.object(module.subprocess, 'Popen', side_effect=spawn):
                self.assertTrue(self.engine.start(), self.engine.last_error)
            connection = http.client.HTTPConnection('127.0.0.1', self.engine.port, timeout=8)
            try:
                connection.request('GET', f'http://127.0.0.1:{server.server_port}/test')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b'naw-loopback-ok')
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.values = {'ProxyEnable': (1, module.winreg.REG_DWORD),
                       'ProxyServer': ('corp:3128', module.winreg.REG_SZ),
                       'AutoDetect': (1, module.winreg.REG_DWORD),
                       'AutoConfigURL': ('https://example.invalid/corp.pac', module.winreg.REG_SZ)}
        self.before = dict(self.values)
        self.engine = module.ProxyEngine.__new__(module.ProxyEngine)
        self.engine._proxy_settings = None
        self.engine._applied_pac_url = None
        self.engine.port = 8080
        self.engine.log = lambda *a: None
        self.patches = [patch.object(module.winreg, 'OpenKey', return_value=object()),
                        patch.object(module.winreg, 'CloseKey'),
                        patch.object(module.winreg, 'QueryValueEx', side_effect=self.query),
                        patch.object(module.winreg, 'SetValueEx', side_effect=self.write),
                        patch.object(module.winreg, 'DeleteValue', side_effect=self.delete),
                        patch.object(self.engine, '_refresh_wininet'),
                        patch.object(self.engine, '_start_pac_server', return_value=True),
                        patch.object(self.engine, '_stop_pac_server'),
                        patch.object(self.engine, '_pac_url', return_value='http://127.0.0.1:5500/proxy.pac?t=1')]
        for item in self.patches:
            item.start()
    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
    def query(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]
    def write(self, key, name, reserved, kind, value):
        self.values[name] = (value, kind)
    def delete(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]
    def test_restore_exact_settings_and_absent_values(self):
        self.assertTrue(self.engine.set_system_proxy(True))
        self.assertTrue(self.engine.set_system_proxy(False))
        self.assertEqual(self.values, self.before)
    def test_preserve_external_network_change(self):
        self.assertTrue(self.engine.set_system_proxy(True))
        self.values['AutoConfigURL'] = ('https://example.invalid/new.pac', module.winreg.REG_SZ)
        modified = dict(self.values)
        self.assertTrue(self.engine.set_system_proxy(False))
        self.assertEqual(self.values, modified)
    def test_foreign_proxy_is_not_reported_as_naw_pac(self):
        self.assertFalse(self.engine.is_system_proxy_enabled())
        self.assertTrue(self.engine.set_system_proxy(True))
        self.assertTrue(self.engine.is_system_proxy_enabled())
        self.assertTrue(self.engine.set_system_proxy(False))
        self.assertFalse(self.engine.is_system_proxy_enabled())
    def test_refresh_updates_ownership_and_still_restores_settings(self):
        self.assertTrue(self.engine.set_system_proxy(True))
        self.engine.is_running = True
        self.engine.pac_port = 5500
        self.engine._pac_server = None
        with patch.object(self.engine, '_write_pac_file', return_value=b''), patch.object(module, 'list_intercept_swfs', return_value=[]), patch.object(self.engine, '_pac_url', return_value='http://127.0.0.1:5500/proxy.pac?t=2'):
            self.engine.refresh_pac()
        self.assertEqual(self.engine._applied_pac_url, 'http://127.0.0.1:5500/proxy.pac?t=2')
        self.assertTrue(self.engine.set_system_proxy(False))
        self.assertEqual(self.values, self.before)
    def test_refresh_does_not_overwrite_external_pac(self):
        self.assertTrue(self.engine.set_system_proxy(True))
        self.engine.is_running = True
        self.engine.pac_port = 5500
        self.engine._pac_server = None
        self.values['AutoConfigURL'] = ('https://example.invalid/new.pac', module.winreg.REG_SZ)
        modified = dict(self.values)
        with patch.object(self.engine, '_write_pac_file', return_value=b''), patch.object(module, 'list_intercept_swfs', return_value=[]):
            self.engine.refresh_pac()
        self.assertEqual(self.values, modified)
    def test_partial_failure_rolls_back(self):
        real_write = self.write
        failed = False
        def fail_once(key, name, reserved, kind, value):
            nonlocal failed
            if name == 'AutoConfigURL' and not failed:
                failed = True
                raise PermissionError('denied')
            real_write(key, name, reserved, kind, value)
        with patch.object(module.winreg, 'SetValueEx', side_effect=fail_once):
            self.assertFalse(self.engine.set_system_proxy(True))
        self.assertEqual(self.values, self.before)


if __name__ == '__main__':
    unittest.main()
