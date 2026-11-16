import '@fontsource/saira-stencil-one/latin-400.css'
import '@fontsource/barlow/latin-400.css'
import '@fontsource/barlow/latin-500.css'
import '@fontsource/barlow/latin-600.css'
import '@fontsource/barlow-condensed/latin-600.css'
import '@fontsource/barlow-condensed/latin-700.css'
import '@fontsource/jetbrains-mono/latin-400.css'
import '@fontsource/jetbrains-mono/latin-500.css'
import './index.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { probeInkMode } from './lib/ink'

const root = document.getElementById('root')
if (!root) throw new Error('#root missing from index.html')

probeInkMode()

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
