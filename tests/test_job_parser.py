from pathlib import Path

from cv_generator.infrastructure.parsers.job_parser import JobPostingParser


def test_job_parser_html_extracts_basic_fields() -> None:
    parser = JobPostingParser()
    job = parser.parse_path(Path("examples/sample_job.html"))

    assert job.source_type == "html"
    assert "Ingeniero" in job.title
    assert job.company == "DataNova"
    assert job.location is not None
    assert any("ETL" in s.upper() for s in job.required_skills)
    assert any("Python" in s for s in job.required_skills)
    assert job.raw_text
