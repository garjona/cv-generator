from pathlib import Path

from cv_generator.infrastructure.rendering.html_pdf_compiler import HtmlPdfCompiler


def test_html_pdf_compiler_reports_missing_browser(tmp_path: Path) -> None:
    html_file = tmp_path / "cv.html"
    html_file.write_text("<html><body>ok</body></html>", encoding="utf-8")

    compiler = HtmlPdfCompiler(browser_candidates=["__no_browser__"])
    pdf, error = compiler.compile_pdf(html_file)

    assert pdf is None
    assert error is not None
    assert "No se encontró navegador compatible" in error
