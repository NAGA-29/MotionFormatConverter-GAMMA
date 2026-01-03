import unittest
import tracemalloc
from unittest.mock import patch, MagicMock, call
from app.utils.memory_profiler import init_memory_profiling, log_memory_snapshot

class TestMemoryProfiler(unittest.TestCase):

    @patch('tracemalloc.start')
    @patch('app.utils.memory_profiler.logger')
    def test_init_memory_profiling(self, mock_logger, mock_tracemalloc_start):
        """
        init_memory_profilingがtracemallocを開始し、メッセージをログに記録することをテストします。
        """
        init_memory_profiling()
        mock_tracemalloc_start.assert_called_once()
        mock_logger.info.assert_called_with("Memory profiling started with tracemalloc.")

    @patch('tracemalloc.take_snapshot')
    @patch('app.utils.memory_profiler.logger')
    def test_log_memory_snapshot(self, mock_logger, mock_take_snapshot):
        """
        log_memory_snapshotがスナップショットを取得し、上位の統計をログに記録することをテストします。
        """
        # スナップショットとその統計をモック化します
        mock_snapshot = MagicMock()
        mock_stat = "mock_stat_line"
        mock_snapshot.statistics.return_value = [mock_stat] * 5 # 5つの統計をシミュレート
        mock_take_snapshot.return_value = mock_snapshot

        log_memory_snapshot()

        mock_take_snapshot.assert_called_once()
        mock_snapshot.statistics.assert_called_with('lineno')

        # ロガーが正しいメッセージで呼び出されたことを確認します
        expected_calls = [
            call("Top 10 memory usage stats:"),
            call(mock_stat),
            call(mock_stat),
            call(mock_stat),
            call(mock_stat),
            call(mock_stat),
        ]
        mock_logger.info.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(mock_logger.info.call_count, 6)


    def tearDown(self):
        # テスト後にtracemallocが実行中の場合は停止します
        if tracemalloc.is_tracing():
            tracemalloc.stop()

if __name__ == '__main__':
    unittest.main()
