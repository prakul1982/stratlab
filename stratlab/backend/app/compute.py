"""Backtests in worker processes. A backtest holds the CPU for up to a second; run in the web server's own process it
would slow every other page while it runs (Python runs one thread at a time). Worker processes keep pages quick.

BACKTEST_PROCESSES sets how many (default 2; 0 runs everything in the server's process, as the tests do). If a worker
can't be used for any reason, the backtest runs in the server's process instead: never a failure."""
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

_pool: ProcessPoolExecutor | None = None
_lock = threading.Lock()


def processes() -> int:
    try:
        return max(0, min(8, int(os.environ.get("BACKTEST_PROCESSES", "2"))))
    except ValueError:
        return 2


def _work(strategy: dict, data: dict) -> dict:
    from . import research
    from .models import Strategy
    return research.run(Strategy(**strategy), data)


def _get() -> ProcessPoolExecutor:
    global _pool
    with _lock:
        if _pool is None:
            import multiprocessing as mp
            _pool = ProcessPoolExecutor(max_workers=processes(), mp_context=mp.get_context("spawn"))
        return _pool


def _reset():
    global _pool
    with _lock:
        old, _pool = _pool, None
    if old is not None:
        old.shutdown(wait=False, cancel_futures=True)


def run(strategy, data: dict) -> dict:
    """research.run(strategy, data), in a worker process when there are any."""
    from . import research
    if processes() == 0:
        return research.run(strategy, data)
    try:
        return _get().submit(_work, strategy.model_dump(), data).result(timeout=600)
    except BrokenProcessPool:
        _reset()                           # a worker died (out of memory?): start fresh next time, answer now
    except (TypeError, AttributeError, OSError, RuntimeError) as e:     # couldn't be sent to a worker
        print("backtest worker unavailable, running in-process:", e.__class__.__name__, str(e)[:120])
    return research.run(strategy, data)
