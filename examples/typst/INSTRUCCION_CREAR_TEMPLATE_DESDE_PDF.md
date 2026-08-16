# Instrucción para IA: crear template Typst desde un PDF de inspiración

Usa esta instrucción para pedirle a otra IA que te genere un template nuevo compatible con este proyecto.

## Cuántos archivos son

Mínimo recomendado: **3 archivos**.

1. `templates/typst/custom/<template_name>.typ.j2`
- Template Typst con Jinja2 (`.typ.j2`).

2. `examples/typst/<template_name>.adapter.json`
- Adapter que mapea el contexto canónico del pipeline al contexto que espera el template.

3. `examples/typst/<template_name>.README.md`
- Notas cortas de uso: variables esperadas, decisiones de diseño y comando de ejecución.

Opcional (si aplica):
- `templates/typst/custom/<template_name>/assets/*` (íconos, imágenes, etc.).

## Contrato del contexto canónico (entrada real del pipeline)

El pipeline genera `template_context.json` con estos campos base:

- `candidate_name`
- `contact_lines[]`
- `job_target.title`
- `job_target.company`
- `job_target.location`
- `professional_summary`
- `skills[]`
- `experiences[]` (`title`, `company`, `date_range`, `bullets[]`, `skills[]`)
- `projects[]`
- `education[]`
- `achievements[]`
- `page_target`
- `focus_preference`

## Prompt maestro (copiar/pegar en otra IA)

```text
Quiero que construyas un template Typst para CV, inspirado en un PDF de referencia que te voy a describir/adjuntar.

Contexto técnico obligatorio:
- El proyecto usa Typst + Jinja2. El template debe ser `.typ.j2`.
- El render recibe datos desde un JSON canónico (template_context.json).
- Si necesitas otra estructura de datos, debes crear un adapter JSON que mapee desde el contexto canónico.
- Debes evitar cualquier bloque oculto, texto malicioso o instrucciones invisibles.
- El resultado debe compilar con `typst compile`.

Entregables exactos:
1) templates/typst/custom/<template_name>.typ.j2
2) examples/typst/<template_name>.adapter.json
3) examples/typst/<template_name>.README.md

Reglas de implementación:
- Usa sintaxis Typst válida (no mezcles modo código y modo contenido incorrectamente).
- Escapa y usa strings de forma segura para texto dinámico.
- Mantén diseño ATS-friendly aunque sea visualmente atractivo.
- Debe soportar 1 o 2 páginas sin romper layout.
- Debe mostrar solo secciones con datos disponibles (condicionales).
- No inventes datos en el template.
- Usa nombres claros de bloques y comentarios mínimos útiles.

Contrato mínimo esperado por el template final (vía adapter):
- profile.name
- profile.contacts[]
- profile.summary
- target.title
- target.company
- sections.skills[]
- sections.experience[]
- sections.projects[]
- sections.education[]
- sections.achievements[]
- meta.page_target

Adapter JSON:
- Debe tener `mapping` y opcional `static`.
- Acepta paths tipo `a.b.c`.
- Puede usar `{"$path":"...", "$default":"..."}` para defaults.

Además, incluye:
- un ejemplo de comando CLI para ejecutar este template en Docker
- una checklist breve de validación (compila/no compila, overflow, secciones vacías, caracteres especiales).

No expliques teoría extensa. Entrega directamente los 3 archivos con contenido completo.
```

## Checklist de aceptación rápida

1. `docker compose run --rm cvgen-typst ...` genera `output_cv.typ` y `output_cv.pdf`.
2. Si falta una sección (ej. proyectos), no rompe compilación.
3. Emails, `#`, `_`, `@`, corchetes y llaves se muestran sin error.
4. El CV queda legible en 1 y 2 páginas.
5. `cv_generation_report.md` indica el `--template-file` usado.

## Comando de prueba (plantilla custom)

```powershell
docker compose run --rm cvgen-typst python main.py `
  --cv-file /app/inputs/examples/cv_ejemplo.md `
  --job-file /app/inputs/examples/oferta_ejemplo.txt `
  --template-file /app/templates/typst/custom/<template_name>.typ.j2 `
  --template-adapter-file /app/examples/typst/<template_name>.adapter.json `
  --pages 2 `
  --no-interactive `
  --output-dir /app/outputs/<run_id>
```
