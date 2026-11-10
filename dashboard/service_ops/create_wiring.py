from dataclasses import replace

from docker_utils import image_presence_warnings
from service_templates import generate_api_key

from .create import CreateDeps
from .wiring import build_infra


def create_deps(compose_file: str, **overrides) -> CreateDeps:
    return CreateDeps(
        replace(build_infra(compose_file), **overrides),
        generate_key=lambda: generate_api_key(),
        image_presence_warnings=lambda image: image_presence_warnings(image),
    )
