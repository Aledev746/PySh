import os
import tempfile
import unittest
from io import StringIO

from app.main import JOBS, execute_builtin, lex, parse, parse_job, run_command, wait_builtin


class LexerTests(unittest.TestCase):
    def test_quotes_and_expansion(self):
        os.environ["PYSH_TEST_VALUE"] = "hello world"
        self.assertEqual(
            lex("""echo '$PYSH_TEST_VALUE' "$PYSH_TEST_VALUE" $PYSH_TEST_VALUE"""),
            ["echo", "$PYSH_TEST_VALUE", "hello world", "hello", "world"],
        )

    def test_operators_without_spaces(self):
        self.assertEqual(lex("echo hi>out|cat"), ["echo", "hi", ">", "out", "|", "cat"])

    def test_default_parameter_and_tilde_expansion(self):
        os.environ.pop("PYSH_MISSING_VALUE", None)
        self.assertEqual(lex("echo ${PYSH_MISSING_VALUE:-fallback}"), ["echo", "fallback"])
        self.assertEqual(lex("echo ~/project")[0:2], ["echo", os.path.expanduser("~") + "/project"])


class ParserTests(unittest.TestCase):
    def test_pipeline_and_redirects(self):
        commands = parse("printf hi 2>errors | tr h H")
        self.assertEqual([command.argv for command in commands], [["printf", "hi"], ["tr", "h", "H"]])
        self.assertEqual(commands[0].redirects[0].fd, 2)

    def test_syntax_error(self):
        with self.assertRaises(ValueError):
            parse("echo |")

    def test_background_marker(self):
        commands, background = parse_job("sleep 0.01 &")
        self.assertTrue(background)
        self.assertEqual(commands[0].argv, ["sleep", "0.01"])


class BuiltinTests(unittest.TestCase):
    def test_echo(self):
        output = StringIO()
        self.assertEqual(execute_builtin(["echo", "-n", "hello"], output, StringIO()), 0)
        self.assertEqual(output.getvalue(), "hello")

    def test_cd_changes_parent_process(self):
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(run_command(parse(f"cd {directory}")), 0)
            self.assertEqual(os.getcwd(), directory)
        os.chdir(original)

    def test_pipeline(self):
        status = run_command(parse("printf hello | tr a-z A-Z"))
        self.assertEqual(status, 0)

    def test_background_job_can_be_waited(self):
        commands, background = parse_job("sleep 0.01 &")
        self.assertTrue(background)
        self.assertEqual(run_command(commands, "sleep 0.01 &", background), 0)
        self.assertTrue(JOBS)
        self.assertEqual(wait_builtin([], StringIO()), 0)
        self.assertFalse(JOBS)


if __name__ == "__main__":
    unittest.main()