import asyncio
import sys
import time

import traceback
import aiohttp
import aioredis
from waifustream import danbooru, index

task_sem = asyncio.Semaphore(value=10)
n_complete = 0

async def index_one(redis, sess, post):
    global task_sem, n_complete
    
    if post.url is None:
        return 0
    
    async with task_sem:
        try:
            t1 = time.perf_counter()
            inserted, as_id = await index.index_post(redis, sess, post)
            t2 = time.perf_counter()
            
            n_complete += 1
            
            if inserted:
                print("Indexed post {} in {:.4f} seconds (n={})".format(post.id, t2-t1, n_complete))
                return 1
            else:
                print("Post {} already in index as post {} ({:.4f} seconds for query, n={})".format(post.id, as_id, t2-t1, n_complete))
                return 0
        except Exception as e:
            traceback.print_exc()
    
    return 0

async def main():
    character = sys.argv[1]
    
    futs = []
    
    t_start = time.perf_counter()
    
    redis = await aioredis.create_redis('redis://localhost')
    async with aiohttp.ClientSession() as sess:
        async for post in danbooru.search(sess, [character], index.exclude_tags):
            futs.append(asyncio.ensure_future(index_one(redis, sess, post)))
    
        print("=== waiting for {} tasks to return ===".format(len(futs)))
        res = await asyncio.gather(*futs)
    
    t_end = time.perf_counter()
    
    n_success = sum(res)
    n_total = len(res)
    
    print("Indexed {} / {} images in {:.4f} seconds".format(n_success, n_total, t_end - t_start))

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
