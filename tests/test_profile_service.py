from cv_generator.application.profile_service import ProfileService
from cv_generator.domain.models import MasterProfile


def test_apply_interactive_answers_skips_negative_placeholder_achievements() -> None:
    profile = MasterProfile.empty("p-negative")
    answers = [
        {"question_type": "achievement", "answer": "No tengo."},
        {"question_type": "leadership", "answer": "No tengo"},
    ]

    updated = ProfileService().apply_interactive_answers(profile, answers)

    assert updated.achievements == []
    assert len(updated.interaction_answers) == 2

