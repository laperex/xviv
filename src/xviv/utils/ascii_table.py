import re
from typing import Any, Callable, Dict, List, Optional

from xviv.utils.theme import theme_cfg

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_ALIGN_CHARS = {"l": "<", "r": ">", "c": "^"}
_DIVIDER = object()  # sentinel — marks a horizontal rule inside the body


# -- minimal internal colour helpers ------------------------------------------


# def _supports_color() -> bool:
# 	return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


# def _c(code: str, text: str) -> str:
# 	if not _supports_color():
# 		return text
# 	return f"\033[{code}m{text}\033[0m"


# def _dim(t: str) -> str:
# 	return _c("2", t)


# -- ANSI-aware string helpers -------------------------------------------------


def _visual_len(s: str) -> int:

	return len(_ANSI_RE.sub("", s))


def _pad(s: str, width: int, align: str = "<") -> str:

	pad = max(0, width - _visual_len(s))
	if align == ">":
		return " " * pad + s
	if align == "^":
		lp = pad // 2
		return " " * lp + s + " " * (pad - lp)
	return s + " " * pad


# -- table ---------------------------------------------------------------------


class AsciiTable:
	def __init__(
		self,
		title: str,
		headers: Optional[List[str]] = None,
		max_widths: Optional[List[Optional[int]]] = None,
		align: Optional[List[str]] = None,
		color_map: Optional[Dict[str, Callable[[str], str]]] = None,
		dim_borders: bool = True,
	) -> None:
		self._title = title
		self._headers: Optional[List[str]] = [str(h) for h in headers] if headers else None
		self._rows: List[Any] = []
		self._max_widths: List[Optional[int]] = list(max_widths) if max_widths else []
		self._align: List[str] = list(align) if align else []
		self._color_map: Dict[str, Callable] = color_map or {}
		self._dim_borders: bool = dim_borders

	# ------------------------------------------------------------------ API

	def add_row(self, *cells: Any) -> "AsciiTable":

		self._rows.append([str(c) for c in cells])
		return self

	def add_rows(self, rows: List[List[Any]]) -> "AsciiTable":

		for row in rows:
			self.add_row(*row)
		return self

	def add_divider(self) -> "AsciiTable":

		self._rows.append(_DIVIDER)
		return self

	def clear(self) -> "AsciiTable":

		self._rows.clear()
		return self

	# ------------------------------------------------------------ internals

	@staticmethod
	def _trunc(s: str, max_w: int) -> str:

		plain = _ANSI_RE.sub("", s)
		if len(plain) <= max_w:
			return s  # short enough — keep any existing colour
		return plain[: max_w - 3] + "..."

	def _col_widths(self) -> List[int]:
		all_rows: List[List[str]] = []
		if self._headers:
			all_rows.append(self._headers)
		all_rows.extend(r for r in self._rows if r is not _DIVIDER)
		if not all_rows:
			return []
		n_cols = max(len(r) for r in all_rows)
		widths: List[int] = []
		for i in range(n_cols):
			# Use visual length so pre-coloured cells don't bloat the column.
			raw = max(_visual_len(r[i]) if i < len(r) else 0 for r in all_rows)
			cap = self._max_widths[i] if i < len(self._max_widths) else None
			widths.append(min(raw, cap) if cap is not None else raw)
		return widths

	def _b(self, s: str) -> str:

		return theme_cfg.dim(s) if self._dim_borders else s

	def _sep(self, widths: List[int]) -> str:
		return self._b("+" + "+".join("-" * (w + 2) for w in widths) + "+")

	def _colorize(self, cell: str) -> str:

		plain = _ANSI_RE.sub("", cell)
		fn = self._color_map.get(plain)
		return fn(plain) if fn else cell

	def _fmt_row(self, cells: List[str], widths: List[int], colorize: bool = True) -> str:
		pipe = self._b("|")
		parts: List[str] = []
		for i, w in enumerate(widths):
			cell = cells[i] if i < len(cells) else ""
			cap = self._max_widths[i] if i < len(self._max_widths) else None
			if cap is not None:
				cell = self._trunc(cell, cap)
			if colorize:
				cell = self._colorize(cell)
			a = _ALIGN_CHARS.get(self._align[i] if i < len(self._align) else "l", "<")
			parts.append(" " + _pad(cell, w, a) + " ")
		return pipe + pipe.join(parts) + pipe

	# --------------------------------------------------------------- render

	def render(self) -> str:
		widths = self._col_widths()
		if not widths:
			return ""
		sep = self._sep(widths)
		lines: List[str] = [self._title, sep]
		if self._headers:
			lines.append(self._fmt_row(self._headers, widths, colorize=False))
			lines.append(sep)
		for row in self._rows:
			if row is _DIVIDER:
				lines.append(sep)
			else:
				lines.append(self._fmt_row(row, widths))
		lines.append(sep)
		return "\n".join(lines)

	def print(self) -> None:
		print()
		print(self.render())

	def __str__(self) -> str:
		return self.render()
