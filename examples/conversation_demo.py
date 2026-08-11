"""Run a persisted multi-turn website conversation without external APIs."""

import sys
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402
from src.engine.customer_response_generator import (  # noqa: E402
    DeterministicCustomerResponseGenerator,
)
from src.engine.intent_extractor import DeterministicIntentExtractor  # noqa: E402
from src.engine.question_generator import DeterministicQuestionGenerator  # noqa: E402
from src.persistence.conversation_service import ConversationService  # noqa: E402
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine  # noqa: E402


def main() -> None:
    settings = Settings.from_environment()
    if settings.ai_provider != "deterministic":
        raise RuntimeError("conversation demo requires AI_PROVIDER=deterministic")
    engine = create_database_engine(settings.database_url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    service = ConversationService(
        factory,
        DeterministicIntentExtractor(),
        DeterministicQuestionGenerator(),
        DeterministicCustomerResponseGenerator(),
        token_ttl_hours=settings.public_conversation_token_ttl_hours,
    )
    demo_phone = f"+1555{uuid4().int % 10_000_000:07d}"
    try:
        first = service.create(
            "acme-home-services",
            message_text="I need someone to look at my AC",
            external_message_id=str(uuid4()),
        )
        print("Customer: I need someone to look at my AC")
        print(f"Assistant: {first.messages[-1].text}")

        second = service.send_message(
            "acme-home-services",
            first.conversation_token,
            message_text="60601",
            external_message_id=str(uuid4()),
        )
        print("Customer: 60601")
        print(f"Assistant: {second.messages[-1].text}")

        final = service.send_message(
            "acme-home-services",
            first.conversation_token,
            message_text=f"My phone is {demo_phone}. My name is Ada",
            external_message_id=str(uuid4()),
        )
        print(f"Customer: My phone is {demo_phone}. My name is Ada")
        print(f"Assistant: {final.messages[-1].text}")
        print(f"State: {final.current_state.value if final.current_state else 'none'}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
