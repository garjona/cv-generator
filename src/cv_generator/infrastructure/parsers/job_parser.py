from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from cv_generator.domain.domain_config import DomainConfig
from cv_generator.domain.models import JobPostingNormalized

COMMON_SKILLS = [
    "python",
    "sql",
    "excel",
    "power bi",
    "tableau",
    "looker",
    "bigquery",
    "dataflow",
    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    "git",
    "linux",
    "javascript",
    "typescript",
    "react",
    "node.js",
    "java",
    "c#",
    ".net",
    "spring",
    "django",
    "flask",
    "fastapi",
    "pandas",
    "numpy",
    "scikit-learn",
    "tensorflow",
    "pytorch",
    "machine learning",
    "ml",
    "nlp",
    "llm",
    "openai",
    "ia generativa",
    "business intelligence",
    "ci/cd",
    "jenkins",
    "github actions",
    "scrum",
    "agile",
    "etl",
    "spark",
    "hadoop",
    "postgresql",
    "mysql",
    "mongodb",
    "redis",
    "api",
    "rest",
    "restful",
    "microservicios",
    "comunicacion",
    "comunicación",
    "liderazgo",
    "gestion de proyectos",
    "gestión de proyectos",
    # Lenguajes / frameworks backend
    "go",
    "golang",
    "grpc",
    "graphql",
    # Mensajería / eventos / streaming
    "pub/sub",
    "pubsub",
    "kafka",
    "rabbitmq",
    "event-driven",
    "sistemas distribuidos",
    # Datos / almacenamiento
    "firestore",
    "sql server",
    "oracle",
    "cloud storage",
    # GCP / infra
    "cloud run",
    "cloud build",
    "vertex ai",
    "terraform",
    # Observabilidad / testing
    "datadog",
    "grafana",
    "prometheus",
    "observabilidad",
    "pytest",
    "testing automatizado",
    # GenAI / agentes / tooling de IA
    "mcp",
    "model context protocol",
    "claude code",
    "codex",
    "copilot",
    "cursor",
    "agentes",
    "rag",
]

STOPWORDS_ES = {
    "de", "la", "el", "y", "en", "para", "con", "un", "una", "que", "del", "los", "las",
    "por", "se", "al", "como", "su", "o", "a", "tu", "te", "ser", "más", "mas", "lo",
    "trabajo", "empresa", "equipo", "experiencia", "años", "anos", "requisitos", "responsabilidades",
    "deseable", "skills", "habilidades", "perfil", "posición", "puesto", "rol",
}


class JobPostingParser:
    def __init__(self, domain: DomainConfig | None = None) -> None:
        # Sin dominio explícito se usa el catálogo tech histórico, para no
        # romper a quien ya use el parser sin configuración.
        self.domain = domain
        self._skills = list(domain.skills) if domain and domain.skills else list(COMMON_SKILLS)

    def parse_path(self, path: Path) -> JobPostingNormalized:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix.lower() in {".html", ".htm"}:
            return self._parse(text, source_type="html")
        return self._parse(text, source_type="txt")

    def parse_text(self, text: str) -> JobPostingNormalized:
        return self._parse(text, source_type="txt")

    def _parse(self, raw: str, source_type: str) -> JobPostingNormalized:
        warnings: list[str] = []
        title_tag_text: str | None = None

        if source_type == "html":
            cleaned_text, html_title, html_h1 = self._html_to_text(raw)
            title_tag_text = html_h1 or html_title
            raw_text = cleaned_text or self._strip_tags_basic(raw)
            if not cleaned_text.strip():
                warnings.append("No se pudo extraer texto útil del HTML; se usó limpieza básica.")
        else:
            raw_text = raw

        lines = self._clean_lines(raw_text)
        if source_type == "html":
            lines = self._drop_html_noise_lines(lines)
        if not lines:
            warnings.append("La oferta quedó vacía tras la limpieza.")
            lines = ["Oferta sin contenido detectable"]

        title = self._extract_title(lines, title_tag_text) or "Puesto no identificado"
        company = self._extract_company(lines)
        location = self._extract_location(lines)
        seniority = self._infer_seniority(raw_text, title)
        responsibilities = self._extract_bullets_under_headers(
            lines,
            [
                "responsabilidades",
                "funciones",
                "que haras",
                "qué harás",
                "tu misión",
                "actividades",
                "siendo responsable de",
                "responsable de",
                "imaginate emprendiendo proyectos",
                "imagínate emprendiendo proyectos",
            ],
        )
        req_lines = self._extract_bullets_under_headers(
            lines,
            ["requisitos", "requerimientos", "must have", "imprescindible", "perfil requerido"],
        )
        pref_lines = self._extract_bullets_under_headers(
            lines,
            ["deseable", "nice to have", "plus", "valorado", "preferible"],
        )
        soft_req_lines = [line for line in req_lines if re.search(r"\b(deseable|plus|valorad[oa]|nice to have)\b", line, re.I)]
        if soft_req_lines:
            req_lines = [line for line in req_lines if line not in soft_req_lines]
            pref_lines = self._dedupe_preserve_order([*soft_req_lines, *pref_lines])

        required_skill_source = " ".join(req_lines) if req_lines else raw_text
        preferred_skill_source = " ".join(pref_lines) if pref_lines else ""
        required_skills = self._extract_skills(required_skill_source, req_lines or lines)
        preferred_skills = self._extract_skills(preferred_skill_source, pref_lines) if pref_lines else []
        keywords = self._extract_keywords(raw_text, title, responsibilities, required_skills, preferred_skills)

        if not responsibilities:
            warnings.append("No se detectó bloque claro de responsabilidades.")
        if not required_skills:
            warnings.append("No se detectaron skills requeridas con alta confianza.")

        return JobPostingNormalized(
            title=title,
            company=company,
            location=location,
            seniority=seniority,
            responsibilities=responsibilities,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            keywords=keywords,
            raw_text="\n".join(lines),
            source_type=source_type,
            parsing_warnings=warnings,
        )

    def _html_to_text(self, html: str) -> tuple[str, str | None, str | None]:
        try:
            from bs4 import BeautifulSoup  # type: ignore
        except Exception:
            return self._strip_tags_basic(html), None, None

        soup = BeautifulSoup(html, "lxml")
        for tag_name in ["script", "style", "nav", "footer", "header", "noscript", "aside"]:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        title = soup.title.get_text(" ", strip=True) if soup.title else None
        h1 = soup.find("h1")
        h1_text = h1.get_text(" ", strip=True) if h1 else None
        text = soup.get_text("\n", strip=True)
        return text, title, h1_text

    def _strip_tags_basic(self, html: str) -> str:
        html = re.sub(r"(?is)<head.*?>.*?</head>", " ", html)
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        text = re.sub(r"(?is)<[^>]+>", "\n", text)
        return re.sub(r"\n{2,}", "\n", text)

    def _clean_lines(self, text: str) -> list[str]:
        lines = []
        for line in text.splitlines():
            line = re.sub(r"\s+", " ", line).strip(" \t\r\n")
            line = re.sub(r"^[\-\*\u2022]+\s*", "", line)
            if not line or len(line) <= 2:
                continue
            lines.append(line)
        return lines

    def _drop_html_noise_lines(self, lines: list[str]) -> list[str]:
        noise_words = {"menu", "menú", "inicio", "empleos", "blog", "contacto", "cookies", "privacidad"}
        cleaned: list[str] = []
        for line in lines:
            norm = self._normalize(line)
            if norm.startswith("©"):
                continue
            if "|" in line:
                tokens = [t.strip().lower() for t in line.split("|") if t.strip()]
                if len(tokens) >= 3 and all(tok in noise_words for tok in tokens):
                    continue
            if norm in noise_words:
                continue
            cleaned.append(line)
        return cleaned

    def _extract_title(self, lines: list[str], title_tag_text: str | None) -> str | None:
        if title_tag_text:
            cleaned = self._clean_lines(title_tag_text)
            if cleaned:
                return cleaned[0]
        for line in lines[:8]:
            if len(line) < 110 and not re.search(r"(requisitos|responsabilidades|beneficios|aplica)", line, re.I):
                return line
        return None

    def _extract_company(self, lines: list[str]) -> str | None:
        patterns = [
            re.compile(r"^(?:empresa|compañ[ií]a|compania)\s*:\s*(.+)$", re.I),
            re.compile(r"^En\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ ]+?)\s+estamos\b", re.I),
        ]
        for line in lines[:15]:
            for pattern in patterns:
                m = pattern.search(line)
                if m:
                    return m.group(1).strip()
        if lines:
            # Fallback: title often includes business unit suffix after " - "
            first = lines[0]
            if " - " in first:
                _, tail = first.split(" - ", 1)
                if 2 <= len(tail.split()) <= 5:
                    return tail.strip()
        return None

    def _extract_location(self, lines: list[str]) -> str | None:
        patterns = [
            re.compile(r"^(?:ubicaci[oó]n|location|lugar)\s*:\s*(.+)$", re.I),
            re.compile(r"\b(remoto|h[ií]brido|presencial)\b", re.I),
        ]
        for line in lines[:20]:
            for pattern in patterns:
                m = pattern.search(line)
                if m:
                    return m.group(m.lastindex or 1).strip()
        for line in lines[:8]:
            if len(line) <= 90 and re.search(r"\b(chile|argentina|mexico|méxico|colombia|peru|perú|santiago|bogotá|buenos aires)\b", line, re.I):
                if not re.search(r"(puesto|empleo|id de puesto|postularse|curriculum|currículum)", line, re.I):
                    return line.strip()
        return None

    def _infer_seniority(self, text: str, title: str) -> str | None:
        joined = f"{title}\n{text}".lower()
        mapping = [
            ("principal", "principal"),
            ("staff", "staff"),
            ("lead", "lead"),
            ("senior", "senior"),
            ("sr.", "senior"),
            ("semi senior", "semi-senior"),
            ("semisenior", "semi-senior"),
            ("ssr", "semi-senior"),
            ("junior", "junior"),
            ("jr.", "junior"),
            ("trainee", "trainee"),
            ("practicante", "intern"),
            ("intern", "intern"),
        ]
        for token, normalized in mapping:
            if token in joined:
                return normalized
        return None

    def _extract_bullets_under_headers(self, lines: list[str], header_keywords: list[str]) -> list[str]:
        headers = [self._normalize(h) for h in header_keywords]
        bullets: list[str] = []
        capture = False
        stop_keywords = [
            "requisitos",
            "¿cuales son los requisitos",
            "cuales son los requisitos",
            "deseable",
            "te proponemos",
            "te ofrecemos",
            "beneficios",
            "postularse",
            "sumate a nuestro equipo",
        ]
        stop_keywords_norm = [self._normalize(x) for x in stop_keywords]
        for line in lines:
            norm = self._normalize(line)
            if any(h in norm for h in headers):
                capture = True
                continue
            if capture and any(sk in norm for sk in stop_keywords_norm):
                break
            if capture and re.match(r"^[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ ]{0,40}:?$", line) and len(line.split()) <= 5:
                break
            if capture:
                bullets.append(line)
                if len(bullets) >= 12:
                    break
        return self._dedupe_preserve_order([b for b in bullets if len(b) > 4])

    def _extract_skills(self, text: str, candidate_lines: list[str]) -> list[str]:
        haystack = f"{text}\n" + "\n".join(candidate_lines)
        haystack_low = haystack.lower()
        found: list[str] = []
        for skill in self._skills:
            pattern = re.escape(skill).replace(r"\ ", r"\s+")
            if re.search(rf"(?<!\w){pattern}(?!\w)", haystack_low, flags=re.I):
                normalized = self._canonical_skill_name(skill)
                found.append(normalized)

        for line in candidate_lines:
            if "," not in line or len(line) > 180:
                continue
            if len(line.split()) > 12:
                continue
            for part in [p.strip() for p in line.split(",") if p.strip()]:
                cleaned_part = self._clean_skill_fragment(part)
                if 2 <= len(cleaned_part) <= 35 and re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", cleaned_part):
                    if any(t in cleaned_part.lower() for t in ["años", "anos", "experiencia", "capacidad"]):
                        continue
                    if (" y " in cleaned_part.lower() or " o " in cleaned_part.lower()) and len(cleaned_part.split()) > 2:
                        continue
                    found.append(self._canonical_skill_name(cleaned_part))
        return self._dedupe_preserve_order(found)[:25]

    def _extract_keywords(
        self,
        raw_text: str,
        title: str,
        responsibilities: list[str],
        required_skills: list[str],
        preferred_skills: list[str],
    ) -> list[str]:
        source = " ".join([title, raw_text, *responsibilities, *required_skills, *preferred_skills]).lower()
        tokens = re.findall(r"[a-záéíóúñ0-9\+\#\.]{3,}", source, flags=re.I)
        filtered = []
        for tok in tokens:
            if tok in STOPWORDS_ES or tok.isdigit():
                continue
            filtered.append(tok)
        counts = Counter(filtered)
        top_words = [word for word, _ in counts.most_common(20)]
        return self._dedupe_preserve_order([*required_skills, *preferred_skills, *top_words])[:30]

    def _normalize(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.lower().strip())

    def _canonical_skill_name(self, skill: str) -> str:
        if self.domain and self.domain.canonical_labels:
            mapped = self.domain.canonical_labels.get(skill.lower())
            if mapped:
                return mapped
        canonical = {
            "sql": "SQL",
            "aws": "AWS",
            "gcp": "GCP",
            "git": "Git",
            "etl": "ETL",
            "api": "API",
            "rest": "REST",
            "ci/cd": "CI/CD",
            "llm": "LLM",
            "nlp": "NLP",
            "ml": "ML",
            "pandas": "Pandas",
            "numpy": "NumPy",
            "postgresql": "PostgreSQL",
            "bigquery": "BigQuery",
            "dataflow": "DataFlow",
            "looker": "Looker",
            "ia generativa": "IA Generativa",
            "business intelligence": "Business Intelligence",
            "go": "Go",
            "golang": "Go",
            "grpc": "gRPC",
            "graphql": "GraphQL",
            "pub/sub": "Pub/Sub",
            "pubsub": "Pub/Sub",
            "kafka": "Kafka",
            "rabbitmq": "RabbitMQ",
            "event-driven": "Arquitectura orientada a eventos",
            "firestore": "Firestore",
            "sql server": "SQL Server",
            "oracle": "Oracle",
            "cloud storage": "Cloud Storage",
            "cloud run": "Cloud Run",
            "cloud build": "Cloud Build",
            "vertex ai": "Vertex AI",
            "terraform": "Terraform",
            "datadog": "Datadog",
            "grafana": "Grafana",
            "prometheus": "Prometheus",
            "pytest": "pytest",
            "mcp": "MCP",
            "model context protocol": "MCP",
            "claude code": "Claude Code",
            "codex": "Codex",
            "copilot": "Copilot",
            "cursor": "Cursor",
            "restful": "REST",
            "fastapi": "FastAPI",
            "node.js": "Node.js",
            ".net": ".NET",
            "kubernetes": "Kubernetes",
            "redis": "Redis",
            "mongodb": "MongoDB",
            "mysql": "MySQL",
            "spark": "Spark",
            "jenkins": "Jenkins",
            "github actions": "GitHub Actions",
            "docker": "Docker",
            "java": "Java",
            "flask": "Flask",
            "django": "Django",
        }
        if skill.lower() in canonical:
            return canonical[skill.lower()]
        return skill.title() if skill.islower() and len(skill) > 3 else skill

    def _clean_skill_fragment(self, value: str) -> str:
        value = value.strip()
        value = re.sub(r"^[\(\[\-•\*]+", "", value).strip()
        value = re.sub(r"[\)\].,;:]+$", "", value).strip()
        value = re.split(
            r"\b(?:para|junto con|utilizando|como|incluyendo|enfocado en|enfocada en)\b",
            value,
            maxsplit=1,
            flags=re.I,
        )[0].strip()
        value = value.strip("()[] .,:;")
        return value

    def _dedupe_preserve_order(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = item.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item.strip())
        return out
