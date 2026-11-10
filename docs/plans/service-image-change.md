# Changing a service's image from the dashboard (#250)

## Decisions

- **Extend `PUT /api/services/<name>`; no new endpoint.** `image` is already a
  services.json field that PUT persists. A second endpoint would be a second
  owner of one field.
- **One rule for the effective image.** `flag_metadata.IMAGE_OVERRIDE_ENGINES`
  names the engines whose templates render `{{ image }}`; `effective_image()`
  is the override when the engine honours one and it is non-empty, else the
  default. The compose render and the service payload both read it. Before,
  four hand-written lines in `compose_manager` and `docker_utils._service_image`
  disagreed: `.get(key, default)` rendered a stored `""` as an empty `image:`,
  and the payload ignored a Maya override. A guard test ties the set to the
  templates, so a new engine cannot drift.
- **Recreate only when the effective image changes.** Other PUTs keep
  persisting and rebuilding only. The recreate is `recreate_service(
  only_if_running=True)` through `restart_if_running`, with
  `IMAGE_CHANGE_TIMEOUT_S = 600` because `up` can pull first. It holds
  `SERVICES_DB_LOCK` for that long, the same trade-off as `/recreate`.
- **Empty string resets to the default.** Valid on every engine; a non-empty
  value on ds4, tabbyapi or ninfer is a 400, so no inert value is stored.
- **A failed recreate is not reported as applied.** The response is 200 (the
  config is committed) with `restarted: false` and `recreate_error`, and the
  UI shows it as an error. The response field is `configured_image`: what
  services.json now renders, not necessarily what runs. The
  `metadata-changed` delta carries the image the payload will report, computed
  by `docker_utils.reported_image` (the creation-time image of an existing
  container, else the configured one), so a failed recreate or an existing
  stopped container announces the old image and a successful recreate or a
  service with no container announces the new one.
- **Planner and executor.** `flag_metadata.plan_image_change` is the pure
  before/after comparison; `service_recreate.apply_update_effects` runs the
  rebuild or the recreate and returns `restarted`, `error` and the reported
  image. The route only wires them, and the case table is tested without Flask.
- **Advisory presence check.** `docker_utils.image_presence_warnings` reuses
  `get_image_info`: a missing local image adds a non-blocking warning, a
  lookup failure adds nothing.
- **Capability to the UI.** `GET /api/services/<name>` adds `image_override`,
  derived from `IMAGE_OVERRIDE_ENGINES`, so the panel carries no engine list.

## Not done

- A live check (recreating a real container onto a different image) was not
  run; the cases are covered with a fake docker runner and fixtures.
- `get_flags_metadata` keeps its own hand-written engine whitelist; it is a
  different rule and tracked separately.
