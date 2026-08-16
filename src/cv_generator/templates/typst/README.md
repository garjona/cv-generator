# Typst Templates Contract

El generador entrega un contexto canónico en `template_context.json` por cada ejecución.

Campos principales del contexto canónico:
- `candidate_name`
- `contact_lines[]`
- `job_target.{title,company,location}`
- `professional_summary`
- `skills[]`
- `experiences[]` (`title`, `company`, `date_range`, `bullets[]`, `skills[]`)
- `projects[]`
- `education[]`
- `achievements[]`
- `page_target`

## Template por defecto
- `ats_typst.typ.j2`
- Alternativo compacto: `minimal_cv.typ.j2`
- Ejemplo externo adaptado (fuera de `src/`):
  - Template: `templates/typst/custom/minimal_cv_repo.typ.j2`
  - Adapter: `examples/typst/minimal_cv_repo.adapter.json`
  - Template: `templates/typst/custom/arjona_two_col_clean.typ.j2`
  - Adapter: `examples/typst/arjona_two_col_clean.adapter.json`

## Usar tu propio template
1. Crea un `.typ.j2` (ej. `templates/typst/custom/my_cv.typ.j2`).
2. Ejecuta el pipeline con:
   - `--template-file templates/typst/custom/my_cv.typ.j2`
3. Si tu template no usa los nombres del contexto canónico, agrega:
   - `--template-adapter-file examples/typst/adapter_example.json`

## Adapter JSON
El adapter permite mapear campos del contexto canónico hacia la estructura que espera tu template.

Formato:
```json
{
  "mapping": {
    "profile": {
      "name": "candidate_name",
      "summary": "professional_summary"
    }
  },
  "static": {
    "meta": {"source": "typst"}
  }
}
```

Reglas:
- Un string es un path (`a.b.c`) sobre el contexto canónico.
- También se acepta `{ "$path": "a.b", "$default": "..." }`.
- `static` se mergea sobre el resultado.
