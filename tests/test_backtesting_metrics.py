import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

from backtesting.backtest import (
    compute_business_metrics,
    binary_brier_score,
    compute_llm_performance_metrics,
    compute_model_brier_metrics,
    compute_inference_latency_metrics,
    evaluate_trade_outcome,
    model_brier_probability,
    save_results,
    winning_llm_response,
)


class BacktestingMetricsTests(unittest.TestCase):
    def test_binary_brier_score_uses_target_before_stop_event(self):
        self.assertAlmostEqual(binary_brier_score(0.8, "success"), 0.04)
        self.assertAlmostEqual(binary_brier_score(0.8, "failure"), 0.64)
        self.assertAlmostEqual(binary_brier_score(0.8, "timeout"), 0.64)

    def test_brier_probability_uses_success_probability_for_jev_and_confidence_for_chat(self):
        response = {
            "confidence": 0.64,
            "trade_success_probability": 0.81,
        }

        self.assertEqual(
            model_brier_probability(response, "typesafe/jev-1.14"),
            0.81,
        )
        self.assertEqual(
            model_brier_probability(response, "openai/gpt-6-luna"),
            0.64,
        )

    def test_model_brier_metrics_average_window_scores_and_report_coverage(self):
        metrics = compute_model_brier_metrics(
            {"model-a": [0.04, 0.64]},
            {"model-a": Counter({"no_trade": 1, "ambiguous": 2})},
        )

        self.assertAlmostEqual(metrics["model-a"]["brier_score"], 0.34)
        self.assertEqual(metrics["model-a"]["scored_windows"], 2)
        self.assertEqual(metrics["model-a"]["excluded_no_trade"], 1)
        self.assertEqual(metrics["model-a"]["excluded_ambiguous"], 2)
        self.assertIsNone(metrics.get("model-b", {}).get("brier_score"))

    def test_inference_latency_metrics_report_count_mean_median_and_p95(self):
        metrics = compute_inference_latency_metrics({
            "model-b": [0.1, 0.2, 0.3, 1.0],
            "model-a": [],
        })

        self.assertEqual(metrics["model-b"]["request_count"], 4)
        self.assertAlmostEqual(metrics["model-b"]["mean_seconds"], 0.4)
        self.assertAlmostEqual(metrics["model-b"]["median_seconds"], 0.25)
        self.assertAlmostEqual(metrics["model-b"]["p95_seconds"], 1.0)
        self.assertNotIn("model-a", metrics)

    def test_save_results_includes_run_level_inference_latency(self):
        latency_metrics = {
            "model-a": {
                "request_count": 2,
                "mean_seconds": 0.3,
                "median_seconds": 0.3,
                "p95_seconds": 0.5,
            }
        }
        with tempfile.TemporaryDirectory() as output_dir:
            save_results({
                "total_tokens": 0,
                "inference_latency_by_model": latency_metrics,
            }, output_dir)
            summary = json.loads(
                (Path(output_dir) / "summary.json").read_text(encoding="utf-8")
            )

        self.assertEqual(summary["inference_latency_by_model"], latency_metrics)

    def test_trade_outcome_uses_first_touched_barrier(self):
        future = pd.DataFrame([
            {"high": 104, "low": 99},
            {"high": 111, "low": 98},
        ])

        outcome, return_pct = evaluate_trade_outcome(
            future, "up", entry_price=100, target_price=110, stop_loss=95
        )

        self.assertEqual(outcome, "success")
        self.assertAlmostEqual(return_pct, 10.0)

    def test_trade_outcome_marks_same_candle_barrier_crossing_ambiguous(self):
        future = pd.DataFrame([{"high": 111, "low": 94}])

        outcome, return_pct = evaluate_trade_outcome(
            future, "up", entry_price=100, target_price=110, stop_loss=95
        )

        self.assertEqual(outcome, "ambiguous")
        self.assertEqual(return_pct, 0.0)

    def test_compute_business_metrics(self):
        trades = [
            {"outcome": "success", "return_pct": 10.0, "expected_time": 2},
            {"outcome": "failure", "return_pct": -5.0, "expected_time": 3},
            {"outcome": "success", "return_pct": 20.0, "expected_time": 4},
        ]

        metrics = compute_business_metrics(trades)

        self.assertAlmostEqual(metrics["win_rate"], 2 / 3)
        self.assertAlmostEqual(metrics["profit_factor"], 6.0)
        self.assertAlmostEqual(metrics["avg_win"], 15.0)
        self.assertAlmostEqual(metrics["avg_loss"], -5.0)
        self.assertAlmostEqual(metrics["average_trade_duration"], 3.0)
        self.assertAlmostEqual(metrics["max_drawdown"], 5.0)

    def test_compute_business_metrics_excludes_ambiguous_trades_from_win_rate(self):
        metrics = compute_business_metrics([
            {"outcome": "success", "return_pct": 10.0, "expected_time": 2},
            {"outcome": "ambiguous", "return_pct": 0.0, "expected_time": 3},
        ])

        self.assertAlmostEqual(metrics["win_rate"], 1.0)
        self.assertAlmostEqual(metrics["average_trade_duration"], 2.0)

    def test_compute_llm_performance_metrics(self):
        windows = [
            {
                "status": "agree",
                "outcome": "success",
                "confidence": 0.8,
                "responses": [
                    {"scenario": "up", "confidence": 0.8, "entry_price": 100, "target_price": 110, "stop_loss": 95, "expected_time": 3},
                    {"scenario": "up", "confidence": 0.7, "entry_price": 101, "target_price": 111, "stop_loss": 94, "expected_time": 4},
                ],
            },
            {
                "status": "agree",
                "outcome": "failure",
                "confidence": 0.6,
                "responses": [
                    {"scenario": "down", "confidence": 0.6, "entry_price": 100, "target_price": 90, "stop_loss": 105, "expected_time": 3},
                    {"scenario": "down", "confidence": 0.6, "entry_price": 100, "target_price": 90, "stop_loss": 105, "expected_time": 3},
                ],
            },
            {"status": "disagree", "responses": [{"scenario": "up"}, {"scenario": "down"}]},
            {"status": "no_trade", "responses": [{"scenario": "no_trade"}, {"scenario": "no_trade"}]},
        ]

        metrics = compute_llm_performance_metrics(windows, iterations=2)

        self.assertAlmostEqual(metrics["agreement_ratio"], 2 / 3)
        self.assertAlmostEqual(metrics["direction_accuracy"], 1 / 2)
        self.assertAlmostEqual(metrics["confidence_calibration_error"], 0.4)
        self.assertGreater(metrics["decision_stability"], 0.0)
        self.assertLess(metrics["decision_stability"], 1.0)

    def test_single_iteration_llm_agreement_is_perfect(self):
        windows = [
            {
                "status": "agree",
                "outcome": "success",
                "confidence": 75,
                "responses": [
                    {"scenario": "up", "confidence": 75, "entry_price": 100, "target_price": 110, "stop_loss": 95, "expected_time": 3}
                ],
            }
        ]

        metrics = compute_llm_performance_metrics(windows, iterations=1)

        self.assertAlmostEqual(metrics["agreement_ratio"], 1.0)
        self.assertAlmostEqual(metrics["direction_accuracy"], 1.0)
        self.assertAlmostEqual(metrics["confidence_calibration_error"], 0.25)
        self.assertAlmostEqual(metrics["decision_stability"], 1.0)

    def test_decision_model_outcome_calibration_uses_trade_success_probability(self):
        metrics = compute_llm_performance_metrics([
            {
                "status": "agree",
                "outcome": "success",
                "confidence": 0.2,
                "trade_success_probability": 0.8,
                "responses": [],
            }
        ], iterations=1)

        self.assertAlmostEqual(metrics["confidence_calibration_error"], 0.2)

    def test_winning_llm_response_uses_majority_vote(self):
        response, status = winning_llm_response([
            {"scenario": "up", "confidence": 0.6},
            {"scenario": "down", "confidence": 0.9},
            {"scenario": "up", "confidence": 0.8},
        ])

        self.assertEqual(status, "agree")
        self.assertEqual(response["scenario"], "up")
        self.assertAlmostEqual(response["confidence"], 0.8)

    def test_winning_llm_response_rejects_tie(self):
        response, status = winning_llm_response([
            {"scenario": "up", "confidence": 0.6},
            {"scenario": "down", "confidence": 0.9},
        ])

        self.assertIsNone(response)
        self.assertEqual(status, "disagree")


if __name__ == "__main__":
    unittest.main()
