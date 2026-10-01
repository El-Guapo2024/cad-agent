import { createRoot } from 'react-dom/client'
import 'dockview-react/dist/styles/dockview.css'
import 'three-cad-viewer/css'
import './freecad.css'
import { App } from './App'
import { getDock, getView, showPanel, start } from './actions'
import { getState, setState } from './store'
import * as placement from './placement'
import * as quantity from './quantity'
import * as quantityInput from './quantity-input'
import { initTooltips } from './tooltip'
import { initSliders } from './qslider'

createRoot(document.getElementById('root')!).render(<App />)
start()
initTooltips()
initSliders()
// For debugging from the console: cadui.getState(), cadui.getView()
Object.assign(window, { cadui: { getState, setState, getView, getDock, showPanel, placement, quantity, quantityInput } })
