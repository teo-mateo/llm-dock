from dataclasses import replace

from docker_utils import image_presence_warnings, reported_image
from service_recreate import IMAGE_CHANGE_TIMEOUT_S, restart_if_running

from .update import UpdateDeps
from .wiring import build_infra


def update_deps(compose_file: str, **overrides) -> UpdateDeps:
    return UpdateDeps(
        replace(build_infra(compose_file), **overrides),
        image_presence_warnings=lambda image: image_presence_warnings(image),
        recreate_for_image=lambda name, status, finish: restart_if_running(
            compose_file, name, status, True, lambda services, n: finish(), timeout=IMAGE_CHANGE_TIMEOUT_S
        ),
        reported_image=reported_image,
    )
