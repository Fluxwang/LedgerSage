from __future__ import annotations

import requests

TIMEOUT = 30


class EmbeddingClient:
    def __init__(self, settings):
        self.settings = settings

    def embed(self, texts: list[str]):
        config = self.settings.embedding
        payload = {
            "model": config.model,
            "input": texts,
            # 返回的向量用浮点数表示
            "encoding_format": "float",
        }
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {config.api_key}",
        }

        response = requests.post(
            config.api_url, json=payload, headers=headers, timeout=TIMEOUT
        )

        response.raise_for_status()
        data = response.json()
        if data.get("code"):
            raise ValueError("Error occurred during embedding: " + data["message"])
            # raise ValueError(data)
        return data["data"], data["usage"]["total_tokens"]
