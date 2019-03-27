import asyncio
import io
import logging
from pathlib import Path
import re
import subprocess as sp
import sys
import time
import traceback

import discord
from PIL import Image
import ujson as json

from . import utils, index, danbooru
from .index import IndexEntry

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
        bio = io.BytesIO()
        await identify_attachment.save(bio)
        
        with Image.open(bio) as img:
            imhash = index.combined_hash(img)
            
            bio.close()
            
            t1 = time.perf_counter()
            res = await index.search_index(client.redis, imhash)
            t2 = time.perf_counter()
            
            res_imhash, dist = res[0]
            entry = await IndexEntry.load_from_index(client.redis, res_imhash)
            
            lines = [
                "Lookup completed in {:.3f} seconds:".format(t2-t1),
                "    **Image Hash:** `{}`".format(entry.imhash.hex()),
                "    **Source:** `{}#{}`".format(entry.src, entry.src_id),
                "    **Characters:**: {}".format(', '.join('`{}`'.format(c) for c in entry.characters)),
                "    **Rating:**: {}".format(index.friendly_ratings.get(entry.rating, 'Unknown'))
            ]
            
            return await client.reply(msg, '\n'.join(lines))
    except OSError:
        return await client.reply(msg, "I couldn't open that image file.")
    
