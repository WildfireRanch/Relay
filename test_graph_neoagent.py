# file: test_graph.py
from services.neo4j_driver import execute_read

import asyncio

async def test():
    result = await execute_read("RETURN 1 AS ok")
    print(result)

asyncio.run(test())
