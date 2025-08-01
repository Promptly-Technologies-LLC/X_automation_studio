# models.py
import sqlmodel
from sqlmodel import Session, select, SQLModel
from typing import Optional
from enum import Enum

# --- DB ---

DATABASE_URL = "sqlite:///./database.db"
engine = sqlmodel.create_engine(DATABASE_URL, echo=True)

# --- MODELS ---

class PromptType(Enum):
    TEXT = "text"
    IMAGE = "image"

class AIModel(sqlmodel.SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    # Name under which model can be accessed through LiteLLM
    name: str
    text_output: bool
    image_output: bool

    textoutputs: list["TextOutput"] = sqlmodel.Relationship(back_populates="aimodel")
    imageoutputs: list["ImageOutput"] = sqlmodel.Relationship(back_populates="aimodel")

class Domain(SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    name: str

    prompts: list["Prompt"] = sqlmodel.Relationship(back_populates="domain")

class Prompt(sqlmodel.SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    # Full text of the prompt
    prompt: str
    prompt_type: PromptType

    domain_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="domain.id")
    domain: Optional[Domain] = sqlmodel.Relationship(back_populates="prompts")

    textoutputs: list["TextOutput"] = sqlmodel.Relationship(back_populates="prompt")
    imageoutputs: list["ImageOutput"] = sqlmodel.Relationship(back_populates="prompt")

class TextOutput(sqlmodel.SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    # Full text of the output
    text: str

    prompt_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="prompt.id")
    prompt: Prompt = sqlmodel.Relationship(back_populates="textoutputs")

    aimodel_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="aimodel.id")
    aimodel: AIModel = sqlmodel.Relationship(back_populates="textoutputs")

    feedback: list["Feedback"] = sqlmodel.Relationship(back_populates="textoutput")

class ImageOutput(sqlmodel.SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    # Blob of the image
    image: bytes

    prompt_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="prompt.id")
    prompt: Prompt = sqlmodel.Relationship(back_populates="imageoutputs")

    aimodel_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="aimodel.id")
    aimodel: AIModel = sqlmodel.Relationship(back_populates="imageoutputs")

    feedback: list["Feedback"] = sqlmodel.Relationship(back_populates="imageoutput")

class Feedback(sqlmodel.SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    # Full text of the feedback
    score: int
    comment: Optional[str] = sqlmodel.Field(default=None)

    textoutput_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="textoutput.id")
    textoutput: TextOutput = sqlmodel.Relationship(back_populates="feedback")

    imageoutput_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="imageoutput.id")
    imageoutput: ImageOutput = sqlmodel.Relationship(back_populates="feedback")

# --- SEED ---

# Only free text models are seeded by default
DEFAULT_MODELS = [
    AIModel(name="openrouter/horizon-alpha", text_output=True, image_output=False),
    AIModel(name="mistralai/mistral-small-3.2-24b-instruct:free", text_output=True, image_output=False),
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
