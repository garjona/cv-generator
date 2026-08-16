from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class HtmlPdfCompiler:
    def __init__(self, browser_candidates: list[str] | None = None) -> None:
        self.browser_candidates = browser_candidates or [
            "chromium",
            "chromium-browser",
            "google-chrome",
            "google-chrome-stable",
            "chrome",
            "msedge",
            "microsoft-edge",
        ]

    def _find_browser(self) -> str | None:
        for candidate in self.browser_candidates:
            browser = shutil.which(candidate)
            if browser:
                return browser
        return None

    def compile_pdf(self, html_path: Path, output_pdf_path: Path | None = None) -> tuple[Path | None, str | None]:
        if not html_path.exists():
            return None, f"No se encontró el HTML para compilar: {html_path}"

        browser = self._find_browser()
        if not browser:
            return None, "No se encontró navegador compatible para PDF HTML (Chromium/Chrome/Edge)."

        output_pdf = output_pdf_path or html_path.with_suffix(".pdf")
        output_pdf.parent.mkdir(parents=True, exist_ok=True)

        html_uri = html_path.resolve().as_uri()
        cmd = [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            # Some Chromium versions use this newer switch.
            "--no-pdf-header-footer",
            # Backward-compatible variants for older Chromium/Chrome builds.
            "--print-to-pdf-no-header-footer",
            f"--print-to-pdf={str(output_pdf.resolve())}",
            "--print-to-pdf-no-header",
            html_uri,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except Exception as exc:
            return None, f"Error al compilar PDF desde HTML: {exc}"

        if proc.returncode != 0:
            msg = (proc.stderr or "").strip() or (proc.stdout or "").strip() or "Error desconocido"
            return None, f"Browser devolvió código {proc.returncode}. {msg}"

        if not output_pdf.exists():
            return None, "La compilación HTML->PDF terminó sin archivo PDF."

        return output_pdf, None
