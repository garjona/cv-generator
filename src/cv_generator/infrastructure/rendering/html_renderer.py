from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


class JinjaHtmlRenderer:
    def __init__(self, templates_dir: Path) -> None:
        self.templates_dir = templates_dir
        self.html_env = self._build_env(templates_dir, autoescape_html=True)
        self.css_env = self._build_env(templates_dir, autoescape_html=False)

    def _build_env(self, templates_dir: Path, autoescape_html: bool) -> Environment:
        return Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(("html", "xml")) if autoescape_html else False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _resolve_env(self, template_name: str, is_css: bool) -> tuple[Environment, str]:
        candidate = Path(template_name)
        if candidate.exists():
            env = self._build_env(candidate.parent, autoescape_html=not is_css)
            return env, candidate.name
        return (self.css_env if is_css else self.html_env), template_name

    def render_html(self, template_name: str, context: dict[str, Any], output_html_path: Path) -> Path:
        env, name = self._resolve_env(template_name, is_css=False)
        template = env.get_template(name)
        output_html_path.parent.mkdir(parents=True, exist_ok=True)
        output_html_path.write_text(template.render(**context), encoding="utf-8")
        return output_html_path

    def render_css(self, template_name: str, context: dict[str, Any], output_css_path: Path) -> Path:
        env, name = self._resolve_env(template_name, is_css=True)
        template = env.get_template(name)
        output_css_path.parent.mkdir(parents=True, exist_ok=True)
        output_css_path.write_text(template.render(**context), encoding="utf-8")
        return output_css_path
