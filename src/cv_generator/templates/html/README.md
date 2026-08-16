# Templates HTML (Jinja2)

Motor principal actual del proyecto.

## Templates incluidos

- `ats_friendly.html.j2`
- `ats_friendly.css.j2`

## Contexto esperado

El contexto canónico viene de `template_context.json` y, como mínimo, usa:

- `candidate_name`
- `contact_lines[]`
- `job_target.title/company/location`
- `professional_summary`
- `skills[]`
- `experiences[]`
- `projects[]`
- `education[]`
- `achievements[]`
- `page_target`

Además, el renderer agrega:

- `css_file_name` (nombre del CSS generado para enlazarlo desde el HTML)
