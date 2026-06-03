import logging
import os
import sys



class Theme:
	@staticmethod
	def _supports_color() -> bool:
		if os.environ.get("NO_COLOR"):
			return False
		if os.environ.get("FORCE_COLOR"):
			return True
		return sys.stdout.isatty()

	@staticmethod
	def _c(code: str, text: str) -> str:
		if not Theme._supports_color():
			return text
		return f"\033[{code}m{text}\033[0m"

	def bold(self, t: str) -> str:    return self._c("1",    t)
	def dim(self, t: str) -> str:     return self._c("2",    t)
	def red(self, t: str) -> str:     return self._c("31;1", t)
	def green(self, t: str) -> str:   return self._c("32;1", t)
	def yellow(self, t: str) -> str:  return self._c("33;1", t)
	def cyan(self, t: str) -> str:    return self._c("36",   t)
	def magenta(self, t: str) -> str: return self._c("35",   t)

	# - semantic -------------------------------

	def ok(self, t: str) -> str:      return self.green(t)    # fully constrained
	def fail(self, t: str) -> str:    return self.red(t)      # error / missing
	def warn(self, t: str) -> str:    return self.yellow(t)   # partial / stale
	def good(self, t: str) -> str:    return self.green(t)    # value present & valid
	def missing(self, t: str) -> str: return self.red(t)      # value absent but expected
	def path(self, t: str) -> str:    return self.cyan(t)     # file paths
	def header(self, t: str) -> str:  return self.bold(t)     # section titles

	def debug(self, t: str) -> str: return self.cyan(t)
	def info(self, t: str) -> str: return self.green(t)
	def warning(self, t: str) -> str: return self.yellow(t)
	def error(self, t: str) -> str: return self.red(t)
	def critical(self, t: str) -> str: return self.magenta(t)
	
	def level(self, t: str, lvl: int):
		match lvl:
			case logging.DEBUG: return self.cyan(t)
			case logging.INFO: return self.green(t)
			case logging.WARNING: return self.yellow(t)
			case logging.ERROR: return self.red(t)
			case logging.CRITICAL: return self.magenta(t)

theme = Theme()