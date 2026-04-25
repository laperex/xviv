from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import typing


def run_parallel(jobs: list[tuple[Callable[[], None], str]], *, stage: typing.Optional[int] = None, max_workers: int = 4):
	with ThreadPoolExecutor(max_workers=max_workers) as pool:
		futures: dict[Future[None], str] = {
			pool.submit(fn): label
			for fn, label in jobs
		}
		for fut in as_completed(futures):
			label = futures[fut]
			fut.result()

			if stage is not None:
				print(f"[stage {stage}] {label} done")