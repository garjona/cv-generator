from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from cv_generator.application import CVGenerationOrchestrator, GenerationRequest
from cv_generator.application.cv_writer import CVContentBuilder
from cv_generator.config import load_settings
from cv_generator.infrastructure.config import available_candidates, load_candidate, load_domain
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
    parser.add_argument("--candidate", default=None, help="Slug del candidato en inputs/candidates/ (resuelve CV, oferta, perfil y salida)")
    parser.add_argument("--job", default=None, help="Nombre de la oferta dentro de la carpeta jobs/ del candidato")
    parser.add_argument("--candidates-dir", default=None, help="Directorio de candidatos (default: inputs/candidates)")
    parser.add_argument("--domain", default=None, help="Dominio profesional (tech, docencia, ...). Default: el del candidato")
    parser.add_argument("--list-candidates", action="store_true", help="Lista los candidatos disponibles y termina")
    parser.add_argument("--cv-file", default=None, help="Ruta al CV base (.docx, .pdf o .md)")
    group = parser.add_mutually_exclusive_group(required=False)
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
    parser.add_argument(
        "--output-name",
        default=None,
        help="Nombre base de los archivos generados (si no, se deriva del nombre del candidato: CV_Nombre_Apellido)",
    )
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


def _candidate_basics(candidate) -> dict | None:
    """Datos declarados en candidate.json que mandan sobre lo parseado."""
    if candidate is None:
        return None
    basics = dict(candidate.basics)
    if candidate.name:
        basics["name"] = candidate.name
    return basics or None


def main() -> None:
    args = build_arg_parser().parse_args()
    settings = load_settings()

    candidates_dir = Path(args.candidates_dir) if args.candidates_dir else None

    if args.list_candidates:
        found = available_candidates(candidates_dir)
        print("Candidatos disponibles:" if found else "No hay candidatos configurados.")
        for slug in found:
            print(f"  - {slug}")
        return

    candidate = None
    if args.candidate:
        try:
            candidate = load_candidate(args.candidate, candidates_dir)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc))

    # Los argumentos explícitos siempre ganan sobre la configuración del candidato.
    cv_value = args.cv_file or (str(candidate.cv_file) if candidate and candidate.cv_file else None)
    if not cv_value:
        raise SystemExit("Debes indicar --cv-file o --candidate con un CV configurado.")
    cv_path = Path(cv_value)
    if not cv_path.exists():
        raise SystemExit(f"CV no encontrado: {cv_path}")

    job_path = Path(args.job_file) if args.job_file else None
    if job_path is None and args.job:
        if candidate is None:
            raise SystemExit("--job requiere --candidate.")
        try:
            job_path = candidate.resolve_job(args.job)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc))
    if job_path is None and not args.job_text:
        raise SystemExit("Debes indicar una oferta con --job, --job-file o --job-text.")
    if job_path and not job_path.exists():
        raise SystemExit(f"Oferta no encontrada: {job_path}")

    domain_name = args.domain or (candidate.domain if candidate else None)
    domain = None
    if domain_name:
        try:
            domain = load_domain(domain_name)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc))

    template_value = args.template_file or (str(candidate.template_file) if candidate and candidate.template_file else None)
    template_file = Path(template_value) if template_value else None
    if template_file and not template_file.exists():
        raise SystemExit(f"Template no encontrado: {template_file}")

    css_value = args.template_css_file or (str(candidate.template_css_file) if candidate and candidate.template_css_file else None)
    template_css_file = Path(css_value) if css_value else None
    if template_css_file and not template_css_file.exists():
        raise SystemExit(f"Template CSS no encontrado: {template_css_file}")

    template_adapter_file = Path(args.template_adapter_file) if args.template_adapter_file else None
    if template_adapter_file and not template_adapter_file.exists():
        raise SystemExit(f"Adapter no encontrado: {template_adapter_file}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output_dir:
        output_dir = Path(args.output_dir)
    elif candidate:
        # Cada candidato acumula sus salidas en su propia carpeta.
        output_dir = settings.default_output_dir / candidate.slug / stamp
    else:
        output_dir = settings.default_output_dir / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir / "execution.log")
    if args.db_path:
        db_path = Path(args.db_path)
    elif candidate:
        db_path = candidate.db_path
    else:
        db_path = settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repository = SQLiteProfileRepository(db_path)
    llm_client = build_llm_client(settings)
    templates_root = Path(__file__).resolve().parents[2] / "templates"
    html_renderer = JinjaHtmlRenderer(templates_root / "html")
    typst_renderer = JinjaTypstRenderer(templates_root / "typst")
    html_pdf_compiler = HtmlPdfCompiler()

    orchestrator = CVGenerationOrchestrator(
        job_parser=JobPostingParser(domain=domain),
        cv_parser=CVParser(domain=domain),
        profile_repository=repository,
        html_renderer=html_renderer,
        html_pdf_compiler=html_pdf_compiler,
        typst_renderer=typst_renderer,
        page_image_exporter=PDFPageImageExporter(),
        llm_client=llm_client,
        content_builder=CVContentBuilder(llm_client=llm_client, domain=domain),
        logger=logger,
    )

    request = GenerationRequest(
        cv_path=cv_path,
        job_path=job_path,
        job_text=args.job_text,
        output_dir=output_dir,
        pages=(candidate.pages if candidate and args.pages == 1 else args.pages),
        template_style=args.template_style or settings.default_template_style,
        profile_id=(candidate.profile_id if candidate and args.profile_id == "default" else args.profile_id),
        render_format=args.render_format,
        template_file=template_file,
        template_css_file=template_css_file,
        template_adapter_file=template_adapter_file,
        interactive=not args.no_interactive,
        compile_pdf=not args.no_pdf,
        export_jpg_pages=not args.no_jpg_pages,
        jpg_dpi=max(72, args.jpg_dpi),
        output_name=args.output_name or (candidate.output_name if candidate else None),
        basics_override=_candidate_basics(candidate),
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
