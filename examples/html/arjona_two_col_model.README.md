# arjona_two_col_model (HTML+CSS + Jinja2)

Template de CV en **HTML + CSS (Jinja2)** para convertir a PDF con **Chromium headless**,
replicando el formato de las imágenes de referencia:
- Header serif grande en mayúsculas
- Títulos azules con línea
- Layout 2 columnas (sidebar + contenido)
- Barras de habilidades tipo “píldora”
- Bloques ATS-friendly (texto seleccionable)

## Archivos

- `templates/html/custom/arjona_two_col_model.html.j2`
- `templates/html/custom/arjona_two_col_model.css.j2`
- `examples/html/arjona_two_col_model.adapter.json` (opcional)

## Contrato canónico soportado (entrada real del pipeline)

Usa directamente los campos del `template_context.json`:

- `candidate_name`
- `contact_lines[]`
- `job_target.title`, `job_target.company`, `job_target.location`
- `professional_summary`
- `skills[]` (string o `{name, level}` donde `level` está en 0..1)
- `experiences[]` (`title`, `company`, `date_range`, `location`, `bullets[]`, `skills[]`)
- `projects[]` (`name`, `bullets[]`, `skills[]`)
- `education[]` (`degree`, `institution`, `year`, `details[]`)
- `achievements[]`
- `page_target`
- `focus_preference`

Opcionales (si vienen en el contexto, se renderizan; si no, NO aparecen):
- `soft_skills[]`
- `hobbies[]` (string o `{icon, label}`)

## Decisiones de diseño

- Grilla 2 columnas: `0.37fr / 0.63fr` (similar al modelo).
- Tipografía: serif segura (Georgia / Times) para replicar el look sin depender de una fuente instalada.
- Secciones condicionales: no se imprime nada si no hay datos.
- Skills:
  - Se muestran hasta `max_sidebar_skills` como barras en la columna izquierda.
  - El resto pasa a `MÁS HABILIDADES` (lista inline con separador `·`) en la derecha.
- ATS-friendly: HTML semántico; contenido en texto real (no imágenes).

## Impresión / PDF

CSS incluye:
- `@page { size: A4; margin: ... }`
- `break-inside: avoid; page-break-inside: avoid;` en bloques de experiencia/educación/proyectos.

## Comando Docker de prueba (ejemplo)

Asumiendo un entrypoint similar al de tu pipeline (adaptar flags a tu runner):

```powershell
docker compose run --rm cvgen-typst python main.py `
  --cv-file /app/inputs/examples/cv_ejemplo.md `
  --job-file /app/inputs/examples/oferta_ejemplo.txt `
  --template-file /app/templates/html/custom/arjona_two_col_model.html.j2 `
  --template-css-file /app/templates/html/custom/arjona_two_col_model.css.j2 `
  --template-adapter-file /app/examples/html/arjona_two_col_model.adapter.json `
  --pages 2 `
  --no-interactive `
  --output-dir /app/outputs/arjona_two_col_model_demo