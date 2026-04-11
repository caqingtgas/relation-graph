from __future__ import annotations

from knowledge_graph.kg_models import RelationBatch, model_json_schema


RELATION_SYSTEM_PROMPT = (
    "请从文本中抽取最关键、最明确、最适合直接构建关系图谱的实体或概念关系。"
    "只保留最重要的关系，不要贪多，最多返回 20 条。"
    "节点必须原子化，避免长句、动作片段和冗余修饰。"
    "关系必须是简洁、可直接作为图谱连线展示的谓词短语。"
    "边(edge)方向必须严格克制：默认使用 undirected。"
    "只有当关系本身明确表达单向动作、作用流向、因果影响、控制支配、发布传递或从属指向时，才使用 directed。"
    "若使用 directed，关系文本至少要满足把它念成“A + 关系文本 + B”时整体通顺自然。"
    "其余关系尽量按 undirected 处理，不要强行给出明确方向。只要关系更像关联、合作、并列性联系，或方向并不十分明确，一律使用 undirected。"
    "统一使用简体中文。"
)


def build_relation_user_prompt(text: str) -> str:
    return (
        "请基于以下文本抽取可直接建图的关系。"
        "只保留最重要的关系，最多返回 20 条。"
        "对边方向保持克制，只有方向非常明确时才使用 directed。\n\n"
        f"{text}"
    )


def build_relation_response_schema() -> dict:
    return model_json_schema(RelationBatch)
