from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class JobPostingNormalized:
    title: str
    company: str | None
    location: str | None
    seniority: str | None
    responsibilities: list[str]
    required_skills: list[str]
    preferred_skills: list[str]
    keywords: list[str]
    raw_text: str
    source_type: str
    parsing_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CVNormalized:
    source_type: str
    raw_text: str
    basics: dict[str, Any]
    summary: str | None
    experiences: list[dict[str, Any]]
    education: list[dict[str, Any]]
    skills: list[str]
    projects: list[dict[str, Any]]
    sections: dict[str, list[str]]
    languages: list[dict[str, Any]] = field(default_factory=list)
    parsing_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MasterProfile:
    profile_id: str
    basics: dict[str, Any]
    summary: str | None
    experiences: list[dict[str, Any]]
    education: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    skills: list[dict[str, Any]]
    achievements: list[dict[str, Any]]
    interaction_answers: list[dict[str, Any]]
    metadata: dict[str, Any]
    languages: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def empty(cls, profile_id: str) -> "MasterProfile":
        return cls(
            profile_id=profile_id,
            basics={},
            summary=None,
            experiences=[],
            education=[],
            projects=[],
            skills=[],
            achievements=[],
            interaction_answers=[],
            metadata={"created_at": utc_now_iso(), "updated_at": utc_now_iso(), "sources": []},
            languages=[],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MasterProfile":
        return cls(
            profile_id=data["profile_id"],
            basics=data.get("basics", {}),
            summary=data.get("summary"),
            experiences=data.get("experiences", []),
            education=data.get("education", []),
            projects=data.get("projects", []),
            skills=data.get("skills", []),
            achievements=data.get("achievements", []),
            interaction_answers=data.get("interaction_answers", []),
            metadata=data.get("metadata", {}),
            languages=data.get("languages", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MatchAnalysis:
    compatibility_score: int
    score_breakdown: dict[str, Any]
    matching_skills: list[str]
    missing_skills: list[str]
    unconfirmed_skills: list[str]
    prioritized_experiences: list[dict[str, Any]]
    recommendations: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GeneratedCVContent:
    template_style: str
    page_target: int
    latex_context: dict[str, Any]
    report_markdown: str
    qa_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PipelineArtifacts:
    output_dir: Path
    job_posting_json: Path
    master_profile_json: Path
    cv_generation_report_md: Path
    output_source: Path
    output_css: Path | None
    output_pdf: Path | None
    output_page_images: list[Path]
    log_file: Path
    output_tex: Path | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
                continue
            if isinstance(value, list):
                data[key] = [str(item) if isinstance(item, Path) else item for item in value]
        return data
