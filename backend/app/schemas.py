from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

Language = Literal["pt", "en", "zh", "es", "hi"]

class ToolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    description: str = Field(min_length=1, max_length=500)
    kind: Literal["prompt_template"]
    template: str = Field(min_length=1, max_length=8000)

class SkillManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(min_length=1, max_length=1000)
    languages: list[Language] = Field(default_factory=lambda: ["pt"])
    # Optional hint used only when the user selects automatic language mode.
    default_language: Language | None = None
    tools: list[ToolManifest] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_default_language(self):
        if self.default_language and self.default_language not in self.languages:
            raise ValueError("default_language must be included in languages")
        return self

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)

class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    # None means resolve from an approved selected skill, falling back to Portuguese.
    language: Language | None = None
    skill_ids: list[str] = Field(default_factory=list, max_length=50)

class ChatResponse(BaseModel):
    answer: str
    language: Language
    active_skills: list[str]
    provider: str

class SkillSummary(BaseModel):
    id: str
    name: str
    version: str
    description: str
    status: Literal["pending_review", "active", "rejected"]
    languages: list[Language]
    tools: list[str]
