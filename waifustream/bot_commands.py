import asyncio
import io
import logging
from pathlib import Path
import re
import subprocess as sp
import sys
import time
import traceback

import aiohttp
import discord
from PIL import Image
import ujson as json

from . import utils, index, danbooru
from .index import IndexEntry


async def cmd_remove_indexed_tag(client, msg, args):
    if len(args) == 0:
        return await client.reply(msg, "Usage: `w!index [tags...]`")
        
    tags = list(filter(lambda t: t not in index.exclude_tags, (t.lower().strip() for t in args)))
    
    async with aiohttp.ClientSession() as sess:
        url = danbooru.base_url+'/tags.json?search[name]='+(','.join(tags))
        
        async with sess.get(url) as resp:
            tags_data = await resp.json()
        
    valid_tags = list(d['name'] for d in tags_data)
    if len(valid_tags) == 0:
        return await client.reply(msg, "None of the tags you listed are valid Danbooru tags.")
        
    valid_tags = list(d['name'] for d in tags_data)
    if len(valid_tags) == 0:
        return await client.reply(msg, "None of the tags you listed are valid Danbooru tags.")
    
    for tag in valid_tags:    
        await client.redis.lrem('indexed_tags', 0, tag)
    
    out = ' '.join('`{}`'.format(t) for t in valid_tags)
    
    return await client.reply(msg, "Removed tags from indexing: "+out)

async def cmd_add_indexed_tag(client, msg, args):
    if len(args) == 0:
        return await client.reply(msg, "Usage: `w!index [tags...]`")
        
    tags = list(filter(lambda t: t not in index.exclude_tags, (t.lower().strip() for t in args)))
    
    async with aiohttp.ClientSession() as sess:
        url = danbooru.base_url+'/tags.json?search[name]='+(','.join(tags))
        
        async with sess.get(url) as resp:
            tags_data = await resp.json()
        
    valid_tags = list(d['name'] for d in tags_data)
    if len(valid_tags) == 0:
        return await client.reply(msg, "None of the tags you listed are valid Danbooru tags.")
        
    await client.redis.lpush('indexed_tags', *valid_tags)
    out = ' '.join('`{}`'.format(t) for t in valid_tags)
    
    return await client.reply(msg, "Queued tags for indexing: "+out)

async def cmd_indexer_status(client, msg, args):
    if len(args) == 0:
        characters = await index.get_indexed_tags(client.redis)
        out_lines = []
        
        for character in characters:
            q_len = await index.get_character_queue_length(client.redis, character)
            n_indexed = await client.redis.scard('character:'+character)
            
            out = "`{}`: **{}** items queued".format(character, q_len)
            if n_indexed > 0:
                out += ", **{}** items indexed".format(n_indexed)
            
            out_lines.append((out, q_len))
        
        out_lines = sorted(out_lines, key=lambda o: o[1], reverse=True)
        if len(out_lines) > 10:
            out_lines = out_lines[:10]
        
        return await client.reply(msg, "Currently indexing tags:\n"+("\n".join(l[0] for l in out_lines)))
    else:
        character = args[0]
        q_len = await index.get_character_queue_length(client.redis, character)
        n_indexed = await client.redis.scard('character:'+character)
        
        out = "`{}`: **{}** items queued, **{}** items indexed".format(character, q_len, n_indexed)
        
        return await client.reply(msg, out)

async def cmd_identify(client, msg, args):
    identify_idx = 0
    
    if len(args) == 0:
        if len(msg.attachments) > 0:
            identify_idx = 0   # identify the current image
        else:
            identify_idx = 1   # identify the last posted image
    else:
        identify_idx = int(args[0])
    
    identify_attachment = None
    if identify_idx == 0:
        identify_attachment = msg.attachments[0]
    else:
        i = identify_idx
        
        async for m in msg.channel.history(before=msg):
            if len(m.attachments) == 0:
                continue
                
            i -= 1
            if i == 0:
                identify_attachment = m.attachments[0]
                break
        else:
            return await client.reply(msg, "I couldn't find any image to identify. (Maybe it's too far back?)")

    try:
        t1 = time.perf_counter()
        
        bio = io.BytesIO()
        await identify_attachment.save(bio)
        
        with Image.open(bio) as img:
            imhash = index.combined_hash(img)    
            bio.close()
            
            res = await index.search_index(client.redis, imhash)
            t2 = time.perf_counter()
            
            res_imhash, dist = res[0]
            entry = await IndexEntry.load_from_index(client.redis, res_imhash)
            
            async with aiohttp.ClientSession() as sess:
                db_post = await danbooru.DanbooruPost.get_post(sess, entry.src_id)
            
            lines = [
                "Lookup completed in {:.3f} seconds:".format(t2-t1),
                "    **Confidence:**: {:.1%} (distance {})".format((64 - dist) / 64, dist),
                "    **Source:** {}#{}".format(entry.src.title(), entry.src_id),
                "    **Rating:**: {}".format(index.friendly_ratings.get(entry.rating, 'Unknown')),
                "    **Franchises:**: {}".format(', '.join('`{}`'.format(c) for c in db_post.copyrights)),
                "    **Characters:**: {}".format(', '.join('`{}`'.format(c) for c in entry.characters)),
                "    **Artists:**: {}".format(', '.join('`{}`'.format(c) for c in db_post.artists)),
            ]
            
            return await client.reply(msg, '\n'.join(lines))
    except OSError:
        return await client.reply(msg, "I couldn't open that image file.")
    
