import sys
import unittest
from core.tool_output import run_text_tool


class ToolOutputTests(unittest.TestCase):
    def test_utf8_and_windows_output(self):
        text = 'L’été : facture et quantité'
        for encoding in ('utf-8', 'cp1252'):
            with self.subTest(encoding=encoding):
                command = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(' + repr(text.encode(encoding)) + ')']
                self.assertEqual(run_text_tool(command), text)

    def test_legacy_stderr_does_not_break_valid_stdout(self):
        command = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(b"Pages: 2"); sys.stderr.buffer.write(' + repr('L’outil'.encode('cp1252')) + ')']
        self.assertEqual(run_text_tool(command), 'Pages: 2')

    def test_failure_preserves_legacy_diagnostic(self):
        command = [sys.executable, '-c', 'import sys; sys.stderr.buffer.write(' + repr('L’accès refusé'.encode('cp1252')) + '); sys.exit(1)']
        with self.assertRaisesRegex(RuntimeError, 'L’accès refusé'):
            run_text_tool(command)
