import unittest
import subprocess
import sys


class TestCLI(unittest.TestCase):
    def test_cli_starts_successfully(self):
        """
        Test that the CLI starts up without syntax errors by running a simple command.
        """
        # We need to use the python executable from the current virtual environment
        python_executable = sys.executable
        result = subprocess.run(
            [python_executable, "-m", "tasklist.cli", "--version"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"CLI failed to start. Stderr: {result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
