import { StrictMode, useState, useCallback } from 'react'
import { createRoot } from 'react-dom/client'
import Pet from './components/Pet'
import './pet.css'

function PetApp() {
  const [visible, setVisible] = useState(true)
  const handleToggle = useCallback((show: boolean) => {
    setVisible(show)
    localStorage.setItem('cd_pet_visible', show ? '1' : '0')
    window.electronAPI?.togglePet(show)
  }, [])
  if (!visible) return null
  return <Pet />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PetApp />
  </StrictMode>,
)
