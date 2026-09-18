// Client-side mirror of the server's service naming: flag_metadata's
// generate_service_name (prefix table) + service_templates.sanitize_service_name.
// Used only for the live name preview in the create-service modal — the server
// is the owner of the actual name, so any drift here costs a preview, not a write.

export const SERVICE_NAME_PREFIXES = {
  ik_llamacpp: "ik",
  tabbyapi: "exl3",
}

export function sanitizeServiceName(name) {
  let n = String(name).toLowerCase()
  n = n.replace(/_/g, "-").replace(/ /g, "-")
  n = n.replace(/[^a-z0-9-]/g, "")
  n = n.replace(/-+/g, "-")
  n = n.replace(/^-+|-+$/g, "")
  if (n.length > 63) n = n.slice(0, 63).replace(/-+$/, "")
  return n
}

export function generateServiceName(templateType, alias) {
  const prefix = SERVICE_NAME_PREFIXES[templateType] || templateType
  return sanitizeServiceName(`${prefix}-${alias}`)
}

export function aliasFromModelName(modelName) {
  let base = String(modelName).replace(/\s*\[[^\]]*\]$/, "")
  base = base.split("/").pop()
  base = base.replace(/-GGUF$/i, "").replace(/-Instruct$/i, "").replace(/-FP8-Dynamic$/i, "")
  return sanitizeServiceName(base)
}
