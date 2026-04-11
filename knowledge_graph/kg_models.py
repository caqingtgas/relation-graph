from __future__ import annotations

from collections import Counter
from typing import Any, Literal
import unicodedata

from pydantic import BaseModel, Field


ENTITY_TYPES = (
    "Person",
    "Organization",
    "Location",
    "Concept",
    "Event",
    "Technology",
    "Object",
    "Other",
)
EDGE_MODES = ("directed", "undirected")

EntityType = Literal[
    "Person",
    "Organization",
    "Location",
    "Concept",
    "Event",
    "Technology",
    "Object",
    "Other",
]
EdgeMode = Literal["directed", "undirected"]


def parse_model(model_cls: type[BaseModel], payload: Any) -> BaseModel:
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(payload)
    return model_cls.parse_obj(payload)


def model_json_schema(model_cls: type[BaseModel]) -> dict:
    if hasattr(model_cls, "model_json_schema"):
        return model_cls.model_json_schema()
    return model_cls.schema()


def normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.split()).strip()


def canonical_text_key(value: Any) -> str:
    return normalize_text(value).casefold()


def choose_display_value(values: list[str]) -> str:
    cleaned_values = [normalize_text(item) for item in values if normalize_text(item)]
    if not cleaned_values:
        return ""
    counts = Counter(cleaned_values)
    # 计数优先，其次偏向更短的规范表达，最后用字典序保证稳定输出。
    ranked_values = sorted(counts.items(), key=lambda item: (-item[1], len(item[0]), item[0]))
    return ranked_values[0][0]


def choose_entity_type(values: list[str]) -> str:
    normalized = [normalize_text(item) or "Other" for item in values]
    non_other = [item for item in normalized if item != "Other"]
    if non_other:
        return choose_display_value(non_other)
    return "Other"


class RelationPayloadItem(BaseModel):
    node_1: str
    node_1_type: EntityType = "Other"
    node_2: str
    node_2_type: EntityType = "Other"
    edge: str = Field(
        ...,
        description="可直接展示在图谱连线上的关系短语，不要把方向性写成解释句。",
    )
    edge_mode: EdgeMode = Field(
        default="undirected",
        description="默认使用 undirected；仅当关系具有非常明确的单向语义时才使用 directed。",
    )


class RelationBatch(BaseModel):
    relations: list[RelationPayloadItem] = Field(
        default_factory=list,
        max_length=20,
        description="最多返回 20 条最关键、最明确、最适合建图的关系。",
    )


class RelationItem(BaseModel):
    node_1: str
    node_1_type: EntityType = "Other"
    node_2: str
    node_2_type: EntityType = "Other"
    edge: str
    edge_mode: EdgeMode = "undirected"
    chunk_id: str

    @property
    def node_1_key(self) -> str:
        return canonical_text_key(self.node_1)

    @property
    def node_2_key(self) -> str:
        return canonical_text_key(self.node_2)


class ConceptItem(BaseModel):
    entity: str
    importance: int
    category: str


class ConceptBatch(BaseModel):
    concepts: list[ConceptItem] = Field(default_factory=list)


def relation_items_from_batch(batch_payload: dict, *, chunk_id: str) -> list[RelationItem]:
    parsed_batch = parse_model(RelationBatch, batch_payload)
    relations: list[RelationItem] = []
    for item in parsed_batch.relations:
        node_1 = normalize_text(item.node_1)
        node_2 = normalize_text(item.node_2)
        edge = normalize_text(item.edge)
        if not node_1 or not node_2 or not edge:
            continue
        relations.append(
            parse_model(
                RelationItem,
                {
                    "node_1": node_1,
                    "node_1_type": normalize_text(item.node_1_type) or "Other",
                    "node_2": node_2,
                    "node_2_type": normalize_text(item.node_2_type) or "Other",
                    "edge": edge,
                    "edge_mode": normalize_text(item.edge_mode).lower() or "undirected",
                    "chunk_id": normalize_text(chunk_id),
                },
            )
        )
    return relations
