import asyncio
import sys
import time

import traceback
import aioredis
from waifustream import index


async def main():
    redis = await aioredis.create_redis('redis://localhost')
    tag = await index.resolve_tag(sys.argv[1])
    
    if tag is None:
        print("No known tags for tag: "+sys.argv[1])
        return
    
    print("Adding tag: "+tag)
    await index.add_indexed_character(redis, tag)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
