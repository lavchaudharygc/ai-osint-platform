import unittest
from pathlib import Path

from backend.core.config import BACKEND_ENV_FILE, Settings


class SettingsEnvironmentFileTests(unittest.TestCase):
    def test_runtime_environment_file_is_backend_dotenv(self) -> None:
        expected = Path(__file__).resolve().parents[1] / ".env"

        self.assertEqual(BACKEND_ENV_FILE, expected)
        self.assertEqual(Path(Settings.model_config["env_file"]), expected)
        self.assertEqual(BACKEND_ENV_FILE.name, ".env")
        self.assertNotEqual(BACKEND_ENV_FILE.name, ".env.example")


if __name__ == "__main__":
    unittest.main()
