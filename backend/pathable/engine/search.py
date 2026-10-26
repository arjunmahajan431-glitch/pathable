"""Deterministic Dijkstra and A* implemented directly on the NetworkX graph.

We do not use NetworkX's shortest-path functions for routing. NetworkX is used
only in tests as an independent oracle. The graph is a directed MultiDiGraph;
parallel edges are considered separately and the cheapest one wins.

A* correctness: edge cost is always >= edge length (cost.py guarantees this),
and OSM edge length is at least the straight-line distance between its
endpoints. The heuristic is the haversine distance to the goal, so it never
overestimates the remaining cost. It is also consistent, because for any edge
``h(u) <= length(u, v) + h(v) <= cost(u, v) + h(v)``. A* therefore returns the
same minimum cost as Dijkstra. A test checks this on random graphs.

Determinism: neighbours are visited in a sorted order, and heap entries use a
monotonic counter rather than comparing node objects. Equal-cost paths
therefore resolve the same way on every run.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Collection, Hashable, Iterator
from dataclasses import dataclass
from typing import Any

import networkx as nx

from pathable.graph.loader import haversine_m
from pathable.graph.model import EdgeFeatures

Node = Hashable
WeightFn = Callable[[Node, Node, Any, EdgeFeatures], float | None]
HeuristicFn = Callable[[Node], float]


@dataclass(frozen=True)
class EdgeStep:
    u: Node
    v: Node
    key: Any


@dataclass(frozen=True)
class RoutePath:
    nodes: tuple[Node, ...]
    edges: tuple[EdgeStep, ...]
    cost: float
    length_m: float
    explored: int


def _sorted_out_edges(graph: nx.MultiDiGraph, node: Node) -> Iterator[tuple[Node, Any]]:
    adjacency = _adjacency(graph)
    return iter(adjacency.get(node, ()))


def _adjacency(graph: nx.MultiDiGraph) -> dict[Node, tuple[tuple[Node, Any], ...]]:
    """Sorted out-edges per node, built once and cached on the graph.

    A* pops tens of thousands of nodes. Sorting each node's edge list on every
    pop is pure repeated work, and it dominated citywide requests. The graph is
    immutable after loading, so one sorted tuple per node is safe.
    """
    cached = graph.graph.get("_pathable_adjacency")
    if isinstance(cached, dict):
        return cached
    adjacency: dict[Node, tuple[tuple[Node, Any], ...]] = {}
    for node in graph.nodes:
        edges = graph.out_edges(node, keys=True)
        adjacency[node] = tuple(
            (v, key) for _, v, key in sorted(edges, key=lambda item: (str(item[1]), str(item[2])))
        )
    graph.graph["_pathable_adjacency"] = adjacency
    return adjacency


def _node_coords(graph: nx.MultiDiGraph) -> dict[Node, tuple[float, float]]:
    cached = graph.graph.get("_pathable_node_coords")
    if isinstance(cached, dict):
        return cached
    coords = {
        node: (float(data["features"].lat), float(data["features"].lon))
        for node, data in graph.nodes(data=True)
        if data.get("features") is not None
    }
    graph.graph["_pathable_node_coords"] = coords
    return coords


def _features(graph: nx.MultiDiGraph, u: Node, v: Node, key: Any) -> EdgeFeatures:
    data = graph.get_edge_data(u, v, key)
    if not data or "features" not in data:
        raise KeyError(f"edge {u!r}->{v!r} key={key!r} has no normalized features")
    features: EdgeFeatures = data["features"]
    return features


def _reconstruct(
    graph: nx.MultiDiGraph,
    prev: dict[Node, tuple[Node, Any] | None],
    source: Node,
    target: Node,
    cost: float,
    explored: int,
) -> RoutePath:
    if source == target:
        return RoutePath(nodes=(source,), edges=(), cost=0.0, length_m=0.0, explored=explored)
    nodes: list[Node] = [target]
    edges: list[EdgeStep] = []
    current = target
    while current != source:
        step = prev[current]
        if step is None:
            raise RuntimeError("target reached without a predecessor chain")
        parent, key = step
        edges.append(EdgeStep(u=parent, v=current, key=key))
        nodes.append(parent)
        current = parent
    nodes.reverse()
    edges.reverse()
    length = sum(_features(graph, e.u, e.v, e.key).length_m for e in edges)
    return RoutePath(
        nodes=tuple(nodes),
        edges=tuple(edges),
        cost=float(cost),
        length_m=round(length, 3),
        explored=explored,
    )


def dijkstra(
    graph: nx.MultiDiGraph,
    source: Node,
    target: Node,
    weight: WeightFn,
) -> RoutePath | None:
    """Shortest path by ``weight``. ``None`` weights mean hard-blocked."""
    if source not in graph or target not in graph:
        raise KeyError("source or target is not in the graph")
    if source == target:
        return RoutePath(nodes=(source,), edges=(), cost=0.0, length_m=0.0, explored=1)

    best: dict[Node, float] = {source: 0.0}
    prev: dict[Node, tuple[Node, Any] | None] = {source: None}
    counter = 0
    heap: list[tuple[float, int, Node]] = [(0.0, counter, source)]
    explored = 0

    while heap:
        distance, _, node = heapq.heappop(heap)
        if distance > best.get(node, float("inf")):
            continue
        explored += 1
        if node == target:
            return _reconstruct(graph, prev, source, target, distance, explored)
        for neighbor, key in _sorted_out_edges(graph, node):
            edge_weight = weight(node, neighbor, key, _features(graph, node, neighbor, key))
            if edge_weight is None:
                continue
            candidate = distance + edge_weight
            if candidate < best.get(neighbor, float("inf")) - 1e-12:
                best[neighbor] = candidate
                prev[neighbor] = (node, key)
                counter += 1
                heapq.heappush(heap, (candidate, counter, neighbor))
    return None


def a_star(
    graph: nx.MultiDiGraph,
    source: Node,
    target: Node,
    weight: WeightFn,
    heuristic: HeuristicFn,
) -> RoutePath | None:
    """A* with an admissible heuristic. Must find the same cost as Dijkstra."""
    if source not in graph or target not in graph:
        raise KeyError("source or target is not in the graph")
    if source == target:
        return RoutePath(nodes=(source,), edges=(), cost=0.0, length_m=0.0, explored=1)

    best: dict[Node, float] = {source: 0.0}
    prev: dict[Node, tuple[Node, Any] | None] = {source: None}
    counter = 0
    heap: list[tuple[float, int, Node]] = [(heuristic(source), counter, source)]
    explored = 0

    while heap:
        _, _, node = heapq.heappop(heap)
        g = best.get(node)
        if g is None:
            continue
        explored += 1
        if node == target:
            return _reconstruct(graph, prev, source, target, g, explored)
        for neighbor, key in _sorted_out_edges(graph, node):
            edge_weight = weight(node, neighbor, key, _features(graph, node, neighbor, key))
            if edge_weight is None:
                continue
            candidate = g + edge_weight
            if candidate < best.get(neighbor, float("inf")) - 1e-12:
                best[neighbor] = candidate
                prev[neighbor] = (node, key)
                counter += 1
                heapq.heappush(heap, (candidate + heuristic(neighbor), counter, neighbor))
    return None


def haversine_heuristic(graph: nx.MultiDiGraph, target: Node) -> HeuristicFn:
    """Admissible, consistent heuristic for a graph with lat/lon node features."""
    coords = _node_coords(graph)
    if target not in coords:
        raise KeyError(f"target {target!r} has no coordinates")
    goal_lat, goal_lon = coords[target]

    def heuristic(node: Node) -> float:
        here = coords.get(node)
        if here is None:
            raise KeyError(f"node {node!r} has no coordinates")
        return haversine_m(here[0], here[1], goal_lat, goal_lon)

    return heuristic


def length_weight(_u: Node, _v: Node, _key: Any, features: EdgeFeatures) -> float:
    """Objective A: shortest route, length only. Hard blocks are ignored."""
    return features.length_m


def snap_to_node(
    graph: nx.MultiDiGraph,
    lat: float,
    lon: float,
    max_distance_m: float,
    *,
    eligible: Collection[Node] | None = None,
) -> tuple[Node, float]:
    """Nearest routable node and its distance. Refuses overly distant snaps.

    ``eligible`` limits the search to nodes that can actually take part in a
    route (normally the largest strongly connected component). Without it, an
    isolated two-node fragment beside a landmark can win the nearest-node race
    and leave the user with a route that cannot leave the fragment.
    """
    if graph.number_of_nodes() == 0:
        raise ValueError("graph has no nodes")
    best_node: Node | None = None
    best_distance = float("inf")
    for node, (node_lat, node_lon) in _node_coords(graph).items():
        if eligible is not None and node not in eligible:
            continue
        distance = haversine_m(lat, lon, node_lat, node_lon)
        if distance < best_distance - 1e-9 or (
            abs(distance - best_distance) <= 1e-9
            and best_node is not None
            and str(node) < str(best_node)
        ):
            best_node, best_distance = node, distance
    if best_node is None:
        raise ValueError("graph has no eligible nodes with coordinates")
    if best_distance > max_distance_m:
        raise SnapTooFarError(best_node, best_distance, max_distance_m)
    return best_node, best_distance


def routable_nodes(graph: nx.MultiDiGraph) -> frozenset[Node]:
    """Nodes in the largest connected component, cached on the graph.

    Pedestrian networks often contain tiny disconnected fragments (a short path
    inside a park, or a way that is not joined to a crossing). Routing can only
    succeed inside one component, so snapping and the UI should use the main one.
    Direction is still enforced by A*: this is the weakly connected component,
    because a pedestrian network can contain a genuinely one-way link.
    The component is cached because recomputing it on a 50k-node city graph
    costs more than the rest of a short route request.
    """
    cached = graph.graph.get("_pathable_routable_nodes")
    if isinstance(cached, frozenset):
        return cached
    if graph.number_of_nodes() == 0:
        nodes: frozenset[Node] = frozenset()
    else:
        components: Iterator[set[Node]] = nx.weakly_connected_components(graph)
        largest: set[Node] = set()
        for component in components:
            if len(component) > len(largest):
                largest = component
        nodes = frozenset(largest)
    graph.graph["_pathable_routable_nodes"] = nodes
    return nodes


class SnapTooFarError(Exception):
    def __init__(self, node: Node, distance_m: float, limit_m: float) -> None:
        self.node = node
        self.distance_m = distance_m
        self.limit_m = limit_m
        super().__init__(
            f"nearest node on the connected pedestrian network is "
            f"{distance_m:.0f} m away (limit {limit_m:.0f} m)"
        )
