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
          pypkgs.certifi
        ];
        dev-inputs = pypkgs: [
          pypkgs.pytest
          pypkgs.pytest-asyncio
          pypkgs.pytest-vcr
          pypkgs.mypy
          pypkgs.types-pyyaml
          pypkgs.polars
          pypkgs.lxml
          pypkgs.lxml-stubs
          pypkgs.snakemake
          pypkgs.dominate
          pypkgs.tabulate
          pypkgs.icecream
        ];
        version = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version;
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
            pyproject = true;
            pname = "repro-validator";
            version = version;
            propagatedBuildInputs = inputs python.pkgs;
            nativeBuildInputs = [ python.pkgs.setuptools ];
            doCheck = false;
            src = ./.;
          };
          docker = let
            py = python.withPackages(ps: [ps.aiohttp ps.aiodns ps.requests ps.certifi]);
          in pkgs.dockerTools.buildLayeredImage {
            name = "ghcr.io/charmoniumQ/repro-validator";
            tag = version;
            contents = [
              self.packages.${system}.default
            ];
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
