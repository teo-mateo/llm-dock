// Renders the container command line a service config would start with, for
// the config panel's collapsible preview and the create-service modal.
// Kept in its own module so both components can share it without breaking
// react-refresh's components-only rule on the importing component files.

export function renderCommandPreview(config, apiKey, params) {
  if (!config) return ''
  const parts = []

  if (config.template_type === 'llamacpp' || config.template_type === 'ik_llamacpp') {
    parts.push('llama-server')
    if (config.model_path) parts.push(`-m ${config.model_path}`)
    parts.push(`--port 8080`)
    parts.push(`--api-key ${apiKey || '***'}`)
  } else if (config.template_type === 'ds4') {
    // ds4-server has no --api-key flag (auth not enforced by the container).
    parts.push('ds4-server')
    if (config.model_path) parts.push(`-m ${config.model_path}`)
    parts.push(`--host 0.0.0.0`)
    parts.push(`--port 8000`)
  } else if (config.template_type === 'tabbyapi') {
    // TabbyAPI has no --api-key flag; keys arrive as a mounted api_tokens.yml.
    parts.push('python3 main.py')
    parts.push(`--host 0.0.0.0`)
    parts.push(`--port 8000`)
    if (config.model_path) {
      const trimmed = String(config.model_path).replace(/\/+$/, '')
      const name = trimmed.split('/').pop()
      parts.push(`--model-dir ${trimmed.slice(0, trimmed.length - name.length - 1)}`)
      parts.push(`--model-name ${name}`)
    }
  } else if (config.template_type === 'ninfer') {
    // NInfer takes the .ninfer artifact positionally; auth is --api-key like llama.cpp.
    parts.push('ninfer-serve')
    if (config.model_path) parts.push(config.model_path)
    parts.push('--host 0.0.0.0')
    parts.push('--port 8080')
    parts.push(`--api-key ${apiKey || '***'}`)
  } else {
    parts.push('vllm serve')
    if (config.model_name) parts.push(config.model_name)
    parts.push(`--port 8000`)
    parts.push(`--api-key ${apiKey || '***'}`)
  }

  for (const { flag, value } of params) {
    if (!flag) continue
    if (value) {
      parts.push(`${flag} ${value}`)
    } else {
      parts.push(flag)
    }
  }

  return parts.join(' \\\n  ')
}
