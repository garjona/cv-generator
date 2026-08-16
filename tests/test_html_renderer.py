from pathlib import Path

from cv_generator.infrastructure.rendering.html_renderer import JinjaHtmlRenderer


def test_html_renderer_writes_html_and_css(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    templates.mkdir(parents=True, exist_ok=True)

    (templates / "resume.html.j2").write_text(
        "<!doctype html><html><head><link rel='stylesheet' href='{{ css_file_name }}'></head>"
        "<body><h1>{{ candidate_name }}</h1></body></html>",
        encoding="utf-8",
    )
    (templates / "resume.css.j2").write_text("body { color: #111; }", encoding="utf-8")

    renderer = JinjaHtmlRenderer(templates)
    out_html = tmp_path / "output_cv.html"
    out_css = tmp_path / "output_cv.css"

    renderer.render_html("resume.html.j2", {"candidate_name": "Ana Perez", "css_file_name": "output_cv.css"}, out_html)
    renderer.render_css("resume.css.j2", {}, out_css)

    assert out_html.exists()
    assert out_css.exists()
    assert "Ana Perez" in out_html.read_text(encoding="utf-8")
    assert "output_cv.css" in out_html.read_text(encoding="utf-8")
    assert "color: #111" in out_css.read_text(encoding="utf-8")
