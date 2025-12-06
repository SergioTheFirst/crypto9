import asyncio
import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("ml.signal_filter")

from analytics.features import label_from_profit
from analytics.history_store import HistoryStore
from state.redis_state import RedisState


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class SimpleLogisticModel:
    def __init__(self):
        self.weights: Dict[str, float] = {}
        self.bias: float = 0.0
        self.feature_order: List[str] = []

    def _vectorize(self, features: Dict[str, float]) -> List[float]:
        if not self.feature_order:
            self.feature_order = sorted(features.keys())
        return [float(features.get(k, 0.0)) for k in self.feature_order]

    def fit(self, samples: List[Tuple[Dict[str, float], int]], lr: float = 0.01, epochs: int = 30):
        if not samples:
            return

        for _ in range(epochs):
            for feats, label in samples:
                vec = self._vectorize(feats)
                score = self.bias + sum(self.weights.get(k, 0.0) * v for k, v in zip(self.feature_order, vec))
                prob = _sigmoid(score)

                # Gradient descent step
                error = label - prob
                self.bias += lr * error
                for k, v in zip(self.feature_order, vec):
                    self.weights[k] = self.weights.get(k, 0.0) + lr * error * v

    def predict_proba(self, features: Dict[str, float]) -> float:
        vec = self._vectorize(features)
        score = self.bias + sum(self.weights.get(k, 0.0) * v for k, v in zip(self.feature_order, vec))
        return _sigmoid(score)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "weights": self.weights,
            "bias": self.bias,
            "feature_order": self.feature_order,
        }

    def load_snapshot(self, snap: Dict[str, Any]):
        self.weights = snap.get("weights", {})
        self.bias = snap.get("bias", 0.0)
        self.feature_order = snap.get("feature_order", [])


class SignalFilter:
    def __init__(self, cfg, redis: RedisState):
        self.cfg = cfg
        self.redis = redis
        self.model = SimpleLogisticModel()
        self._last_error_logged = False
        self._store_key = "state:ml:signal_filter"

    async def training_loop(self, history: HistoryStore):
        if not self.cfg.ml.enable: 
            return
        
        interval = self.cfg.ml.update_interval_sec
        log.info("Signal filter training loop started")

        while True:
            try:
                await self.re_train(history)
            except Exception as exc:
                log.error("Signal filter training error: %s", exc)
            
            await asyncio.sleep(interval)
            
    async def re_train(self, history: HistoryStore):
        raw_features = await history.recent_features(self.cfg.ml.history_window)
        samples = []

        if not raw_features:
            log.debug("No historical features found, skipping training")
            pass
        else:
            for item in raw_features:
                feats = item.get("features") or {}
                label = item.get("label")
                if feats and label is not None:
                    samples.append((feats, int(label)))

        if not samples:
            log.debug("Signal filter skipped training due to empty samples")
            return

        self.model = SimpleLogisticModel()
        self.model.fit(samples)
        await self.redis.client.set(
            "state:ml:signal_filter", json.dumps(self.model.snapshot())
        )
        log.debug("Signal filter trained on %d samples", len(samples))

    async def score(self, features: Dict[str, float]) -> Optional[float]:
        if not self.cfg.ml.enable:
            return None
        try:
            if not self.model.weights:
                snap_raw = await self.redis.client.get("state:ml:signal_filter")
                if isinstance(snap_raw, str):
                    try:
                        snap = json.loads(snap_raw)
                        self.model.load_snapshot(snap)
                    except Exception:
                        pass
            return self.model.predict_proba(features)
        except Exception as exc:
            if not self._last_error_logged:
                log.error("Signal filter inference failed: %s", exc)
                self._last_error_logged = True
            return None