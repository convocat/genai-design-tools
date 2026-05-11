import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// StrictMode is intentionally off: it double-invokes the runtime's async
// generator in dev, which creates duplicate parallel runs that overwrite
// each other's rendered content. Production (which Vercel uses) never
// enables StrictMode, so dev behaviour now matches prod.
createRoot(document.getElementById('root')!).render(<App />)
