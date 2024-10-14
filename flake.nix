{
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        inputs = pypkgs: [
          pypkgs.typer
          pypkgs.rich
          pypkgs.pydantic
          pypkgs.pyyaml
          pypkgs.aiohttp
          pypkgs.aiodns
          pypkgs.rdflib
          pypkgs.vcrpy
        ];
        dev-inputs = pypkgs: [
          pypkgs.pytest
          pypkgs.pytest-asyncio
          pypkgs.pytest-vcr
          pypkgs.mypy
          pypkgs.types-pyyaml
          pypkgs.types-setuptools
        ];
        version = builtins.replaceStrings ["\n"] [""] (builtins.readFile ./version);
      in {
        devShells = {
          default = pkgs.mkShell {
            packages = [
              (pkgs.python312.withPackages (pypkgs: (inputs pypkgs) ++ (dev-inputs pypkgs)))
              pkgs.ruff
            ];
          };
        };
        packages = rec {
          default = python.pkgs.buildPythonApplication {
            pname = "repro-validator";
            version = version;
            propagatedBuildInputs = inputs python.pkgs;
            doCheck = false;
            src = ./.;
          };
          docker = pkgs.dockerTools.buildLayeredImage {
            name = "ghcr.io/charmoniumQ/repro-validator";
            tag = version;
            contents = self.packages.${system}.default;
            config = {
              Entrypoint = "${self.packages.${system}.default}/bin/repro-validator";
            };
          };
        };
        apps = rec {
          default = {
            type = "app";
            program = "${self.packages.${system}.default}/bin/repro-validator";
          };
        };
      }
    );
}
