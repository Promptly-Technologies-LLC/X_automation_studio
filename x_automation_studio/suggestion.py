import re
import logging
import random
import math
from enum import Enum
from typing import Optional, List, TypeVar
from dotenv import load_dotenv
from litellm import completion, ModelResponse
from sqlmodel import Session, select, func
from .models import Prompt, TextOutput, AIModel, engine, Feedback

load_dotenv(override=True)

logger: logging.Logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

class Mode(Enum):
    RANDOM = "random"
    WEIGHTED = "weighted"
    HIGHEST = "highest"

T = TypeVar('T')

def softmax(weights: List[float], temperature: float = 1.0) -> List[float]:
    """Compute the softmax probability distribution for a list of weights."""
    exps = [math.exp(w / temperature) for w in weights]
    total = sum(exps)
    return [exp_val / total for exp_val in exps]

def weighted_random_choice(items: List[T], probabilities: List[float]) -> T:
    """Return a randomly selected item from items using the given probabilities."""
    # Using random.choices which accepts a weights argument:
    return random.choices(items, weights=probabilities, k=1)[0]

def select_weighted_prompt(session: Session, temperature: float = 1.0, domain_id: int | str = "") -> Prompt:
    # Optionally filter by domain
    query = select(Prompt)
    if domain_id:
        query = query.where(Prompt.domain_id == domain_id)

    prompts = session.exec(query).all()
    if not prompts:
        raise ValueError("No prompts available for the specified domain")

    scores = []
    for prompt in prompts:
        score = session.exec(
            select(func.sum(func.coalesce(TextOutput.feedback.score, 0)))
            .where(TextOutput.prompt_id == prompt.id)
        ).one() or 0
        scores.append(score)

    # Shift scores if necessary (if there are negatives)
    min_score = min(scores)
    if min_score < 0:
        scores = [s - min_score for s in scores]

    # Convert scores to probabilities (using softmax here)
    probabilities = softmax(scores, temperature=temperature)
    
    # Choose a prompt using the weighted random choice:
    return weighted_random_choice(prompts, probabilities)


def select_weighted_model(session: Session, temperature: float = 1.0) -> AIModel:
    # Retrieve all models that support text output.
    models = session.exec(
        select(AIModel).where(AIModel.text_output == True)
    ).all()
    if not models:
        raise ValueError("No models available")

    scores = []
    for model in models:
        score = session.exec(
            select(func.sum(func.coalesce(TextOutput.feedback.score, 0)))
            .where(TextOutput.aimodel_id == model.id)
        ).one() or 0
        scores.append(score)
    
    min_score = min(scores)
    if min_score < 0:
        scores = [s - min_score for s in scores]

    probabilities = softmax(scores, temperature=temperature)
    
    return weighted_random_choice(models, probabilities)


def select_highest_rated_prompt(session: Session, domain_id: int | str = "") -> Prompt:
    """Select the prompt with the highest total output feedback score.

    Args:
        session (Session): The active database session.

    Returns:
        Prompt: The prompt with the highest cumulative score.
    """
    query = select(Prompt)
    if domain_id:
        query = query.where(Prompt.domain_id == domain_id)

    return session.exec(
        query.order_by(
            func.sum(func.coalesce(TextOutput.feedback.score, 0)).desc()
        )
    ).first()


def select_random_prompt(session: Session, domain_id: int | str = "") -> Prompt:
    """Select a random prompt from the database.

    Args:
        session (Session): The active database session.

    Returns:
        Prompt: A randomly selected prompt.
    """
    query = select(Prompt)
    if domain_id:
        query = query.where(Prompt.domain_id == domain_id)

    return session.exec(query.order_by(func.random())).first()


def select_random_model(session: Session) -> AIModel:
    """Select a random AI model from the database.

    Args:
        session (Session): The active database session.

    Returns:
        AIModel: A randomly selected AI model.
    """
    return session.exec(
        select(AIModel).where(
            AIModel.text_output == True
        ).order_by(func.random())
    ).first()


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


def create_output_record(
        suggestion: dict, feedback: Optional[dict] = None
    ) -> int:
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


def get_suggestion(context: str = "", mode: Mode = Mode.WEIGHTED, domain_id: int | str = "") -> dict:
    if not context:
        context = get_random_noun()

    with Session(engine) as session:
        if mode == Mode.HIGHEST:
            prompt_obj = select_highest_rated_prompt(session, domain_id=domain_id)
            model = select_highest_rated_model(session)
        elif mode == Mode.WEIGHTED:
            prompt_obj = select_weighted_prompt(session, temperature=1.0, domain_id=domain_id)
            model = select_weighted_model(session, temperature=1.0)
        else:
            prompt_obj = select_random_prompt(session, domain_id=domain_id)
            model = select_random_model(session)

    # Format the prompt with the context
    prompt = prompt_obj.prompt.format(context=context)

    # Call the model
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
