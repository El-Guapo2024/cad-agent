// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/SketcherSettings.cpp: 2014 Werner Mayer
//   src/Mod/Sketcher/Gui/AppSketcherGui.cpp: 2008 Jürgen Riegel
//   No copyright line in the file: src/Mod/Sketcher/Gui/SketcherSettings.ui, src/Mod/Sketcher/Gui/SketcherSettingsGrid.ui,
//       src/Mod/Sketcher/Gui/SketcherSettingsDisplay.ui, src/Mod/Sketcher/Gui/SketcherSettingsAppearance.ui
// The Sketcher's Preferences pages (AppSketcherGui.cpp registers General, Grid, Display and Appearance under "Sketcher"; FreeCAD lists
// the group once the Sketcher module is loaded, which a fresh profile has done by the time Preferences opens). Each is the form of its
// .ui (uiforms-sketcher.ts, drawn by qtform.tsx) with the widgets that do something here bound to the parameter FreeCAD's page writes
// (sketcherParam, by its path under Preferences); the others show what FreeCAD shows in a fresh profile, greyed out.
import { useState } from 'react'
import { QtForm, type Bindings } from './qtform'
import { SKETCHER_FORMS } from './uiforms-sketcher'
import { sketcherParam, setSketcherParams } from './sketchovp'
import * as S from './sketcher'

/** The parameters a page edits, as the page shows them; setting one writes it (PrefWidget::onSave as the box changes, as the other
 *  pages here apply at once) and redraws the page. */
function useParams() {
  const [, setGen] = useState(0)
  const get = <T extends number | boolean>(path: string, d: T) => sketcherParam<T>(path, d)
  const set = (ps: Record<string, number | boolean | null>) => { setSketcherParams(ps); setGen((g) => g + 1) }
  return { get, set }
}
const na = (why: string) => ({ why })
const GEOM = 'the sketch is drawn with FreeCAD Light\'s look; this setting is not read here'

/** SketcherSettings (General): the Dimension Constraint combos (loadSettings fills them: Single tool / Separated tools / Both, Auto /
 *  Diameter / Radius, Always / Never / When no scale feature is visible) and Tool Parameters' On-view-parameters. */
export function SketcherGeneralPage() {
  const { get, set } = useParams()
  const dia = get('Mod/Sketcher/dimensioning/DimensioningDiameter', true), rad = get('Mod/Sketcher/dimensioning/DimensioningRadius', true)
  const single = get('Mod/Sketcher/dimensioning/SingleDimensioningTool', true), separated = get('Mod/Sketcher/dimensioning/SeparatedDimensioningTools', false)
  const dimMode = separated ? (single ? 2 : 1) : 0
  const bind: Bindings = {
    checkBoxAdvancedSolverTaskBox: na('the edit panel has no Advanced solver control section here'),
    checkBoxRecalculateInitialSolutionWhileDragging: na('dragging always solves from the last solution here'),
    checkBoxAutoRemoveRedundants: na('redundant constraints are reported, not removed, here'),
    checkBoxEnableEscape: { value: get('Mod/Sketcher/LeaveSketchWithEscape', true), set: (v: boolean) => set({ 'Mod/Sketcher/LeaveSketchWithEscape': v }) },
    checkBoxNotifyConstraintSubstitutions: na('constraint substitutions are not offered here'),
    checkBoxUnifiedCoincident: na('the toolbar has the unified coincident command only'),
    checkBoxHorVerAuto: na('the toolbar has its commands as they are'),
    checkBoxLineGroup: na('the toolbar has its commands as they are'),
    checkBoxAddExtGeo: na('external geometry is added as FreeCAD adds it by default'),
    checkBoxMakeInternals: na('the sketch\'s faces are made by the CAD worker'),
    // the dimensioning mode only greys the radius/diameter mode here (Separated tools: no automatic radius/diameter)
    dimensioningMode: { value: dimMode, opts: [[0, 'Single tool'], [1, 'Separated tools'], [2, 'Both']], off: true, why: 'the toolbar has its dimension commands as they are' },
    radiusDiameterMode: {
      value: dia ? (rad ? 0 : 1) : 2, opts: [[0, 'Auto'], [1, 'Diameter'], [2, 'Radius']], off: dimMode === 1,
      set: (i: number) => set({ 'Mod/Sketcher/dimensioning/DimensioningDiameter': i !== 2, 'Mod/Sketcher/dimensioning/DimensioningRadius': i !== 1 }),
    },
    autoScaleMode: na('a sketch is never scaled on its first constraint here'),
    ovpVisibility: {
      value: get('Mod/Sketcher/Tools/OnViewParameterVisibility', 1), opts: [[0, 'None'], [1, 'Dimensions only'], [2, 'Position and dimensions']],
      set: (i: number) => set({ 'Mod/Sketcher/Tools/OnViewParameterVisibility': i }),
    },
  }
  return <QtForm form={SKETCHER_FORMS.sketcher} bind={bind} />
}

/** SketcherSettingsGrid: the grid's display; Grid (ShowGrid) is the edit panel's Display grid. */
export function SketcherGridPage() {
  const [grid, setGrid] = useState(() => S.showGrid())
  const bind: Bindings = {
    checkBoxShowGrid: { value: grid, set: (v: boolean) => { S.setShowGrid(v); setGrid(v) } },
  }
  for (const n of ['checkBoxGridAuto', 'gridSize', 'gridSizePixelThreshold', 'gridTransparency', 'gridLinePattern', 'gridLineWidth', 'gridLineColor',
    'gridNumberSubdivision', 'gridDivLinePattern', 'gridDivLineWidth', 'gridDivLineColor']) bind[n] = na('the grid is drawn with FreeCAD\'s defaults here')
  return <QtForm form={SKETCHER_FORMS.sketchergrid} bind={bind} />
}

/** SketcherSettingsDisplay: Continue tool mode (ContinuousCreationMode) and Show coordinates next to the cursor (ShowCursorCoords) are
 *  read by the tools; the rest are FreeCAD's. */
export function SketcherDisplayPage() {
  const { get, set } = useParams()
  const bind: Bindings = {
    continueMode: { value: get('Mod/Sketcher/ContinuousCreationMode', true), set: (v: boolean) => set({ 'Mod/Sketcher/ContinuousCreationMode': v }) },
    checkBoxShowCursorCoords: { value: get('Mod/Sketcher/ShowCursorCoords', true), set: (v: boolean) => set({ 'Mod/Sketcher/ShowCursorCoords': v }) },
  }
  for (const n of ['fontBoxSketcherFontName', 'EditSketcherFontSize', 'ConstraintSymbolSize', 'viewScalingFactor', 'axisTransparency', 'occludedAxisTransparency',
    'SegmentsPerGeometry', 'checkBoxHideUnits', 'checkBoxUseSystemDecimals', 'checkBoxShowDimensionalName', 'prefDimensionalStringFormat',
    'checkBoxShowDirectionalAutoConstraintHints']) bind[n] = na(GEOM)
  bind.dialogOnDistanceConstraint = na('a new dimension always takes the value it has')
  bind.constraintMode = na('a constraint tool always goes on until Esc here')
  for (const n of ['checkBoxTVHideDependent', 'checkBoxTVShowLinks', 'checkBoxTVShowSupport', 'checkBoxTVRestoreCamera', 'checkBoxTVForceOrtho', 'checkBoxTVSectionView', 'btnTVApply'])
    bind[n] = na('the edit mode shows the part as it is set here; these visibility options are not read')
  return <QtForm form={SKETCHER_FORMS.sketcherdisplay} bind={bind} />
}

/** SketcherSettingsAppearance: the edit mode's colours and line widths, FreeCAD Light's here. */
export function SketcherAppearancePage() {
  return <QtForm form={SKETCHER_FORMS.sketcherappearance} bind={{}} />
}

/** What Reset Page puts back: the parameters each page writes, unset (FreeCAD's resetSettingsToDefaults removes them). */
export const SKETCHER_RESET: Record<string, string[]> = {
  'Sketcher General': ['Mod/Sketcher/LeaveSketchWithEscape', 'Mod/Sketcher/dimensioning/DimensioningDiameter', 'Mod/Sketcher/dimensioning/DimensioningRadius',
    'Mod/Sketcher/Tools/OnViewParameterVisibility'],
  'Sketcher Grid': [],
  'Sketcher Display': ['Mod/Sketcher/ContinuousCreationMode', 'Mod/Sketcher/ShowCursorCoords'],
  'Sketcher Appearance': [],
}
