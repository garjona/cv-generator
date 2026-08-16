from pathlib import Path

from cv_generator.application.orchestrator import CVGenerationOrchestrator, GenerationRequest
from cv_generator.domain.models import MasterProfile


def _orchestrator() -> CVGenerationOrchestrator:
    return CVGenerationOrchestrator(
        job_parser=None,
        cv_parser=None,
        profile_repository=None,
        html_renderer=None,
    )


def _request(output_name: str | None = None) -> GenerationRequest:
    return GenerationRequest(
        cv_path=Path("cv.md"),
        job_path=Path("job.txt"),
        job_text=None,
        output_dir=Path("out"),
        pages=2,
        template_style="html_ats",
        profile_id="demo",
        output_name=output_name,
    )


def _profile(name: str) -> MasterProfile:
    profile = MasterProfile.empty("demo")
    if name:
        profile.basics["name"] = name
    return profile


def test_base_name_uses_candidate_name():
    orch = _orchestrator()
    assert orch._output_base_name(_request(), _profile("Ana Perez")) == "CV_Ana_Perez"


def test_base_name_strips_accents_and_drops_middle_name():
    orch = _orchestrator()
    # Nombre hispano completo: se omite el segundo nombre y se quitan acentos.
    base = orch._output_base_name(_request(), _profile("Gabriel Aníbal Arjona Gálvez"))
    assert base == "CV_Gabriel_Arjona_Galvez"


def test_explicit_output_name_wins():
    orch = _orchestrator()
    base = orch._output_base_name(_request(output_name="CV Backend 2026"), _profile("Ana Perez"))
    assert base == "CV_Backend_2026"


def test_falls_back_when_profile_has_no_name():
    orch = _orchestrator()
    assert orch._output_base_name(_request(), _profile("")) == "output_cv"
