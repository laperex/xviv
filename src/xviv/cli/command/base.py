import argparse
from abc import ABC, abstractmethod


class Command(ABC):
	name: str
	help: str

	@classmethod
	@abstractmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		pass

	@abstractmethod
	def run(self, cfg, args: argparse.Namespace) -> None:
		pass