import { isToolError } from '../../../utils/piTools/payload'
import CappedText from './CappedText'

export default function ResultMessage({ tool, when }) {
  const text = (tool.result?.text ?? '').trim()
  if (text === '') return null
  const error = isToolError(tool)
  if ((when === 'error') !== error) return null
  return <CappedText text={text} tone={error ? 'error' : 'muted'} />
}
