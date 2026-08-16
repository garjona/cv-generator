# arjona_two_col_clean (Typst + Jinja2)

Template CV estilo 2 columnas inspirado en el diseño de referencia (títulos azules con línea, header grande serif, barras de skills) con fondo blanco.

## Archivos

- `templates/typst/custom/arjona_two_col_clean.typ.j2`
- `examples/typst/arjona_two_col_clean.adapter.json`

## Contrato esperado (vía adapter)

Mínimo requerido:

- `profile.name` (string)
- `profile.contacts[]` (array strings)
- `profile.summary` (string)
- `target.title`, `target.company`, `target.location` (strings)
- `sections.skills[]` (array)
- `sections.experience[]` (array de objetos: `title`, `company`, `date_range`, `bullets[]`, `skills[]`)
- `sections.education[]` (array de objetos: `degree`, `institution`, `date_range|year`, `details`)
- `sections.projects[]` (array opcional)
- `sections.achievements[]` (array opcional)
- `meta.page_target` (number)

Opcionales soportados:

- `sections.soft_skills[]` (array strings)
- `sections.hobbies[]` (array)
  - Puede ser string, o `{ "icon": "🎮", "label": "Videojuegos cooperativos" }`

### Meta knobs (recomendado para estabilidad del layout)

Para evitar que la columna izquierda (sidebar) crezca a varias páginas y empuje el contenido de la derecha, el template soporta estos parámetros en `meta`:

- `meta.max_sidebar_skills` (number): máximo de skills con barra que se renderizan en la columna izquierda.  
  - **Sugerido:** `8–12` (default recomendado: `10`).
- `meta.skills_columns` (1|2): número de subcolumnas internas para las barras de skills dentro del sidebar.  
  - **Sugerido:** `2` para reducir altura.
- `meta.show_skill_percent` (bool): muestra/oculta el porcentaje al lado de cada barra.  
  - **Sugerido:** `false` para un look más limpio y compacto.

Comportamiento: si `sections.skills` excede `meta.max_sidebar_skills`, el excedente se mueve a la columna derecha como lista compacta en una sección **“MÁS HABILIDADES”**.

## Decisiones de diseño

- Estructura: header full-width + body grid 37/63.
- ATS-friendly moderado: dos columnas pero texto limpio y sin assets externos obligatorios.
- Barras de skills:
  - Si skill es string => nivel default `75%`.
  - Si skill es objeto `{name, level}` => usa `level` en rango `[0..1]`.
- Control de overflow (importante):
  - El sidebar puede desbordar si hay demasiadas barras; por eso existe `meta.max_sidebar_skills` y el overflow se traslada a la derecha.
- Secciones condicionales: si no hay datos, no se imprime la sección.
- Inserción de texto dinámica como string escapado (`tstr`) para soportar caracteres especiales.

## Ejecución Docker (ejemplo)

```powershell
docker compose run --rm cvgen-typst python main.py `
  --cv-file /app/inputs/examples/cv_ejemplo.md `
  --job-file /app/inputs/examples/oferta_ejemplo.txt `
  --template-file /app/templates/typst/custom/arjona_two_col_clean.typ.j2 `
  --template-adapter-file /app/examples/typst/arjona_two_col_clean.adapter.json `
  --pages 2 `
  --no-interactive `
  --output-dir /app/outputs/arjona_two_col_clean_demo