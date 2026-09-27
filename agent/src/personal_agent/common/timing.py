"""Phase timings go to stderr; never include message contents."""
from contextlib import contextmanager
from functools import wraps
from inspect import iscoroutinefunction
import logging
from threading import Event, Thread
from time import perf_counter

logger = logging.getLogger(__name__)


def log_duration(name: str):
    """Log the total duration of a sync or async function."""
    def decorator(function):
        if iscoroutinefunction(function):
            @wraps(function)
            async def async_wrapper(*args, **kwargs):
                started = perf_counter()
                try:
                    return await function(*args, **kwargs)
                finally:
                    logger.info("%s | 총 %.2f초", name, perf_counter() - started)

            return async_wrapper

        @wraps(function)
        def sync_wrapper(*args, **kwargs):
            started = perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                logger.info("%s | 총 %.2f초", name, perf_counter() - started)

        return sync_wrapper

    return decorator


@contextmanager
def log_timing(phase: str):
    started = perf_counter()
    stopped = Event()
    logger.info("[시작] %s", phase)

    def report_wait():
        while not stopped.wait(10):
            logger.info("[진행] %s | %.1f초 경과", phase, perf_counter() - started)

    reporter = Thread(target=report_wait, daemon=True)
    reporter.start()
    try:
        yield
    except BaseException:
        logger.info("[실패] %s | %.2f초", phase, perf_counter() - started)
        raise
    else:
        logger.info("[완료] %s | %.2f초", phase, perf_counter() - started)
    finally:
        stopped.set()
        reporter.join(timeout=0.1)


def log_timed(phase: str):
    """동기·비동기 함수 전체에 단계별 실행 시간 로그를 남긴다."""
    def decorator(function):
        if iscoroutinefunction(function):
            @wraps(function)
            async def async_wrapper(*args, **kwargs):
                with log_timing(phase):
                    return await function(*args, **kwargs)

            return async_wrapper

        @wraps(function)
        def sync_wrapper(*args, **kwargs):
            with log_timing(phase):
                return function(*args, **kwargs)

        return sync_wrapper

    return decorator
