import asyncio
import sys
import time

import traceback
import aiohttp
import aioredis
from waifustream import danbooru, index
from waifustream.index import IndexEntry

task_sem = asyncio.Semaphore(value=10)
n_complete = 0

async def index_one(redis, sess, post):
    global task_sem, n_complete
    
    if post.url is None:
        return 0
    
    async with task_sem:
        t1 = time.perf_counter()
        
        img = await post.fetch(sess)
        t2 = time.perf_counter()
        
        imhash = danbooru.combined_hash(img)
        t3 = time.perf_counter()
        
        img.close()
        entry = IndexEntry.from_danbooru_post(imhash, post)
        inserted, as_id = await entry.add_to_index(redis)
        t4 = time.perf_counter()
        
        total_time = t4 - t1
        fetch_time = t2 - t1
        hash_time = t3 - t2
        index_time = t4 - t3
        
        n_complete += 1
        
        if inserted:
            print("Indexed post {} (#{}) - times: {:.4f} / {:.4f} / {:.4f} (total {:.4f} seconds)".format(post.id, n_complete, fetch_time, hash_time, index_time, total_time))
            return 1
        else:
            print("Post {} already in index as post {} (#{}) - times: {:.4f} / {:.4f} / {:.4f} (total {:.4f} seconds)".format(post.id, as_id, n_complete, fetch_time, hash_time, index_time, total_time))
            return 0
    
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
