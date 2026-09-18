import GpuMonitor from './components/GpuMonitor'
import ServicesTable from './components/ServicesTable'
import ServiceDetailsPage from './components/ServiceDetailsPage'
import ChatPage from './components/chat/ChatPage'
import GhostChatPage from './components/chat/GhostChatPage'
import ToolsPage from './components/tools/ToolsPage'
import InspectorPage from './components/inspector/InspectorPage'
import SettingsPage from './components/SettingsPage'
import { DefaultLayout, AppShell } from './layout'

// Route table for the data router (createBrowserRouter in App.jsx). Child
// paths are relative to the '/' layout, which preserves the old absolute
// routes' matching and ranking (static 'ghost' still wins the param route,
// 'chat/project/:projectId' still beats 'chat/:conversationId?').
export const routes = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <DefaultLayout><GpuMonitor /><ServicesTable /></DefaultLayout> },
      // Static segment, listed before the parameterised /chat routes: a
      // ghost chat is a mode, not a conversation id.
      { path: 'chat/ghost', element: <GhostChatPage /> },
      { path: 'chat/:conversationId?', element: <ChatPage /> },
      { path: 'chat/project/:projectId', element: <ChatPage /> },
      { path: 'tools', element: <DefaultLayout><ToolsPage /></DefaultLayout> },
      { path: 'inspector', element: <DefaultLayout><InspectorPage /></DefaultLayout> },
      { path: 'services/:serviceName/*', element: <DefaultLayout><ServiceDetailsPage /></DefaultLayout> },
      { path: 'settings', element: <DefaultLayout><SettingsPage /></DefaultLayout> },
    ],
  },
]
