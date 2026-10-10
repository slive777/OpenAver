"""自訂來源檢視：把已載入的來源（含載入失敗者）合成 SourceConfig；狀態推導只在此做一次。"""
from dataclasses import dataclass

from core.custom_source import gate, registry, state
from core.custom_source.registry import LoadedSource
from core.source_config import SourceConfig

ORDER_BASE = 1000


@dataclass(frozen=True)
class CustomSourceView:
    config: SourceConfig
    status: str
    routable: bool
    loaded: LoadedSource


def custom_source_views():
    entries = state.read_all()
    running_id = state.get_running_id()
    views = []
    for idx, loaded in enumerate(registry.load_all()):
        entry = entries.get(loaded.id)
        status, result = gate.judge(loaded, entry, running_id)
        config = SourceConfig(
            id=f"custom:{loaded.id}",
            type="custom",
            display_name_raw=loaded.spec.name if loaded.spec is not None else loaded.id,
            enabled=state.effective_enabled(entry, status),
            order=ORDER_BASE + idx,
            manual_only=True,
            is_beta=False,
            requires_proxy=False,
            config={"censored_type": "censored"},
        )
        views.append(CustomSourceView(config, status, result.ok, loaded))
    return views


def custom_source_configs():
    return [v.config for v in custom_source_views()]


def routable_hosts():
    """可路由（驗收通過＋已啟用＋sha 相符）自訂來源宣告的基底 host；每次即時計算。"""
    return tuple(h for v in custom_source_views() if v.routable for h in v.loaded.spec.hosts)
