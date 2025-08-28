from llama_index.core import load_index_from_storage, StorageContext
from llama_index.embeddings.openai import OpenAIEmbedding

INDEX_DIR = "./data/index"
_embed_model = OpenAIEmbedding(model="text-embedding-3-large")

try:
    storage_context = StorageContext.from_defaults(persist_dir=INDEX_DIR)
    _index = load_index_from_storage(storage_context=storage_context, embed_model=_embed_model)
    print("LlamaIndex loaded successfully!")
    results = _index.query("hello world", top_k=2)
    for r in results:
        print(r.text)
except Exception as e:
    import traceback
    print("LlamaIndex FAILED to load or query:")
    traceback.print_exc()
