import sys

import aiohttp
import attr
from PIL import Image
import aioredis
import numpy as np

from . import danbooru

exclude_tags = [
    "loli",
    "bestiality",
    "guro",
    "shadman"
]

def construct_hash_idx_key(idx, val):
    return 'hash_idx:{:02d}:{:02x}'.format(idx, val).encode('utf-8')

async def index_post(redis, http_sess, post):
    if post.url is None:
        raise ValueError("Post has no file URL!")
        
    img = await post.fetch(http_sess)
    h = danbooru.combined_hash(img)
    h_bytes = h.tobytes()
    img.close()
        
    ex = await redis.get(b'hash:'+h_bytes+b':id')
    if ex is not None:
        return False, ex
        
    tr = redis.multi_exec()
    tr.set(b'hash:'+h_bytes+b':id', post.id)
    tr.set(b'hash:'+h_bytes+b':src', 'danbooru')
    
    for idx, val in enumerate(h_bytes):
        tr.sadd(construct_hash_idx_key(idx, val), h_bytes)
        
    if len(post.characters) > 0:
        tr.sadd(b'hash:'+h_bytes+b':characters', *post.characters)
        for character in post.characters:
            b_char = character.encode('utf-8')
            tr.sadd(b'character:'+b_char, h_bytes)
        
    res = await tr.execute()
    return True, post.id
    
async def search_index(redis, imhash):
    h_bytes = imhash.tobytes()
    
    keys = []
    for idx, val in enumerate(h_bytes):
        keys.append(construct_hash_idx_key(idx, val))
    
    hashes = await redis.sunion(*keys)
    _t = []
    
    for h in hashes:
        arr = np.frombuffer(h, dtype=np.uint8)
        dist = danbooru.hamming_dist(arr, imhash)
        _t.append((h, dist))
        
    return sorted(_t, key=lambda o: o[1])

async def get_by_imhash(redis, h_bytes):
    post_id = await redis.get(b'hash:'+h_bytes+b':id')
    
    if post_id is not None:
        post_id = post_id.decode('utf-8')
        async with aiohttp.ClientSession() as sess:
            return await danbooru.DanbooruPost.get_post(sess, post_id)
