"""Packaged, offline Gemini studio shell. No external assets or inline scripts."""
from importlib.resources import files

HTML_SHELL = files("reportmaker.v2").joinpath("web_assets", "index.html").read_text(encoding="utf-8")
