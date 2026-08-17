from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cv_generator.application.cv_writer import CVContentBuilder, SimpleQAAgent
from cv_generator.application.matching import JobMatchAnalyzer
from cv_generator.application.profile_service import ProfileService
from cv_generator.application.questioning import GuidedQuestion, GuidedQuestionEngine
from cv_generator.domain.models import PipelineArtifacts
from cv_generator.infrastructure.rendering.context_adapter import adapt_context_with_mapping


@dataclass(slots=True)
class GenerationRequest:
    cv_path: Path
    job_path: Path | None
    job_text: str | None
    output_dir: Path
    pages: int
    template_style: str
    profile_id: str
    render_format: str = "typst"
    template_file: Path | None = None
    template_css_file: Path | None = None
    template_adapter_file: Path | None = None
    interactive: bool = True
    compile_pdf: bool = True
    export_jpg_pages: bool = True
    jpg_dpi: int = 180
    output_name: str | None = None
    basics_override: dict | None = None


class CVGenerationOrchestrator:
    def __init__(
        self,
        job_parser,
        cv_parser,
        profile_repository,
        html_renderer=None,
        html_pdf_compiler=None,
        typst_renderer=None,
        llm_client=None,
        page_image_exporter=None,
        profile_service: ProfileService | None = None,
        matcher: JobMatchAnalyzer | None = None,
        question_engine: GuidedQuestionEngine | None = None,
        content_builder: CVContentBuilder | None = None,
        qa_agent: SimpleQAAgent | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.job_parser = job_parser
        self.cv_parser = cv_parser
        self.profile_repository = profile_repository
        self.html_renderer = html_renderer
        self.html_pdf_compiler = html_pdf_compiler
        self.typst_renderer = typst_renderer
        self.llm_client = llm_client
        self.page_image_exporter = page_image_exporter
        self.profile_service = profile_service or ProfileService()
        self.matcher = matcher or JobMatchAnalyzer()
        self.question_engine = question_engine or GuidedQuestionEngine()
        self.content_builder = content_builder or CVContentBuilder(llm_client=llm_client)
        self.qa_agent = qa_agent or SimpleQAAgent()
        self.logger = logger or logging.getLogger("cv_generator")

    def run(
        self,
        request: GenerationRequest,
        ask_user: Callable[[list[GuidedQuestion]], dict[str, str]] | None = None,
    ) -> PipelineArtifacts:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info("Inicio de pipeline para profile_id=%s", request.profile_id)

        if request.job_path is None and not request.job_text:
            raise ValueError("Debes indicar una oferta por archivo o texto.")

        job = self.job_parser.parse_path(request.job_path) if request.job_path else self.job_parser.parse_text(request.job_text or "")
        cv = self.cv_parser.parse_path(request.cv_path)

        # El parseo nunca debe fallar en silencio: lo que no se pudo extraer se avisa.
        for warning in cv.parsing_warnings:
            self.logger.warning("Parseo CV base: %s", warning)
        for warning in job.parsing_warnings:
            self.logger.warning("Parseo oferta: %s", warning)

        job_json = request.output_dir / "job_posting_normalized.json"
        job_json.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        cv_json = request.output_dir / "cv_base_normalized.json"
        cv_json.write_text(json.dumps(cv.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        profile = self.profile_repository.get(request.profile_id)
        profile = self.profile_service.merge_cv_into_profile(profile, cv, request.profile_id)

        # Los datos declarados por el candidato mandan sobre lo inferido del CV:
        # hay documentos donde el nombre o el contacto no son parseables.
        for key, value in (request.basics_override or {}).items():
            if str(value).strip():
                profile.basics[key] = value
        self.profile_repository.save(profile, event_type="ingest_cv", payload={"cv_path": str(request.cv_path)})

        match = self.matcher.analyze(job, profile)
        self.logger.info("Matching inicial: %s", match.compatibility_score)

        questions = self.question_engine.generate(job, match, profile, max_questions=6)
        if request.interactive and ask_user and questions:
            answers_map = ask_user(questions)
            answers = self.question_engine.materialize_answers(questions, answers_map)
            if answers:
                profile = self.profile_service.apply_interactive_answers(profile, answers)
                self.profile_repository.save(profile, event_type="interactive_update", payload={"count": len(answers)})
                match = self.matcher.analyze(job, profile)
                self.logger.info("Matching post-interacción: %s", match.compatibility_score)
        else:
            self.logger.info("Interacción guiada omitida.")

        effective_template_style = str(request.template_file) if request.template_file else request.template_style
        generated = self.content_builder.build(job, profile, match, request.pages, effective_template_style)
        qa_warnings = self.qa_agent.validate(generated, profile, job)
        if qa_warnings:
            generated.report_markdown += "\n## QA Warnings\n"
            for warning in qa_warnings:
                generated.report_markdown += f"- {warning}\n"

        if cv.parsing_warnings or job.parsing_warnings:
            generated.report_markdown += "\n## Advertencias de parseo\n"
            for warning in cv.parsing_warnings:
                generated.report_markdown += f"- [CV base] {warning}\n"
            for warning in job.parsing_warnings:
                generated.report_markdown += f"- [Oferta] {warning}\n"

        template_context = dict(generated.latex_context)
        if request.template_adapter_file:
            template_context = adapt_context_with_mapping(template_context, request.template_adapter_file)

        context_json = request.output_dir / "template_context.json"
        context_json.write_text(json.dumps(template_context, ensure_ascii=False, indent=2), encoding="utf-8")

        render_format = (request.render_format or "typst").strip().lower()
        output_source: Path
        output_css: Path | None = None
        output_pdf: Path | None = None
        pdf_error: str | None = None

        if render_format == "html":
            if self.html_renderer is None:
                raise ValueError("No hay renderer HTML configurado en el orquestador.")

            base_name = self._output_base_name(request, profile)
            template_name = self._html_template_name(request.template_style, request.template_file)
            css_template_name = self._html_css_template_name(
                request.template_style,
                request.template_css_file,
                request.template_file,
            )

            output_source = request.output_dir / f"{base_name}.html"
            output_css = request.output_dir / f"{base_name}.css"
            html_context = dict(template_context)
            html_context["css_file_name"] = output_css.name

            self.html_renderer.render_html(template_name, html_context, output_source)
            self.html_renderer.render_css(css_template_name, template_context, output_css)

            generated.report_markdown += "\n## HTML Render\n"
            generated.report_markdown += f"- HTML generado: `{output_source.name}`\n"
            generated.report_markdown += f"- CSS generado: `{output_css.name}`\n"
            if request.compile_pdf:
                if self.html_pdf_compiler is None:
                    pdf_error = "No hay compilador HTML->PDF configurado en el orquestador."
                else:
                    output_pdf, pdf_error = self.html_pdf_compiler.compile_pdf(
                        output_source,
                        output_pdf_path=request.output_dir / f"{base_name}.pdf",
                    )

                if pdf_error:
                    generated.report_markdown += f"\n## PDF Compilation\n- {pdf_error}\n"
                    self.logger.warning("Compilación PDF (HTML) falló: %s", pdf_error)
                elif output_pdf:
                    generated.report_markdown += f"\n## PDF Compilation\n- PDF generado: `{output_pdf.name}`\n"
                    self.logger.info("PDF generado desde HTML: %s", output_pdf)
            else:
                generated.report_markdown += "\n## PDF Compilation\n- Omitida por configuración (`compile_pdf=false`).\n"
        elif render_format == "typst":
            if self.typst_renderer is None:
                raise ValueError("No hay renderer Typst configurado en el orquestador.")

            base_name = self._output_base_name(request, profile)
            template_name = self._typst_template_name(request.template_style, request.template_file)
            output_source = request.output_dir / f"{base_name}.typ"
            self.typst_renderer.render(template_name, template_context, output_source)

            if request.compile_pdf:
                output_pdf, pdf_error = self.typst_renderer.compile_pdf(output_source)
            else:
                output_pdf, pdf_error = None, None
                generated.report_markdown += "\n## PDF Compilation\n- Omitida por configuración (`compile_pdf=false`).\n"

            if pdf_error:
                generated.report_markdown += f"\n## PDF Compilation\n- {pdf_error}\n"
                self.logger.warning("Compilación PDF falló: %s", pdf_error)
            elif output_pdf:
                generated.report_markdown += f"\n## PDF Compilation\n- PDF generado: `{output_pdf.name}`\n"
                self.logger.info("PDF generado: %s", output_pdf)
        else:
            raise ValueError(f"Formato de render no soportado: {render_format}. Usa 'html' o 'typst'.")

        output_page_images: list[Path] = []
        jpg_error: str | None = None
        if request.export_jpg_pages:
            if not output_pdf:
                generated.report_markdown += (
                    "\n## JPG Export\n- Omitida: no hay PDF disponible para convertir a JPG por página.\n"
                )
            elif self.page_image_exporter is None:
                generated.report_markdown += (
                    "\n## JPG Export\n- Omitida: no hay exportador de imágenes configurado en el orquestador.\n"
                )
            else:
                output_page_images, jpg_error = self.page_image_exporter.export_jpg_pages(
                    output_pdf,
                    output_stem=output_source.stem,
                    dpi=request.jpg_dpi,
                )
                if jpg_error:
                    generated.report_markdown += f"\n## JPG Export\n- {jpg_error}\n"
                    self.logger.warning("Exportación JPG falló: %s", jpg_error)
                elif output_page_images:
                    generated.report_markdown += "\n## JPG Export\n"
                    generated.report_markdown += f"- Páginas JPG generadas: {len(output_page_images)}\n"
                    for image_path in output_page_images:
                        generated.report_markdown += f"- `{image_path.name}`\n"
                    self.logger.info("JPG por página generados: %s", len(output_page_images))

        report_md = request.output_dir / "cv_generation_report.md"
        report_md.write_text(generated.report_markdown, encoding="utf-8")

        master_profile_json = request.output_dir / "master_profile.json"
        self.profile_repository.export_json(request.profile_id, master_profile_json)

        return PipelineArtifacts(
            output_dir=request.output_dir,
            job_posting_json=job_json,
            master_profile_json=master_profile_json,
            cv_generation_report_md=report_md,
            output_source=output_source,
            output_css=output_css,
            output_pdf=output_pdf,
            output_page_images=output_page_images,
            log_file=request.output_dir / "execution.log",
            output_tex=None,
            notes=[x for x in [pdf_error, jpg_error] if x],
        )

    def _typst_template_name(self, template_style: str, template_file: Path | None) -> str:
        if template_file:
            return str(template_file)
        return {
            "typst_ats": "ats_typst.typ.j2",
            "ats_friendly": "ats_typst.typ.j2",
            "minimal_cv": "minimal_cv.typ.j2",
        }.get(template_style, "ats_typst.typ.j2")

    def _output_base_name(self, request: GenerationRequest, profile) -> str:
        """Nombre base de los archivos de salida.

        Un PDF llamado `output_cv.pdf` se ve genérico cuando alguien lo descarga;
        se prefiere `CV_Nombre_Apellido`. Se puede forzar con `output_name`.
        """
        explicit = str(getattr(request, "output_name", "") or "").strip()
        if explicit:
            return self._slugify_name(explicit) or "output_cv"

        name = str(profile.basics.get("name", "")).strip()
        if not name:
            return "output_cv"

        parts = [p for p in re.split(r"\s+", name) if p]
        # En nombres hispanos (nombre + segundo nombre + dos apellidos) se omite
        # el segundo nombre para un archivo más corto y legible.
        if len(parts) >= 4:
            parts = [parts[0], *parts[-2:]]
        return self._slugify_name("CV " + " ".join(parts)) or "output_cv"

    def _slugify_name(self, value: str) -> str:
        """Sin acentos ni caracteres raros: máxima compatibilidad entre sistemas."""
        normalized = unicodedata.normalize("NFKD", value)
        ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", ascii_only).strip("_")
        return cleaned

    def _html_template_name(self, template_style: str, template_file: Path | None) -> str:
        if template_file:
            return str(template_file)
        return {
            "html_ats": "ats_friendly.html.j2",
            "ats_friendly_html": "ats_friendly.html.j2",
            "ats_friendly": "ats_friendly.html.j2",
        }.get(template_style, "ats_friendly.html.j2")

    def _html_css_template_name(
        self,
        template_style: str,
        template_css_file: Path | None,
        template_file: Path | None,
    ) -> str:
        if template_css_file:
            return str(template_css_file)

        if template_file:
            parent = template_file.parent
            name = template_file.name
            candidates: list[Path] = []
            if name.endswith(".html.j2"):
                base = name[: -len(".html.j2")]
                candidates = [parent / f"{base}.css.j2", parent / f"{base}.css"]
            elif name.endswith(".html"):
                base = name[: -len(".html")]
                candidates = [parent / f"{base}.css.j2", parent / f"{base}.css"]
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate)

        return {
            "html_ats": "ats_friendly.css.j2",
            "ats_friendly_html": "ats_friendly.css.j2",
            "ats_friendly": "ats_friendly.css.j2",
        }.get(template_style, "ats_friendly.css.j2")
