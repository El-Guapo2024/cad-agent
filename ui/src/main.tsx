// SPDX-License-Identifier: LGPL-2.1-or-later
import { createRoot } from 'react-dom/client'
import 'dockview-react/dist/styles/dockview.css'
import 'three-cad-viewer/css'
import './freecad.css'
import { App } from './App'
import { getDock, getView, select, showPanel, start } from './actions'
import { getState, setState } from './store'
import { getCommand } from './cmdreg'
import * as placement from './placement'
import * as quantity from './quantity'
import * as quantityInput from './quantity-input'
import { initTooltips } from './tooltip'
import { initSliders } from './qslider'
import { newSketch, pdMenus } from './partdesign'
import { createDatum, editAttachment } from './pd_attach'
import { panelFields } from './pd_revolve'
import { loadFeatures } from './actions'

createRoot(document.getElementById('root')!).render(<App />)
start()
initTooltips()
initSliders()
// For debugging from the console: cadui.getState(), cadui.getView(), cadui.getCommand('Std_ViewHome').run([])
Object.assign(window, { cadui: { getState, setState, getView, getDock, showPanel, getCommand, placement, quantity, quantityInput, pd: pdMenus,
  // attachcheck.mjs: the 3D selection, New Sketch, Edit > Create > Datums, Edit Attachment
  select, newSketch, createDatum, editAttachment } })
Object.assign((window as unknown as { cadui: object }).cadui, { pdPanel: panelFields, loadFeatures })   // revolvecheck.mjs
