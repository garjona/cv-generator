from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from cv_generator.application import CVGenerationOrchestrator, GenerationRequest
from cv_generator.config import load_settings
from cv_generator.infrastructure.llm import build_llm_client
from cv_generator.infrastructure.parsers import CVParser, JobPostingParser
from cv_generator.infrastructure.persistence import SQLiteProfileRepository
from cv_generator.infrastructure.rendering import (
    HtmlPdfCompiler,
    JinjaHtmlRenderer,
    JinjaTypstRenderer,
    PDFPageImageExporter,
)
from cv_generator.logging_utils import setup_logging


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera un CV adaptado en español con salida HTML+CSS (default) o Typst."
    )
    parser.add_argument("--cv-file", required=True, help="Ruta al CV base (.docx, .pdf o .md)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--job-file", help="Ruta a la oferta laboral (.html o .txt)")
    group.add_argument("--job-text", help="Texto plano de la oferta laboral")
    parser.add_argument("--pages", type=int, choices=[1, 2], default=1, help="Cantidad objetivo de páginas")
    parser.add_argument(
        "--render-format",
        choices=["html", "typst"],
        default="html",
        help="Formato de render de salida (default: html)",
    )
    parser.add_argument("--template-style", default=None, help="Estilo de plantilla (ej: html_ats o typst_ats)")
    parser.add_argument(
        "--template-file",
        default=None,
        help="Ruta a template custom (.html.j2 para html, .typ.j2 para typst)",
    )
    parser.add_argument(
        "--template-css-file",
        default=None,
        help="Ruta opcional al template CSS (.css o .css.j2) cuando render-format=html",
    )
    parser.add_argument(
        "--template-adapter-file",
        default=None,
        help="Ruta a adapter JSON para mapear el contexto canónico del CV al template elegido",
    )
    parser.add_argument("--profile-id", default="default", help="ID del perfil maestro")
    parser.add_argument("--db-path", default=None, help="Ruta SQLite para persistencia del perfil maestro")
    parser.add_argument("--output-dir", default=None, help="Directorio de salida (si no, se genera timestamp)")
    parser.add_argument("--no-interactive", action="store_true", help="Omitir preguntas guiadas")
    parser.add_argument("--no-pdf", action="store_true", help="No intentar compilación a PDF")
    parser.add_argument(
        "--no-jpg-pages",
        action="store_true",
        help="No exportar páginas JPG desde el PDF generado",
    )
    parser.add_argument(
        "--jpg-dpi",
        type=int,
        default=180,
        help="Resolución DPI para JPG por página (default: 180)",
    )
    return parser


def ask_questions_cli(questions) -> dict[str, str]:
    print("\n=== Interacción guiada (máx. 6 preguntas) ===")
    answers: dict[str, str] = {}
    for question in questions:
        print(f"\n[{question.id}] {question.prompt}")
        print(f"Motivo: {question.rationale}")
        try:
            answers[question.id] = input("> ").strip()
        except EOFError:
            answers[question.id] = ""
    return answers


def main() -> None:
    args = build_arg_parser().parse_args()
    settings = load_settings()

    cv_path = Path(args.cv_file)
    if not cv_path.exists():
        raise SystemExit(f"CV no encontrado: {cv_path}")

    job_path = Path(args.job_file) if args.job_file else None
    if job_path and not job_path.exists():
        raise SystemExit(f"Oferta no encontrada: {job_path}")

    template_file = Path(args.template_file) if args.template_file else None
    if template_file and not template_file.exists():
        raise SystemExit(f"Template no encontrado: {template_file}")

    template_css_file = Path(args.template_css_file) if args.template_css_file else None
    if template_css_file and not template_css_file.exists():
        raise SystemExit(f"Template CSS no encontrado: {template_css_file}")

    template_adapter_file = Path(args.template_adapter_file) if args.template_adapter_file else None
    if template_adapter_file and not template_adapter_file.exists():
        raise SystemExit(f"Adapter no encontrado: {template_adapter_file}")

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else settings.default_output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir / "execution.log")
    repository = SQLiteProfileRepository(Path(args.db_path) if args.db_path else settings.database_path)
    llm_client = build_llm_client(settings)
    templates_root = Path(__file__).resolve().parents[2] / "templates"
    html_renderer = JinjaHtmlRenderer(templates_root / "html")
    typst_renderer = JinjaTypstRenderer(templates_root / "typst")
    html_pdf_compiler = HtmlPdfCompiler()

    orchestrator = CVGenerationOrchestrator(
        job_parser=JobPostingParser(),
        cv_parser=CVParser(),
        profile_repository=repository,
        html_renderer=html_renderer,
        html_pdf_compiler=html_pdf_compiler,
        typst_renderer=typst_renderer,
        page_image_exporter=PDFPageImageExporter(),
        llm_client=llm_client,
        logger=logger,
    )

    request = GenerationRequest(
        cv_path=cv_path,
        job_path=job_path,
        job_text=args.job_text,
        output_dir=output_dir,
        pages=args.pages,
        template_style=args.template_style or settings.default_template_style,
        profile_id=args.profile_id,
        render_format=args.render_format,
        template_file=template_file,
        template_css_file=template_css_file,
        template_adapter_file=template_adapter_file,
        interactive=not args.no_interactive,
        compile_pdf=not args.no_pdf,
        export_jpg_pages=not args.no_jpg_pages,
        jpg_dpi=max(72, args.jpg_dpi),
    )

    artifacts = orchestrator.run(request, ask_user=None if args.no_interactive else ask_questions_cli)

    print("\n=== Resultado ===")
    print(f"Oferta normalizada: {artifacts.job_posting_json}")
    print(f"Perfil maestro exportado: {artifacts.master_profile_json}")
    print(f"Reporte generación: {artifacts.cv_generation_report_md}")
    print(f"Archivo principal generado: {artifacts.output_source}")
    if artifacts.output_css:
        print(f"CSS generado: {artifacts.output_css}")
    print(f"PDF generado: {artifacts.output_pdf}" if artifacts.output_pdf else "PDF no generado (ver reporte/logs)")
    if artifacts.output_page_images:
        print("JPG por página:")
        for image_path in artifacts.output_page_images:
            print(f"- {image_path}")
    else:
        print("JPG por página no generados (ver reporte/logs)")
    print(f"Logs: {artifacts.log_file}")


if __name__ == "__main__":
    main()
