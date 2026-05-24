from importlib.metadata import version, PackageNotFoundError
try:
	__version__ = version("xviv")
except PackageNotFoundError:
	__version__ = "0.0.0+unknown"