from pathlib import Path

from cv_generator.infrastructure.rendering.pdf_image_exporter import PDFPageImageExporter


def test_pdf_image_exporter_reports_missing_pdf(tmp_path: Path) -> None:
    exporter = PDFPageImageExporter()
    images, error = exporter.export_jpg_pages(tmp_path / "no_existe.pdf")
    assert images == []
    assert error is not None
    assert "No se encontró el PDF" in error
