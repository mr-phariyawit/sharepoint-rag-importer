
import asyncio
from app.processing.embedder import TextEmbedder
from app.config import settings

async def test():
    print(f"Testing embedder with model: {settings.EMBEDDING_MODEL}")
    embedder = TextEmbedder()
    try:
        res = await embedder.embed_text("Hello world")
        print(f"Success! Vector length: {len(res)}")
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
