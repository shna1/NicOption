import unittest

import pandas as pd

from bambo_bot.forecast import backtest_copper, backtest_gold, backtest_silver


def model_frame(length=40):
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=length, freq="D"),
        "price": [100 + index for index in range(length)],
        "bubble_zscore": [0.5] * length,
        "volume_zscore_bucket": [0] * length,
        "bubble_zscore_bucket": [5] * length,
    })


class ForecastBacktestTests(unittest.TestCase):
    def test_gold_executes_signal_from_next_day(self):
        frame = model_frame()
        frame.loc[1, "bubble_zscore"] = -0.6
        frame.loc[2:3, "bubble_zscore"] = -0.2
        frame.loc[4, "bubble_zscore"] = 0.1
        result = backtest_gold(frame)
        self.assertEqual(result.loc[1, "signal"], "buy")
        self.assertEqual(result.loc[1, "position"], 0)
        self.assertEqual(result.loc[2, "position"], 1)
        self.assertEqual(result.loc[4, "signal"], "sell")
        self.assertEqual(result.loc[5, "position"], 0)

    def test_copper_exits_after_ten_rows_in_trade(self):
        frame = model_frame()
        frame.loc[1, "volume_zscore_bucket"] = 8
        result = backtest_copper(frame)
        self.assertEqual(result.loc[1, "signal"], "buy")
        self.assertEqual(result.loc[11, "signal"], "sell")
        self.assertEqual(int((result["signal"] == "buy").sum()), 1)

    def test_silver_uses_joint_entry_and_bubble_exit(self):
        frame = model_frame()
        frame.loc[2, ["bubble_zscore_bucket", "volume_zscore_bucket"]] = [4, 6]
        frame.loc[6, "bubble_zscore_bucket"] = 7
        result = backtest_silver(frame)
        self.assertEqual(result.loc[2, "signal"], "buy")
        self.assertEqual(result.loc[6, "signal"], "sell")
        self.assertGreater(result["equity"].iloc[-1], 100_000_000)


if __name__ == "__main__":
    unittest.main()
