import asyncio
import sys

import aiohttp
import attr
from PIL import Image
import imagehash
import motor.motor_asyncio
import numpy as np

from . import danbooru


fetch_queue = asyncio.Queue()
task_sem = asyncio.Semaphore(value=10)

awaiting_fetch = set()
index_in_progress = set()

exclude_tags = [
    "loli",
    "beastiality",
    "guro",
    "shadman"
]

async def fetch(post, sess, db_conn):
    global task_sem
    
    async with task_sem:
        async with post.fetch(sess) as img:
            hash_arr = danbooru.imhash(img)
            new_post = attr.evolve(post, imhash=tuple(hash_arr))
            index_elem = new_post.asdict()
            
            db = db_conn.waifustream
            await db.images.update_one({'id': post.id}, index_elem, upsert=True)
            
            try:
                awaiting_fetch.remove(post.id)
            except KeyError:
                pass

async def index_character(character, db_conn):
    global awaiting_fetch, index_in_progress
    
    if character in index_in_progress:
        return
    index_in_progress.add(character)
    
    cursor = db_conn.waifustream.images.aggregate([
        {'$match': {
            'characters': character
        }},
        {'$group': {
            '_id': None,
            'ids': {'$addToSet': '$id'}
        }}
    ])
    
    ids = (await cursor.to_list(1))[0]['ids']
    
    async with aiohttp.Session() as sess:
        cur_batch = []
        
        async for post in danbooru.search(sess, [character], exclude_tags):
            if post.id in ids or post.id in awaiting_fetch:
                continue
            
            awaiting_fetch.add(post.id)
            cur_batch.append(post)
            if len(cur_batch) >= 10:
                await asyncio.gather(*(fetch(p, sess, db_conn) for p in cur_batch))
                cur_batch = []
        
        if len(cur_batch) > 0:
            await asyncio.gather(*(fetch(p, sess, db_conn) for p in cur_batch))
    
    try:
        index_in_progress.remove(character)
    except KeyError:
        pass

async def main_loop():
    db_conn = motor.motor_asyncio.AsyncIOMotorClient('localhost', 27017)
    
    while True:
        cursor = db_conn.waifustream.characters.find({})
        async for doc in cursor:
            fut = asyncio.ensure_future(index_character(doc['character'], db_conn))
        
        await asyncio.sleep(300)
        
def main():
    asyncio.run(main_loop())
        
if __name__ == '__main__':
    main()
        
