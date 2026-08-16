from __future__ import annotations

import re
from typing import Any

from cv_generator.domain.models import JobPostingNormalized, MasterProfile, MatchAnalysis


class JobMatchAnalyzer:
    def analyze(self, job: JobPostingNormalized, profile: MasterProfile) -> MatchAnalysis:
        profile_skill_names = [str(s.get("name", "")).strip() for s in profile.skills if s.get("name")]
        profile_skill_set = {s.lower() for s in profile_skill_names}
        negative_confirmations = self._negative_skill_confirmations(profile)
        profile_text = self._profile_text(profile).lower()

        required = self._norm(job.required_skills)
        preferred = self._norm(job.preferred_skills)
        matching_required = [
            s
            for s in required
            if s.lower() not in negative_confirmations and (s.lower() in profile_skill_set or self._has_skill(profile_text, s))
        ]
        missing_required = [s for s in required if s not in matching_required]
        matching_preferred = [
            s
            for s in preferred
            if s.lower() not in negative_confirmations and (s.lower() in profile_skill_set or self._has_skill(profile_text, s))
        ]

        exp_scores = self._score_experiences(profile.experiences, job)
        score = self._compute_score(required, preferred, matching_required, matching_preferred, exp_scores)
        recommendations = self._build_recommendations(job, matching_required, missing_required, exp_scores)

        breakdown = {
            "required_match_ratio": round(len(matching_required) / max(len(required), 1), 2),
            "preferred_match_ratio": round(len(matching_preferred) / max(len(preferred), 1), 2) if preferred else None,
            "experience_relevance_avg_top3": round(
                (sum(item["match_score"] for item in exp_scores[:3]) / max(min(3, len(exp_scores)), 1)) if exp_scores else 0,
                2,
            ),
            "weights": {"required": 70, "preferred": 15, "experience": 15},
        }

        notes = []
        if not required:
            notes.append("La oferta no expone skills requeridas claras; score de compatibilidad menos confiable.")
        if not profile.experiences:
            notes.append("Perfil sin experiencias estructuradas; priorización limitada.")

        return MatchAnalysis(
            compatibility_score=score,
            score_breakdown=breakdown,
            matching_skills=self._dedupe([*matching_required, *matching_preferred]),
            missing_skills=self._dedupe(missing_required),
            unconfirmed_skills=self._dedupe(missing_required),
            prioritized_experiences=exp_scores,
            recommendations=recommendations,
            notes=notes,
        )

    def _profile_text(self, profile: MasterProfile) -> str:
        chunks = [profile.summary or ""]
        for exp in profile.experiences:
            chunks.extend(
                [
                    str(exp.get("title", "")),
                    str(exp.get("company", "")),
                    str(exp.get("summary", "")),
                    *[str(x) for x in exp.get("bullets", [])],
                    *[str(x) for x in exp.get("skills", [])],
                ]
            )
        for proj in profile.projects:
            chunks.extend(
                [
                    str(proj.get("name", "")),
                    str(proj.get("description", "")),
                    *[str(x) for x in proj.get("bullets", [])],
                    *[str(x) for x in proj.get("skills", [])],
                ]
            )
        for ach in profile.achievements:
            if self._ignore_achievement_for_matching(ach):
                continue
            chunks.append(str(ach.get("text", "")))
        return " ".join(chunks)

    def _negative_skill_confirmations(self, profile: MasterProfile) -> set[str]:
        confirmations = profile.metadata.get("skill_confirmations", {})
        if not isinstance(confirmations, dict):
            return set()
        out = set()
        for key, value in confirmations.items():
            if isinstance(value, dict) and value.get("confirmed") is False:
                out.add(str(value.get("skill") or key).strip().lower())
        return out

    def _ignore_achievement_for_matching(self, achievement: dict[str, Any]) -> bool:
        category = str(achievement.get("category", "")).strip().lower()
        text = str(achievement.get("text", "")).strip().lower()
        if category == "confirm_skill":
            return True
        if category and category.startswith("confirm_skill_"):
            return True
        return "no tengo experiencia real con" in text

    def _score_experiences(self, experiences: list[dict[str, Any]], job: JobPostingNormalized) -> list[dict[str, Any]]:
        terms = {str(t).lower() for t in [*job.keywords, *job.required_skills, *job.preferred_skills] if str(t).strip()}
        scored: list[dict[str, Any]] = []
        for idx, exp in enumerate(experiences):
            text = " ".join(
                [
                    str(exp.get("title", "")),
                    str(exp.get("company", "")),
                    str(exp.get("summary", "")),
                    *[str(x) for x in exp.get("bullets", [])],
                    *[str(x) for x in exp.get("skills", [])],
                ]
            ).lower()
            matches = sorted([t for t in terms if t and t in text])
            match_score = min(100, len(matches) * 12 + (5 if exp.get("bullets") else 0))
            scored.append(
                {
                    "index": idx,
                    "title": exp.get("title"),
                    "company": exp.get("company"),
                    "match_score": match_score,
                    "matching_terms": matches[:12],
                }
            )
        scored.sort(key=lambda x: x["match_score"], reverse=True)
        return scored

    def _compute_score(
        self,
        required: list[str],
        preferred: list[str],
        matching_required: list[str],
        matching_preferred: list[str],
        exp_scores: list[dict[str, Any]],
    ) -> int:
        required_ratio = len(matching_required) / max(len(required), 1)
        preferred_ratio = (len(matching_preferred) / len(preferred)) if preferred else 0.5
        exp_ratio = ((sum(x["match_score"] for x in exp_scores[:3]) / max(min(3, len(exp_scores)), 1)) / 100) if exp_scores else 0
        score = round(required_ratio * 70 + preferred_ratio * 15 + exp_ratio * 15)
        return max(0, min(100, score))

    def _build_recommendations(
        self,
        job: JobPostingNormalized,
        matching_required: list[str],
        missing_required: list[str],
        exp_scores: list[dict[str, Any]],
    ) -> list[str]:
        recs: list[str] = []
        if exp_scores:
            top_titles = [str(e.get("title")) for e in exp_scores[:3] if e.get("title")]
            if top_titles:
                recs.append(f"Priorizar experiencias: {', '.join(top_titles)}.")
        if matching_required:
            recs.append(f"Enfatizar skills confirmadas: {', '.join(matching_required[:6])}.")
        if missing_required:
            recs.append(
                "Preguntar y confirmar evidencia para skills faltantes (sin inventar): "
                + ", ".join(missing_required[:6])
                + "."
            )
        if (job.seniority or "").lower() in {"lead", "senior", "principal"}:
            recs.append("Si está confirmado, incluir evidencia de liderazgo, coordinación o mentoring.")
        return recs

    def _norm(self, items: list[str]) -> list[str]:
        out = []
        seen = set()
        for item in items:
            value = re.sub(r"\s+", " ", str(item)).strip()
            key = value.lower()
            if not value or key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out

    def _dedupe(self, items: list[str]) -> list[str]:
        return self._norm(items)

    def _has_skill(self, text: str, skill: str) -> bool:
        return bool(re.search(rf"(?<!\w){re.escape(skill.lower())}(?!\w)", text, flags=re.I))
