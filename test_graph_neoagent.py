# File: test_graph_neoagent.py
# Directory: .
# Purpose: # Purpose: Provides unit tests for the Neo4j graph database interactions within the NeoAgent service.
#
# Upstream:
#   - ENV: —
#   - Imports: asyncio, services.neo4j_driver
#
# Downstream:
#   - —
#
# Contents:
#   - test()







# file: test_graph.py
from services.neo4j_driver import execute_read

import asyncio

async def test():
    result = await execute_read("RETURN 1 AS ok")
    print(result)

asyncio.run(test())
