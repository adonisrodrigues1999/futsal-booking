from io import StringIO
import sys

from django.test import SimpleTestCase
from django.test import override_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from unittest.mock import patch

from config.settings import env_secret, env_text
from config import startup


class EnvHelpersTests(SimpleTestCase):
    def test_env_text_strips_whitespace(self):
        with patch("os.getenv", return_value="  FootBook  "):
            self.assertEqual(env_text("EMAIL_SENDER_NAME"), "FootBook")

    def test_env_secret_removes_whitespace(self):
        with patch("os.getenv", return_value="hozw frdx mjpu sefz"):
            self.assertEqual(env_secret("EMAIL_HOST_PASSWORD"), "hozwfrdxmjpusefz")

    def test_check_email_config_reports_summary(self):
        stream = StringIO()

        call_command("check_email_config", stdout=stream)

        self.assertIn("Email config: backend=", stream.getvalue())

    @override_settings(DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_check_email_config_warns_in_production(self):
        stream = StringIO()

        with self.assertRaises(CommandError):
            call_command("check_email_config", stdout=stream)

        self.assertIn("Production is using console email backend", stream.getvalue())

    @override_settings(DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_check_email_config_fails_in_production(self):
        with self.assertRaises(CommandError):
            call_command("check_email_config", stdout=StringIO())

    @patch("config.startup.subprocess.check_call")
    @patch("config.startup.os.execvp")
    @patch("config.startup.os.getenv", return_value="9000")
    def test_startup_invokes_manage_commands_and_gunicorn(self, mocked_getenv, mocked_execvp, mocked_check_call):
        startup.main()

        mocked_check_call.assert_any_call([sys.executable, "manage.py", "migrate", "--noinput"])
        mocked_check_call.assert_any_call([sys.executable, "manage.py", "collectstatic", "--noinput"])
        mocked_execvp.assert_called_once_with(
            "gunicorn",
            ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:9000"],
        )
