import asyncio
import discord
import re
import sys
import ujson as json
import logging
import traceback
from pathlib import Path
import subprocess as sp

from . import utils

class WaifuStreamClient(discord.Client):
    perms_integer = 379968
    cmd_regex = r"\"([^\"]+)\"|\'([^\']+)\'|\`\`\`([^\`]+)\`\`\`|\`([^\`]+)\`|(\S+)"
    ready = False

    def load_config(self, conf_path=None):
        if conf_path is None:
            conf_path = sys.argv[1]

        with open(conf_path, 'r') as config_file:
            self.config = json.load(config_file)

    def get_config(self, key):
        try:
            return self.config[key]
        except AtrributeError:
            load_config()
            return self.config[key]

    def iter_channels(self, channel_id_list):
        for ch_id in channel_id_list:
            yield self.get_channel(ch_id)

    async def log_notify(self, msg, **kwargs):
        timestamp = datetime.now(timezone.utc).isoformat()
        for channel in self.iter_channels(self.get_config('log_channels')):
            await channel.send('`[{}]` {}'.format(timestamp, msg), **kwargs)

    async def error_notify(self, msg, **kwargs):
        timestamp = datetime.now(timezone.utc).isoformat()
        for channel in self.iter_channels(self.get_config('error_channels')):
            await channel.send('`[{}]` {}'.format(timestamp, msg), **kwargs)

    async def reply(self, original_msg, reply_text, timed=True, **kwargs):
        ch = original_msg.channel
        msg = await ch.send(
            "<@!{}> | {:s}".format(original_msg.author.id, reply_text),
            **kwargs
        )

        if timed:
            self.set_message_ttl(msg)

        return msg

    def is_authorized(self, user):
        return user.id in self.get_config('authorized_users')

    def display_name(self, guild, user):
        if guild is None:
            return user.display_name

        member = guild.get_member(user.id)

        if member is not None:
            return member.display_name
        else:
            return user.display_name
            
    async def dispatch_cmd(self, cmd, args):
        
    
    async def on_ready(self):
        print('Logged in as')
        print(self.user.name)
        print(self.user.id)
        print('------')
        print("Invite URL:")
        print("https://discordapp.com/api/oauth2/authorize?client_id={}&scope=bot&permissions={}".format(self.user.id, self.perms_integer))

        mention_string = "<@{}>".format(self.user.id)
        nick_mention_string = "<@!{}>".format(self.user.id)

        self.summon_prefixes = ['w!', 'W!', mention_string, nick_mention_string]

        v = await utils.get_version()
        await self.log_notify("WaifuStream Version {} starting up!".format(v))

        if self.get_config('maintenance_mode'):
            await self.change_presence(activity=discord.Game("Maintenance Mode"))
        else:
            await self.change_presence(activity=discord.Game("Version {}".format(v)))

        self.indexer = sp.Popen([sys.executable, '/waifustream/indexer.py'])

        self.ready = True

    async def on_message(self, msg):
        if not self.ready:
            return

        if msg.author.id == self.user.id or msg.author.bot:
            return

        if msg.type != discord.MessageType.default:
            return

        is_cmd = False
        if (msg.channel.id in self.get_config('command_channels')) or isinstance(msg.channel, discord.DMChannel):
            normalized_content = msg.content.lower().strip()

            # check to see if this is a command
            content = msg.content.strip()

            for prefix in self.summon_prefixes:
                if content.startswith(prefix):
                    content = content[len(prefix):].strip()
                    is_cmd = True
                    break
            else:
                if isinstance(msg.channel, discord.DMChannel):
                    is_cmd = True

        if is_cmd:
            if self.get_config('maintenance_mode') and not self.is_authorized(msg.author):
                return

            args = []
            for m in re.finditer(self.cmd_regex, content):
                for group in m.groups():
                    if group is not None:
                        args.append(group)
                        break

            if len(args) == 0:
                cmd = 'help'
            else:
                cmd = args[0].lower().strip()
                
            args = args[1:]

            return await self.dispatch_cmd(msg, cmd, args)
            
    async def on_error(self, ev, *args, **kwargs):
        exc_type, exc_val, exc_tb = sys.exc_info()
        tb_lines = traceback.format_exception(exc_type, exc_val, exc_tb)
        
        full_tb = ""
        
        for line in tb_lines:
            full_tb += line
            
        ext_error_info = ""
        if str(ev) == 'on_message':
            msg = args[0]
            is_cmd = False
            
            if (msg.channel.id in self.get_config('command_channels')) or isinstance(msg.channel, discord.DMChannel):
                content = msg.content.strip()
                for prefix in self.summon_prefixes:
                    if content.startswith(prefix):
                        content = content[len(prefix):].strip()
                        is_cmd = True
                        break
                else:
                    if isinstance(msg.channel, discord.DMChannel):
                        is_cmd = True
                        
            if is_cmd:
                ext_error_info = " when handing command from **{}#{}** ({}): `{}`".format(
                    msg.author.name,
                    msg.author.discriminator,
                    msg.author.id,
                    msg.content.strip()
                )
            else:
                ext_error_info = " when handing message from **{}#{}** ({})".format(
                    msg.author.name,
                    msg.author.discriminator,
                    msg.author.id,
                )
            
        await self.error_notify("<@!135165531908079616> Exception caught in `{}` handler{}:```{}```".format(str(ev), ext_error_info, full_tb))
        traceback.print_exception(exc_type, exc_val, exc_tb)

async def run_bot():
    client = WaifuStreamClient(activity=discord.Game("Starting..."))
    client.load_config()
    cards.load_cards_config()

    tokenfile = client.get_config('tokenfile')

    with open(tokenfile, 'r', encoding='utf-8') as f:
        token = f.read().strip()

    v = await utils.get_version()

    print(f'Starting version {v}...')
    try:
        await asyncio.gather(
            client.start(token)
        )
    except KeyboardInterrupt:
        await client.logout()

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_bot())
