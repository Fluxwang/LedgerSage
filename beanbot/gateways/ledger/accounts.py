"""账户前缀统一按冒号分段，避免 Food 匹配到 FoodDelivery。"""


def normalize_prefix(prefix: str | None) -> str:
    return (prefix or '').strip().rstrip(':')


def account_matches(account: str, prefix: str | None) -> bool:
    normalized = normalize_prefix(prefix)
    return not normalized or account == normalized or account.startswith(normalized + ':')
