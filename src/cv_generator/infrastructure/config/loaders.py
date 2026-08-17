from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cv_generator.domain.domain_config import DomainConfig

DEFAULT_DOMAINS_DIR = Path("config/domains")
DEFAULT_CANDIDATES_DIR = Path("inputs/candidates")


def load_domain(name: str, domains_dir: Path | None = None) -> DomainConfig:
    """Carga un dominio por nombre desde `config/domains/<nombre>.json`."""
    directory = domains_dir or DEFAULT_DOMAINS_DIR
    path = directory / f"{name}.json"
    if not path.exists():
        available = sorted(p.stem for p in directory.glob("*.json")) if directory.exists() else []
        raise FileNotFoundError(
            f"No existe el dominio '{name}' en {directory}. Disponibles: {', '.join(available) or 'ninguno'}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return DomainConfig.from_dict(data)


def available_domains(domains_dir: Path | None = None) -> list[str]:
    directory = domains_dir or DEFAULT_DOMAINS_DIR
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


@dataclass(slots=True)
class CandidateConfig:
    """Un candidato y sus rutas resueltas."""

    slug: str
    root: Path
    name: str = ""
    domain: str = "tech"
    cv_file: Path | None = None
    template_file: Path | None = None
    template_css_file: Path | None = None
    pages: int = 2
    basics: dict[str, Any] = field(default_factory=dict)
    output_name: str | None = None

    @property
    def profile_id(self) -> str:
        return self.slug

    @property
    def db_path(self) -> Path:
        return self.root / "profile.db"

    @property
    def jobs_dir(self) -> Path:
        return self.root / "jobs"

    def resolve_job(self, job: str) -> Path:
        """Acepta el nombre de la oferta, con o sin extensión, o una ruta directa."""
        direct = Path(job)
        if direct.exists():
            return direct
        candidates = [self.jobs_dir / job, *(self.jobs_dir.glob(f"{job}.*") if self.jobs_dir.exists() else [])]
        for path in candidates:
            if path.exists() and path.is_file():
                return path
        available = sorted(p.name for p in self.jobs_dir.glob("*")) if self.jobs_dir.exists() else []
        raise FileNotFoundError(
            f"No se encontró la oferta '{job}' para {self.slug}. Disponibles: {', '.join(available) or 'ninguna'}"
        )


def load_candidate(slug: str, candidates_dir: Path | None = None) -> CandidateConfig:
    """Carga `inputs/candidates/<slug>/candidate.json` y resuelve sus rutas."""
    directory = candidates_dir or DEFAULT_CANDIDATES_DIR
    root = directory / slug
    config_path = root / "candidate.json"
    if not config_path.exists():
        available = available_candidates(directory)
        raise FileNotFoundError(
            f"No existe el candidato '{slug}' ({config_path}). Disponibles: {', '.join(available) or 'ninguno'}"
        )

    data = json.loads(config_path.read_text(encoding="utf-8"))

    cv_value = str(data.get("cv", "")).strip()
    cv_file = (root / cv_value) if cv_value else _autodetect_cv(root)
    if cv_file is not None and not cv_file.exists():
        raise FileNotFoundError(f"El CV base de '{slug}' no existe: {cv_file}")

    def _resolve_optional(key: str) -> Path | None:
        value = str(data.get(key, "")).strip()
        if not value:
            return None
        path = Path(value)
        return path if path.exists() else (root / value)

    return CandidateConfig(
        slug=slug,
        root=root,
        name=str(data.get("name", "")).strip(),
        domain=str(data.get("domain", "tech")).strip() or "tech",
        cv_file=cv_file,
        template_file=_resolve_optional("template"),
        template_css_file=_resolve_optional("template_css"),
        pages=int(data.get("pages", 2) or 2),
        basics={k: v for k, v in (data.get("basics") or {}).items() if v},
        output_name=str(data.get("output_name", "")).strip() or None,
    )


def available_candidates(candidates_dir: Path | None = None) -> list[str]:
    directory = candidates_dir or DEFAULT_CANDIDATES_DIR
    if not directory.exists():
        return []
    return sorted(p.name for p in directory.iterdir() if (p / "candidate.json").exists())


def _autodetect_cv(root: Path) -> Path | None:
    for pattern in ("cv.md", "cv.docx", "cv.pdf", "cv.txt"):
        path = root / pattern
        if path.exists():
            return path
    for suffix in (".md", ".docx", ".pdf"):
        matches = sorted(root.glob(f"*{suffix}"))
        if matches:
            return matches[0]
    return None
