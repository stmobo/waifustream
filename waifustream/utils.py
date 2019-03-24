import asyncio
from datetime import datetime, timedelta

version = None

async def get_cmd_output(cmd, do_strip=True):
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
    stdout, _ = await proc.communicate()
    output = stdout.decode('utf-8')

    if do_strip:
        return output.strip()
    else:
        return output
        
async def get_version():
    global version
    if version is None:
        version = await get_cmd_output('git rev-parse --short HEAD')

    return version

async def sleep_to_minute(freq):
    cur_time = datetime.utcnow()
    last_check_time = datetime(cur_time.year, cur_time.month, cur_time.day, cur_time.hour, int(cur_time.minute / freq), 0)
    next_check_time = last_check_time + timedelta(minutes=freq)
    return await asyncio.sleep((next_check_time - datetime.utcnow()).total_seconds())
    
