from cv_generator.application.matching import JobMatchAnalyzer
from cv_generator.domain.models import JobPostingNormalized, MasterProfile


def test_matching_detects_missing_and_matching_skills() -> None:
    profile = MasterProfile.empty("test")
    profile.skills = [
        {"name": "Python", "sources": ["cv_docx"], "metadata": {}},
        {"name": "SQL", "sources": ["cv_docx"], "metadata": {}},
        {"name": "Docker", "sources": ["cv_docx"], "metadata": {}},
    ]
    profile.experiences = [
        {
            "title": "Ingeniera de Datos",
            "company": "Acme",
            "summary": "Construcción de ETL y APIs REST",
            "bullets": ["Pipelines ETL con Python y SQL", "APIs REST internas"],
            "skills": ["Python", "SQL", "ETL", "API"],
            "metadata": {},
        }
    ]

    job = JobPostingNormalized(
        title="Ingeniero/a de Datos Senior",
        company="DataNova",
        location="Remoto",
        seniority="senior",
        responsibilities=["Diseñar pipelines ETL", "Automatizar despliegues con CI/CD"],
        required_skills=["Python", "SQL", "ETL", "AWS", "Git"],
        preferred_skills=["Spark"],
        keywords=["datos", "etl", "api", "docker"],
        raw_text="",
        source_type="txt",
        parsing_warnings=[],
    )

    analysis = JobMatchAnalyzer().analyze(job, profile)

    assert analysis.compatibility_score >= 40
    assert "Python" in analysis.matching_skills
    assert "AWS" in analysis.missing_skills
    assert analysis.prioritized_experiences[0]["match_score"] > 0


def test_negative_skill_confirmation_does_not_count_as_match() -> None:
    profile = MasterProfile.empty("test-negative")
    profile.achievements = [
        {
            "text": "[Tableau] No tengo experiencia real con Tableau.",
            "category": "confirm_skill",
            "metadata": {},
        }
    ]
    profile.metadata["skill_confirmations"] = {
        "tableau": {"skill": "Tableau", "confirmed": False, "evidence": "No tengo experiencia real con Tableau."}
    }

    job = JobPostingNormalized(
        title="Analista BI",
        company="Acme",
        location="Remoto",
        seniority="semi senior",
        responsibilities=[],
        required_skills=["Tableau", "SQL"],
        preferred_skills=[],
        keywords=[],
        raw_text="",
        source_type="txt",
        parsing_warnings=[],
    )

    analysis = JobMatchAnalyzer().analyze(job, profile)

    assert "Tableau" in analysis.missing_skills
    assert "Tableau" not in analysis.matching_skills
