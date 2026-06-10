import hashlib

from loguru import logger
from openai import AsyncAzureOpenAI

from app.core.settings import settings


async def get_embedding(text: str, redis=None) -> list[float]:
    cache_key = f"embed:{hashlib.sha256(text.encode()).hexdigest()[:16]}"

    if redis:
        cached = await redis.get(cache_key)
        if cached:
            import json
            return json.loads(cached)

    client = AsyncAzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint or "",
        api_version=settings.azure_openai_api_version,
    )
    response = await client.embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=text,
    )
    vector = response.data[0].embedding
    logger.debug("embedding generated dim={}", len(vector))

    if redis:
        import json
        await redis.setex(cache_key, 3600, json.dumps(vector))

    return vector
