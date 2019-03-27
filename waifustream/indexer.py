import asyncio
import json
import multiprocessing as mp
import sys
import time
import traceback

import attr
import aiohttp
import aioredis
from waifustream import danbooru, index
from waifustream.index import IndexEntry

MIN_DOWNLOAD_DELAY = 2
REDIS_URL = 'redis://localhost'


async def refresh_character_worker():
    redis = await aioredis.create_redis(REDIS_URL)
    print("[refresh] Character refresh worker started.")
    
    while True:
        character = await redis.brpoplpush('indexed_tags', 'indexed_tags')
        character = character.decode('utf-8')
        print("[refresh] Refreshing character: "+character)
        
        n = 0
        async with aiohttp.ClientSession() as sess:
            async for post in danbooru.search(sess, [character], index.exclude_tags):
                is_indexed, awaiting_index = await asyncio.gather(
                    redis.sismember('indexed:danbooru', str(post.id)),
                    redis.sismember('awaiting_index:danbooru', str(post.id))
                )
                
                if is_indexed or awaiting_index:
                    continue
                
                entry = IndexEntry.from_danbooru_post(None, post)
                ser = json.dumps(attr.asdict(entry))
                
                await redis.lpush('index_queue:'+character, ser)
                await redis.sadd('awaiting_index:danbooru', str(post.id))
                n += 1
                
        print("[refresh] Enqueued {} items for {}".format(n, character))
    
        await asyncio.sleep(30)


async def fetch_worker():
    redis = await aioredis.create_redis(REDIS_URL)
    print("[fetch] Fetch worker started.")
    
    async with aiohttp.ClientSession() as sess:
        last_fetch_time = time.perf_counter()
        
        while True:
            characters = await redis.lrange('indexed_tags', 0, -1)
            for character in characters:
                character = character.decode('utf-8')
                next_entry = await redis.rpop('index_queue:'+character)
                
                if next_entry is None:
                    continue
                
                entry_dict = json.loads(next_entry)
                entry = IndexEntry(**entry_dict)
                
                if entry.src_url is None:
                    await redis.sadd('indexed:'+entry.src, entry.src_id)
                    continue
                
                try:
                    img = await entry.fetch(sess)
                    imhash = index.combined_hash(img)
                    img.close()
                    
                    entry = attr.evolve(entry, imhash=imhash)
                    await entry.add_to_index(redis)
                    await redis.srem('awaiting_index:'+entry.src, entry.src_id)
                    
                    print("[fetch] Indexed: {}#{}".format(entry.src, entry.src_id))
                except (OSError, aiohttp.ClientError):
                    traceback.print_exc()
                    await redis.sadd('indexed:'+entry.src, entry.src_id)
                    
                cur_time = time.perf_counter()
                
                dt = cur_time - last_fetch_time
                last_fetch_time = cur_time
                
                if dt < MIN_DOWNLOAD_DELAY:
                    await asyncio.sleep(MIN_DOWNLOAD_DELAY - dt)

def _start_worker(f):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(f())

def start_fetch_worker():
    _start_worker(fetch_worker)

def start_refresh_worker():
    _start_worker(refresh_character_worker)
    
def main():
    targets = [start_refresh_worker]
    workers = []
    
    for tgt in targets:
        p = mp.Process(target=tgt, daemon=True)
        p.start()

        workers.append(p)
    
    start_fetch_worker()
        
if __name__ == '__main__':
    main()
    
