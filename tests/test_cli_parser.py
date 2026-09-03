import sys


def test_parse_arguments_accepts_prompt_files(monkeypatch):
    import main

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--symbols",
            "BTCUSDT",
            "--prompt-files",
            "prompts/long.txt",
            "prompts/short.txt",
        ],
    )

    args = main.parse_arguments()

    assert args.prompt_files == ["prompts/long.txt", "prompts/short.txt"]
