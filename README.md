# Running

If you don't like Nix:

``` sh
docker run -it --rm -v $PWD:$PWD -w $PWD ghcr.io/uiuc-cs527-fa24/mp2-validator/mp2-validator:0.1.0 path/to/cs527
```

If you don't like Docker:

``` sh
nix run github:uiuc-cs527-fa24/mp2-validator -- path/to/cs527
```
