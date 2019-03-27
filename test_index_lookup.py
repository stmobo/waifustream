import asyncio
import sys
import time

from PIL import Image
import aiohttp
import aioredis
import numpy as np

from waifustream import danbooru, index
from waifustream.index import IndexEntry


async def main():
    with Image.open(sys.argv[1]) as img:
        imhash = index.combined_hash(img)
        h_bytes = imhash.tobytes()
        
    print("Lookup: "+h_bytes.hex())
    
    redis = await aioredis.create_redis('redis://localhost')
    
    t1 = time.perf_counter()
    res = await index.search_index(redis, imhash)
    t2 = time.perf_counter()
    
    dh1 = imhash[:8]
    ah1 = imhash[8:]
    
    print("Lookup completed in {:.4f} seconds".format(t2-t1))
    print("Results: ")
    for h, dist in res:
        entry = await IndexEntry.load_from_index(redis, h)
        
        arr = np.frombuffer(h, dtype=np.uint8)
        dh2 = arr[:8]
        ah2 = arr[8:]
        
        dist1 = index.hamming_dist(dh1, dh2)
        dist2 = index.hamming_dist(ah1, ah2)
        
        print("{} (ID {}) - distance {} ({}+{})".format(h.hex(), entry.src_id, dist, dist1, dist2))
    

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
