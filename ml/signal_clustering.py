import asyncio
import logging
import math
import random
from typing import Dict, List, Optional

from analytics.history_store import HistoryStore
from state.models import ClusterState, SignalCluster

log = logging.getLogger("ml.signal_clustering")


def _euclidean(a: List[float], b: List[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _vectorize(features: Dict[str, float], order: List[str]) -> List[float]:
    return [float(features.get(k, 0.0)) for k in order]


class SignalClusterer:
    def __init__(self, cfg, redis):
        self.cfg = cfg
        self.redis = redis
        self.feature_order: List[str] = []
        self.centroids: List[List[float]] = []

    async def training_loop(self, history: HistoryStore):
        if not self.cfg.clustering.enabled:
            return
        interval = self.cfg.clustering.update_interval_sec
        while True:
            try:
                await self.recompute(history)
            except Exception as exc:
                log.error("Clustering error: %s", exc)
            await asyncio.sleep(interval)

    async def recompute(self, history: HistoryStore):
        raw = await history.recent_features(self.cfg.clustering.history_window)
        feature_list = [item.get("features") or {} for item in raw if item.get("features")]
        if not feature_list:
            return

        self.feature_order = sorted(feature_list[0].keys())
        vectors = [_vectorize(f, self.feature_order) for f in feature_list]
        k = min(self.cfg.clustering.k, len(vectors))
        self.centroids = random.sample(vectors, k)

        for _ in range(5):
            assignments = [[] for _ in range(k)]
            for vec in vectors:
                idx = self._closest(vec)
                assignments[idx].append(vec)
            new_centroids = []
            for group in assignments:
                if not group:
                    new_centroids.append(random.choice(vectors))
                else:
                    means = [sum(values) / len(values) for values in zip(*group)]
                    new_centroids.append(means)
            self.centroids = new_centroids

        clusters = []
        for idx, centroid in enumerate(self.centroids):
            clusters.append(
                SignalCluster(
                    cluster_id=idx,
                    size=len([v for v in vectors if self._closest(v) == idx]),
                    centroid={k: v for k, v in zip(self.feature_order, centroid)},
                )
            )

        await self.redis.set_cluster_state(ClusterState(clusters=clusters))

    def _closest(self, vec: List[float]) -> int:
        distances = [_euclidean(vec, c) for c in self.centroids]
        return distances.index(min(distances)) if distances else 0

    def predict(self, features: Dict[str, float]) -> Optional[int]:
        if not self.centroids or not self.feature_order:
            return None
        vec = _vectorize(features, self.feature_order)
        return self._closest(vec)
