from __future__ import annotations

from pathlib import Path


class PDFPageImageExporter:
    def export_jpg_pages(
        self,
        pdf_path: Path,
        output_stem: str = "output_cv",
        dpi: int = 180,
        quality: int = 90,
    ) -> tuple[list[Path], str | None]:
        if not pdf_path.exists():
            return [], f"No se encontró el PDF para exportar páginas JPG: {pdf_path}"

        try:
            import pypdfium2 as pdfium
        except Exception as exc:  # pragma: no cover - dependency/runtime dependent
            return [], f"No se pudo importar pypdfium2 para exportar JPG: {exc}"

        try:
            document = pdfium.PdfDocument(str(pdf_path))
        except Exception as exc:
            return [], f"No se pudo abrir el PDF para exportar JPG: {exc}"

        scale = max(float(dpi), 72.0) / 72.0
        out_images: list[Path] = []
        try:
            total_pages = len(document)
            for index in range(total_pages):
                page = document[index]
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil().convert("RGB")
                output_path = pdf_path.with_name(f"{output_stem}_page_{index + 1}.jpg")
                image.save(output_path, format="JPEG", quality=max(1, min(quality, 100)), optimize=True)
                out_images.append(output_path)
        except Exception as exc:
            return [], f"Falló la exportación de páginas JPG: {exc}"

        return out_images, None
