import type { RelationGraphApi } from "../types";

export function getRelationGraphApi(): RelationGraphApi {
  return window.relationGraph;
}
