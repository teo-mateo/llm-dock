const PATH = '/hf-cache/… or /local-models/…'
const DIR = '/hf-cache/… or /local-models/… (model directory)'

function entry(type, label, hint, over = {}) {
  return {
    type, label, hint, model_source: 'file', placeholder: PATH, gguf_picker: false,
    badge_label: type, metrics: false, benchmark: false, slots: false, web_ui: false,
    name_prefix: type, ...over,
  }
}

export const SAMPLE_ENGINES = [
  entry('llamacpp', 'llama.cpp', 'GGUF file', {
    badge_label: 'llama.cpp', gguf_picker: true, metrics: true, benchmark: true, slots: true, web_ui: true,
  }),
  entry('ik_llamacpp', 'ik llama.cpp', 'GGUF file (ik fork)', { badge_label: 'ik_llama', gguf_picker: true, name_prefix: 'ik' }),
  entry('vllm', 'vLLM', 'HuggingFace org/name', { badge_label: 'vLLM', model_source: 'repo', metrics: true }),
  entry('ds4', 'ds4', 'DeepSeek V4 Flash file', { badge_label: 'DS4', gguf_picker: true }),
  entry('tabbyapi', 'TabbyAPI', 'EXL3 model directory', { badge_label: 'EXL3', model_source: 'directory', placeholder: DIR, name_prefix: 'exl3' }),
  entry('ninfer', 'NInfer', '.ninfer artifact', { badge_label: 'NInfer', metrics: true }),
  entry('sglang', 'SGLang / Pennyroyal', 'RTX PRO 6000 model directory', { badge_label: 'SGLang', model_source: 'directory', placeholder: DIR, metrics: true }),
  entry('maya', 'Project Maya', 'Maya pack directory', {
    badge_label: 'Maya', model_source: 'directory', placeholder: '~/.cache/maya/<model>/<pack> (absolute host path)',
  }),
]

export const ENGINES_RESPONSE = { engines: SAMPLE_ENGINES }
