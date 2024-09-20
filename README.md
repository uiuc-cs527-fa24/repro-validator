# Running

If you don't like Nix, use Docker:

``` sh
docker run -it --rm -v $PWD:$PWD -w $PWD ghcr.io/uiuc-cs527-fa24/mp2-validator:0.1.2 path/to/cs527
```

If you don't like Docker, use Nix:

``` sh
nix run github:uiuc-cs527-fa24/mp2-validator/0.1.2 -- path/to/cs527
```
