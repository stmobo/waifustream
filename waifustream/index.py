import sys

import aiohttp
import attr
from PIL import Image
import imagehash
import aioredis
import numpy as np

from . import danbooru

exclude_tags = [
    "loli",
    "beastiality",
    "guro",
    "shadman"
]

def construct_hash_idx_key(idx, val):
    return 'hash_idx:{:02d}:{:02x}'.format(idx, val).encode('utf-8')

async def index_post(redis, http_sess, post):
    async with post.fetch(http_sess) as img:
        h = danbooru.imhash(img)
        h_bytes = h.tobytes()
        
    ex = await redis.exists(b'phash:'+h_bytes+b':characters')
    if ex:
        return
        
    tr = redis.multi_exec()
    tr.set(b'phash:'+h_bytes+b':id', post.id)
    tr.set(b'phash':+h_bytes+b':src', 'danbooru')
    
    for idx, val in enumerate(h_bytes):
        tr.sadd(construct_hash_idx_key(idx, val), h_bytes)
        
    if len(post.characters) > 0:
        tr.sadd(b'phash:'+h_bytes+b':characters', *post.characters)
        for character in post.characters:
            b_char = character.encode('utf-8')
            tr.sadd('character:'+b_char, h_bytes)
        
    res = await tr.execute()
    
async def search_index(redis, imhash):
    h_bytes = imhash.tobytes()
    
    keys = []
    for idx, val in enumerate(h_bytes):
        keys.append(construct_hash_idx_key(idx, val))
    
    hashes = await redis.sunion(*keys)
    _t = []
    
    for h in hashes:
        dist = danbooru.hamming_dist(h, imhash)
        _t.append((h, dist))
        
    return sorted(_t, key=lambda o: o[1])

async def get_by_imhash(redis, imhash):
    h_bytes = imhash.tobytes()
    post_id = await redis.get(b'phash:'+h_bytes+b':id')
    
    if post_id is not None:
        async with aiohttp.Session() as sess:
            return await danbooru.DanbooruPost.get_post(sess, post_id)
