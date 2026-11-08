import os
import subprocess
import sys
from pathlib import Path


def test_dotenv_api_key_overrides_process_environment(tmp_path):
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=dotenv-test-key\nTYPESAFE_API_KEY=dotenv-typesafe-key\n",
        encoding="utf-8",
    )
    project_root = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        "OPENROUTER_API_KEY": "stale-process-key",
        "TYPESAFE_API_KEY": "stale-typesafe-key",
        "PYTHONPATH": str(project_root),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config; print(config.OPENROUTER_API_KEY); print(config.TYPESAFE_API_KEY)",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.splitlines() == ["dotenv-test-key", "dotenv-typesafe-key"]
