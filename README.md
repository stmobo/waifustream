# WaifuStream Reverse Image Search Bot

**WaifuStream** is a simple reverse image search engine built on top of Redis.
It also comes with a Discord bot for performing searches and management.

## Overview

Each image processed by **WaifuStream** is indexed by its perceptual hash value,
and searches are also performed with perceptual hashes as input.


An initial search is performed by dividing the query image hash into byte-sized chunks,
and returning all indexed image hashes that share at least one corresponding chunk with the query hash.

For example:
```
Query Hash:        05 a2 ff b5 ...
Potential Match 1: 05 c6 d2 a2 ... (match in position 0)
Potential Match 2: 2d a2 cc b5 ... (match in position 1 and 3)
```

Afterwards, the full Hamming distance is then computed for every hash matched
by this initial search. Potential matches with a high distance are then filtered out,
and the final result list is returned, sorted by increasing distance.

## Indexer

The Indexer forms the core of this system, and is responsible for:
  - Monitoring source sites (i.e. Danbooru) for images to index
  - Fetching queued images and indexing them within Redis.
  
Both of these are handled by separate worker processes within the Indexer.

The Indexer is provided with a list of tags to monitor via the `indexed_tags`
Redis key. It will periodically scan source sites for posts with monitored
tags, and add them to per-tag queues. Images will then be fetched and indexed
from each queue in round-robin fashion.

## Client Interface

The main interface for the engine is the `waifustream.index` module.
There, you'll find functions for performing searches and for retrieving indexed
data. Additional functions for working with the Indexer are also provided.

## Discord Bot

Currently, the only extant end-user interface for this engine is via the
included Discord chatbot.

Valid commands for the chatbot include:
```
status [tag]               : Show the status of the indexer, either as a whole or for the provided tag
add / index [tags...]      : Add a set of tags to the indexed tags list.
remove / unindex [tags...] : Remove a set of tags from the indexed tags list.
identify [n]               : Look up a previously posted image within the index.
```

## Config

The following keys can be set within `config.json` to control both the Bot and the Indexer:
```
redis_url           : The URL of the Redis server to connect to.
min_download_delay  : Minimum delay between each fetched image, in seconds. 
bot_ua              : The User-Agent string to use for HTTP requests made by the Discord bot.
indexer_ua          : The User-Agent string to use for HTTP requests made by the Indexer.
exclude_tags        : A list of tags that will be excluded from indexing and from bot search results.
tokenfile           : Path to a file containing the bot's login token.
maintenance_mode    : If True, the bot will start in Maintenance Mode, and regular users won't be able to access any bot commands.
authorized_users    : A list of Discord user IDs that are allowed to access privileged commands.
log_channels        : A list of Discord channel IDs to post log messages to.
error_channels      : A list of Discord channel IDs to post error reports to.
command_channels    : A list of Discord channel IDs that will be monitored for commands.
```
