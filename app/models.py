from pydantic import BaseModel, Field


class Section(BaseModel):
    title: str
    short_description: str
    bullet_points: list[str] = Field(
        min_length=2,
        max_length=5
    )
    visual_description: str


class InfographicContent(BaseModel):
    title: str
    subtitle: str
    sections: list[Section] = Field(
        min_length=3,
        max_length=8
    )


class GenerateRequest(BaseModel):
    topic: str
    audience: str = "Beginner"
    style: str = "Technical / Modern"
    format: str = "A4 Portrait"
    sections: int = 6


class GenerateInfographicRequest(BaseModel):
    project_id: str
