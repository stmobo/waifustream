import asyncio
import sys
import time

import traceback
import aioredis
from waifustream import index


async def main():
    redis = await aioredis.create_redis('redis://localhost')
    
    characters = await index.get_indexed_characters(redis)
    for character in characters:
        q_len = await index.get_tag_queue_length(redis, character)
        n_indexed = await redis.scard('character:'+character)
        
        print("{}: {} items queued, {} items indexed".format(character, q_len, n_indexed))

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
