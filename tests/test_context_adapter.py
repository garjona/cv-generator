from pathlib import Path

from cv_generator.infrastructure.rendering.context_adapter import adapt_context_with_mapping


def test_adapter_maps_and_merges_static(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.json"
    adapter.write_text(
        """{
  "mapping": {
    "profile": {
      "name": "candidate_name",
      "skills": "skills"
    },
    "target": {
      "title": "job_target.title"
    }
  },
  "static": {
    "meta": {"engine": "typst"}
  }
}""",
        encoding="utf-8",
    )

    context = {
        "candidate_name": "Ana Perez",
        "skills": ["Python", "SQL"],
        "job_target": {"title": "Analista BI"},
    }

    adapted = adapt_context_with_mapping(context, adapter)

    assert adapted["profile"]["name"] == "Ana Perez"
    assert adapted["profile"]["skills"] == ["Python", "SQL"]
    assert adapted["target"]["title"] == "Analista BI"
    assert adapted["meta"]["engine"] == "typst"

