import aiohttp
import rich.console
import yarl
import pydantic_core


def pydantic_to_yarl(url: pydantic_core.Url) -> yarl.URL:
    return yarl.URL(str(url))


def yarl_to_pydantic(url: yarl.URL) -> pydantic_core.Url:
    return pydantic_core.Url(str(url))


console = rich.console.Console()


async def url_status(
    aiohttp_client: aiohttp.ClientSession,
    url: yarl.URL,
) -> tuple[yarl.URL, int, yarl.URL]:
    console.print(f"[gray]HEAD {url!s}")
    async with aiohttp_client.head(url, allow_redirects=True, max_redirects=20) as resp:
        return url, resp.status, resp.url


async def url_bytes(
    aiohttp_client: aiohttp.ClientSession,
    url: yarl.URL,
) -> tuple[yarl.URL, int, yarl.URL, bytes]:
    console.print(f"[gray]GET {url!s}")
    async with aiohttp_client.get(url, allow_redirects=True, max_redirects=20) as resp:
        text = await resp.read()
        return url, resp.status, resp.url, text
