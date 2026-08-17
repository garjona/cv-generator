from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DomainConfig:
    """Vocabulario de un rubro profesional.

    Aísla lo que antes estaba incrustado en el código (términos de foco,
    catálogo de skills, etiquetas canónicas) para que el generador sirva a
    cualquier perfil: un profesor no debe evaluarse con términos de datos.
    """

    name: str = "generico"
    description: str = ""
    # Términos que suben el puntaje de un bullet cuando aparecen en él.
    focus_terms: list[str] = field(default_factory=list)
    # Catálogo de habilidades reconocibles en el texto del CV y de la oferta.
    skills: list[str] = field(default_factory=list)
    # Etiqueta correcta para cada skill (clave en minúsculas).
    canonical_labels: dict[str, str] = field(default_factory=dict)
    # Skills demasiado genéricas para este rubro (en otro rubro pueden ser clave).
    omit_labels: list[str] = field(default_factory=list)
    # Encabezados de sección adicionales: {seccion_canonica: [alias, ...]}
    section_aliases: dict[str, list[str]] = field(default_factory=dict)
    # Rótulos visibles del CV: en docencia "Tecnologías" no aplica.
    labels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainConfig":
        return cls(
            name=str(data.get("name", "generico")),
            description=str(data.get("description", "")),
            focus_terms=[str(x) for x in data.get("focus_terms", [])],
            skills=[str(x) for x in data.get("skills", [])],
            canonical_labels={str(k).lower(): str(v) for k, v in (data.get("canonical_labels") or {}).items()},
            omit_labels=[str(x).lower() for x in data.get("omit_labels", [])],
            section_aliases={
                str(k): [str(a) for a in v] for k, v in (data.get("section_aliases") or {}).items()
            },
            labels={str(k): str(v) for k, v in (data.get("labels") or {}).items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "focus_terms": self.focus_terms,
            "skills": self.skills,
            "canonical_labels": self.canonical_labels,
            "omit_labels": self.omit_labels,
            "section_aliases": self.section_aliases,
            "labels": self.labels,
        }

    def canonical(self, label: str) -> str:
        value = str(label or "").strip()
        return self.canonical_labels.get(value.lower(), value)

    def should_omit(self, label: str) -> bool:
        return str(label or "").strip().lower() in set(self.omit_labels)
