import asyncio
import sys
import time

import aiohttp
import aioredis
from waifustream import danbooru, index

async def main():
    post_id = sys.argv[1]
    
    redis = await aioredis.create_redis('redis://localhost')
    
    async with aiohttp.ClientSession() as sess:
        t1 = time.perf_counter()
        post = await danbooru.DanbooruPost.get_post(sess, post_id)
        t2 = time.perf_counter()
        
        print("Retrieved metadata in {:.4f} seconds".format(t2-t1))
        
        t1 = time.perf_counter()
        await index.index_post(redis, sess, post)
        t2 = time.perf_counter()
        
        print("Indexed post {} in {:.4f} seconds".format(post.id, t2-t1))
    

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
