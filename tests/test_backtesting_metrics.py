import unittest

from backtesting.backtest import compute_business_metrics, compute_llm_performance_metrics, winning_llm_response


class BacktestingMetricsTests(unittest.TestCase):
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
