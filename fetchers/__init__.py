from .base import FetchResult, UA, to_roc
from . import uni, capital, nomura, allianz

# 各 issuer module 註冊：etf_id → (module, fund_code)
REGISTRY: dict[str, tuple] = {}
REGISTRY.update(uni.REGISTRY)
REGISTRY.update(capital.REGISTRY)
REGISTRY.update(nomura.REGISTRY)
REGISTRY.update(allianz.REGISTRY)


def fetch(etf_id: str, date):
    if etf_id not in REGISTRY:
        return FetchResult(etf_id=etf_id, date=date, error=f'no fetcher registered for {etf_id}')
    module, fund_code = REGISTRY[etf_id]
    return module.fetch(etf_id, fund_code, date)
