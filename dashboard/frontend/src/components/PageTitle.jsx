import { createElement } from 'react'

export default function PageTitle({ children, className = '', as = 'h1' }) {
  return createElement(as, {
    className: `text-xl font-semibold leading-7 tracking-tight text-fg ${className}`,
  }, children)
}
