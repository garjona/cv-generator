from __future__ import annotations

import re
from typing import Any

from cv_generator.domain.models import GeneratedCVContent, JobPostingNormalized, MasterProfile, MatchAnalysis


class CVContentBuilder:
    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

    def build(
        self,
        job: JobPostingNormalized,
        profile: MasterProfile,
        match: MatchAnalysis,
        pages: int,
        template_style: str,
    ) -> GeneratedCVContent:
        pages = 1 if pages not in {1, 2} else pages
        exp_limit = 3 if pages == 1 else 5
        bullets_limit = 3 if pages == 1 else 4
        project_limit = 1 if pages == 1 else 2

        prioritized_indices = [x["index"] for x in match.prioritized_experiences[:exp_limit]]
        selected_raw: list[dict[str, Any]] = [
            profile.experiences[idx] for idx in prioritized_indices if 0 <= idx < len(profile.experiences)
        ]
        if not selected_raw:
            selected_raw = list(profile.experiences[:exp_limit])
        # Selección por relevancia, pero orden de despliegue cronológico inverso (estándar en CV).
        selected_raw = sorted(selected_raw, key=self._experience_sort_key, reverse=True)
        # Bullets escalonados: el rol más reciente/relevante muestra más; los antiguos menos,
        # para densificar sin desbordar el objetivo de páginas.
        bullet_limits = self._bullet_limits(pages, len(selected_raw), bullets_limit)
        selected_experiences = [self._format_experience(e, bullet_limits[i]) for i, e in enumerate(selected_raw)]
        selected_experiences = self._refine_experiences_for_job(job, match, selected_experiences, bullet_limits)

        selected_projects = [self._format_project(p, bullets_limit) for p in profile.projects[:project_limit]]
        selected_education = [self._format_education(e) for e in profile.education[:2]]
        selected_skills = self._build_skills(profile, match, limit=12 if pages == 1 else 18)
        summary = self._build_summary(job, profile, match, selected_skills, selected_experiences)

        latex_context = {
            "candidate_name": profile.basics.get("name", "Candidato/a"),
            "professional_title": self._professional_title(profile, selected_raw),
            "contact_lines": self._contact_lines(profile.basics),
            "contact_links": self._contact_links(profile.basics),
            "job_target": {"title": job.title, "company": job.company, "location": job.location},
            "professional_summary": summary,
            "skills_section_title": "Habilidades Relevantes",
            "skills": selected_skills,
            "languages": self._build_languages(profile),
            "experiences": selected_experiences,
            "projects": selected_projects,
            "education": selected_education,
            "achievements": self._select_achievements(profile, pages),
            "page_target": pages,
            "focus_preference": profile.metadata.get("cv_focus_preference", {}).get("value"),
        }

        report = self._build_report(job, match, selected_experiences, pages, template_style, profile)
        qa_warnings = self._basic_checks(latex_context, match)

        return GeneratedCVContent(
            template_style=template_style,
            page_target=pages,
            latex_context=latex_context,
            report_markdown=report,
            qa_warnings=qa_warnings,
        )

    CONTACT_KEYS = ["email", "phone", "linkedin", "github", "portfolio", "location"]

    def _contact_lines(self, basics: dict[str, Any]) -> list[str]:
        values = [str(basics.get(k, "")).strip() for k in self.CONTACT_KEYS if str(basics.get(k, "")).strip()]
        return values[:5]

    def _contact_links(self, basics: dict[str, Any]) -> list[dict[str, Any]]:
        """Contactos con su href, para que los links queden clickeables en el PDF."""
        out: list[dict[str, Any]] = []
        for key in self.CONTACT_KEYS:
            value = str(basics.get(key, "")).strip()
            if not value:
                continue
            label = re.sub(r"^https?://", "", value)
            href: str | None = None
            if key == "email":
                href = f"mailto:{value}"
            elif key == "phone":
                digits = re.sub(r"[^\d+]", "", value)
                href = f"tel:{digits}" if digits else None
            elif key in {"linkedin", "github", "portfolio"}:
                href = value if value.lower().startswith("http") else f"https://{value}"
            out.append({"label": label, "href": href})
        return out[:5]

    def _professional_title(self, profile: MasterProfile, selected_raw: list[dict[str, Any]]) -> str:
        headline = str(profile.basics.get("headline", "")).strip()
        if headline:
            return headline
        # Fallback honesto: título del cargo más reciente del propio perfil (no de la oferta).
        for exp in selected_raw or profile.experiences:
            title = str(exp.get("title", "")).strip()
            if title:
                return title
        return ""

    def _build_languages(self, profile: MasterProfile) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for lang in getattr(profile, "languages", []) or []:
            name = str(lang.get("name", "")).strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append({"name": name, "level": str(lang.get("level") or "").strip() or None})
        return out

    def _experience_sort_key(self, exp: dict[str, Any]) -> tuple[int, int]:
        """Clave cronológica descendente. 'Actualidad'/'Presente' pesa como el futuro."""
        end = self._date_sort_value(exp.get("end_date"))
        start = self._date_sort_value(exp.get("start_date"))
        return (end, start)

    def _date_sort_value(self, value: Any) -> int:
        text = str(value or "").strip().lower()
        if not text:
            return 0
        if any(tok in text for tok in ["actualidad", "presente", "current", "present"]):
            return 999912
        year_match = re.search(r"(19|20)\d{2}", text)
        if not year_match:
            return 0
        year = int(year_match.group(0))
        month_match = re.search(r"-(\d{1,2})\b", text)
        month = int(month_match.group(1)) if month_match else 0
        return year * 100 + month

    def _build_skills(self, profile: MasterProfile, match: MatchAnalysis, limit: int) -> list[str]:
        ordered = []
        seen = set()
        negative = self._negative_skill_confirmations(profile)
        for skill in [*match.matching_skills, *[str(s.get("name", "")) for s in profile.skills]]:
            val = self._canonical_skill_label(str(skill).strip())
            key = val.lower()
            if not val or key in seen or key in negative or self._should_omit_skill_label(val):
                continue
            seen.add(key)
            ordered.append(val)
            if len(ordered) >= limit:
                break
        return ordered

    def _build_summary(
        self,
        job: JobPostingNormalized,
        profile: MasterProfile,
        match: MatchAnalysis,
        skills: list[str],
        selected_experiences: list[dict[str, Any]],
    ) -> str:
        focus = ", ".join(skills[:5]) if skills else "habilidades técnicas relevantes"
        exp_titles = [str(e.get("title")) for e in selected_experiences[:2] if e.get("title")]
        deterministic = (
            f"Profesional con experiencia en {focus}, orientado/a a roles de {job.title}. "
            "Enfoque en resultados, ejecución y colaboración con equipos multidisciplinarios."
        )
        if exp_titles:
            deterministic = (
                f"Profesional con experiencia en {focus}, con trayectoria en {', '.join(exp_titles)} y enfoque en {job.title}. "
                "Capacidad para priorizar entregables y comunicar avances con claridad."
            )

        base_summary = (profile.summary or "").strip()
        if self.llm_client and getattr(self.llm_client, "is_available", lambda: False)():
            system_prompt = (
                "Reescribe un resumen de CV en español usando SOLO los hechos provistos. "
                "No inventes años, empresas, logros ni tecnologías. Devuelve 2-3 frases."
            )
            user_prompt = (
                f"Oferta objetivo: {job.title}\n"
                f"Skills confirmadas: {', '.join(skills[:8])}\n"
                f"Experiencias seleccionadas: {', '.join(exp_titles)}\n"
                f"Resumen base: {base_summary}\n"
                f"Resumen sugerido: {deterministic}\n"
            )
            llm_text = self.llm_client.complete(system_prompt, user_prompt, temperature=0.1)
            if llm_text:
                return self._sanitize_sentences(llm_text, 3)

        # Si el resumen base del propio CV ya es sólido, se usa tal cual (evita
        # duplicar ideas y mencionar el cargo objetivo con sufijos de la oferta).
        if base_summary and len(base_summary) >= 120:
            return self._sanitize_sentences(base_summary, 4)
        if base_summary and len(base_summary) > 20:
            return self._sanitize_sentences(base_summary + " " + deterministic, 4)
        return deterministic

    def _format_experience(self, exp: dict[str, Any], bullets_limit: int) -> dict[str, Any]:
        bullets = [self._clean_candidate_line(str(b)) for b in exp.get("bullets", []) if str(b).strip()]
        bullets = [b for b in bullets if b]
        summary = self._clean_candidate_line(str(exp.get("summary") or "").strip())
        if summary and summary not in bullets:
            bullets = [summary, *bullets]
        bullets = self._dedupe_strings(bullets)[:bullets_limit]
        return {
            "title": exp.get("title"),
            "company": exp.get("company"),
            "date_range": self._date_range(exp.get("start_date"), exp.get("end_date")),
            "location": exp.get("location"),
            "bullets": bullets,
            "skills": self._canonical_skill_list(exp.get("skills", []), limit=6),
        }

    def _format_project(self, proj: dict[str, Any], bullets_limit: int) -> dict[str, Any]:
        bullets = [self._clean_candidate_line(str(b)) for b in proj.get("bullets", []) if str(b).strip()]
        bullets = [b for b in bullets if b]
        if not bullets and proj.get("description"):
            cleaned_description = self._clean_candidate_line(str(proj["description"]).strip())
            bullets = [cleaned_description] if cleaned_description else []
        return {
            "name": proj.get("name"),
            "bullets": self._dedupe_strings(bullets)[:bullets_limit],
            "skills": self._canonical_skill_list(proj.get("skills", []), limit=6),
        }

    def _format_education(self, edu: dict[str, Any]) -> dict[str, Any]:
        details = []
        for x in edu.get("details", []):
            text = self._clean_candidate_line(str(x))
            if not text:
                continue
            if "pendiente de completar" in text.lower():
                continue
            details.append(text)
        return {
            "degree": edu.get("degree"),
            "institution": edu.get("institution"),
            "year": edu.get("year"),
            "details": details[:2],
        }

    def _date_range(self, start: Any, end: Any) -> str | None:
        start_s = str(start).strip() if start else ""
        end_s = str(end).strip() if end else ""
        if not start_s and not end_s:
            return None
        return f"{start_s} - {end_s}".strip(" -")

    def _select_achievements(self, profile: MasterProfile, pages: int) -> list[str]:
        limit = 2 if pages == 1 else 4
        out: list[str] = []
        for achievement in profile.achievements:
            category = str(achievement.get("category", "")).strip().lower()
            if category == "confirm_skill" or category.startswith("confirm_skill_"):
                continue
            text = str(achievement.get("text", "")).strip()
            if not text:
                continue
            if self._looks_non_informative_achievement(text):
                continue
            out.append(text)
            if len(out) >= limit:
                break
        return out

    def _build_report(
        self,
        job: JobPostingNormalized,
        match: MatchAnalysis,
        selected_experiences: list[dict[str, Any]],
        pages: int,
        template_style: str,
        profile: MasterProfile,
    ) -> str:
        lines = [
            "# CV Generation Report",
            "",
            "## Resumen",
            f"- Oferta objetivo: {job.title}",
            f"- Empresa: {job.company or 'No detectada'}",
            f"- Seniority: {job.seniority or 'No detectado'}",
            f"- Páginas objetivo: {pages}",
            f"- Plantilla: {template_style}",
            f"- Score compatibilidad: {match.compatibility_score}/100",
            "- Refinamiento de contenido: priorizacion deterministica de bullets por relevancia a la oferta (sin inventar informacion).",
            "",
            "## Matching",
            f"- Skills coincidentes: {', '.join(match.matching_skills) if match.matching_skills else 'Ninguna'}",
            f"- Skills faltantes/no confirmadas: {', '.join(match.missing_skills) if match.missing_skills else 'Ninguna'}",
            "",
            "## Experiencias priorizadas y seleccionadas",
        ]
        if selected_experiences:
            for exp in selected_experiences:
                lines.append(f"- {exp.get('title', 'Experiencia')} ({exp.get('company') or 'Sin empresa'})")
        else:
            lines.append("- Sin experiencias estructuradas")

        lines.extend(["", "## Recomendaciones aplicadas"])
        for rec in match.recommendations:
            lines.append(f"- {rec}")

        lines.extend(
            [
                "",
                "## Reglas anti-alucinación",
                "- Se usó únicamente información del CV base, perfil maestro y respuestas interactivas confirmadas.",
                "- Las skills faltantes se reportan como gap y no se agregan como conocimiento afirmado.",
            ]
        )

        if profile.interaction_answers:
            lines.extend(["", "## Respuestas interactivas guardadas"])
            for ans in profile.interaction_answers[-8:]:
                lines.append(f"- [{ans.get('question_type')}] {ans.get('answer', '')}")

        return "\n".join(lines) + "\n"

    def _basic_checks(self, latex_context: dict[str, Any], match: MatchAnalysis) -> list[str]:
        warnings = []
        if not latex_context.get("experiences"):
            warnings.append("El CV generado no incluye experiencias estructuradas.")
        blob = " ".join(
            [
                str(latex_context.get("professional_summary", "")),
                " ".join(str(s) for s in latex_context.get("skills", [])),
                " ".join(" ".join(exp.get("bullets", [])) for exp in latex_context.get("experiences", [])),
            ]
        ).lower()
        confirmed = {s.lower() for s in match.matching_skills}
        for missing in match.missing_skills:
            if missing.lower() in blob and missing.lower() not in confirmed:
                warnings.append(f"Revisar mención de skill no confirmada en salida: {missing}")
        return warnings

    def _bullet_limits(self, pages: int, count: int, base: int) -> list[int]:
        if count <= 0:
            return []
        pattern = [3, 2] if pages == 1 else [4, 3, 3, 2]
        tail = pattern[-1] if pattern else base
        return [pattern[i] if i < len(pattern) else tail for i in range(count)]

    def _refine_experiences_for_job(
        self,
        job: JobPostingNormalized,
        match: MatchAnalysis,
        experiences: list[dict[str, Any]],
        bullets_limit: int | list[int],
    ) -> list[dict[str, Any]]:
        focus_terms = self._job_focus_terms(job, match)
        refined: list[dict[str, Any]] = []
        for i, exp in enumerate(experiences):
            exp_copy = dict(exp)
            limit = bullets_limit[i] if isinstance(bullets_limit, list) else bullets_limit
            bullets = [str(b).strip() for b in exp_copy.get("bullets", []) if str(b).strip()]
            exp_copy["bullets"] = self._refine_bullets_for_job(bullets, focus_terms, limit)
            refined.append(exp_copy)
        return refined

    def _refine_bullets_for_job(self, bullets: list[str], focus_terms: list[str], limit: int) -> list[str]:
        if not bullets:
            return []
        expanded: list[str] = []
        for bullet in bullets:
            expanded.extend(self._split_long_bullet(self._clean_candidate_line(bullet)))
        expanded = [b for b in expanded if b]
        if not expanded:
            return []

        scored: list[tuple[int, int, str]] = []
        for idx, bullet in enumerate(expanded):
            scored.append((self._bullet_relevance_score(bullet, focus_terms), idx, bullet))
        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)

        selected: list[str] = []
        seen = set()
        for _, _, bullet in scored:
            norm = bullet.lower()
            if norm in seen:
                continue
            seen.add(norm)
            selected.append(bullet)
            if len(selected) >= limit:
                break

        ordered: list[str] = []
        for bullet in expanded:
            if bullet in selected and bullet not in ordered:
                ordered.append(bullet)
        for bullet in selected:
            if bullet not in ordered:
                ordered.append(bullet)
        return ordered[:limit]

    def _job_focus_terms(self, job: JobPostingNormalized, match: MatchAnalysis) -> list[str]:
        seed_terms = [
            *job.required_skills,
            *job.preferred_skills,
            *job.keywords,
            *match.matching_skills,
            "business intelligence",
            "analisis de datos",
            "análisis de datos",
            "data insights",
            "automatizacion",
            "automatización",
            "reportes",
            "metricas",
            "métricas",
            "python",
            "sql",
            "dataflow",
            "bigquery",
            "etl",
            "ia",
            "inteligencia artificial",
            "negocio",
        ]
        out: list[str] = []
        seen = set()
        for term in seed_terms:
            value = re.sub(r"\s+", " ", str(term)).strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
        return out

    def _bullet_relevance_score(self, bullet: str, focus_terms: list[str]) -> int:
        text = bullet.lower()
        score = 0
        for term in focus_terms:
            if term and term in text:
                score += 8 if len(term) <= 6 else 10
        for token in [
            "desarrollo",
            "implement",
            "automatiz",
            "anal",
            "report",
            "etl",
            "pipeline",
            "datos",
            "negocio",
            "requerimientos",
            "lider",
            "coordin",
        ]:
            if token in text:
                score += 3
        if any(ch.isdigit() for ch in bullet):
            score += 2
        return score

    def _split_long_bullet(self, bullet: str) -> list[str]:
        text = str(bullet or "").strip()
        if not text:
            return []
        if len(text) <= 240:
            return [text]
        parts = [p.strip() for p in re.split(r"(?<=[\.\!\?])\s+", text) if p.strip()]
        if len(parts) <= 1:
            return [text]
        return [re.sub(r"^\-\s*", "", part).strip() for part in parts if part.strip()]

    def _clean_candidate_line(self, text: str) -> str:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        if not value:
            return ""
        value = re.sub(r"\((?:seg[uú]n|recomendad[oa]).*?\)", "", value, flags=re.I)
        value = re.sub(r",?\s*seg[uú]n [^)]*(\))", r"\1", value, flags=re.I)
        value = re.sub(r",?\s*seg[uú]n [^\.]*?(?:cv previo|cv anterior)[^\.]*", "", value, flags=re.I)
        value = re.sub(r"\(\s*([^)]+?)\s*\.\s*\)", r"(\1)", value)
        if value.count("(") > value.count(")"):
            value = value.replace("(", "", 1)
        value = re.sub(r"\s{2,}", " ", value).strip(" -")
        if value.lower().startswith("pendiente de completar"):
            return ""
        return value

    def _looks_non_informative_achievement(self, text: str) -> bool:
        lowered = " ".join(str(text).lower().strip().split())
        if lowered in {"no", "no tengo", "no tengo.", "no aplica", "n/a"}:
            return True
        return lowered.startswith("no tengo metric")

    def _canonical_skill_label(self, label: str) -> str:
        value = str(label or "").strip()
        key = value.lower()
        mapping = {
            "sql": "SQL",
            "python": "Python",
            "dataflow": "DataFlow",
            "business intelligence": "Business Intelligence",
            "etl": "ETL",
            "bigquery": "BigQuery",
            "gcp": "GCP",
            "git": "Git",
            "linux": "Linux",
            "java": "Java",
            "c#": "C#",
            "spark": "Spark",
            "postgresql": "PostgreSQL",
            "api": "API",
            "microservicios": "Microservicios",
            "pandas": "Pandas",
            "numpy": "NumPy",
            "ia generativa": "IA Generativa",
            "vertex ai": "Vertex AI",
            "cloud run": "Cloud Run",
            "cloud storage": "Cloud Storage",
            "jupyter notebook": "Jupyter Notebook",
            "google cloud platform (gcp)": "Google Cloud Platform (GCP)",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "fastapi": "FastAPI",
            "flask": "Flask",
            "django": "Django",
            "node.js": "Node.js",
            ".net": ".NET",
            "go": "Go",
            "golang": "Go",
            "grpc": "gRPC",
            "graphql": "GraphQL",
            "pub/sub": "Pub/Sub",
            "pubsub": "Pub/Sub",
            "kafka": "Kafka",
            "firestore": "Firestore",
            "redis": "Redis",
            "datadog": "Datadog",
            "grafana": "Grafana",
            "prometheus": "Prometheus",
            "cloud monitoring": "Cloud Monitoring",
            "pytest": "pytest",
            "ci/cd": "CI/CD",
            "github actions": "GitHub Actions",
            "jenkins": "Jenkins",
            "cloud build": "Cloud Build",
            "kubernetes": "Kubernetes",
            "terraform": "Terraform",
            "mcp": "MCP",
            "llm": "LLM",
            "llms": "LLMs",
            "claude code": "Claude Code",
            "oracle": "Oracle",
            "sql server": "SQL Server",
            "rest": "REST",
            "sistemas distribuidos": "Sistemas distribuidos",
            "observabilidad": "Observabilidad",
            "testing automatizado": "Testing automatizado",
            "looker": "Looker Studio",
            "looker studio": "Looker Studio",
            "tableau": "Tableau",
            "power bi": "Power BI",
            "sql server": "SQL Server",
            "mcp": "MCP",
            "llms": "LLMs",
        }
        return mapping.get(key, value)

    def _canonical_skill_list(self, skills: list[Any], limit: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for skill in skills:
            label = self._canonical_skill_label(str(skill).strip())
            key = label.lower()
            if not label or key in seen or self._should_omit_skill_label(label):
                continue
            seen.add(key)
            out.append(label)
            if len(out) >= limit:
                break
        return out

    def _should_omit_skill_label(self, label: str) -> bool:
        # Ubicaciones y modalidades se filtran: llegan desde la oferta pero no son skills.
        if label.strip().lower() in {
            "chile",
            "santiago",
            "región metropolitana",
            "region metropolitana",
            "remoto",
            "híbrido",
            "hibrido",
            "presencial",
        }:
            return True
        return label.strip().lower() in {
            "comunicación",
            "comunicacion",
            "liderazgo",
            "aprendizaje continuo",
            "adaptabilidad",
            "respeto",
            "compañerismo",
            "companerismo",
            "cloud & ia (google cloud)",
            "datos / bi / analítica",
            "datos / bi / analitica",
            "programación",
            "programacion",
            "integración",
            "integracion",
            "backend",
            "dev",
        }

    def _sanitize_sentences(self, text: str, max_sentences: int) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        parts = re.split(r"(?<=[\.\!\?])\s+", text)
        return " ".join(parts[:max_sentences]).strip()

    def _dedupe_strings(self, items: list[str]) -> list[str]:
        out = []
        seen = set()
        for item in items:
            val = str(item).strip()
            key = val.lower()
            if not val or key in seen:
                continue
            seen.add(key)
            out.append(val)
        return out

    def _negative_skill_confirmations(self, profile: MasterProfile) -> set[str]:
        confirmations = profile.metadata.get("skill_confirmations", {})
        if not isinstance(confirmations, dict):
            return set()
        out = set()
        for key, value in confirmations.items():
            if isinstance(value, dict) and value.get("confirmed") is False:
                out.add(str(value.get("skill") or key).strip().lower())
        return out


class SimpleQAAgent:
    def validate(self, generated: GeneratedCVContent, profile: MasterProfile, job: JobPostingNormalized) -> list[str]:
        warnings = list(generated.qa_warnings)
        if not profile.basics.get("name"):
            warnings.append("No se detectó nombre en el perfil; encabezado genérico.")
        if not generated.latex_context.get("skills"):
            warnings.append("No se incluyeron skills en el CV generado.")
        if not job.title:
            warnings.append("Oferta sin título; personalización limitada.")
        return warnings
