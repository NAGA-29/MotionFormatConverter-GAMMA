import unittest
import tracemalloc
from unittest.mock import patch, MagicMock, call
from app.utils.memory_profiler import init_memory_profiling, log_memory_snapshot, TOP_MEMORY_STATS_COUNT

class TestMemoryProfiler(unittest.TestCase):

    def setUp(self):
        # 各テストの前にtracemallocが停止していることを確認します
        if tracemalloc.is_tracing():
            tracemalloc.stop()

    def tearDown(self):
        # テスト後にtracemallocが実行中の場合は停止します
        if tracemalloc.is_tracing():
            tracemalloc.stop()

    @patch('app.utils.memory_profiler.logger')
    def test_init_memory_profiling_starts_when_not_tracing(self, mock_logger):
        """
        tracemallocが実行中でない場合にinit_memory_profilingがそれを開始することをテストします。
        """
        self.assertFalse(tracemalloc.is_tracing())
        init_memory_profiling()
        self.assertTrue(tracemalloc.is_tracing())
        mock_logger.info.assert_called_with("Memory profiling started with tracemalloc.")

    @patch('app.utils.memory_profiler.logger')
    def test_init_memory_profiling_does_not_start_when_already_tracing(self, mock_logger):
        """
        tracemallocが既に実行中の場合にinit_memory_profilingが再度開始しないことをテストします。
        """
        tracemalloc.start()
        self.assertTrue(tracemalloc.is_tracing())
        init_memory_profiling()
        self.assertTrue(tracemalloc.is_tracing())
        mock_logger.warning.assert_called_with("tracemalloc is already running.")

    @patch('tracemalloc.take_snapshot')
    @patch('app.utils.memory_profiler.logger')
    def test_log_memory_snapshot_when_tracing(self, mock_logger, mock_take_snapshot):
        """
        tracemallocが実行中の場合にlog_memory_snapshotがスナップショットを記録することをテストします。
        """
        tracemalloc.start()
        mock_snapshot = MagicMock()
        mock_stat = "mock_stat_line"
        # TOP_MEMORY_STATS_COUNTより多い統計をシミュレート
        mock_snapshot.statistics.return_value = [mock_stat] * (TOP_MEMORY_STATS_COUNT + 5)
        mock_take_snapshot.return_value = mock_snapshot

        log_memory_snapshot()

        mock_take_snapshot.assert_called_once()
        mock_snapshot.statistics.assert_called_with('lineno')

        # ログメッセージが定数を使用していることを確認します
        expected_first_call = call(f"Top {TOP_MEMORY_STATS_COUNT} memory usage stats:")
        # 統計情報が正しい回数ログに記録されたことを確認します
        self.assertEqual(mock_logger.info.call_count, TOP_MEMORY_STATS_COUNT + 1)
        # 最初の呼び出しが期待通りであることを確認します
        self.assertEqual(mock_logger.info.call_args_list[0], expected_first_call)


    @patch('tracemalloc.take_snapshot')
    @patch('app.utils.memory_profiler.logger')
    def test_log_memory_snapshot_when_not_tracing(self, mock_logger, mock_take_snapshot):
        """
        tracemallocが実行中でない場合にlog_memory_snapshotが警告を記録することをテストします。
        """
        self.assertFalse(tracemalloc.is_tracing())
        log_memory_snapshot()
        mock_take_snapshot.assert_not_called()
        mock_logger.warning.assert_called_with("Cannot take memory snapshot because tracemalloc is not running.")

    @patch('tracemalloc.take_snapshot')
    @patch('app.utils.memory_profiler.logger')
    def test_log_memory_snapshot_handles_runtime_error(self, mock_logger, mock_take_snapshot):
        """
        take_snapshotがRuntimeErrorを発生させた場合にlog_memory_snapshotがエラーを記録することをテストします。
        """
        tracemalloc.start()
        error_message = "test error"
        mock_take_snapshot.side_effect = RuntimeError(error_message)

        log_memory_snapshot()

        mock_take_snapshot.assert_called_once()
        mock_logger.error.assert_called_with(f"Failed to take memory snapshot: {error_message}")


if __name__ == '__main__':
    unittest.main()
