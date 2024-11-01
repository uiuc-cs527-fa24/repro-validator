import asyncio
import aiohttp
import rich.console
import rich.progress
import yarl
import pydantic_core


def pydantic_to_yarl(url: pydantic_core.Url) -> yarl.URL:
    return yarl.URL(str(url))


def yarl_to_pydantic(url: yarl.URL) -> pydantic_core.Url:
    return pydantic_core.Url(str(url))


console = rich.console.Console()
progress = rich.progress.Progress(console=console)
timeout = 10
max_redirects = 20


async def url_status(
    aiohttp_client: aiohttp.ClientSession,
    url: yarl.URL,
) -> tuple[yarl.URL, int, yarl.URL]:
    console.print(f"[gray]HEAD {url!s}")
    try:
        async with aiohttp_client.head(
            url, allow_redirects=True, max_redirects=max_redirects, timeout=timeout
        ) as resp:
            console.print("[gray]done")
            return url, resp.status, resp.url
    except asyncio.TimeoutError:
        return url, 400, url


async def url_bytes(
    aiohttp_client: aiohttp.ClientSession,
    url: yarl.URL,
) -> tuple[yarl.URL, int, yarl.URL, bytes]:
    console.print(f"[gray]GET {url!s}")
    try:
        async with aiohttp_client.get(
            url, allow_redirects=True, max_redirects=max_redirects, timeout=timeout
        ) as resp:
            content_length = int(resp.headers.get("Content-Length", 0))
            # progress_task = progress.add_task("Downloading...", total=content_length)
            content = bytearray()
            async for chunk in resp.content.iter_chunked(1024):
                content.extend(chunk)
                # progress.update(progress_task, advance=len(chunk))
                if len(content) % (1024 * 10) == 0:
                    console.print(
                        "[gray]Downloaded", len(content), "of", content_length
                    )
            return url, resp.status, resp.url, content
    except asyncio.TimeoutError:
        return url, 400, url, b""
