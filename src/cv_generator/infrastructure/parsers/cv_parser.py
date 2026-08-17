from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cv_generator.domain.domain_config import DomainConfig
from cv_generator.domain.models import CVNormalized
from cv_generator.infrastructure.parsers.job_parser import COMMON_SKILLS

SECTION_ALIASES = {
    "summary": {
        "resumen",
        "perfil",
        "perfil profesional",
        "professional summary",
        "summary",
        "about",
        "presentacion",
        "presentación",
    },
    "experience": {
        "experiencia",
        "experiencia profesional",
        "experiencia laboral",
        "experience",
        "work experience",
        "trayectoria",
    },
    "education": {
        "educacion",
        "educación",
        "educacion universitaria",
        "educación universitaria",
        "education",
        "formacion",
        "formación",
        "formación académica",
        "academic background",
    },
    "skills": {
        "skills",
        "habilidades",
        "habilidades tecnicas",
        "habilidades técnicas",
        "tecnologias",
        "tecnologías",
        "competencias",
    },
    "projects": {"proyectos", "projects", "proyecto", "proyectos independientes"},
    "headline": {
        "titulo profesional objetivo",
        "titulo profesional",
        "objetivo profesional",
        "titular profesional",
        "cargo objetivo",
        "headline",
    },
    "contact": {"contacto"},
    "soft_skills": {"habilidades blandas"},
    "misc": {"hobbies y pasatiempos", "hobbies", "pasatiempos"},
    "languages": {"idiomas", "idioma", "languages"},
    "professional_skills": {
        "habilidades profesionales",
        "habilidades profesionales sugeridas version mas reclutable",
        "competencias profesionales",
    },
    "recommendations_meta": {
        "recomendaciones",
        "recomendaciones clave",
        "recomendaciones clave para fortalecer este cv prioridad alta",
    },
    "positioning_meta": {"nota de posicionamiento"},
}


class CVParser:
    def __init__(self, domain: DomainConfig | None = None) -> None:
        self.domain = domain
        self._skills = list(domain.skills) if domain and domain.skills else list(COMMON_SKILLS)
        # Los alias del dominio se suman a los base (no los reemplazan).
        self._section_aliases: dict[str, set[str]] = {k: set(v) for k, v in SECTION_ALIASES.items()}
        if domain:
            for canonical, aliases in domain.section_aliases.items():
                normalized = {self._normalize_header(a) for a in aliases}
                self._section_aliases.setdefault(canonical, set()).update(normalized)

    def parse_path(self, path: Path) -> CVNormalized:
        suffix = path.suffix.lower()
        if suffix == ".docx":
            text, warnings = self._extract_text_from_docx(path)
            source_type = "docx"
        elif suffix == ".pdf":
            text, warnings = self._extract_text_from_pdf(path)
            source_type = "pdf"
        elif suffix in {".md", ".txt"}:
            text, warnings = self._extract_text_from_text_file(path)
            source_type = "md" if suffix == ".md" else "txt"
            if suffix == ".md":
                text = self._preprocess_markdown_text(text)
        else:
            raise ValueError(f"Formato de CV no soportado para MVP: {suffix}")
        return self.parse_text_content(text, source_type=source_type, warnings=warnings)

    def parse_text_content(
        self,
        text: str,
        source_type: str = "txt",
        warnings: list[str] | None = None,
    ) -> CVNormalized:
        warnings = list(warnings or [])
        cleaned = self._normalize_text(text)
        if not cleaned.strip():
            warnings.append("El texto extraído del CV quedó vacío.")
        lines = [line.strip() for line in cleaned.splitlines()]
        basics = self._parse_basics(lines)
        warnings.extend(self._basics_warnings(basics))
        sections, section_warnings = self._segment_sections(lines)
        warnings.extend(section_warnings)

        summary = self._join_section_lines(sections.get("summary", [])) or None
        skills = self._parse_skills(sections.get("skills", []), cleaned)
        experiences = self._parse_experiences(sections.get("experience", []))
        education = self._parse_education(sections.get("education", []))
        projects = self._parse_projects(sections.get("projects", []))
        languages = self._parse_languages(sections.get("languages", []))
        certifications = self._parse_certifications(sections.get("certifications", []))

        headline = self._parse_headline(sections.get("headline", []))
        if headline and not basics.get("headline"):
            basics["headline"] = headline

        if not experiences:
            warnings.append("No se detectaron experiencias estructuradas; revisar formato del CV base.")
        if not skills:
            warnings.append("No se detectó sección de skills o no se pudieron extraer habilidades.")

        return CVNormalized(
            source_type=source_type,
            raw_text=cleaned,
            basics=basics,
            summary=summary,
            experiences=experiences,
            education=education,
            skills=skills,
            projects=projects,
            sections=sections,
            languages=languages,
            certifications=certifications,
            parsing_warnings=self._dedupe_preserve_order(warnings),
        )

    def _extract_text_from_docx(self, path: Path) -> tuple[str, list[str]]:
        warnings: list[str] = []
        try:
            from docx import Document  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "python-docx no está instalado o falló la importación. Instala dependencias para parsear .docx."
            ) from exc

        try:
            document = Document(str(path))
        except Exception as exc:
            raise RuntimeError(f"No se pudo abrir el archivo .docx: {path}") from exc

        blocks = self._iter_docx_blocks(document)
        if not blocks:
            warnings.append(
                "El .docx no contenía texto detectable (¿está en imágenes o requiere OCR?)."
            )
        return "\n".join(blocks), warnings

    def _iter_docx_blocks(self, document: Any) -> list[str]:
        """Texto del .docx en orden de documento, incluyendo tablas.

        Muchos CVs maquetan sus columnas con tablas de Word; leer sólo
        `document.paragraphs` deja fuera todo ese contenido.
        """
        from docx.table import Table  # type: ignore
        from docx.text.paragraph import Paragraph  # type: ignore

        blocks: list[str] = []
        body = document.element.body
        for child in body.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "p":
                text = Paragraph(child, document).text.strip()
                if text:
                    blocks.append(text)
            elif tag == "tbl":
                blocks.extend(self._docx_table_blocks(Table(child, document), document))

        if not blocks:
            # Último recurso: cuadros de texto y formas, que no aparecen ni como
            # párrafo ni como tabla en el árbol del cuerpo.
            blocks.extend(self._docx_textbox_blocks(document))
        return blocks

    def _docx_table_blocks(self, table: Any, document: Any) -> list[str]:
        from docx.table import Table  # type: ignore
        from docx.text.paragraph import Paragraph  # type: ignore

        blocks: list[str] = []
        seen_cells: set[int] = set()
        for row in table.rows:
            for cell in row.cells:
                # Las celdas combinadas se repiten entre filas/columnas.
                cell_id = id(cell._tc)
                if cell_id in seen_cells:
                    continue
                seen_cells.add(cell_id)
                for child in cell._tc.iterchildren():
                    tag = child.tag.split("}")[-1]
                    if tag == "p":
                        text = Paragraph(child, document).text.strip()
                        if text:
                            blocks.append(text)
                    elif tag == "tbl":
                        blocks.extend(self._docx_table_blocks(Table(child, document), document))
        return blocks

    def _docx_textbox_blocks(self, document: Any) -> list[str]:
        import re as _re

        xml = document.element.xml
        fragments = _re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
        joined = " ".join(fragment for fragment in fragments if fragment.strip())
        return [joined] if joined.strip() else []

    def _extract_text_from_pdf(self, path: Path) -> tuple[str, list[str]]:
        warnings: list[str] = []
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "pypdf no está instalado o falló la importación. Instala dependencias para parsear .pdf."
            ) from exc

        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise RuntimeError(f"No se pudo abrir el archivo .pdf: {path}") from exc

        pages_text: list[str] = []
        for page in reader.pages:
            try:
                pages_text.append(page.extract_text() or "")
            except Exception:
                warnings.append("Falló la extracción de texto en una página del PDF.")
        text = "\n".join(pages_text)
        if not text.strip():
            warnings.append("No se pudo extraer texto del PDF (posible PDF escaneado/OCR requerido).")
        return text, warnings

    def _extract_text_from_text_file(self, path: Path) -> tuple[str, list[str]]:
        warnings: list[str] = []
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            warnings.append(f"El archivo de texto {path.name} está vacío.")
        return text, warnings

    def _preprocess_markdown_text(self, text: str) -> str:
        # Keep line structure but remove common markdown markers for better parsing.
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        text = re.sub(r"^\s*>\s*", "", text, flags=re.M)
        text = re.sub(r"^\s*-{3,}\s*$", "", text, flags=re.M)
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
        text = re.sub(r" {2,}\n", "\n", text)
        return text

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _parse_basics(self, lines: list[str]) -> dict[str, Any]:
        basics: dict[str, Any] = {}
        head = [line for line in lines[:12] if line]
        if head:
            name = self._strip_format_markers(head[0])
            name = re.sub(r"^(cv|curriculum vitae)\s*[-:]\s*", "", name, flags=re.I).strip()
            name = re.sub(r"\s*\(actualizado al .*?\)\s*$", "", name, flags=re.I).strip()
            basics["name"] = name

        search_lines = [line for line in lines[:40] if line]
        joined = "\n".join(search_lines)
        email = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", joined)
        phone = self._extract_phone_from_lines(search_lines)
        linkedin = re.search(r"((?:https?://)?(?:www\.)?linkedin\.com/[^\s]+)", joined, flags=re.I)
        github = re.search(r"(https?://(?:www\.)?github\.com/[^\s]+)", joined, flags=re.I)

        if email:
            basics["email"] = email.group(0)
        if phone:
            basics["phone"] = phone
        location = self._extract_location(search_lines)
        if location:
            basics["location"] = location
        if linkedin:
            basics["linkedin"] = self._ensure_url_scheme(linkedin.group(1))
        if github:
            basics["github"] = github.group(1)
        return basics

    def _extract_phone_from_lines(self, lines: list[str]) -> str | None:
        labeled_candidates: list[str] = []
        fallback_candidates: list[str] = []
        for line in lines:
            lower = line.lower()
            matches = re.findall(r"(\+?\d[\d\-\s]{7,}\d)", line)
            for match in matches:
                cleaned = " ".join(match.split()).strip()
                if self._looks_like_date_token(cleaned):
                    continue
                if "tel" in lower or "fono" in lower or "mÃ³vil" in lower or "movil" in lower:
                    labeled_candidates.append(cleaned)
                elif cleaned.startswith("+"):
                    fallback_candidates.append(cleaned)
        return (labeled_candidates or fallback_candidates or [None])[0]

    def _looks_like_date_token(self, value: str) -> bool:
        return bool(re.fullmatch(r"\d{2}\-\d{2}\-\d{4}", value.strip()))

    def _basics_warnings(self, basics: dict[str, Any]) -> list[str]:
        """Avisa explícitamente por cada dato de contacto que no se pudo extraer.

        El parseo no debe fallar en silencio: si el CV trae el dato pero la
        heurística no lo reconoce, el usuario tiene que enterarse.
        """
        expected = {
            "name": "nombre",
            "email": "email",
            "phone": "teléfono",
            "linkedin": "LinkedIn",
            "location": "ubicación (usa una línea 'Ubicación: Ciudad, País')",
        }
        missing = [label for key, label in expected.items() if not str(basics.get(key, "")).strip()]
        if not missing:
            return []
        return [f"No se detectó en el CV base: {', '.join(missing)}."]

    def _extract_location(self, lines: list[str]) -> str | None:
        """Extrae la ubicación desde una línea etiquetada (Ubicación/Ciudad/Location)."""
        for line in lines:
            match = re.match(
                r"^\s*[\-\*•]?\s*(?:ubicaci[oó]n|ciudad|location|residencia|domicilio)\s*[:\-]\s*(.+)$",
                self._strip_format_markers(line),
                flags=re.I,
            )
            if match:
                value = re.sub(r"\s+", " ", match.group(1)).strip().strip(".")
                if value:
                    return value
        return None

    def _ensure_url_scheme(self, value: str) -> str:
        if re.match(r"^https?://", value, flags=re.I):
            return value
        return f"https://{value}"

    def _segment_sections(self, lines: list[str]) -> tuple[dict[str, list[str]], list[str]]:
        sections: dict[str, list[str]] = {"header": []}
        warnings: list[str] = []
        current = "header"
        found_headers = False

        for raw in lines:
            line = raw.strip()
            if not line:
                sections.setdefault(current, []).append("")
                continue
            matched = self._match_section_alias(line)
            if matched:
                current = matched
                sections.setdefault(current, [])
                found_headers = True
                continue
            sections.setdefault(current, []).append(line)

        if not found_headers:
            warnings.append("No se detectaron encabezados de sección; se aplicaron heurísticas básicas.")
            header_lines = sections.get("header", [])
            sections["summary"] = header_lines[:4]
            sections["experience"] = header_lines[4:]

        for key in ["summary", "experience", "education", "skills", "projects"]:
            sections.setdefault(key, [])

        rescue_warning = self._rescue_orphan_experience(sections)
        if rescue_warning:
            warnings.append(rescue_warning)
        return sections, warnings

    ENTRY_WITH_DATES = re.compile(
        r"^\s*(?:"
        r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+)?"
        r"(?:19|20)\d{2}\s*[-–—]\s*"
        r"(?:(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+)?"
        r"(?:(?:19|20)\d{2}|actualidad|presente)\s*[-–—]\s*\S+",
        flags=re.I,
    )

    def _rescue_orphan_experience(self, sections: dict[str, list[str]]) -> str | None:
        """Recupera experiencias que quedaron bajo otra sección.

        Hay CVs (sobre todo .docx maquetados) donde el título "Experiencia" es
        una imagen o una forma y se pierde al extraer el texto: las entradas
        terminan colgando de la sección anterior. Si no hay experiencias pero sí
        líneas con formato "2024 - 2025 - Cargo, Institución", se reubican.
        """
        if [line for line in sections.get("experience", []) if line.strip()]:
            return None

        for source in ("education", "certifications", "summary", "header"):
            lines = sections.get(source, [])
            start = next((i for i, line in enumerate(lines) if self.ENTRY_WITH_DATES.match(line)), None)
            if start is None:
                continue
            moved = lines[start:]
            sections[source] = lines[:start]
            sections["experience"] = moved
            return (
                f"No se encontró el encabezado de experiencia; se recuperaron {len(moved)} líneas "
                f"desde la sección '{source}' por su formato de fechas."
            )
        return None

    def _match_section_alias(self, line: str) -> str | None:
        normalized = self._normalize_header(line)
        for canonical, aliases in self._section_aliases.items():
            if normalized in aliases:
                return canonical
        return None

    def _normalize_header(self, value: str) -> str:
        value = value.strip().lower().strip(":")
        value = value.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        value = re.sub(r"[^a-zñ ]", "", value)
        return re.sub(r"\s+", " ", value).strip()

    def _join_section_lines(self, lines: list[str]) -> str:
        return re.sub(r"\s+", " ", " ".join([l for l in lines if l.strip()])).strip()

    def _parse_headline(self, lines: list[str]) -> str | None:
        for raw in lines:
            text = self._strip_format_markers(raw)
            text = re.sub(r"^[\-\*•]\s*", "", text).strip()
            if text:
                return text
        return None

    YEAR_SUFFIX = re.compile(
        r"^(?P<name>.+?)\s*[-–—]\s*"
        r"(?P<year>(?:19|20)\d{2}(?:\s*[-–—]\s*(?:(?:19|20)\d{2}|actualidad|presente))?)\s*$",
        flags=re.I,
    )
    YEAR_PREFIX = re.compile(
        r"^(?P<year>(?:19|20)\d{2}(?:\s*[-–—]\s*(?:(?:19|20)\d{2}|actualidad|presente))?)"
        r"\s*[-–—:]?\s*(?P<name>.*)$",
        flags=re.I,
    )

    def _parse_certifications(self, lines: list[str]) -> list[dict[str, Any]]:
        """Capacitaciones, cursos y perfeccionamiento.

        Una entrada empieza con un subtítulo, con su año al inicio o al final,
        o con la forma "Nombre: descripción". El resto son detalles de la anterior.
        """
        result: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        for raw in lines:
            is_heading = bool(re.match(r"^\s*#{2,6}\s+", raw))
            line = re.sub(r"^[\-\*•]\s*", "", self._strip_format_markers(raw)).strip()
            if not line or len(re.sub(r"[^\w]", "", line)) <= 1:
                continue

            name: str | None = None
            year: str | None = None
            detail: str | None = None

            suffix = self.YEAR_SUFFIX.match(line)
            prefix = self.YEAR_PREFIX.match(line)
            if suffix:
                name, year = suffix.group("name").strip(), suffix.group("year").strip()
            elif prefix:
                year = prefix.group("year").strip()
                name = prefix.group("name").strip(" .,;-–—") or None
            elif is_heading:
                name = line
            elif ":" in line[:80]:
                head, _, rest = line.partition(":")
                if head.strip():
                    name, detail = head.strip(), rest.strip()

            if name:
                current = {"name": name, "year": year, "details": [d for d in [detail] if d]}
                result.append(current)
            elif current is not None:
                current["details"].append(line)

        return [c for c in result if c.get("name")]

    def _parse_languages(self, lines: list[str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in lines:
            text = self._strip_format_markers(raw)
            text = re.sub(r"^[\-\*•]\s*", "", text).strip()
            if not text:
                continue
            # Drop parenthetical recommendations/notes that are not part of the level.
            text = re.sub(r"\*\((?:recomendado|nivel).*?\)\*", "", text, flags=re.I).strip()
            name, _, level = text.partition(":")
            name = name.strip()
            level = level.strip().strip(".")
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append({"name": name, "level": level or None})
        return result

    def _split_respecting_parens(self, text: str) -> list[str]:
        parts: list[str] = []
        buffer = ""
        depth = 0
        for ch in text:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth = max(0, depth - 1)
            if ch in ",|;/" and depth == 0:
                parts.append(buffer)
                buffer = ""
            else:
                buffer += ch
        parts.append(buffer)
        return [p.strip() for p in parts if p.strip()]

    def _parse_skills(self, skill_lines: list[str], full_text: str) -> list[str]:
        chunks = []
        for line in skill_lines:
            # Category subheadings (### Programaci\u00f3n, ### Datos / BI / Anal\u00edtica) are
            # labels, not skills: skip them so they don't leak into the skill list.
            if line.lstrip().startswith("#"):
                continue
            line_clean = self._strip_format_markers(line)
            line_clean = re.sub(r"^[\-\*\u2022]\s*", "", line_clean).strip()
            # Drop trailing emphasis notes like "*(nivel por confirmar)*".
            line_clean = re.sub(r"\*\([^)]*\)\*", "", line_clean).strip()
            if not line_clean:
                continue
            if line_clean.lower().startswith("nota:"):
                continue
            # Only split delimiters that live outside parentheses so entries like
            # "An\u00e1lisis de datos (rating, reproducciones, consumo)" stay intact.
            chunks.extend(self._split_respecting_parens(line_clean))

        detected: list[str] = []
        lower = full_text.lower()
        for skill in self._skills:
            pattern = re.escape(skill).replace(r"\ ", r"\s+")
            if re.search(rf"(?<!\w){pattern}(?!\w)", lower, flags=re.I):
                detected.append(skill.title() if skill.islower() and len(skill) > 3 else skill)

        for chunk in chunks:
            if 1 < len(chunk) <= 40 and re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", chunk):
                if any(tok in chunk.lower() for tok in ["años", "anos", "experiencia", "nivel"]):
                    continue
                if chunk.lower().startswith("nota:"):
                    continue
                detected.append(chunk)
        return self._dedupe_preserve_order(detected)[:40]

    def _parse_experiences(self, lines: list[str]) -> list[dict[str, Any]]:
        if any(re.match(r"^\s*#{3,6}\s+", line) for line in lines):
            return self._parse_experiences_markdown(lines)
        experiences: list[dict[str, Any]] = []
        for block in self._split_experience_blocks(lines):
            parsed = self._parse_experience_block(block)
            if parsed:
                experiences.append(parsed)
        return experiences

    def _parse_experiences_markdown(self, lines: list[str]) -> list[dict[str, Any]]:
        experiences: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        def flush() -> None:
            nonlocal current
            if not current:
                return
            summary_parts = [p.strip() for p in current.pop("_summary_parts", []) if p and p.strip()]
            bullets = self._dedupe_preserve_order([b.strip() for b in current.get("bullets", []) if b and b.strip()])
            current["bullets"] = bullets
            current["summary"] = " ".join(summary_parts).strip() if summary_parts else None
            current["skills"] = self._skills_from_text(
                " ".join(
                    [
                        str(current.get("title", "")),
                        str(current.get("company", "")),
                        str(current.get("summary", "")),
                        *[str(b) for b in current.get("bullets", [])],
                    ]
                )
            )
            if current.get("title"):
                experiences.append(current)
            current = None

        for raw in lines:
            line = raw.rstrip()
            if re.match(r"^\s*#{3,6}\s+", line):
                flush()
                heading = self._strip_format_markers(line)
                title, company = self._split_markdown_experience_heading(heading)
                current = {
                    "title": title,
                    "company": company,
                    "start_date": None,
                    "end_date": None,
                    "summary": None,
                    "bullets": [],
                    "skills": [],
                    "_summary_parts": [],
                }
                continue

            if current is None:
                continue

            stripped = self._strip_format_markers(line).strip()
            if not stripped:
                continue

            if re.match(r"^[\-\*\u2022]\s+", stripped):
                current["bullets"].append(re.sub(r"^[\-\*\u2022]\s*", "", stripped).strip())
                continue

            if self._looks_like_date_line(stripped):
                start, end = self._extract_date_range(stripped, current.get("start_date"), current.get("end_date"))
                current["start_date"] = start or current.get("start_date")
                current["end_date"] = end or current.get("end_date")
                continue

            if current.get("company") is None and self._looks_like_company_line(stripped):
                current["company"] = stripped.strip().strip(".")
                continue

            current["_summary_parts"].append(stripped)

        flush()
        return experiences

    def _split_markdown_experience_heading(self, heading: str) -> tuple[str, str | None]:
        clean = self._strip_format_markers(heading).strip()
        for sep in [" — ", " – ", " - ", " | "]:
            if sep not in clean:
                continue
            left, right = [part.strip() for part in clean.split(sep, 1)]
            if not left or not right:
                continue
            # For markdown CVs it's common to use "Empresa — Cargo".
            # Prefer that interpretation when the left side looks like an organization label.
            if len(left.split()) <= 8 and (
                any(
                    tok in left.lower()
                    for tok in ["banco", "consultora", "media", "ltda", "spa", "s.a", "inc", "corp", "group"]
                )
                or left[:1].isupper()
            ):
                return right, left
            return clean, None
        return clean, None

    def _parse_experience_block(self, block: list[str]) -> dict[str, Any] | None:
        clean = [line for line in block if line.strip()]
        if not clean:
            return None

        header = self._strip_format_markers(clean[0])
        title = header
        company = None
        start_date = None
        end_date = None

        date_match = re.search(r"\b(\d{4})\s*[-–]\s*(actualidad|presente|\d{4})\b", header, flags=re.I)
        if date_match:
            start_date = date_match.group(1)
            end_date = date_match.group(2)
            header = header.replace(date_match.group(0), "").strip(" -–—|,")
        elif self.ENTRY_WITH_DATES.match(header):
            # Formato "Octubre 2024 - Noviembre 2024 - Cargo, Institucion":
            # las fechas van al inicio y el ultimo separador abre el cargo.
            parts = re.split(r"\s*[-–—]\s*", header)
            date_parts, rest_parts = [], []
            for part in parts:
                if not rest_parts and re.search(r"(19|20)\d{2}|actualidad|presente", part, flags=re.I):
                    date_parts.append(part)
                else:
                    rest_parts.append(part)
            start_date, end_date = self._extract_date_range(" - ".join(date_parts), None, None)
            header = " - ".join(rest_parts).strip(" -–—|,") or header

        if " - " in header:
            title, company = [p.strip() for p in header.split(" - ", 1)]
        elif " | " in header:
            title, company = [p.strip() for p in header.split(" | ", 1)]
        elif "," in header:
            left, right = [p.strip() for p in header.split(",", 1)]
            # "Cargo, Institución" sólo si el lado derecho parece una organización.
            if left and right and self._looks_like_company_line(right):
                title, company = left, right
            else:
                title = header.strip()
        else:
            title = header.strip()

        remaining = [self._strip_format_markers(line) for line in clean[1:]]

        # Markdown/text CVs often use:
        #   title
        #   company
        #   date range
        if remaining:
            if self._looks_like_date_line(remaining[0]):
                start_date, end_date = self._extract_date_range(remaining[0], start_date, end_date)
                remaining = remaining[1:]
            elif company is None and self._looks_like_company_line(remaining[0]):
                company = remaining[0].strip().strip(".")
                if len(remaining) > 1 and self._looks_like_date_line(remaining[1]):
                    start_date, end_date = self._extract_date_range(remaining[1], start_date, end_date)
                    remaining = remaining[2:]
                else:
                    remaining = remaining[1:]

        bullets = [re.sub(r"^[\-\*\u2022]\s*", "", line).strip() for line in remaining if re.match(r"^[\-\*\u2022]\s+", line)]
        summary_lines = [line for line in remaining if not re.match(r"^[\-\*\u2022]\s+", line)]
        # Muchos CVs listan logros como parrafos sueltos, sin vineta: cada linea
        # es un item, no un bloque de prosa.
        if not bullets and len(summary_lines) > 1:
            bullets = [line.strip() for line in summary_lines if line.strip()]
            summary_lines = []
        summary = " ".join(summary_lines).strip() if summary_lines else None
        skills = self._skills_from_text(" ".join(clean))

        return {
            "title": title,
            "company": company,
            "start_date": start_date,
            "end_date": end_date,
            "summary": summary,
            "bullets": bullets,
            "skills": skills,
        }

    def _parse_education(self, lines: list[str]) -> list[dict[str, Any]]:
        if any(re.match(r"^\s*#{3,6}\s+", line) for line in lines):
            return self._parse_education_markdown(lines)
        result: list[dict[str, Any]] = []
        for block in self._split_blocks(lines):
            clean = [self._strip_format_markers(l) for l in block if l.strip()]
            # Restos de encabezados perdidos en la extracción (p. ej. sólo ".").
            clean = [l for l in clean if len(re.sub(r"[^\w]", "", l)) > 1]
            one_liners = [self._one_line_education(l) for l in clean]
            # Si cada línea del bloque es una titulación completa, son entradas
            # independientes y no un único título con su institución debajo.
            if len(clean) > 1 and all(one_liners):
                result.extend([e for e in one_liners if e])
                continue
            entry = self._parse_education_block(block)
            if entry:
                result.append(entry)
        return result

    ONE_LINE_DEGREE = re.compile(
        r"^(?P<degree>.+?)\s*[–—]\s*(?P<institution>[^()]+?)\s*(?:\((?P<years>[^)]*)\))?\s*$"
    )

    def _one_line_education(self, line: str) -> dict[str, Any] | None:
        """Entradas del tipo "Título — Universidad (2018–2022)" en una sola línea."""
        if not self._looks_like_degree(line):
            return None
        match = self.ONE_LINE_DEGREE.match(line.strip())
        if not match:
            return None
        institution = (match.group("institution") or "").strip(" .,;")
        if not institution or not self._looks_like_institution(institution):
            return None
        years = (match.group("years") or "").strip()
        year_match = re.search(r"(19|20)\d{2}", years)
        return {
            "degree": match.group("degree").strip(" .,;"),
            "institution": institution,
            "year": years or (year_match.group(0) if year_match else None),
            "details": [],
        }

    def _parse_education_block(self, block: list[str]) -> dict[str, Any] | None:
        clean = [self._strip_format_markers(line) for line in block if line.strip()]
        clean = [line for line in clean if line and not self._is_pending_placeholder(line)]
        if not clean:
            return None

        bullet_lines = [re.sub(r"^[\-\*\u2022]\s*", "", l).strip() for l in clean if re.match(r"^[\-\*\u2022]\s+", l)]
        plain_lines = [l for l in clean if not re.match(r"^[\-\*\u2022]\s+", l)]

        year_match = re.search(r"\b(19|20)\d{2}\b", " ".join(clean))
        year = year_match.group(0) if year_match else None

        # Case 1: several bullets that are all degrees/credentials (no institution line).
        # Keep the first as the main degree and list the rest as details, instead of
        # mistaking the second credential for an institution.
        if len(bullet_lines) >= 2 and all(self._looks_like_degree(b) for b in bullet_lines):
            institution = next((l for l in plain_lines if self._looks_like_institution(l)), None)
            details = [b for b in bullet_lines[1:]]
            details += [l for l in plain_lines if l != institution and l.strip() != (year or "")]
            return {
                "degree": bullet_lines[0],
                "institution": institution,
                "year": year,
                "details": details,
            }

        # Case 2: classic "Degree / Institution / Year" layout.
        merged = bullet_lines + plain_lines
        degree = merged[0] if merged else None
        institution = None
        if len(merged) > 1 and self._looks_like_institution(merged[1]) and not self._looks_like_degree(merged[1]):
            institution = merged[1]
            rest = merged[2:]
        else:
            rest = merged[1:]
        details = [l for l in rest if l.strip() != (year or "")]
        return {"degree": degree, "institution": institution, "year": year, "details": details}

    def _is_pending_placeholder(self, value: str) -> bool:
        return value.strip().lower().startswith("pendiente de completar")

    def _looks_like_degree(self, value: str) -> bool:
        return bool(
            re.match(
                r"^\s*(ingenier[oa]|licenciad[oa]|licenciatura|t[e\u00e9]cnic[oa]|mag\u00edster|magister|master|m\u00e1ster|bachiller|"
                r"profesor[ea]?|profesorad[oa]|pedagog[ií]a|educador[ea]?|"
                r"doctor(?:ad[oa])?|diplomad[oa]|post\u00edtulo|postitulo|postgrado|posgrado)\b",
                value,
                flags=re.I,
            )
        )

    def _looks_like_institution(self, value: str) -> bool:
        val = value.strip()
        if not val or len(val) > 120:
            return False
        if self._looks_like_degree(val):
            return False
        if re.search(
            r"\b(universidad|instituto|colegio|escuela|facultad|college|university|centro de formaci[o\u00f3]n|duoc|inacap)\b",
            val,
            flags=re.I,
        ):
            return True
        return self._looks_like_company_line(val)

    def _parse_education_markdown(self, lines: list[str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        def flush() -> None:
            nonlocal current
            if not current:
                return
            current["details"] = [d for d in current.get("details", []) if d]
            if current.get("degree"):
                result.append(current)
            current = None

        for raw in lines:
            line = raw.rstrip()
            if not line.strip():
                continue

            if re.match(r"^\s*#{3,6}\s+", line):
                flush()
                current = {
                    "degree": self._strip_format_markers(line),
                    "institution": None,
                    "year": None,
                    "details": [],
                }
                continue

            if current is None:
                continue

            stripped = self._strip_format_markers(line).strip()
            if not stripped:
                continue

            # Date lines are often ranges like "2014 – 2020"
            if self._looks_like_date_line(stripped) or re.search(r"\b(19|20)\d{2}\b", stripped):
                year_match = re.search(r"\b(19|20)\d{2}\b", stripped)
                if year_match and not current.get("year"):
                    current["year"] = year_match.group(0)
                # Keep full date range only if it adds info beyond the year.
                if stripped != str(current.get("year", "")):
                    current["details"].append(stripped)
                continue

            stripped = re.sub(r"^[\-\*•]\s*", "", stripped).strip()
            if self._is_pending_placeholder(stripped):
                continue

            if current.get("institution") is None and self._looks_like_institution(stripped):
                current["institution"] = stripped.strip().strip(".")
                continue

            current["details"].append(stripped)

        flush()
        return result

    def _parse_projects(self, lines: list[str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for block in self._split_blocks(lines):
            clean = [line for line in block if line.strip()]
            if not clean:
                continue
            clean_fmt = [self._strip_format_markers(line) for line in clean]
            bullets = [re.sub(r"^[\-\*\u2022]\s*", "", line).strip() for line in clean_fmt[1:] if re.match(r"^[\-\*\u2022]\s+", line)]

            # Las l\u00edneas sueltas pueden ser fecha o descripci\u00f3n; la fecha se
            # extrae en vez de perderse cuando el proyecto ya tiene bullets.
            start_date: str | None = None
            end_date: str | None = None
            details: list[str] = []
            for line in clean_fmt[1:]:
                if re.match(r"^[\-\*\u2022]\s+", line):
                    continue
                if start_date is None and self._looks_like_date_line(line):
                    start_date, end_date = self._extract_date_range(line, None, None)
                    if start_date or end_date:
                        continue
                details.append(line)

            result.append(
                {
                    "name": self._strip_format_markers(clean_fmt[0]),
                    "description": " ".join(details).strip() if details else None,
                    "start_date": start_date,
                    "end_date": end_date,
                    "bullets": bullets,
                    "skills": self._skills_from_text(" ".join(clean_fmt)),
                }
            )
        return result

    def _split_blocks(self, lines: list[str]) -> list[list[str]]:
        blocks: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if not line.strip():
                if current:
                    blocks.append(current)
                    current = []
                continue
            current.append(line)
        if current:
            blocks.append(current)
        return blocks

    def _split_experience_blocks(self, lines: list[str]) -> list[list[str]]:
        blocks: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if not line.strip():
                if current:
                    blocks.append(current)
                    current = []
                continue

            is_bullet = bool(re.match(r"^[\-\*\u2022]\s+", line))
            is_markdown_subheading = bool(re.match(r"^\s*#{3,6}\s+", line))
            looks_like_new_header = (
                not is_bullet
                and (
                    is_markdown_subheading
                    or bool(re.search(r"\b\d{4}\s*[-–]\s*(?:actualidad|presente|\d{4})\b", line, flags=re.I))
                    or bool(self.ENTRY_WITH_DATES.match(line))
                )
                and len(current) > 0
            )
            if looks_like_new_header:
                blocks.append(current)
                current = [line]
                continue

            current.append(line)

        if current:
            blocks.append(current)
        return blocks

    def _strip_format_markers(self, value: str) -> str:
        value = value.strip()
        value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value)
        value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
        value = re.sub(r"__(.*?)__", r"\1", value)
        return value.strip()

    def _looks_like_date_line(self, value: str) -> bool:
        return bool(
            re.search(
                r"\b(\d{4}|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
                value,
                flags=re.I,
            )
            and re.search(r"[-–]", value)
        )

    def _looks_like_company_line(self, value: str) -> bool:
        val = value.strip()
        if not val or len(val) > 120:
            return False
        if self._looks_like_date_line(val):
            return False
        # Often company lines are short labels without trailing long prose.
        return len(val.split()) <= 8

    def _extract_date_range(
        self,
        line: str,
        existing_start: str | None,
        existing_end: str | None,
    ) -> tuple[str | None, str | None]:
        if existing_start or existing_end:
            return existing_start, existing_end
        year_match = re.search(r"\b(\d{4})\s*[-–]\s*(actualidad|presente|\d{4})\b", line, flags=re.I)
        if year_match:
            return year_match.group(1), year_match.group(2)
        month_map = {
            "enero": "01",
            "febrero": "02",
            "marzo": "03",
            "abril": "04",
            "mayo": "05",
            "junio": "06",
            "julio": "07",
            "agosto": "08",
            "septiembre": "09",
            "setiembre": "09",
            "octubre": "10",
            "noviembre": "11",
            "diciembre": "12",
        }
        matches = list(
            re.finditer(
                r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)?\s*(\d{4}|actualidad|presente)",
                line,
                flags=re.I,
            )
        )
        if len(matches) >= 2:
            start = self._format_date_token(matches[0].group(1), matches[0].group(2), month_map)
            end = self._format_date_token(matches[1].group(1), matches[1].group(2), month_map)
            return start, end
        return None, None

    def _format_date_token(self, month: str | None, year_or_word: str, month_map: dict[str, str]) -> str:
        val = year_or_word.strip()
        if val.lower() in {"actualidad", "presente"}:
            return val.capitalize()
        if month:
            m = month_map.get(month.lower(), "")
            if m:
                return f"{val}-{m}"
        return val

    def _skills_from_text(self, text: str) -> list[str]:
        lower = text.lower()
        found = []
        for skill in self._skills:
            pattern = re.escape(skill).replace(r"\ ", r"\s+")
            if re.search(rf"(?<!\w){pattern}(?!\w)", lower, flags=re.I):
                found.append(skill.title() if skill.islower() and len(skill) > 3 else skill)
        return self._dedupe_preserve_order(found)

    def _dedupe_preserve_order(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item.strip())
        return out
