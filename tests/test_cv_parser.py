from cv_generator.infrastructure.parsers.cv_parser import CVParser


def test_cv_parser_parse_text_content_detects_sections() -> None:
    parser = CVParser()
    text = """
    Ana Gómez
    ana@email.com

    Perfil Profesional
    Desarrolladora backend con experiencia en APIs y automatización.

    Experiencia Profesional
    Backend Developer - Acme 2022-Actualidad
    - Desarrollo de APIs REST con Python y FastAPI.
    - Docker y Git para despliegues.

    Educación
    Ingeniería de Software
    Universidad X
    2021

    Habilidades
    Python, FastAPI, SQL, Docker, Git
    """
    result = parser.parse_text_content(text, source_type="txt")

    assert result.basics["name"].startswith("Ana")
    assert result.basics["email"] == "ana@email.com"
    assert result.summary is not None
    assert len(result.experiences) >= 1
    assert any(skill.lower() == "python" for skill in result.skills)
    assert any("experience" in k for k in result.sections.keys())
