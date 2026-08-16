from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


def latex_escape(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    mapping = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "\\": r"\textbackslash{}",
    }
    return "".join(mapping.get(ch, ch) for ch in text)


class JinjaLatexRenderer:
    def __init__(self, templates_dir: Path) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["latex"] = latex_escape

    def render(self, template_name: str, context: dict[str, Any], output_tex_path: Path) -> Path:
        template = self.env.get_template(template_name)
        output_tex_path.parent.mkdir(parents=True, exist_ok=True)
        output_tex_path.write_text(template.render(**context), encoding="utf-8")
        return output_tex_path

    def compile_pdf(self, tex_path: Path) -> tuple[Path | None, str | None]:
        pdflatex = shutil.which("pdflatex")
        if not pdflatex:
            return None, "No se encontró compilador LaTeX (`pdflatex`) en el entorno."
        try:
            proc = subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
                cwd=str(tex_path.parent),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except Exception as exc:
            return None, f"Error al ejecutar pdflatex: {exc}"
        if proc.returncode != 0:
            msg = (proc.stderr or "").strip() or (proc.stdout or "").strip() or "Error desconocido"
            return None, f"pdflatex devolvió código {proc.returncode}. {msg}"
        pdf_path = tex_path.with_suffix(".pdf")
        if not pdf_path.exists():
            return None, "La compilación terminó sin generar PDF."
        return pdf_path, None
