import { describe, it, expect } from 'vitest'
import { createMemoryRouter } from 'react-router-dom'
import { routes } from './routes'
import GpuMonitor from './components/GpuMonitor'
import ServicesTable from './components/ServicesTable'
import ServiceDetailsPage from './components/ServiceDetailsPage'
import ChatPage from './components/chat/ChatPage'
import GhostChatPage from './components/chat/GhostChatPage'
import ToolsPage from './components/tools/ToolsPage'
import SettingsPage from './components/SettingsPage'
import { AppShell, DefaultLayout } from './layout'

// The data router's route table is the single source of truth for paths, and
// nothing else renders it — so pin its matching here: every production path
// resolves to the intended element, and the shell/layout wrapping is what it
// used to be under <BrowserRouter> + <Routes>. Initial matches are computed
// synchronously at router creation, so no rendering (and no network) is
// needed.
function leafFor(path) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const matches = router.state.matches
  expect(matches.length).toBe(2)
  expect(matches[0].route.element?.type).toBe(AppShell)
  const leaf = matches[1]
  expect(leaf).toBeTruthy()
  return leaf.route.element
}

describe('route table', () => {
  it('serves the dashboard at / inside the default layout', () => {
    const element = leafFor('/')
    expect(element.type).toBe(DefaultLayout)
    const children = element.props.children
    expect(Array.isArray(children)).toBe(true)
    expect(children[0].type).toBe(GpuMonitor)
    expect(children[1].type).toBe(ServicesTable)
  })

  it('serves the ghost page before the parameterised chat routes', () => {
    expect(leafFor('/chat/ghost').type).toBe(GhostChatPage)
  })

  it('serves chat at /chat (no conversation) and /chat/:id', () => {
    expect(leafFor('/chat').type).toBe(ChatPage)
    expect(leafFor('/chat/abc-123').type).toBe(ChatPage)
  })

  it('serves the project page (beating the optional conversation param)', () => {
    expect(leafFor('/chat/project/p1').type).toBe(ChatPage)
  })

  it('serves tools and settings', () => {
    expect(leafFor('/tools').type).toBe(DefaultLayout)
    expect(leafFor('/settings').type).toBe(DefaultLayout)
    // The page components sit inside the default layout.
    const toolsRouter = createMemoryRouter(routes, { initialEntries: ['/tools'] })
    const toolsEl = toolsRouter.state.matches[1].route.element
    expect(toolsEl.props.children.type).toBe(ToolsPage)
    const settingsRouter = createMemoryRouter(routes, { initialEntries: ['/settings'] })
    expect(settingsRouter.state.matches[1].route.element.props.children.type).toBe(SettingsPage)
  })

  it('serves service details with a wildcard subpath', () => {
    expect(leafFor('/services/vllm-x').type).toBe(DefaultLayout)
    const r = createMemoryRouter(routes, { initialEntries: ['/services/vllm-x/logs'] })
    expect(r.state.matches[1].route.element.props.children.type).toBe(ServiceDetailsPage)
    expect(r.state.matches[1].params.serviceName).toBe('vllm-x')
    expect(r.state.matches[1].params['*']).toBe('logs')
  })

  it('matches nothing below the shell for unknown paths (same as the old <Routes>)', () => {
    const router = createMemoryRouter(routes, { initialEntries: ['/nope'] })
    expect(router.state.matches).toHaveLength(1)
    expect(router.state.matches[0].route.element?.type).toBe(AppShell)
  })
})
