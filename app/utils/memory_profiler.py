import tracemalloc
from app.utils.logger import AppLogger

logger = AppLogger.get_logger(__name__)

TOP_MEMORY_STATS_COUNT = 10

def init_memory_profiling():
    """
    Initializes tracemalloc to monitor memory allocations if it is not already running.
    """
    if tracemalloc.is_tracing():
        logger.warning("tracemalloc is already running.")
    else:
        tracemalloc.start()
        logger.info("Memory profiling started with tracemalloc.")

def log_memory_snapshot():
    """
    Takes a snapshot of memory usage and logs the top 10 memory-consuming lines,
    if tracemalloc is running.
    """
    if not tracemalloc.is_tracing():
        logger.warning("Cannot take memory snapshot because tracemalloc is not running.")
        return

    try:
        snapshot = tracemalloc.take_snapshot()
    except RuntimeError as e:
        logger.error(f"Failed to take memory snapshot: {e}")
        return

    top_stats = snapshot.statistics('lineno')

    logger.info(f"Top {TOP_MEMORY_STATS_COUNT} memory usage stats:")
    for stat in top_stats[:TOP_MEMORY_STATS_COUNT]:
        logger.info(stat)
