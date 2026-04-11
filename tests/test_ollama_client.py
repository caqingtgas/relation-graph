from __future__ import annotations

import json

from knowledge_graph.ollama_client import OllamaClient, OllamaClientConfig


def test_build_payload_disables_thinking_and_grounds_schema():
    with OllamaClient(OllamaClientConfig(model="qwen3.5:4b", retry_count=0, parse_retry_count=0)) as client:
        payload = client._build_payload(
            user_prompt="请抽取关系",
            response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            schema_name="demo_schema",
            schema_description="演示结构化输出",
            system_prompt="你是一个抽取器。",
            model="qwen3.5:4b",
        )

    assert payload["think"] is False
    assert payload["format"]["type"] == "object"
    assert "demo_schema" in payload["messages"][-1]["content"]
    assert "JSON Schema" in payload["messages"][-1]["content"]


def test_parse_json_text_accepts_direct_json():
    parsed = OllamaClient._parse_json_text('{"ok": true}')
    assert parsed == {"ok": True}


def test_parse_json_text_accepts_code_fence_json():
    parsed = OllamaClient._parse_json_text("```json\n{\"ok\": true}\n```")
    assert parsed == {"ok": True}


def test_parse_json_text_accepts_wrapped_json():
    parsed = OllamaClient._parse_json_text('好的，结果如下：{"ok": true}')
    assert parsed == {"ok": True}


def test_extract_structured_content_prefers_tool_arguments_when_content_empty():
    payload = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "emit_json",
                        "arguments": {"ok": True},
                    }
                }
            ],
        }
    }
    extracted = OllamaClient._extract_structured_content(payload)
    assert json.loads(extracted) == {"ok": True}
