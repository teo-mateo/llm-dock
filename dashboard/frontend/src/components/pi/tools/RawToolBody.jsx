import CappedText from './CappedText'
import ToolMeta from './ToolMeta'

export default function RawToolBody({ item }) {
  return (
    <>
      <ToolMeta item={item} />
      {item.args != null && <CappedText text={item.args} />}
      {item.output != null && <CappedText text={item.output} />}
    </>
  )
}
