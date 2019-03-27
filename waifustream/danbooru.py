import asyncio
from pathlib import Path
import io

import aiohttp
import attr
from PIL import Image
import numpy as np

base_url = 'https://danbooru.donmai.us'

@attr.s(frozen=True, cmp=False)
class DanbooruPost(object):
    id: int = attr.ib(converter=int)
    rating: str = attr.ib()
    tags: tuple = attr.ib(converter=tuple)
    url: str = attr.ib()
    characters: tuple = attr.ib(converter=tuple)
    
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
                chunk = await resp.content.read(8*1024)
                if not chunk:
                    break
                bio.write(chunk)
                
        bio.seek(0)
        return bio
    
    async def fetch(self, sess):
        bio = await self.fetch_bytesio(sess)
        img = Image.open(bio)
        img.load()
        
        return img
            
    @classmethod
    def from_api_json(cls, data):
        tags = data['tag_string'].split()
        characters = data['tag_string_character'].split()
        
        url = None
        if 'file_url' in data:
            url = data['file_url']
        elif 'large_file_url' in data:
            url = data['large_file_url']
        elif 'preview_file_url' in data:
            url = data['preview_file_url']
        
        return cls(
            id=data['id'],
            rating=data['rating'],
            tags=tags,
            url=url,
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

def construct_search_endpoint(page, tags, start_id):
    endpoint = '/posts.json?page={}&limit=200'.format(page)
    tags = list(tags)
    
    if start_id is not None:
        if len(tags) >= 2:
            tags = list(tags[:1])
        
        tags.append('id%3A%3C'+str(start_id))
    
    if len(tags) > 0:
        endpoint += '&tags={}'.format('+'.join(map(lambda s: str(s).lower().strip(), tags)))

    return base_url+endpoint

async def search_api(session, tags, start_id=None):
    if len(tags) > 2:
        raise ValueError("Cannot search for more than two tags at a time")
    
    if start_id is not None:
        start_id = int(start_id)
    
    page = 0
    n_tries = 0
        
    while page < 1000:
        await asyncio.sleep(0.5)
        
        if n_tries > 5:
            print("Giving up.")
            return
        
        print("[search] tags: {} - page {}".format(' '.join(tags), page))
        async with session.get(construct_search_endpoint(page, tags, start_id)) as response:
            if response.status < 200 or response.status > 299:
                print("    Got error response code {} when retrieving {} page {}".format(str(response.status), ' '.join(tags), page))
                n_tries += 1
                continue
            
            data = await response.json()
            
            if not isinstance(data, list):
                print("    Got weird response: "+str(data))
                n_tries += 1
                continue
                
            if len(data) == 0:
                return
                
            page += 1
            n_tries = 0
            
            ids = list(int(d['id']) for d in data)
            last_id = min(ids)
            
            if start_id is not None and last_id > start_id:
                continue
                
            for d in data:
                yield DanbooruPost.from_api_json(d)
                
        
async def search(session, with_tags, without_tags, rating=None, start_id=None):
    async for post in search_api(session, with_tags[:2], start_id=start_id):
        if not all((tag in post) for tag in with_tags):
            continue
        
        if any((tag in post) for tag in without_tags):
            continue
        
        if rating is not None and post.rating != rating:
            continue
        
        yield post

async def lookup_tag(tag):
    async with aiohttp.ClientSession() as sess:
        url = base_url+'/tags.json?search[name_matches]=*'+tag+'*'
        
        async with sess.get(url) as resp:
            return await resp.json()
        
