import sqlmodel
from typing import Optional

DATABASE_URL = "sqlite:///./database.db"
engine = sqlmodel.create_engine(DATABASE_URL, echo=True)

class AIModel(sqlmodel.SQLModel, table=True):
    id: int = sqlmodel.Field(default=None, primary_key=True)
    # Name under which model can be accessed through LiteLLM
    name: str

    prompts: list["Prompt"] = sqlmodel.Relationship(back_populates="model")

class Prompt(sqlmodel.SQLModel, table=True):
    id: int = sqlmodel.Field(default=None, primary_key=True)
    # Full text of the prompt
    prompt: str

    outputs: list["Output"] = sqlmodel.Relationship(back_populates="prompt")

class Output(sqlmodel.SQLModel, table=True):
    id: int = sqlmodel.Field(default=None, primary_key=True)
    # Full text of the output
    output: str

    prompt_id: int = sqlmodel.ForeignKey(Prompt.id)
    prompt: Prompt = sqlmodel.Relationship(back_populates="outputs")

    model_id: int = sqlmodel.ForeignKey(AIModel.id)
    model: AIModel = sqlmodel.Relationship(back_populates="outputs")

    feedback: list["Feedback"] = sqlmodel.Relationship(back_populates="output")

class Feedback(sqlmodel.SQLModel, table=True):
    id: int = sqlmodel.Field(default=None, primary_key=True)
    # Full text of the feedback
    score: int
    comment: Optional[str] = sqlmodel.Field(default=None)

    output_id: int = sqlmodel.ForeignKey(Output.id)
    output: Output = sqlmodel.Relationship(back_populates="feedback")
