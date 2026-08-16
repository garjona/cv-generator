from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


def typst_escape(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    mapping = {
        "\\": r"\\",
        "#": r"\#",
        "@": r"\@",
        "[": r"\[",
        "]": r"\]",
        "*": r"\*",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(mapping.get(ch, ch) for ch in text)


class JinjaTypstRenderer:
    def __init__(self, templates_dir: Path) -> None:
        self.templates_dir = templates_dir
        self.env = self._build_env(templates_dir)

    def _build_env(self, templates_dir: Path) -> Environment:
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,
            trim_blocks=False,
            lstrip_blocks=False,
        )
        env.filters["typst"] = typst_escape
        return env

    def render(self, template_name: str, context: dict[str, Any], output_typ_path: Path) -> Path:
        template_path = Path(template_name)
        if template_path.exists():
            env = self._build_env(template_path.parent)
            template = env.get_template(template_path.name)
        else:
            template = self.env.get_template(template_name)

        output_typ_path.parent.mkdir(parents=True, exist_ok=True)
        output_typ_path.write_text(template.render(**context), encoding="utf-8")
        return output_typ_path

    def compile_pdf(self, typ_path: Path) -> tuple[Path | None, str | None]:
        typst_bin = shutil.which("typst")
        if not typst_bin:
            return None, "No se encontró compilador Typst (`typst`) en el entorno."

        output_pdf = typ_path.with_suffix(".pdf")
        try:
            proc = subprocess.run(
                [typst_bin, "compile", typ_path.name, output_pdf.name],
                cwd=str(typ_path.parent),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except Exception as exc:
            return None, f"Error al ejecutar typst compile: {exc}"

        if proc.returncode != 0:
            msg = (proc.stderr or "").strip() or (proc.stdout or "").strip() or "Error desconocido"
            return None, f"typst devolvió código {proc.returncode}. {msg}"

        if not output_pdf.exists():
            return None, "La compilación terminó sin generar PDF."
        return output_pdf, None
