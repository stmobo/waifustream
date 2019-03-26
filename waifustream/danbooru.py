import asyncio
from pathlib import Path
from io import BytesIO

import aiohttp
import attr
from PIL import Image

base_url = 'https://danbooru.donmai.us'

@attr.s(frozen=True, cmp=False)
class DanbooruPost(object):
    id: int = attr.ib(converter=int)
    rating: str = attr.ib()
    tags: tuple = attr.ib(converter=tuple)
    url: str = attr.ib()
    characters: tuple = attr.ib(converter=tuple))
    
    imhash = attr.ib(default=None)
    indexed = attr.ib(default=False)
    
    def __len__(self):
        return len(self.tags)
    
    def tagged(self, tag):
        if tag == self.rating or tag in self.tags:
            return True
        return False
    
    def __getitem__(self, tag):
        return self.tagged(tag)
        
    def __iter__(self):
        return self.tags.__iter__()
        
    def __contains__(self, tag):
        return tag in self.tags
    
    def __eq__(self, rhs):
        if isinstance(rhs, DanbooruPost):
            return self.id == rhs.id
        elif isinstance(rhs, int):
            return self.id == rhs
        else:
            return NotImplemented
            
    def __hash__(self):
        return hash(self.id)
    
    async def fetch_bytesio(self, sess):
        bio = io.BytesIO()
        async with sess.get(self.url) as resp:
            while True:
                chunk = resp.content.read(8*1024)
                if not chunk:
                    break
                bio.write(chunk)
                
        bio.seek(0)
        return bio
    
    async def fetch(self, sess):
        with io.BytesIO() as bio:
            async with sess.get(self.url) as resp:
                while True:
                    chunk = resp.content.read(8*1024)
                    if not chunk:
                        break
                    bio.write(chunk)
                    
            bio.seek(0)
            return Image.open(bio)
            
    @classmethod
    def from_api_json(cls, data):
        tags = data['tag_string'].split()
        characters = data['tag_string_character'].split()
        
        return cls(
            id=data['id'],
            rating=data['rating'],
            tags=tags,
            url=data.get('large_file_url', data['file_url']),
            characters=characters
        )
    
    @classmethod
    async def get_post(cls, session, post_id):
        async with session.get(base_url+'/posts/{}.json'.format(post_id)) as resp:
            data = await resp.json()
            return cls.from_api_json(data)

async def api_random(session, tags):
    if len(tags) > 2:
        raise ValueError("Cannot search for more than two tags at a time")
    
    tags = map(lambda s: str(s).lower().strip(), tags)
    async with session.get(base_url+'/posts.json?tags={}&random=true'.format('%20'.join(tags))) as response:
        data = await response.json()
        return list(DanbooruPost.from_api_json(d) for d in data)

async def search_api(session, tags):
    if len(tags) > 2:
        raise ValueError("Cannot search for more than two tags at a time")
    
    page = 0
    while True:
        endpoint = '/posts.json?page={}&limit=200'.format(tags, page)
        
        if len(tags) > 0:
            endpoint += '&tags={}'.format('%20'.join(map(lambda s: str(s).lower().strip(), tags)))
        
        async with session.get(base_url+endpoint) as response:
            if response.status < 200 or response.status > 299:
                return
            
            data = await response.json()
            if len(data) == 0:
                return
                
            for d in data:
                yield DanbooruPost.from_api_json(d)
                
        page += 1
        
async def search(session, with_tags, without_tags, rating=None):
    async for post in search_api(session, with_tags[:2]):
        if not all((tag in post) for tag in with_tags):
            continue
        
        if any((tag in post) for tag in without_tags):
            continue
        
        if rating is not None and post.rating != rating:
            continue
        
        yield post
        
def imhash(img):
    h = imagehash.dhash(img)
    arr = np.packbits(np.where(h.hash.flatten(), 1, 0))
    
    return arr

def hamming_dist(h1, h2):
    return np.count_nonzero(np.unpackbits(np.bitwise_xor(h1, h2)))
