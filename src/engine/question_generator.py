"""Customer-question generation boundary."""

from typing import Mapping, Protocol

from src.domain.qualification import CustomerResponse, CustomerTone, MissingInformationResult


class QuestionGenerator(Protocol):
    def generate(
        self,
        missing: MissingInformationResult,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        customer_message: str = "",
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse: ...


class DeterministicQuestionGenerator:
    """Renders configured prompts without inventing industry-specific language.
    customer_message/customer_tone are accepted for protocol compatibility with
    AIQuestionGenerator but intentionally unused here -- this generator never
    calls an AI, so it has no tone-adaptive wording to produce; see
    universal-sales-cycle-model.md section 7 for the AI-backed path."""

    def generate(
        self,
        missing: MissingInformationResult,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        customer_message: str = "",
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
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
