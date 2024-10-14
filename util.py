import aiohttp
import rich.console
import yarl
import pydantic_core


def pydantic_to_yarl(url: pydantic_core.Url) -> yarl.URL:
    return yarl.URL.build(
        scheme=url.scheme,
        user=url.username,
        password=url.password,
        host=url.host or "",
        # port=url.port,
        path=url.path or "",
        query_string=url.query or "",
        fragment=url.fragment or "",
    )


def yarl_to_pydantic(url: yarl.URL) -> pydantic_core.Url:
    return pydantic_core.Url.build(
        scheme=url.scheme,
        username=url.user,
        password=url.password,
        host=url.host or "",
        # port=url.port,
        path=url.path,
        query=url.query_string,
        fragment=url.fragment,
    )


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
