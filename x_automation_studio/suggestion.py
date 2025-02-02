import re
import logging
from typing import Optional
from dotenv import load_dotenv
from litellm import completion, ModelResponse
from sqlmodel import Session, select, func
from .models import Prompt, TextOutput, AIModel, engine, Feedback

load_dotenv(override=True)

logger: logging.Logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)


def select_highest_rated_prompt(session: Session) -> Prompt:
    """Select the prompt with the highest total output feedback score.

    Args:
        session (Session): The active database session.

    Returns:
        Prompt: The prompt with the highest cumulative score.
    """
    return session.exec(
        select(Prompt).order_by(
            func.sum(func.coalesce(TextOutput.feedback.score, 0)).desc()
        )
    ).first()


def select_random_prompt(session: Session) -> Prompt:
    """Select a random prompt from the database.

    Args:
        session (Session): The active database session.

    Returns:
        Prompt: A randomly selected prompt.
    """
    return session.exec(select(Prompt).order_by(func.random())).first()


def select_random_model(session: Session) -> AIModel:
    """Select a random AI model from the database.

    Args:
        session (Session): The active database session.

    Returns:
        AIModel: A randomly selected AI model.
    """
    return session.exec(select(AIModel).where(AIModel.text_output == True).order_by(func.random())).first()


def select_highest_rated_model(session: Session) -> AIModel:
    """Select the AI model with the highest total output feedback score.

    Args:
        session (Session): The active database session.

    Returns:
        AIModel: The AI model with the highest cumulative score.
    """
    return session.exec(
        select(AIModel).where(AIModel.text_output == True).order_by(
            func.sum(func.coalesce(TextOutput.feedback.score, 0)).desc()
        )
    ).first()


def get_random_noun() -> str:
    """Return a random noun using the wonderwords module, or an empty string if
    unavailable.

    Returns:
        str: A random noun or an empty string if wonderwords is not installed.
    """
    try:
        import wonderwords
        return wonderwords.RandomWord().word(include_parts_of_speech=["nouns"])
    except ImportError:
        return ""


def call_model(model: AIModel, prompt: str) -> str:
    """Call the AI model with the provided prompt and return its response.

    Args:
        model (AIModel): The AI model to use.
        prompt (str): The prompt to send to the model.

    Returns:
        str: The generated text from the model.
    """
    logger.info(f"Calling model: {model.name}")
    logger.info(f"Prompt: {prompt}")
    response: ModelResponse = completion(
        model=model.name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        num_retries=3
    )
    logger.info(f"Response: {str(response)}")
    return response.choices[0].message.content


def create_output_record(suggestion: dict, feedback: Optional[dict] = None) -> int:
    """
    Create an TextOutput record in the database. This function is intended to be
    used as a background task.
    """
    # Import Session and engine if needed:
    with Session(engine) as session:
        output = TextOutput(
            text=suggestion["text"],
            prompt_id=suggestion["prompt_id"],
            aimodel_id=suggestion["aimodel_id"]
        )
        if feedback:
            output.feedback.append(Feedback(**feedback))
        session.add(output)
        session.commit()
        return output.id


def remove_thinking_tags(text: str) -> str:
    """Remove thinking tags from the text, even if the content spans multiple
    lines."""
    return re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)


def get_suggestion(context: str | None = None, mode: str = "random") -> dict:
    """Generate a tweet suggestion based on the context and mode provided.

    In 'highest' mode, the prompt and model with the highest ratings are
    selected. In any other mode, a random prompt and model are used. The prompt
    is formatted with the provided context.

    Args:
        context (str | None): The context to supplement the prompt. If None, a
        random noun is used.
        mode (str): Mode of selection: 'random' or 'highest'.

    Returns:
        dict: A dictionary containing the suggestion 'text' and the 'prompt_id'
        and the 'aimodel_id' used to generate the suggestion.
    """
    # If no context is provided, use a random noun
    if not context:
        context: str = get_random_noun()

    if mode == "highest":
        with Session(engine) as session:
            prompt_obj = select_highest_rated_prompt(session)
            model = select_highest_rated_model(session)
    else:
        # For random mode, create a new session to get prompt and model
        with Session(engine) as session:
            prompt_obj = select_random_prompt(session)
            model = select_random_model(session)

    # Format the prompt with the context
    prompt = prompt_obj.prompt.format(context=context)

    # Get the initial suggestion from the model
    suggestion_text: str = call_model(
        model,
        "Return your output as a single tweet, <=280 characters with no other "
        "text unless it is enclosed in <thinking> tags. " + prompt
    )
    logger.info(f"Initial tweet: {suggestion_text}")
    suggestion_text = remove_thinking_tags(suggestion_text)
    logger.info(f"Tweet after removing thinking tags: {suggestion_text}")
    
    # If the suggestion is too long, abbreviate it
    while len(suggestion_text) > 280:
        logger.info(f"Abbreviating tweet: {suggestion_text}")
        create_output_record(
            {
                "text": suggestion_text,
                "prompt_id": prompt_obj.id,
                "aimodel_id": model.id
            },
            {
                "score": -1,
                "comment": (
                    "TextOutput should be a single tweet, <=280 characters with "
                    "no other text, but exceeded that limit."
                )
            }
        )
        suggestion_text = call_model(
            model,
            "Abbreviate this draft tweet to 280 characters or less. Only "
            "return a single abbreviated tweet, no other text. " + 
            suggestion_text
        )
        suggestion_text = remove_thinking_tags(suggestion_text)

    return {
        "text": suggestion_text,
        "prompt_id": prompt_obj.id,
        "aimodel_id": model.id
    }