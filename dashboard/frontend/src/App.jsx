import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { routes } from './routes.jsx'

// Data router (issue #80): useBlocker only works under the data-router APIs,
// so the legacy <BrowserRouter> + <Routes> pair was replaced — reverting to
// BrowserRouter breaks the dirty-editor navigation blocker at runtime. The
// basename is what the legacy BrowserRouter carried.
const router = createBrowserRouter(routes, { basename: '/v2' })

function App() {
  return <RouterProvider router={router} />
}

export default App
