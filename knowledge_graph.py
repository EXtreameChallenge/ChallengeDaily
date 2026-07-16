"""
P221-P229: 知识图谱引擎
- P221: 图节点管理
- P222: 边关系管理
- P223: 图遍历算法
- P224: 最短路径
- P225: 社区发现
- P226: 图聚类
- P227: 节点中心性
- P228: 知识推理
- P229: 图可视化数据
"""
import logging
import threading
from collections import defaultdict, deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P221: 图节点管理 ──────────────────────────
class GraphNode:
    """图节点"""
    def __init__(self, node_id: str, label: str = "", node_type: str = "",
                 properties: dict = None):
        self.id = node_id
        self.label = label or node_id
        self.type = node_type
        self.properties = properties or {}


class KnowledgeGraph:
    """知识图谱"""
    def __init__(self):
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, list[dict]] = defaultdict(list)  # adjacency
        self._reverse_edges: dict[str, list[dict]] = defaultdict(list)
        self._lock = threading.Lock()

    def add_node(self, node_id: str, label: str = "", node_type: str = "",
                 properties: dict = None) -> None:
        with self._lock:
            self._nodes[node_id] = GraphNode(node_id, label, node_type, properties)

    def add_edge(self, from_id: str, to_id: str, relation: str = "related",
                 weight: float = 1.0, properties: dict = None) -> None:
        with self._lock:
            edge = {"from": from_id, "to": to_id, "relation": relation,
                    "weight": weight, "properties": properties or {}}
            self._edges[from_id].append(edge)
            self._reverse_edges[to_id].append(edge)

    def get_node(self, node_id: str) -> dict | None:
        with self._lock:
            n = self._nodes.get(node_id)
            if not n:
                return None
            return {"id": n.id, "label": n.label, "type": n.type, "properties": n.properties}

    def get_neighbors(self, node_id: str, relation: str = "") -> list[dict]:
        with self._lock:
            edges = self._edges.get(node_id, [])
        if relation:
            edges = [e for e in edges if e["relation"] == relation]
        return [{"id": e["to"], "relation": e["relation"], "weight": e["weight"]}
                for e in edges]

    def remove_node(self, node_id: str) -> None:
        with self._lock:
            self._nodes.pop(node_id, None)
            self._edges.pop(node_id, None)
            for edges in self._edges.values():
                self._edges[node_id] = [e for e in edges if e["to"] != node_id]

    def get_stats(self) -> dict:
        with self._lock:
            total_edges = sum(len(v) for v in self._edges.values())
            return {"nodes": len(self._nodes), "edges": total_edges}

    def search_nodes(self, query: str, node_type: str = "") -> list[dict]:
        with self._lock:
            results = []
            for n in self._nodes.values():
                if query.lower() not in n.label.lower():
                    continue
                if node_type and n.type != node_type:
                    continue
                results.append({"id": n.id, "label": n.label, "type": n.type})
            return results


# ─── P223: 图遍历算法 ──────────────────────────
class GraphTraversal:
    """图遍历算法"""
    @staticmethod
    def bfs(graph: KnowledgeGraph, start: str, max_depth: int = 10) -> list[str]:
        visited = set()
        queue = deque([(start, 0)])
        result = []
        while queue:
            node, depth = queue.popleft()
            if node in visited or depth > max_depth:
                continue
            visited.add(node)
            result.append(node)
            for neighbor in graph.get_neighbors(node):
                if neighbor["id"] not in visited:
                    queue.append((neighbor["id"], depth + 1))
        return result

    @staticmethod
    def dfs(graph: KnowledgeGraph, start: str, max_depth: int = 10) -> list[str]:
        visited = set()
        result = []
        def _dfs(node, depth):
            if node in visited or depth > max_depth:
                return
            visited.add(node)
            result.append(node)
            for neighbor in graph.get_neighbors(node):
                _dfs(neighbor["id"], depth + 1)
        _dfs(start, 0)
        return result


# ─── P224: 最短路径 ──────────────────────────
class ShortestPath:
    """最短路径(Dijkstra)"""
    @staticmethod
    def find(graph: KnowledgeGraph, start: str, end: str) -> dict:
        import heapq
        dist = {start: 0}
        prev = {}
        heap = [(0, start)]
        visited = set()
        while heap:
            d, node = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)
            if node == end:
                path = []
                cur = end
                while cur in prev:
                    path.append(cur)
                    cur = prev[cur]
                path.append(start)
                path.reverse()
                return {"path": path, "distance": d, "hops": len(path) - 1}
            for neighbor in graph.get_neighbors(node):
                nd = d + neighbor.get("weight", 1)
                if nd < dist.get(neighbor["id"], float('inf')):
                    dist[neighbor["id"]] = nd
                    prev[neighbor["id"]] = node
                    heapq.heappush(heap, (nd, neighbor["id"]))
        return {"path": [], "distance": -1, "hops": 0}


# ─── P225: 社区发现 ──────────────────────────
class CommunityDetection:
    """简单社区发现(标签传播)"""
    @staticmethod
    def detect(graph: KnowledgeGraph, max_iter: int = 10) -> dict[str, int]:
        communities = {}
        with graph._lock:
            for node_id in graph._nodes:
                communities[node_id] = hash(node_id) % 1000
        for _ in range(max_iter):
            changed = False
            for node_id in communities:
                neighbors = graph.get_neighbors(node_id)
                if not neighbors:
                    continue
                neighbor_communities = [communities.get(n["id"], communities[node_id]) for n in neighbors]
                from collections import Counter
                most_common = Counter(neighbor_communities).most_common(1)
                if most_common and most_common[0][0] != communities[node_id]:
                    communities[node_id] = most_common[0][0]
                    changed = True
            if not changed:
                break
        return communities


# ─── P226: 图聚类 ──────────────────────────
class GraphCluster:
    """图聚类"""
    @staticmethod
    def by_degree(graph: KnowledgeGraph, n_clusters: int = 3) -> dict[str, int]:
        degrees = {}
        for node_id in graph._nodes:
            degrees[node_id] = len(graph.get_neighbors(node_id))
        if not degrees:
            return {}
        sorted_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)
        cluster_size = len(sorted_nodes) // n_clusters or 1
        clusters = {}
        for i, (node, _) in enumerate(sorted_nodes):
            clusters[node] = i // cluster_size
        return clusters


# ─── P227: 节点中心性 ──────────────────────────
class Centrality:
    """节点中心性计算"""
    @staticmethod
    def degree_centrality(graph: KnowledgeGraph) -> dict[str, float]:
        max_degree = 1
        degrees = {}
        for node_id in graph._nodes:
            d = len(graph.get_neighbors(node_id))
            degrees[node_id] = d
            max_degree = max(max_degree, d)
        return {k: v / max_degree for k, v in degrees.items()}

    @staticmethod
    def betweenness_centrality(graph: KnowledgeGraph, sample_size: int = 50) -> dict[str, float]:
        nodes = list(graph._nodes.keys())[:sample_size]
        centrality = {n: 0.0 for n in graph._nodes}
        for start in nodes:
            for end in nodes:
                if start == end:
                    continue
                path_result = ShortestPath.find(graph, start, end)
                path = path_result.get("path", [])
                for node in path[1:-1]:
                    centrality[node] = centrality.get(node, 0) + 1
        total = max(1, len(nodes) * (len(nodes) - 1))
        return {k: v / total for k, v in centrality.items()}


# ─── P228: 知识推理 ──────────────────────────
class KnowledgeReasoning:
    """简单知识推理"""
    @staticmethod
    def infer_relations(graph: KnowledgeGraph, node_id: str, max_depth: int = 2) -> list[dict]:
        """推断间接关系"""
        inferred = []
        visited = {node_id}
        queue = deque([(node_id, 0, [])])
        while queue:
            current, depth, path = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor in graph.get_neighbors(current):
                if neighbor["id"] in visited:
                    continue
                visited.add(neighbor["id"])
                new_path = path + [neighbor["relation"]]
                if depth > 0:
                    inferred.append({
                        "from": node_id, "to": neighbor["id"],
                        "path": new_path, "depth": depth + 1,
                        "relation": " → ".join(new_path)
                    })
                queue.append((neighbor["id"], depth + 1, new_path))
        return inferred


# ─── P229: 图可视化数据 ──────────────────────────
class GraphVisualizer:
    """生成图可视化数据"""
    @staticmethod
    def to_vis_data(graph: KnowledgeGraph, limit: int = 100) -> dict:
        with graph._lock:
            nodes = []
            for i, (nid, n) in enumerate(graph._nodes.items()):
                if i >= limit:
                    break
                nodes.append({"id": nid, "label": n.label, "group": n.type or "default"})
            edges = []
            for from_id, edge_list in graph._edges.items():
                for e in edge_list[:5]:
                    edges.append({"from": from_id, "to": e["to"],
                                  "label": e["relation"], "value": e["weight"]})
                    if len(edges) >= limit * 2:
                        break
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def to_adjacency_matrix(graph: KnowledgeGraph, limit: int = 20) -> dict:
        with graph._lock:
            node_ids = list(graph._nodes.keys())[:limit]
        n = len(node_ids)
        id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
        matrix = [[0] * n for _ in range(n)]
        for from_id in node_ids:
            for neighbor in graph.get_neighbors(from_id):
                if neighbor["id"] in id_to_idx:
                    matrix[id_to_idx[from_id]][id_to_idx[neighbor["id"]]] = neighbor.get("weight", 1)
        return {"nodes": node_ids, "matrix": matrix}


_graph = KnowledgeGraph()
_traversal = GraphTraversal()
_path_finder = ShortestPath()
_community = CommunityDetection()
_cluster = GraphCluster()
_centrality = Centrality()
_reasoning = KnowledgeReasoning()
_visualizer = GraphVisualizer()
