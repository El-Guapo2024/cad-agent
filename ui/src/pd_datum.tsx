// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/Command.cpp: 2008 Jürgen Riegel (UnifiedDatumCommand, CmdPartDesignPlane, CmdPartDesignLine,
//     CmdPartDesignPoint, CmdPartDesignCS)
//   src/Mod/PartDesign/Gui/TaskDatumParameters.cpp: 2013 Jan Rheinländer (the panel's title and icon, accept's
//     "Incompatible Reference Set")
//   src/Mod/PartDesign/Gui/ViewProviderDatum*.cpp: 2015 Alexander Golubev (Fat-Zer) (datumType, datumMenuText)
// PartDesign's own datum commands, PartDesign_Plane, _Line, _Point and _CoordinateSystem: FreeCAD 26.3 still has them
// (Tools > Customize, the Python console, `cad gui run`), though its menus make Part's datums. Each makes PartDesign::Plane,
// Line, Point or CoordinateSystem in the active Body with its attachment panel (TaskDatumParameters, a TaskAttacher with the
// datum's icon and title: pd_attach.tsx's AttachTask), the selection as its references when they fit a mode; with one
// datum of that type selected, the command edits it instead.
import { getState } from './store'
import { openTask, showPanel } from './actions'
import { messageBox } from './msgbox'
import { splitRef, targetBody } from './partdesign'
import { editAttachment } from './pd_attach'

/** Each command: the TypeId it makes, its menu text and tooltip (CmdPartDesignPlane …), and TaskDatumParameters' title
 *  (ViewProviderDatum's datumMenuText). */
export const PD_DATUMS: Record<string, { type: string; menu: string; tip: string; title: string; icon: string }> = {
  PartDesign_Plane: { type: 'PartDesign::Plane', menu: 'Datum Plane', tip: 'Creates a new datum plane', title: 'Datum Plane Parameters', icon: 'pd-datum-plane' },
  PartDesign_Line: { type: 'PartDesign::Line', menu: 'Datum Line', tip: 'Creates a new datum line', title: 'Datum Line Parameters', icon: 'pd-datum-line' },
  PartDesign_Point: { type: 'PartDesign::Point', menu: 'Datum Point', tip: 'Creates a new datum point', title: 'Datum Point Parameters', icon: 'pd-datum-point' },
  PartDesign_CoordinateSystem: { type: 'PartDesign::CoordinateSystem', menu: 'Local Coordinate System', tip: 'Creates a new local coordinate system',
    title: 'Local Coordinate System Parameters', icon: 'pd-datum-cs' },
}
/** TaskDatumParameters' title for a datum type, or null for one that is not PartDesign's. */
export const datumPanelTitle = (type: string) => Object.values(PD_DATUMS).find((d) => d.type === type)?.title ?? null
export const datumPanelIcon = (type: string) => Object.values(PD_DATUMS).find((d) => d.type === type)?.icon ?? null

const NO_BODY = 'In order to use PartDesign you need an active Body object in the document. Please make one active (double click) '
  + 'or create one.\n\nIf you have a legacy document with PartDesign objects without Body, use the migrate function in PartDesign '
  + 'to put them into a Body.'

/** UnifiedDatumCommand: one datum of the type selected opens it to edit; else a new one in the active Body (getBody with its
 *  message when there is none), the selection as its references (TaskAttacher's handleInitialSelection), then its panel. */
export async function unifiedDatum(cmd: string) {
  const d = PD_DATUMS[cmd]
  const s = getState()
  if (!d || !s.slug) return
  const sel = s.featSel.map(splitRef)
  if (sel.length === 1 && s.features[sel[0][0]]?.features.find((f) => f.name === sel[0][1])?.type === d.type) {
    editAttachment(sel[0][0], sel[0][1])
    return
  }
  const part = targetBody()
  if (!part) { await messageBox('warning', 'No active body', NO_BODY); return }
  openTask('attach', part, `new:${d.type}`)
  showPanel('tasks')
}

/** The commands for cmdreg.ts's registry. */
export function pdDatumCommands<T>(reg: (label: string, run: (args: string[]) => void, isEnabled?: () => boolean) => T): Record<string, T> {
  return Object.fromEntries(Object.entries(PD_DATUMS).map(([cmd, d]) => [cmd, reg(d.menu, () => void unifiedDatum(cmd), () => !!getState().slug)]))
}
