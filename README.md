# Running

If you don't like Nix, use Docker (most students should do this one):

``` sh
docker run -it --rm -v $PWD:$PWD -w $PWD ghcr.io/charmoniumq/mp2-validator:0.1.4 path/to/cs527
```

If you don't like Docker, use Nix:

``` sh
nix run github:uiuc-cs527-fa24/mp2-validator/0.1.4 -- path/to/cs527
```
