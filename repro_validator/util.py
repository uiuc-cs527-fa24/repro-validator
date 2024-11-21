import hashlib
import typing
import random
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
timeout = aiohttp.ClientTimeout(total=10)
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


_T = typing.TypeVar("_T")


def deterministic_shuffle(seed: int, lst: typing.Iterable[_T]) -> list[_T]:
    rng = random.Random(seed)
    ret = list(lst)
    rng.shuffle(ret)
    return ret


def deterministic_stable_shuffle(
    seed: int,
    lst: typing.Iterable[_T],
    key: typing.Callable[[_T], bytes],
) -> list[_T]:
    """Stable shuffle is a shuffle where inserting/removing one element does not disturb the ordering of the others in the shuffled result."""
    rng = random.Random(seed)
    hash_modifier = int.from_bytes(rng.randbytes(hashlib.sha1().digest_size))
    ret = [
        (int.from_bytes(hashlib.sha1(key(elem)).digest()) ^ hash_modifier, elem)
        for elem in lst
    ]
    return [key for _, key in sorted(ret)]


async def async_id(elem: _T) -> _T:
    return elem
