from __future__ import annotations

from typing import Any

from cv_generator.domain.models import CVNormalized, MasterProfile, utc_now_iso


def source_meta(source: str, confidence: float) -> dict[str, Any]:
    return {
        "source": source,
        "confidence": round(float(confidence), 2),
        "last_updated": utc_now_iso(),
    }


class ProfileService:
    def merge_cv_into_profile(self, existing: MasterProfile | None, cv: CVNormalized, profile_id: str) -> MasterProfile:
        profile = existing or MasterProfile.empty(profile_id)
        cv_source = f"cv_{cv.source_type}"

        for key, value in cv.basics.items():
            if value and (key not in profile.basics or not profile.basics.get(key)):
                profile.basics[key] = value
        if cv.summary and (not profile.summary or len(profile.summary or "") < 20):
            profile.summary = cv.summary

        profile.experiences = self._merge_records(
            profile.experiences,
            cv.experiences,
            source=cv_source,
            identity_keys=("title", "company", "start_date"),
        )
        profile.education = self._merge_records(
            profile.education,
            cv.education,
            source=cv_source,
            identity_keys=("degree", "institution", "year"),
        )
        profile.projects = self._merge_records(
            profile.projects,
            cv.projects,
            source=cv_source,
            identity_keys=("name",),
        )
        profile.skills = self._merge_skills(profile.skills, cv.skills, source=cv_source, confidence=0.82)
        profile.languages = self._merge_languages(profile.languages, getattr(cv, "languages", []))

        profile.metadata.setdefault("sources", [])
        profile.metadata["sources"].append(
            {
                "source": cv_source,
                "ingested_at": utc_now_iso(),
                "warnings": cv.parsing_warnings,
            }
        )
        profile.metadata["updated_at"] = utc_now_iso()
        return profile

    def apply_interactive_answers(self, profile: MasterProfile, answers: list[dict[str, Any]]) -> MasterProfile:
        skill_confirmations = profile.metadata.setdefault("skill_confirmations", {})
        for answer in answers:
            profile.interaction_answers.append(answer)
            q_type = answer.get("question_type")
            text = str(answer.get("answer", "")).strip()
            if not text:
                continue

            if q_type == "confirm_skill":
                skill = str(answer.get("skill") or "").strip()
                if skill:
                    is_affirmative = self._looks_affirmative(text)
                    skill_confirmations[skill.lower()] = {
                        "skill": skill,
                        "confirmed": is_affirmative,
                        "evidence": text,
                        "metadata": source_meta("interactive_input", 0.9 if is_affirmative else 0.95),
                    }
                    if is_affirmative:
                        profile.skills = self._merge_skills(profile.skills, [skill], source="interactive_input", confidence=0.75)
            elif q_type in {"achievement", "leadership", "tool_detail"}:
                if self._looks_non_informative_negative(text):
                    continue
                profile.achievements = self._append_unique_record(
                    profile.achievements,
                    {
                        "text": text,
                        "category": q_type,
                        "metadata": source_meta("interactive_input", 0.9),
                    },
                    key="text",
                )
            elif q_type == "focus_preference":
                profile.metadata["cv_focus_preference"] = {
                    "value": text,
                    "metadata": source_meta("interactive_input", 0.95),
                }

        profile.metadata["updated_at"] = utc_now_iso()
        return profile

    def _merge_records(
        self,
        current: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
        source: str,
        identity_keys: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        result = list(current)
        idx = {self._record_key(item, identity_keys): i for i, item in enumerate(result)}
        for record in incoming:
            enriched = dict(record)
            enriched.setdefault("metadata", source_meta(source, 0.85))
            key = self._record_key(enriched, identity_keys)
            if key and key in idx:
                existing = dict(result[idx[key]])
                for field, value in enriched.items():
                    if field == "metadata":
                        continue
                    if value in (None, "", [], {}):
                        continue
                    if isinstance(value, list) and isinstance(existing.get(field), list):
                        existing[field] = self._merge_string_lists(existing.get(field, []), value)
                    elif not existing.get(field):
                        existing[field] = value
                meta = dict(existing.get("metadata", {}))
                meta["last_updated"] = utc_now_iso()
                existing["metadata"] = meta or source_meta(source, 0.85)
                result[idx[key]] = existing
            else:
                result.append(enriched)
        return result

    def _merge_skills(
        self,
        current: list[dict[str, Any]],
        skill_names: list[str],
        source: str,
        confidence: float,
    ) -> list[dict[str, Any]]:
        result = list(current)
        idx = {str(item.get("name", "")).strip().lower(): i for i, item in enumerate(result)}
        for skill in skill_names:
            skill_clean = skill.strip()
            if not skill_clean:
                continue
            key = skill_clean.lower()
            if key in idx:
                item = dict(result[idx[key]])
                sources = [str(s) for s in item.get("sources", [])]
                if source not in sources:
                    sources.append(source)
                item["sources"] = sources
                meta = dict(item.get("metadata", {}))
                meta["last_updated"] = utc_now_iso()
                item["metadata"] = meta or source_meta(source, confidence)
                result[idx[key]] = item
            else:
                result.append({"name": skill_clean, "sources": [source], "metadata": source_meta(source, confidence)})
        return result

    def _merge_languages(
        self,
        current: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = list(current)
        idx = {str(item.get("name", "")).strip().lower(): i for i, item in enumerate(result)}
        for lang in incoming or []:
            name = str(lang.get("name", "")).strip()
            if not name:
                continue
            key = name.lower()
            level = lang.get("level")
            if key in idx:
                item = dict(result[idx[key]])
                if level and not item.get("level"):
                    item["level"] = level
                result[idx[key]] = item
            else:
                result.append({"name": name, "level": level})
                idx[key] = len(result) - 1
        return result

    def _merge_string_lists(self, current: list[str], incoming: list[str]) -> list[str]:
        out = list(current)
        seen = {str(x).strip().lower() for x in out}
        for item in incoming:
            key = str(item).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(str(item).strip())
        return out

    def _record_key(self, record: dict[str, Any], identity_keys: tuple[str, ...]) -> str:
        parts = [str(record.get(k, "")).strip().lower() for k in identity_keys]
        return "|".join(parts) if any(parts) else ""

    def _append_unique_record(self, current: list[dict[str, Any]], record: dict[str, Any], key: str) -> list[dict[str, Any]]:
        norm = str(record.get(key, "")).strip().lower()
        if not norm:
            return current
        for item in current:
            if str(item.get(key, "")).strip().lower() == norm:
                return current
        return [*current, record]

    def _looks_non_informative_negative(self, text: str) -> bool:
        lowered = " ".join(text.lower().strip().split())
        if lowered in {"no", "no tengo", "no tengo.", "no aplica", "n/a", "ninguno", "ninguna", "sin experiencia"}:
            return True
        return lowered.startswith("no tengo metric")

    def _looks_affirmative(self, text: str) -> bool:
        lowered = text.lower()
        if any(tok in lowered for tok in [" no ", "ninguna", "nunca", "no tengo", "no he"]):
            return False
        return any(tok in lowered for tok in ["sí", "si", "yes", "tengo", "he usado", "utilicé", "utilice", "usé", "use"])
