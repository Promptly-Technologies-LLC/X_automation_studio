# models.py
from sqlmodel import Session, select, SQLModel, Field, Relationship, create_engine
from typing import Optional, List
from enum import Enum
from datetime import datetime, UTC

# --- DB ---

DATABASE_URL = "sqlite:///./database.db"
engine = create_engine(DATABASE_URL, echo=True)

# --- MODELS ---

class PromptType(Enum):
    TEXT = "text"
    IMAGE = "image"

class AIModel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Name under which model can be accessed through LiteLLM
    name: str
    text_output: bool
    image_output: bool

    textoutputs: list["TextOutput"] = Relationship(back_populates="aimodel")
    imageoutputs: list["ImageOutput"] = Relationship(back_populates="aimodel")

class Domain(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

    prompts: list["Prompt"] = Relationship(back_populates="domain")

class Prompt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Full text of the prompt
    prompt: str
    prompt_type: PromptType

    domain_id: Optional[int] = Field(default=None, foreign_key="domain.id")
    domain: Optional[Domain] = Relationship(back_populates="prompts")

    textoutputs: list["TextOutput"] = Relationship(back_populates="prompt")
    imageoutputs: list["ImageOutput"] = Relationship(back_populates="prompt")

class TextOutput(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Full text of the output
    text: str

    prompt_id: Optional[int] = Field(default=None, foreign_key="prompt.id")
    prompt: Prompt = Relationship(back_populates="textoutputs")

    aimodel_id: Optional[int] = Field(default=None, foreign_key="aimodel.id")
    aimodel: AIModel = Relationship(back_populates="textoutputs")

    feedback: list["Feedback"] = Relationship(back_populates="textoutput")

    user_tweets: List["UserTweet"] = Relationship(back_populates="suggestion")

class ImageOutput(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Blob of the image
    image: bytes

    prompt_id: Optional[int] = Field(default=None, foreign_key="prompt.id")
    prompt: Prompt = Relationship(back_populates="imageoutputs")

    aimodel_id: Optional[int] = Field(default=None, foreign_key="aimodel.id")
    aimodel: AIModel = Relationship(back_populates="imageoutputs")

    feedback: list["Feedback"] = Relationship(back_populates="imageoutput")

class Feedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Full text of the feedback
    score: int
    comment: Optional[str] = Field(default=None)

    textoutput_id: Optional[int] = Field(default=None, foreign_key="textoutput.id")
    textoutput: TextOutput = Relationship(back_populates="feedback")

    imageoutput_id: Optional[int] = Field(default=None, foreign_key="imageoutput.id")
    imageoutput: ImageOutput = Relationship(back_populates="feedback")

class UserTweet(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tweet_text: str
    tweet_id: str
    suggestion_id: Optional[int] = Field(default=None, foreign_key="textoutput.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
    suggestion: Optional["TextOutput"] = Relationship(back_populates="user_tweets")

# --- SEED ---

# Only free text models are seeded by default
DEFAULT_MODELS = [
    # AIModel(name="openrouter/minimax/minimax-01", text_output=True, image_output=False),
    # AIModel(name="openrouter/qwen/qwen-turbo-2024-11-01", text_output=True, image_output=False),
    # AIModel(name="openrouter/qwen/qwen-plus", text_output=True, image_output=False),
    AIModel(name="openrouter/openai/o3-mini", text_output=True, image_output=False),
    # AIModel(name="openrouter/deepseek/deepseek-r1-distill-qwen-1.5b", text_output=True, image_output=False),
    # AIModel(name="openrouter/mistralai/mistral-small-24b-instruct-2501", text_output=True, image_output=False),
    # AIModel(name="openrouter/deepseek/deepseek-r1-distill-qwen-32b", text_output=True, image_output=False),
    # AIModel(name="openrouter/deepseek/deepseek-r1-distill-qwen-14b", text_output=True, image_output=False),
    # AIModel(name="openrouter/liquid/lfm-7b", text_output=True, image_output=False),
    # AIModel(name="openrouter/google/gemini-2.0-flash-thinking-exp:free", text_output=True, image_output=False),
    # AIModel(name="openrouter/google/gemini-2.0-flash-001", text_output=True, image_output=False),
    AIModel(name="openrouter/google/gemini-2.0-flash-lite-preview-02-05:free", text_output=True, image_output=False),
    # AIModel(name="openrouter/deepseek/deepseek-r1:free", text_output=True, image_output=False),
    AIModel(name="openrouter/sophosympatheia/rogue-rose-103b-v0.2:free", text_output=True, image_output=False),
    # AIModel(name="openrouter/microsoft/phi-4", text_output=True, image_output=False),
    # AIModel(name="openrouter/openai/o1", text_output=True, image_output=False),
    # AIModel(name="openrouter/x-ai/grok-2-1212", text_output=True, image_output=False),
    AIModel(name="dall-e-3", text_output=False, image_output=True)
]

DEFAULT_DOMAINS = [
    Domain(name="General")
]

DEFAULT_PROMPTS = [
    Prompt(prompt="Write an achingly beautiful tweet. Consider the following user-provided context to seed your response: {context}", prompt_type=PromptType.TEXT),
    Prompt(prompt="Create an achingly beautiful image. Consider the following user-provided context to seed your response: {context}", prompt_type=PromptType.IMAGE),
]

def create_tables():
    SQLModel.metadata.create_all(engine)


def seed_db():
    with Session(engine) as session:
        existing_models = session.exec(select(AIModel)).first()
        if not existing_models:
            for model in DEFAULT_MODELS:
                session.add(model)
            session.commit()

        existing_domains = session.exec(select(Domain)).first()
        if not existing_domains:
            for domain in DEFAULT_DOMAINS:
                for prompt in DEFAULT_PROMPTS:
                    domain.prompts.append(prompt)
                session.add(domain)
            session.commit()
