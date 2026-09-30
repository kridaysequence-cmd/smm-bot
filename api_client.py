import aiohttp

async def fetch_services(api_url, api_key):
    if not api_url or not api_key:
        return []
    params = {"key": api_key, "action": "services"}
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, data=params) as resp:
            data = await resp.json()
            return data if isinstance(data, list) else []


async def create_order(api_url, api_key, service_id, link, quantity):
    params = {
        "key": api_key,
        "action": "add",
        "service": service_id,
        "link": link,
        "quantity": quantity
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, data=params) as resp:
            return await resp.json()
