import { fetchAPI } from '../api'

// The fields one service can take, with their bounds. Served by the same module
// that builds the request, so a knob the engine has no verified mapping for is
// absent here and absent from the payload — the picker cannot offer what the
// runner would drop.
export const getSamplingFields = (service) =>
  fetchAPI(`/chat/sampling-fields?service=${encodeURIComponent(service)}`)
