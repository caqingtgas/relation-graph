from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities

from knowledge_graph.kg_models import canonical_text_key, choose_display_value, choose_entity_type, normalize_text
from knowledge_graph.pipeline.types import AggregatedRelation, RawRelationRecord


@dataclass
class _RelationBucket:
    node_1_values: list[str]
    node_2_values: list[str]
    node_1_type_values: list[str]
    node_2_type_values: list[str]
    chunk_ids: set[str]
    edge_counter: Counter[str]
    count: int = 0


def _choose_primary_edge(counter: Counter[str]) -> str:
    ranked = sorted(counter.items(), key=lambda item: (-item[1], len(item[0]), item[0]))
    return ranked[0][0] if ranked else ""


def _ordered_edge_variants(counter: Counter[str]) -> tuple[str, ...]:
    ranked = sorted(counter.items(), key=lambda item: (-item[1], len(item[0]), item[0]))
    return tuple(edge for edge, _ in ranked)


def _merge_relation_variants(*variant_groups: tuple[str, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for group in variant_groups:
        for edge in group:
            if edge and edge not in seen:
                seen.add(edge)
                ordered.append(edge)
    return tuple(ordered)


def normalize_raw_relations(relations: Iterable[RawRelationRecord]) -> list[RawRelationRecord]:
    normalized_rows: list[RawRelationRecord] = []
    for relation in relations:
        node_1 = normalize_text(relation.node_1)
        node_2 = normalize_text(relation.node_2)
        edge = normalize_text(relation.edge)
        node_1_type = normalize_text(relation.node_1_type) or "Other"
        node_2_type = normalize_text(relation.node_2_type) or "Other"
        edge_mode = normalize_text(relation.edge_mode).lower() or "undirected"
        if not node_1 or not node_2 or not edge or node_1 == node_2:
            continue

        node_1_key = canonical_text_key(node_1)
        node_2_key = canonical_text_key(node_2)
        if edge_mode == "undirected" and node_1_key > node_2_key:
            node_1, node_2 = node_2, node_1
            node_1_type, node_2_type = node_2_type, node_1_type

        normalized_rows.append(
            RawRelationRecord(
                node_1=node_1,
                node_1_type=node_1_type,
                node_2=node_2,
                node_2_type=node_2_type,
                edge=edge,
                edge_mode=edge_mode,
                chunk_id=normalize_text(relation.chunk_id),
                count=int(relation.count),
            )
        )
    return normalized_rows


def aggregate_relations(relations: Sequence[RawRelationRecord]) -> list[AggregatedRelation]:
    grouped: dict[tuple[str, str, str], _RelationBucket] = {}
    for relation in normalize_raw_relations(relations):
        key = (
            canonical_text_key(relation.node_1),
            canonical_text_key(relation.node_2),
            relation.edge_mode,
        )
        bucket = grouped.setdefault(
            key,
            _RelationBucket(
                node_1_values=[],
                node_2_values=[],
                node_1_type_values=[],
                node_2_type_values=[],
                chunk_ids=set(),
                edge_counter=Counter(),
            ),
        )
        bucket.node_1_values.append(relation.node_1)
        bucket.node_2_values.append(relation.node_2)
        bucket.node_1_type_values.append(relation.node_1_type)
        bucket.node_2_type_values.append(relation.node_2_type)
        if relation.chunk_id:
            bucket.chunk_ids.add(relation.chunk_id)
        bucket.edge_counter[relation.edge] += 1
        bucket.count += int(relation.count)

    aggregated: list[AggregatedRelation] = []
    for (_, _, edge_mode), bucket in grouped.items():
        aggregated.append(
            AggregatedRelation(
                node_1=choose_display_value(bucket.node_1_values),
                node_2=choose_display_value(bucket.node_2_values),
                node_1_type=choose_entity_type(bucket.node_1_type_values),
                node_2_type=choose_entity_type(bucket.node_2_type_values),
                chunk_ids=tuple(sorted(bucket.chunk_ids)),
                edge_mode=edge_mode,
                primary_edge=_choose_primary_edge(bucket.edge_counter),
                edge_variants=_ordered_edge_variants(bucket.edge_counter),
                count=bucket.count,
            )
        )
    merged: dict[tuple[str, str], AggregatedRelation] = {}
    for relation in aggregated:
        pair_key = (canonical_text_key(relation.node_1), canonical_text_key(relation.node_2))
        existing = merged.get(pair_key)
        if existing is None:
            merged[pair_key] = relation
            continue
        if {existing.edge_mode, relation.edge_mode} == {"directed", "undirected"}:
            directed = existing if existing.edge_mode == "directed" else relation
            undirected = relation if directed is existing else existing
            variants = _merge_relation_variants(
                (directed.primary_edge,),
                directed.edge_variants,
                undirected.edge_variants,
            )
            merged[pair_key] = AggregatedRelation(
                node_1=directed.node_1,
                node_2=directed.node_2,
                node_1_type=directed.node_1_type if directed.node_1_type != "Other" else undirected.node_1_type,
                node_2_type=directed.node_2_type if directed.node_2_type != "Other" else undirected.node_2_type,
                chunk_ids=tuple(sorted(set(directed.chunk_ids).union(undirected.chunk_ids))),
                edge_mode="directed",
                primary_edge=directed.primary_edge,
                edge_variants=variants,
                count=directed.count + undirected.count,
            )
            continue
        merged[pair_key] = AggregatedRelation(
            node_1=existing.node_1,
            node_2=existing.node_2,
            node_1_type=existing.node_1_type if existing.node_1_type != "Other" else relation.node_1_type,
            node_2_type=existing.node_2_type if existing.node_2_type != "Other" else relation.node_2_type,
            chunk_ids=tuple(sorted(set(existing.chunk_ids).union(relation.chunk_ids))),
            edge_mode=existing.edge_mode,
            primary_edge=existing.primary_edge,
            edge_variants=_merge_relation_variants(
                (existing.primary_edge,),
                existing.edge_variants,
                relation.edge_variants,
            ),
            count=existing.count + relation.count,
        )
    return list(merged.values())


def build_graph(relations: Sequence[AggregatedRelation]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for relation in relations:
        if not graph.has_node(relation.node_1):
            graph.add_node(relation.node_1, entity_type=relation.node_1_type)
        if not graph.has_node(relation.node_2):
            graph.add_node(relation.node_2, entity_type=relation.node_2_type)
        graph.add_edge(
            relation.node_1,
            relation.node_2,
            title=relation.primary_edge,
            weight=float(relation.count),
        )
    return graph


def _build_community_projection(graph: nx.DiGraph) -> nx.Graph:
    projection = nx.Graph()
    for node, attrs in graph.nodes(data=True):
        projection.add_node(node, **attrs)
    for source, target, attrs in graph.edges(data=True):
        weight = float(attrs.get("weight", 1.0))
        if projection.has_edge(source, target):
            projection[source][target]["weight"] += weight
        else:
            projection.add_edge(source, target, weight=weight)
    return projection


def _count_rendered_connections(relations: Sequence[AggregatedRelation], graph: nx.DiGraph) -> dict[str, int]:
    connection_counts = {node: 0 for node in graph.nodes()}
    for relation in relations:
        connection_counts[relation.node_1] = connection_counts.get(relation.node_1, 0) + 1
        connection_counts[relation.node_2] = connection_counts.get(relation.node_2, 0) + 1
    return connection_counts


def _community_colors(communities: Sequence[Sequence[str]]) -> dict[str, tuple[str, int]]:
    preset_colors = [
        "#FFB6C1",
        "#A1C4FD",
        "#C2E9FB",
        "#FFD1DC",
        "#E0C3FC",
        "#D4FC79",
        "#96E6A1",
        "#FCCB90",
        "#F5576C",
        "#4FACFE",
    ]
    color_map: dict[str, tuple[str, int]] = {}
    for index, community in enumerate(communities):
        color = preset_colors[index % len(preset_colors)]
        for node in community:
            color_map[node] = (color, index + 1)
    return color_map


def apply_communities(graph: nx.DiGraph, relations: Sequence[AggregatedRelation]) -> int:
    projection = _build_community_projection(graph)
    if projection.number_of_nodes() == 0:
        return 0
    if projection.number_of_nodes() < 3:
        communities = [[node] for node in projection.nodes()]
    else:
        communities = [list(community) for community in greedy_modularity_communities(projection, weight="weight")]
    color_map = _community_colors(communities)
    connection_counts = _count_rendered_connections(relations, graph)
    max_degree = max(connection_counts.values()) if connection_counts else 1
    for node, (color, group) in color_map.items():
        degree = connection_counts.get(node, 0)
        graph.nodes[node]["group"] = group
        graph.nodes[node]["color"] = color
        graph.nodes[node]["size"] = 15 + (math.log(degree + 1) / math.log(max_degree + 1)) * 20
        entity_type = graph.nodes[node].get("entity_type", "Other")
        graph.nodes[node]["title"] = f"实体: {node}\n类型: {entity_type}\n连接数: {degree}"
    return len(communities)
