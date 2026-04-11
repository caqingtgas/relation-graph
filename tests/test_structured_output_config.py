from __future__ import annotations

from knowledge_graph.ark_client import ArkClient, ArkClientConfig
from knowledge_graph.pipeline.relation_prompts import build_relation_response_schema


def test_relation_response_schema_forbids_extra_fields_and_requires_core_fields():
    schema = build_relation_response_schema()
    item_schema = schema["$defs"]["RelationPayloadItem"]

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["relations"]
    assert item_schema["additionalProperties"] is False
    assert item_schema["required"] == [
        "node_1",
        "node_1_type",
        "node_2",
        "node_2_type",
        "edge",
        "edge_mode",
    ]


def test_ark_payload_uses_strict_structured_output_defaults():
    with ArkClient(ArkClientConfig(api_key="demo-key", retry_count=0, parse_retry_count=0)) as client:
        payload = client._build_payload(
            user_prompt="抽取关系",
            response_schema=build_relation_response_schema(),
            schema_name="knowledge_graph_relations",
            schema_description="知识图谱关系抽取结果",
            system_prompt="你是一个关系抽取器。",
            model="doubao-seed-1-8-251228",
        )

    assert payload["thinking"] == {"type": "disabled"}
    assert payload["temperature"] == 0
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
