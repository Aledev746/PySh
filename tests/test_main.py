import os
import tempfile
import unittest
from io import StringIO

from app.main import execute_builtin, lex, parse, run_command


class LexerTests(unittest.TestCase):
    def test_quotes_and_expansion(self):
        os.environ["PYSH_TEST_VALUE"] = "hello world"
        self.assertEqual(
            lex("""echo '$PYSH_TEST_VALUE' "$PYSH_TEST_VALUE" $PYSH_TEST_VALUE"""),
            ["echo", "$PYSH_TEST_VALUE", "hello world", "hello world"],
        )

    def test_operators_without_spaces(self):
        self.assertEqual(lex("echo hi>out|cat"), ["echo", "hi", ">", "out", "|", "cat"])


class ParserTests(unittest.TestCase):
    def test_pipeline_and_redirects(self):
        commands = parse("printf hi 2>errors | tr h H")
        self.assertEqual([command.argv for command in commands], [["printf", "hi"], ["tr", "h", "H"]])
        self.assertEqual(commands[0].redirects[0].fd, 2)

    def test_syntax_error(self):
        with self.assertRaises(ValueError):
            parse("echo |")


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


if __name__ == "__main__":
    unittest.main()