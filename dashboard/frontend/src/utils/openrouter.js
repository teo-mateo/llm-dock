// Pure helpers for the `openrouter:<model-id>` service-string convention.
// An OpenRouter model rides through the same main_service / sidekick_service /
// model_service strings as local Docker service names — these helpers are the
// single place the prefix is encoded/decoded on the frontend.

export const OPENROUTER_PREFIX = 'openrouter:'

export const isOpenRouterService = (name) =>
  typeof name === 'string' && name.startsWith(OPENROUTER_PREFIX)

export const openRouterModelId = (name) => name.slice(OPENROUTER_PREFIX.length)

export const serviceNameForModel = (id) => OPENROUTER_PREFIX + id

// Display label for a service string. OpenRouter values get their curated
// label when `models` is supplied (array of {id, label}), otherwise the bare
// model id, suffixed with the provider. Local names pass through unchanged.
export function formatModelLabel(name, models = []) {
  if (!isOpenRouterService(name)) return name
  const id = openRouterModelId(name)
  const curated = models.find(m => m.id === id)
  return `${curated?.label || id} · OpenRouter`
}
