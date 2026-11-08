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


def test_fibonacci_decision_run_arguments_parse(monkeypatch):
    import main

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--symbols",
            "BTCUSDT",
            "--model-names",
            "typesafe/jev-1.13",
            "--prompt-files",
            "prompts/fibonacci_decision.txt",
            "--preprocessors",
            "fibonacci",
            "--iterations",
            "1",
        ],
    )

    args = main.parse_arguments()

    assert args.model_names == ["typesafe/jev-1.13"]
    assert args.prompt_files == ["prompts/fibonacci_decision.txt"]
    assert args.preprocessors == ["fibonacci"]
    assert args.iterations == 1


def test_direct_jev_model_uses_typesafe_key_without_openrouter_key(monkeypatch):
    import main

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "typesafe-test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--model-names",
            "typesafe/jev-1.13",
        ],
    )

    args = main.parse_arguments()

    assert args.model_names == ["typesafe/jev-1.13"]


def test_jev_without_fibonacci_prints_feature_guidance(monkeypatch, capsys):
    import main

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--symbols",
            "BTCUSDT",
            "--model-names",
            "typesafe/jev-1.13",
            "--iterations",
            "1",
        ],
    )

    args = main.parse_arguments()

    assert args.preprocessors == ["none"]
    warning = capsys.readouterr().out
    assert "expects Fibonacci levels" in warning
    assert "default chat prompt is not suitable for Jev" in warning


def test_llm_plugin_and_production_skill_parse(monkeypatch):
    import main

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--inference-plugin",
            "model",
            "--inference-skill",
            "risk_first",
            "--preprocessors",
            "fibonacci",
            "none",
        ],
    )

    args = main.parse_arguments()

    assert args.inference_plugin == "model"
    assert args.inference_skill == "risk_first"
    assert args.preprocessors == ["fibonacci", "none"]


def test_model_plugin_parses_with_market_structure_skill_and_supported_preprocessors(monkeypatch):
    import backtesting.backtest as backtest

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backtest.py",
            "--inference-plugin",
            "model",
            "--inference-skill",
            "market_structure",
            "--preprocessors",
            "fibonacci",
            "none",
        ],
    )

    args = backtest.parse_arguments()

    assert args.inference_plugin == "model"
    assert args.inference_skill == "market_structure"
    assert args.preprocessors == ["fibonacci", "none"]


def test_backtest_jev_without_fibonacci_prints_feature_guidance(monkeypatch, capsys):
    import backtesting.backtest as backtest

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backtest.py",
            "--model-names",
            "typesafe/jev-1.13",
        ],
    )

    args = backtest.parse_arguments()

    assert args.preprocessors == ["none"]
    warning = capsys.readouterr().out
    assert "expects Fibonacci levels" in warning
    assert "default chat prompt is not suitable for Jev" in warning


def test_backtest_direct_jev_model_uses_typesafe_key_without_openrouter_key(monkeypatch):
    import backtesting.backtest as backtest

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "typesafe-test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backtest.py",
            "--model-names",
            "typesafe/jev-1.13",
        ],
    )

    args = backtest.parse_arguments()

    assert args.model_names == ["typesafe/jev-1.13"]
