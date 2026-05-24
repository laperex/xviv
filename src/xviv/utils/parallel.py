import logging
import traceback
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from xviv.utils import error

logger = logging.getLogger(__name__)


def run_parallel(
	jobs: list[tuple[Callable[[], None], str]],
	*,
	max_workers: int = 4,
) -> None:
	# Run a list of (callable, label) pairs concurrently.
	# Progress is logged at INFO level as jobs complete.

	if not jobs:
		return

	logger.info("Starting %d parallel job(s) (max_workers=%d)", len(jobs), max_workers)

	failures: list[tuple[str, BaseException]] = []

	with ThreadPoolExecutor(max_workers=max_workers) as pool:
		futures: dict[Future[None], str] = {}
		for fn, label in jobs:
			logger.debug("Submitting job: %s", label)
			futures[pool.submit(fn)] = label

		for fut in as_completed(futures):
			label = futures[fut]
			exc = fut.exception()
			if exc is not None:
				logger.error(
					"Job failed: %s\n%s",
					label,
					"".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
				)
				failures.append((label, exc))
			else:
				logger.info("Job done:   %s", label)

	if failures:
		raise error.ParallelJobError(failures)