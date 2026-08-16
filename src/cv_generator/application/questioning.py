from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from cv_generator.domain.models import JobPostingNormalized, MasterProfile, MatchAnalysis


@dataclass(slots=True)
class GuidedQuestion:
    id: str
    question_type: str
    prompt: str
    rationale: str
    skill: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GuidedQuestionEngine:
    def generate(
        self,
        job: JobPostingNormalized,
        match: MatchAnalysis,
        profile: MasterProfile,
        max_questions: int = 6,
    ) -> list[GuidedQuestion]:
        questions: list[GuidedQuestion] = []
        known_skills = {str(s.get("name", "")).lower() for s in profile.skills}

        for idx, skill in enumerate(match.unconfirmed_skills[:4], start=1):
            questions.append(
                GuidedQuestion(
                    id=f"q_skill_{idx}",
                    question_type="confirm_skill",
                    prompt=(
                        f"La oferta pide '{skill}'. ¿Tienes experiencia real con esa skill? "
                        "Responde sí/no y agrega un ejemplo breve si aplica."
                    ),
                    rationale="Confirmar skill crítica mejora matching sin inventar información.",
                    skill=skill,
                )
            )

        has_metrics = any(any(c.isdigit() for c in str(a.get("text", ""))) for a in profile.achievements)
        if not has_metrics:
            questions.append(
                GuidedQuestion(
                    id="q_achievement_metrics",
                    question_type="achievement",
                    prompt=(
                        "Comparte 1 logro cuantificable relevante (%, tiempo, ahorro, usuarios, ingresos, calidad, etc.)."
                    ),
                    rationale="Los logros con métricas hacen el CV más fuerte y ATS-friendly.",
                )
            )

        if (job.seniority or "").lower() in {"lead", "senior", "principal"}:
            leadership_signals = " ".join(str(a.get("text", "")) for a in profile.achievements).lower()
            if not any(tok in leadership_signals for tok in ["lider", "mentor", "gestion", "coordin", "equipo"]):
                questions.append(
                    GuidedQuestion(
                        id="q_leadership",
                        question_type="leadership",
                        prompt=(
                            "Si aplica, describe una experiencia de liderazgo/coordinación/mentoría (1-2 líneas)."
                        ),
                        rationale="La oferta sugiere seniority alto y conviene evidenciar liderazgo si existe.",
                    )
                )

        preferred_unknown = [s for s in job.preferred_skills if s.lower() not in known_skills]
        if preferred_unknown:
            questions.append(
                GuidedQuestion(
                    id="q_tool_detail",
                    question_type="tool_detail",
                    prompt=(
                        "¿Has usado alguna de estas skills deseables? "
                        + ", ".join(preferred_unknown[:5])
                        + ". Indica contexto breve."
                    ),
                    rationale="Confirmar skills deseables puede subir el score sin arriesgar alucinaciones.",
                )
            )

        questions.append(
            GuidedQuestion(
                id="q_focus_preference",
                question_type="focus_preference",
                prompt="¿Qué enfoque quieres priorizar en este CV (backend, datos, liderazgo, automatización, otro)?",
                rationale="Permite adaptar el énfasis del CV manteniendo datos confirmados.",
            )
        )

        return questions[:max_questions]

    def materialize_answers(self, questions: list[GuidedQuestion], answers_by_id: dict[str, str]) -> list[dict[str, Any]]:
        out = []
        for q in questions:
            answer = (answers_by_id.get(q.id) or "").strip()
            if not answer:
                continue
            payload = q.to_dict()
            payload["answer"] = answer
            out.append(payload)
        return out
