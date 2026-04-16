from __future__ import annotations

from relation_graph.kg_models import RelationBatch, model_json_schema


RELATION_SYSTEM_PROMPT = (
    "任务是从文本中抽取适合直接构建知识图谱的关键关系。"
    "只选择最重要、最明确、最稳定的关系；证据不足时宁可少返回。"
    "节点必须是可独立成图谱节点的原子化实体或概念，优先使用文中原词，避免长句、代词、动作片段和冗余修饰。"
    "关系必须是可直接显示在连线上的简短中文谓词短语。"
    "仅当文本明确表达单向作用、控制、因果、依赖、生成、从属、发布或传递时，才使用 directed；其余使用 undirected。"
    "实体类型必须选择最贴切的一项，不确定时使用 Other。"
    "统一使用简体中文。"
)


def build_relation_user_prompt(text: str) -> str:
    return (
        "阅读以下文本，抽取适合构建关系图谱的关键关系。"
        "如果文本中没有足够明确的关系，返回空数组。\n\n"
        f"{text}"
    )


def build_relation_response_schema() -> dict:
    return model_json_schema(RelationBatch)

