from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .models import CVNormalized, GeneratedCVContent, JobPostingNormalized, MasterProfile, MatchAnalysis


@runtime_checkable
class JobPostingParserPort(Protocol):
    def parse_path(self, path: Path) -> JobPostingNormalized: ...
    def parse_text(self, text: str) -> JobPostingNormalized: ...


@runtime_checkable
class CVParserPort(Protocol):
    def parse_path(self, path: Path) -> CVNormalized: ...


@runtime_checkable
class ProfileRepositoryPort(Protocol):
    def get(self, profile_id: str) -> MasterProfile | None: ...
    def save(self, profile: MasterProfile, event_type: str = "upsert", payload: dict[str, Any] | None = None) -> None: ...
    def export_json(self, profile_id: str, output_path: Path) -> Path: ...


@runtime_checkable
class LLMClientPort(Protocol):
    def is_available(self) -> bool: ...
    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str | None: ...


@runtime_checkable
class TypstRendererPort(Protocol):
    def render(self, template_name: str, context: dict[str, Any], output_typ_path: Path) -> Path: ...
    def compile_pdf(self, typ_path: Path) -> tuple[Path | None, str | None]: ...


# Interfaces para evolución a multi-agent
@runtime_checkable
class ExtractorAgent(Protocol):
    def extract_job(self, source: Path | str) -> JobPostingNormalized: ...
    def extract_cv(self, cv_path: Path) -> CVNormalized: ...


@runtime_checkable
class JobFitAgent(Protocol):
    def analyze_fit(self, job: JobPostingNormalized, profile: MasterProfile) -> MatchAnalysis: ...


@runtime_checkable
class QuestioningAgent(Protocol):
    def generate_questions(self, job: JobPostingNormalized, match: MatchAnalysis, profile: MasterProfile) -> list[dict[str, Any]]: ...
    def apply_answers(self, profile: MasterProfile, answers: list[dict[str, Any]]) -> MasterProfile: ...


@runtime_checkable
class CVWriterAgent(Protocol):
    def generate_cv(self, job: JobPostingNormalized, profile: MasterProfile, match: MatchAnalysis, pages: int) -> GeneratedCVContent: ...


@runtime_checkable
class QAAgent(Protocol):
    def validate(self, generated: GeneratedCVContent, profile: MasterProfile, job: JobPostingNormalized) -> list[str]: ...


@runtime_checkable
class FormattingAgent(Protocol):
    def format_to_typst(self, generated: GeneratedCVContent, output_typ_path: Path) -> Path: ...
