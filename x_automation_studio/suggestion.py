import os
import logging
from dotenv import load_dotenv
from litellm import completion, ModelResponse

load_dotenv(override=True)

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

def get_suggestion(prompt: str = None) -> str:
    if not prompt:
        try:
            import wonderwords
            random_noun = wonderwords.RandomWord().word(include_parts_of_speech=["nouns"])
            logger.info(f"Using random noun: {random_noun}")
            prompt = "Write an achingly beautiful tweet about " + random_noun
        except ImportError:
            prompt = "Write an achingly beautiful tweet"

    response: ModelResponse = completion(
        model="openrouter/minimax/minimax-01",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        api_key=os.getenv("OPENROUTER_API_KEY")
    )

    if len(response.choices[0].message.content) > 280:
        logger.info(f"Tweet was too long; abbreviating")
        return get_suggestion("Abbreviate this draft tweet to 280 characters or less: " + response.choices[0].message.content)
    
    return response.choices[0].message.content