import json
from pathlib import Path

import pytest

from cv_generator.domain.domain_config import DomainConfig
from cv_generator.infrastructure.config import available_domains, load_candidate, load_domain
from cv_generator.infrastructure.parsers import CVParser, JobPostingParser

DOMAINS_DIR = Path("config/domains")


def test_shipped_domains_load():
    names = available_domains(DOMAINS_DIR)
    assert {"tech", "docencia"} <= set(names)
    for name in names:
        domain = load_domain(name, DOMAINS_DIR)
        assert domain.name == name
        assert domain.skills, f"el dominio {name} no declara skills"


def test_unknown_domain_lists_alternatives():
    with pytest.raises(FileNotFoundError) as exc:
        load_domain("no-existe", DOMAINS_DIR)
    assert "tech" in str(exc.value)


def test_domain_drives_skill_detection():
    docencia = load_domain("docencia", DOMAINS_DIR)
    job = JobPostingParser(domain=docencia).parse_text(
        "Profesor de Lengua y Literatura\n\nRequisitos:\n"
        "Manejo de DUA y evaluación formativa.\nExperiencia en gestión de aula.\n"
    )
    detected = " ".join(job.required_skills).lower()
    assert "dua" in detected
    # El vocabulario tech no debe contaminar un perfil docente.
    assert "python" not in detected


def test_domain_section_aliases_extend_defaults():
    docencia = load_domain("docencia", DOMAINS_DIR)
    parser = CVParser(domain=docencia)
    # Alias propio del dominio...
    assert parser._match_section_alias("Competencias pedagógicas.") == "skills"
    # ...sin perder los alias base.
    assert parser._match_section_alias("Experiencia laboral") == "experience"


def test_domain_labels_and_omissions():
    docencia = load_domain("docencia", DOMAINS_DIR)
    assert docencia.labels.get("experience_skills") == "Enfoques y herramientas"
    assert docencia.canonical("dua").startswith("DUA")
    # "comunicación" es genérica en tech pero central en docencia.
    tech = load_domain("tech", DOMAINS_DIR)
    assert tech.should_omit("comunicación")
    assert not docencia.should_omit("comunicación")


def test_domain_config_roundtrip():
    data = {
        "name": "demo",
        "skills": ["algo"],
        "canonical_labels": {"ALGO": "Algo"},
        "omit_labels": ["Ruido"],
        "labels": {"experience_skills": "Herramientas"},
    }
    domain = DomainConfig.from_dict(data)
    assert domain.canonical("algo") == "Algo"
    assert domain.should_omit("ruido")
    assert DomainConfig.from_dict(domain.to_dict()).labels == domain.labels


def test_candidate_resolves_paths(tmp_path):
    root = tmp_path / "candidates" / "ana"
    (root / "jobs").mkdir(parents=True)
    (root / "cv.md").write_text("# Ana", encoding="utf-8")
    (root / "jobs" / "empresa-x.txt").write_text("oferta", encoding="utf-8")
    (root / "candidate.json").write_text(
        json.dumps({"name": "Ana Pérez", "domain": "tech", "cv": "cv.md", "pages": 2}),
        encoding="utf-8",
    )

    candidate = load_candidate("ana", tmp_path / "candidates")
    assert candidate.name == "Ana Pérez"
    assert candidate.cv_file == root / "cv.md"
    assert candidate.profile_id == "ana"
    assert candidate.db_path == root / "profile.db"
    # La oferta se resuelve con o sin extensión.
    assert candidate.resolve_job("empresa-x") == root / "jobs" / "empresa-x.txt"
    assert candidate.resolve_job("empresa-x.txt") == root / "jobs" / "empresa-x.txt"


def test_unknown_job_lists_available(tmp_path):
    root = tmp_path / "candidates" / "ana"
    (root / "jobs").mkdir(parents=True)
    (root / "cv.md").write_text("# Ana", encoding="utf-8")
    (root / "jobs" / "empresa-x.txt").write_text("oferta", encoding="utf-8")
    (root / "candidate.json").write_text(json.dumps({"name": "Ana", "cv": "cv.md"}), encoding="utf-8")

    candidate = load_candidate("ana", tmp_path / "candidates")
    with pytest.raises(FileNotFoundError) as exc:
        candidate.resolve_job("no-existe")
    assert "empresa-x.txt" in str(exc.value)
