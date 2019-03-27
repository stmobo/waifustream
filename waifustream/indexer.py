import asyncio
import ujson as json
import multiprocessing as mp
import sys
import time
import traceback

import attr
import aiohttp
import aioredis
from waifustream import danbooru, index
from waifustream.index import IndexEntry

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    config = json.load(f)
    
    MIN_DOWNLOAD_DELAY = config['min_download_delay']
    REDIS_URL = config['redis_url']
    INDEXER_UA = config['indexer_ua']
    index.exclude_tags = config['exclude_tags']

async def refresh_one_tag(tag, sess, redis):
    print("[refresh] Refreshing tag: "+tag)
    
    cur_head = await redis.lindex('index_queue:'+tag, 0)
    if cur_head is not None:
        head_entry = json.loads(cur_head)
        last_id = head_entry['src_id']
        print("[refresh] starting from ID {} with tag {}".format(last_id, tag))
    else:
        last_id = None
    
    n = 0
    async for post in danbooru.search(sess, [tag], index.exclude_tags, start_id=last_id):
        is_indexed, awaiting_index = await asyncio.gather(
            redis.sismember('indexed:danbooru', str(post.id)),
            redis.sismember('awaiting_index:danbooru', str(post.id))
        )
        
        if is_indexed or awaiting_index:
            continue
        
        entry = IndexEntry.from_danbooru_post(None, post)
        ser = json.dumps(attr.asdict(entry))
        
        await asyncio.gather(
            redis.lpush('index_queue:'+tag, ser),
            redis.sadd('awaiting_index:danbooru', str(post.id))
        )
        
        n += 1
        
    print("[refresh] Enqueued {} items for {}".format(n, tag))

async def refresh_character_worker():
    redis = await aioredis.create_redis(REDIS_URL)
    print("[refresh] Tag refresh worker started.")
    
    while True:
        tags = await redis.lrange('indexed_tags', 0, -1)
        
        async with aiohttp.ClientSession(headers={'User-Agent': INDEXER_UA}) as sess:
            futs = []
            for tag in tags:
                tag = tag.decode('utf-8')
                futs.append(asyncio.ensure_future(refresh_one_tag(tag, sess, redis)))
                
            await asyncio.gather(*futs)
    
        await asyncio.sleep(30*60)


async def fetch_worker():
    redis = await aioredis.create_redis(REDIS_URL)
    print("[fetch] Fetch worker started.")
    
    async with aiohttp.ClientSession(headers={'User-Agent': INDEXER_UA}) as sess:
        while True:
            tags = await redis.lrange('indexed_tags', 0, -1)
            for tag in tags:
                tag = tag.decode('utf-8')
                next_entry = await redis.rpop('index_queue:'+tag)
                
                if next_entry is None:
                    continue
                
                t1 = time.perf_counter()
                
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
                
                t2 = time.perf_counter()
                
                dt = t2 - t1
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
    
