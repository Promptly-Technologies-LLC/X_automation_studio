import sqlmodel
from typing import Optional

DATABASE_URL = "sqlite:///./database.db"
engine = sqlmodel.create_engine(DATABASE_URL, echo=True)

class AIModel(sqlmodel.SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    # Name under which model can be accessed through LiteLLM
    name: str

    outputs: list["Output"] = sqlmodel.Relationship(back_populates="aimodel")

class Prompt(sqlmodel.SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    # Full text of the prompt
    prompt: str

    outputs: list["Output"] = sqlmodel.Relationship(back_populates="prompt")

class Output(sqlmodel.SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    # Full text of the output
    text: str

    prompt_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="prompt.id")
    prompt: Prompt = sqlmodel.Relationship(back_populates="outputs")

    aimodel_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="aimodel.id")
    aimodel: AIModel = sqlmodel.Relationship(back_populates="outputs")

    feedback: list["Feedback"] = sqlmodel.Relationship(back_populates="output")

class Feedback(sqlmodel.SQLModel, table=True):
    id: Optional[int] = sqlmodel.Field(default=None, primary_key=True)
    # Full text of the feedback
    score: int
    comment: Optional[str] = sqlmodel.Field(default=None)

    output_id: Optional[int] = sqlmodel.Field(default=None, foreign_key="output.id")
    output: Output = sqlmodel.Relationship(back_populates="feedback")
