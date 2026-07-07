import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import Pet from './components/Pet'
import './index.css' // 复用主样式

function PetApp() {
  const [visible, setVisible] = useState(true)
  return <Pet visible={visible} onToggle={setVisible} />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PetApp />
  </StrictMode>,
)
