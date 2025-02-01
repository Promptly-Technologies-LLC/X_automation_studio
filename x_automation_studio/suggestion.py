import logging
from dotenv import load_dotenv
from litellm import completion, ModelResponse
from sqlmodel import Session, select, func
from .models import Prompt, Output, AIModel, engine

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
            func.sum(func.coalesce(Output.feedback.score, 0)).desc()
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
    return session.exec(select(AIModel).order_by(func.random())).first()


def select_highest_rated_model(session: Session) -> AIModel:
    """Select the AI model with the highest total output feedback score.

    Args:
        session (Session): The active database session.

    Returns:
        AIModel: The AI model with the highest cumulative score.
    """
    return session.exec(
        select(AIModel).order_by(
            func.sum(func.coalesce(Output.feedback.score, 0)).desc()
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
    response: ModelResponse = completion(
        model=model.name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200
    )
    return response.choices[0].message.content


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
        dict: A dictionary containing the suggestion text, the prompt used, and
        the model name.
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
    suggestion_text: str = call_model(model, prompt)

    # If the suggestion is too long, abbreviate it
    while len(suggestion_text) > 280:
        logger.info("Tweet was too long; abbreviating")
        suggestion_text = call_model(
            model,
            "Abbreviate this draft tweet to "
            "280 characters or less: " + suggestion_text
        )

    return {
        "text": suggestion_text,
        "prompt_used": prompt,
        "model": model.name
    }