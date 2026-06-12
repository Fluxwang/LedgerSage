from __future__ import annotations


# ImportError会在模块文件不存在、依赖库没安装、包结构有问题的情况下触发
def create_vector_store(settings):
    try:
        from beanbot.gateways.vector_store.sqlite_store import SqliteVectorStore
    except ImportError:
        from beanbot.gateways.vector_store.json_store import JsonVectorStore

        return JsonVectorStore(settings)
    return SqliteVectorStore(settings)
