import asyncio
import io
import sys

import aiohttp
import aioredis
import attr
from PIL import Image
import imagehash
import numpy as np

"""Posts with these tags will be excluded from indexing.
"""
exclude_tags = [
    "loli",
    "shota",
    "bestiality",
    "guro",
    "shadman"
]

"""A helper dictionary to convert from single-character ratings to more human-friendly names.
"""
friendly_ratings = {
    's': 'Safe',
    'q': 'Questionable',
    'e': 'Explicit'
}

def construct_hash_idx_key(idx, val):
    return 'hash_idx:{:02d}:{:02x}'.format(idx, val).encode('utf-8')

@attr.s(frozen=True)
class IndexEntry(object):
    def _cvt_imhash(h):
        if isinstance(h, np.ndarray):
            return h.tobytes()
        elif h is None:
            return None
        else:
            return bytes(h)
    
    imhash: bytes = attr.ib(converter=_cvt_imhash)
    src: str = attr.ib(converter=str)
    src_id: str = attr.ib(converter=str)
    src_url: str = attr.ib(converter=str)
    characters: tuple = attr.ib(converter=tuple)
    rating: str = attr.ib(converter=str)
    
    async def fetch_bytesio(self, http_sess):
        """Download the source image for this entry.
        
        Returns:
            A `BytesIO` containing the raw image file data.
        """
        
        bio = io.BytesIO()
        async with http_sess.get(self.src_url) as resp:
            while True:
                chunk = await resp.content.read(8*1024)
                if not chunk:
                    break
                bio.write(chunk)
                
        bio.seek(0)
        return bio
    
    async def fetch(self, http_sess):
        """Fetch and open the source image for this entry.
        
        Returns:
            An Image.
        """
        
        bio = await self.fetch_bytesio(http_sess)
        img = Image.open(bio)
        img.load()
        
        return img
    
    @property
    def imhash_array(self):
        """ndarray: The image hash for this entry, as a uint8 `ndarray`.
        """
        return np.frombuffer(self.imhash, dtype=np.uint8)
    
    @classmethod
    def from_danbooru_post(cls, imhash, post):
        """Create an IndexEntry from an image hash and a DanbooruPost.
        
        Args:
            imhash (bytes or ndarray): An image hash for this entry.
            post (DanbooruPost): A DanbooruPost to create this entry from.
        
        Returns:
            An IndexEntry.
        """
        
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
        """Load the entry for a given image hash from the index.
        
        Args:
            redis (aioredis.Redis): A Redis instance.
            imhash (bytes or ndarray): An image hash to lookup.
            
        Raises:
            KeyError: If the given image hash is not in the index.
        
        Returns:
            An IndexEntry.
        """
        
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
        """Add this entry to the index.
        
        Args:
            redis (aioredis.Redis): A Redis instance.
            
        Returns:
            bool: True if the entry was added, False if it already exists.
        """
        
        await redis.sadd('indexed:'+self.src, self.src_id)
        
        ex = await redis.get(b'hash:'+self.imhash+b':src_id')
        if ex is not None:
            return False
        
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
        return True

async def search_index(redis, imhash, min_threshold=64):
    """Search the index for images with nearby hashes.
    
    Args:
        redis (aioredis.Redis): A Redis interface.
        imhash (ndarray): An image hash to look up. Must be of type `uint8`.
        min_threshold (int): A minimum distance threshold for filtering results.
            The result list will only contain images with a result less than
            this value.
            
    Returns:
        A list of (hash, distance) tuples, sorted by increasing distance.
    """
    
    h_bytes = imhash.tobytes()
    
    keys = []
    for idx, val in enumerate(h_bytes):
        keys.append(construct_hash_idx_key(idx, val))
    
    hashes = await redis.sunion(*keys)
    _t = []
    
    for h in hashes:
        arr = np.frombuffer(h, dtype=np.uint8)
        dist = hamming_dist(arr, imhash)
        
        if dist < min_threshold:
            _t.append((h, dist))
        
    return sorted(_t, key=lambda o: o[1])
    
async def get_indexed_tags(redis):
    """Get all tags monitored for indexing.
    
    Args:
        redis (aioredis.Redis): a Redis interface.
        
    Returns:
        A list of monitored tags as `str` objects.
    """
    
    return await redis.lrange('indexed_tags', 0, -1, encoding='utf-8')
    
async def add_indexed_tag(redis, tag):
    """Add a new tag to be monitored for indexing.
    
    Args:
        redis (aioredis.Redis): A Redis interface.
        tag (str or bytes): The tag to monitor.

    Returns:
        The total number of indexed tags (incl. the added tag).
    """
    
    return await redis.lpush('indexed_tags', tag)
    
async def get_tag_queue_length(redis, tag):
    """Get the current fetch queue length for a given indexed tag.
    
    Args:
        redis (aioredis.Redis): A Redis interface.
        tag (str or bytes): The indexed tag to inspect.
        
    Returns:
        The total number of images awaiting indexing for the tag.
    """
    
    return await redis.llen('index_queue:'+tag)
    
def diff_hash(img):
    """Compute the difference hash of an image.
    
    Returns:
        A `uint8` ndarray.
    """
    
    h = imagehash.dhash(img)
    arr = np.packbits(np.where(h.hash.flatten(), 1, 0))
    
    return arr

def avg_hash(img):
    """Compute the average hash of an image.
    
    Returns:
        A `uint8` ndarray.
    """
    
    h = imagehash.average_hash(img)
    arr = np.packbits(np.where(h.hash.flatten(), 1, 0))
    
    return arr

def combined_hash(img):
    """Compute a combined perceptual hash for an image.
    
    Currently, this is just the concatenation of the dHash and the avgHash.
    
    Returns:
        A `uint8` ndarray.
    """
    
    h1 = imagehash.dhash(img)
    h1 = np.packbits(np.where(h1.hash.flatten(), 1, 0))
    
    h2 = imagehash.average_hash(img)
    h2 = np.packbits(np.where(h2.hash.flatten(), 1, 0))
    
    return np.concatenate((h1, h2))

def hamming_dist(h1, h2):
    """Compute the Hamming distance between two uint8 arrays.
    """
    
    return np.count_nonzero(np.unpackbits(np.bitwise_xor(h1, h2)))
