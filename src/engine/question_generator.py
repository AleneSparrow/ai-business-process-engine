"""Customer-question generation boundary."""

from typing import Mapping, Protocol

from src.domain.qualification import CustomerResponse, MissingInformationResult


class QuestionGenerator(Protocol):
    def generate(
        self,
        missing: MissingInformationResult,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
    ) -> CustomerResponse: ...


class DeterministicQuestionGenerator:
    """Renders configured prompts without inventing industry-specific language."""

    def generate(
        self,
        missing: MissingInformationResult,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
    ) -> CustomerResponse:
        customer_information = business_dna.get("customer_information", {})
        field_questions = (
            customer_information.get("field_questions", {})
            if isinstance(customer_information, Mapping)
            else {}
        )
        prompts: list[str] = []
        for field_name in missing.missing_fields:
            prompt = field_questions.get(field_name) if isinstance(field_questions, Mapping) else None
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"Business DNA has no question configured for required field: {field_name}")
            prompts.append(prompt.strip())
        prompts.extend(question.strip() for question in missing.unanswered_questions)
        if not prompts:
            raise ValueError("cannot generate a missing-information response without questions")
        return CustomerResponse(
            message_text=" ".join(prompts),
            channel=channel,
            reason="missing_information",
            related_case_id=case_id,
        )
