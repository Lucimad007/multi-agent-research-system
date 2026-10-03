from pydantic import BaseModel, ConfigDict, Field


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class SearchResult(BaseModel):
    """Contract the search agent returns and the analysis agent consumes."""

    model_config = ConfigDict(extra="forbid")

    sources: list[Source]


class CitedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    urls: list[str]


class ClaimSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[CitedClaim]


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[str]
    disagreements: list[str]
    gaps: list[str]
    cited_urls: list[str]


class ResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtasks: list[str] = Field(min_length=1, max_length=3)


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[str]
    disagreements: list[str]
    gaps: list[str]


SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["title", "url", "summary"],
            },
        },
    },
    "required": ["sources"],
}
