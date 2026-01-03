import tracemalloc
from app.utils.logger import AppLogger

logger = AppLogger.get_logger(__name__)

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

    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')

    logger.info("Top 10 memory usage stats:")
    for stat in top_stats[:10]:
        logger.info(stat)
