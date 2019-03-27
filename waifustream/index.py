import asyncio
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

@attr.s(frozen=True)
class IndexEntry(object):
    def _cvt_imhash(h):
        if isinstance(h, np.ndarray):
            return h.tobytes()
        else:
            return bytes(h)
    
    imhash: bytes = attr.ib(converter=_cvt_imhash)
    src: str = attr.ib(converter=str)
    src_id: str = attr.ib(converter=str)
    src_url: str = attr.ib(converter=str)
    characters: tuple = attr.ib(converter=tuple)
    rating: str = attr.ib(converter=str)
    
    @property
    def imhash_array(self):
        return np.frombuffer(imhash, dtype=np.uint8)
    
    @classmethod
    def from_danbooru_post(cls, imhash, post):
        return cls(
            imhash=imhash,
            src_id=post.id,
            src_url=post.url,
            src='danbooru',
            characters=post.characters,
            rating=post.rating
        )
    
    @classmethod
    async def load_from_index(cls, redis, imhash):
        imhash = cls._cvt_imhash(imhash)
        
        ex = await redis.exists(b'hash:'+imhash+b':src')
        if not ex:
            raise KeyError("Image with hash "+imhash.hex()+" not found in index")
        
        src, src_id, src_url, rating, characters = await asyncio.gather(
            redis.get(b'hash:'+imhash+b':src'),
            redis.get(b'hash:'+imhash+b':src_id'),
            redis.get(b'hash:'+imhash+b':src_url'),
            redis.get(b'hash:'+imhash+b':rating'),
            redis.smembers(b'hash:'+imhash+b':characters')
        )
        
        return cls(
            imhash=imhash,
            src=src.decode('utf-8'),
            src_id=src_id.decode('utf-8'),
            src_url=src_url.decode('utf-8'),
            characters=map(lambda c: c.decode('utf-8'), characters),
            rating=rating.decode('utf-8')
        )
    
    async def add_to_index(self, redis):
        ex = await redis.get(b'hash:'+self.imhash+b':src_id')
        if ex is not None:
            return False, ex
        
        tr = redis.multi_exec()
        tr.set(b'hash:'+self.imhash+b':src', self.src)
        tr.set(b'hash:'+self.imhash+b':src_id', self.src_id)
        tr.set(b'hash:'+self.imhash+b':src_url', self.src_url)
        tr.set(b'hash:'+self.imhash+b':rating', self.rating)
        
        for idx, val in enumerate(self.imhash):
            tr.sadd(construct_hash_idx_key(idx, val), self.imhash)
            
        if len(self.characters) > 0:
            tr.sadd(b'hash:'+self.imhash+b':characters', *self.characters)
            for character in self.characters:
                b_char = character.encode('utf-8')
                tr.sadd(b'character:'+b_char, self.imhash)
            
        res = await tr.execute()
        return True, self.src_id

async def search_index(redis, imhash, min_threshold=64):
    h_bytes = imhash.tobytes()
    
    keys = []
    for idx, val in enumerate(h_bytes):
        keys.append(construct_hash_idx_key(idx, val))
    
    hashes = await redis.sunion(*keys)
    _t = []
    
    for h in hashes:
        arr = np.frombuffer(h, dtype=np.uint8)
        dist = danbooru.hamming_dist(arr, imhash)
        
        if dist < min_threshold:
            _t.append((h, dist))
        
    return sorted(_t, key=lambda o: o[1])
