// FreeCAD 1.1.4's icons, copied into public/freecad-icons (licences in its
// README). Placeholders until we draw our own.
const FILES = {
  document: 'Document', group: 'Group', part: 'Part_Feature', bought: 'Part_FeatureImport', body: 'PartDesign_Body',
  'wb-design': 'PartDesignWorkbench', 'wb-assembly': 'AssemblyWorkbench', 'wb-inspection': 'InspectionWorkbench',
  iso: 'view-isometric', front: 'view-front', top: 'view-top', right: 'view-right', rear: 'view-rear', bottom: 'view-bottom',
  left: 'view-left', views: 'view-axonometric', 'fit-all': 'zoom-all', 'fit-sel': 'zoom-selection',
  perspective: 'view-perspective', ortho: 'view-isometric', undo: 'edit-undo', redo: 'edit-redo', recompute: 'view-refresh',
  placement: 'Std_Placement', transform: 'Std_TransformManip', measure: 'umf-measurement',
  visibility: 'Std_ToggleVisibility', show: 'Std_ShowObjects', hide: 'Std_HideSelection', eye: 'TreeItemVisible',
  'eye-off': 'TreeItemInvisible', 'ov-error': 'overlay_error', 'ov-recompute': 'overlay_recompute', pass: 'dagViewPass',
  fail: 'dagViewFail', pending: 'dagViewPending', console: 'applications-python', report: 'document-properties',
  open: 'document-open', help: 'help-browser', joint: 'Assembly_CreateJointFixed', 'ds-asis': 'DrawStyleAsIs',
  'ds-flatlines': 'DrawStyleFlatLines', 'ds-shaded': 'DrawStyleShaded', 'ds-wireframe': 'DrawStyleWireFrame',
  'show-sel': 'Std_ShowSelection', home: 'Std_ViewHome', dimetric: 'Std_ViewDimetric', trimetric: 'Std_ViewTrimetric',
  'rot-left': 'view-rotate-left', 'rot-right': 'view-rotate-right', 'zoom-in': 'zoom-in', 'zoom-out': 'zoom-out',
  'axis-cross': 'Std_AxisCross', transparency: 'Std_ToggleTransparency', 'random-color': 'Std_RandomColor',
  unselectable: 'view-unselectable', 'goto-sel': 'tree-goto-sel', 'box-select': 'edit-select-box', 'select-all': 'edit-select-all',
  fullscreen: 'view-fullscreen', clip: 'Std_ToggleClipPlane', 'zoom-box': 'zoom-border', 'ds-points': 'DrawStylePoints',
  'ds-hiddenline': 'DrawStyleHiddenLine', 'ds-noshading': 'DrawStyleNoShading', shot: 'Std_ViewScreenShot', align: 'align-to-selection', 'measure-fc': 'umf-measurement',
  units: 'accessories-calculator', mass: 'MassPropertiesIcon', 'align-obj': 'Std_Alignment', turntable: 'Std_DemoMode', clarify: 'tree-pre-sel', 'edit-default': 'Std_UserEditModeDefault',
  'edit-transform': 'Std_UserEditModeTransform', 'edit-cutting': 'Std_UserEditModeCutting', 'edit-color': 'Std_UserEditModeColor',
  'dlg-parameter': 'Std_DlgParameter',
  // Tools menu additions (tools.tsx): CommandView.cpp/CommandDoc.cpp/CommandStd.cpp's sPixmap.
  'scene-inspector': 'Std_SceneInspector', 'dependency-graph': 'Std_DependencyGraph', 'load-image': 'image-open',
  customize: 'applications-accessories',
  // Help menu (CommandStd.cpp): Std_WhatsThis, Std_RestartInSafeMode, and the website openers,
  // which all share "internet-web-browser" (Std_OnlineHelp keeps our existing 'help' icon).
  'whats-this': 'WhatsThis', 'safe-mode': 'safe-mode-restart', web: 'internet-web-browser',
  // OverlayTabWidget's title bar (OverlayWidgets.cpp refreshIcons/syncAutoMode), light-theme icon set
  // from src/Gui/Stylesheets/overlay/icons/*.svg (not src/Gui/Icons, see public/freecad-icons/README.md).
  'ovl-mode': 'overlay-mode', 'ovl-autohide': 'overlay-autohide', 'ovl-editshow': 'overlay-editshow',
  'ovl-edithide': 'overlay-edithide', 'ovl-taskshow': 'overlay-taskshow', 'ovl-transparent': 'overlay-transparent',
  'ovl-overlay': 'overlay-overlay', 'ovl-float': 'overlay-float', 'ovl-close': 'overlay-close', 'ovl-toggle-left': 'Std_DockOverlayToggleLeft', 'ovl-toggle-bottom': 'Std_DockOverlayToggleBottom', 'toggle-bottom': 'Std_ToggleBottomPanels',
  // Macro menu (CommandMacro.cpp's sPixmap) and Windows menu (CommandWindow.cpp's sPixmap).
  'macro-record': 'media-record', 'macro-stop': 'media-playback-stop', macros: 'accessories-text-editor', 'macro-run': 'media-playback-start',
  'win-tile': 'Std_WindowTileVer', 'win-cascade': 'Std_WindowCascade', 'win-next': 'Std_WindowNext', 'win-prev': 'Std_WindowPrev',
  'win-close': 'Std_CloseActiveWindow', 'win-close-all': 'Std_CloseAllWindows', 'win-list': 'Std_Windows',
  // File menu (filemenu.tsx), CommandDoc.cpp's sPixmap. win-close/win-close-all above are reused
  // there too: Workbench.cpp puts Std_CloseActiveWindow/Std_CloseAllWindows in File at this commit,
  // though their sGroup is still "Window".
  new: 'document-new', save: 'document-save', 'save-as': 'document-save-as', 'save-copy': 'Std_SaveCopy',
  'save-all': 'Std_SaveAll', revert: 'Std_Revert', merge: 'Std_MergeProjects', 'doc-info': 'document-properties',
  print: 'document-print', 'print-preview': 'document-print-preview', 'print-pdf': 'Std_PrintPdf',
  exit: 'application-exit', recent: 'Std_RecentFiles',
  // NotificationArea.cpp's ResourceManager: the status bar button's two tray states and the
  // list/balloon's per-level icons (edit_Cancel/Warning/critical-info/info.svg).
  'notify-tray': 'InTray', 'notify-tray-missed': 'InTray_missed_notifications', 'notify-error': 'edit_Cancel',
  'notify-warn': 'Warning', 'notify-critical': 'critical-info', 'notify-info': 'info',
  // Edit's clipboard group, View's added entries, Help > Start Page, Tools' addon entries.
  'edit-cut': 'edit-cut', 'edit-copy': 'edit-copy', 'edit-paste': 'edit-paste', 'edit-delete': 'edit-delete',
  duplicate: 'Std_DuplicateSelection', 'window-new': 'window-new', 'issue-cam': 'Std_ViewIvIssueCamPos',
  texture: 'Std_TextureMapping', 'toggle-nav': 'Std_ToggleNavigation', appearance: 'Std_SetAppearance',
  material: 'Material_Edit', 'link-select': 'LinkSelect', 'link-select-final': 'LinkSelectFinal',
  'link-select-all': 'LinkSelectAll', 'tree-drag': 'tree-item-drag', 'tree-collapse': 'tree-doc-collapse',
  addon: 'AddonManager', start: 'StartCommandIcon', export: 'Std_Export',
  // StdWorkbench's Structure toolbar.
  'std-part': 'Geofeaturegroup', 'std-group': 'folder', varset: 'VarSet', link: 'Link',
  // Part_SelectFilter's gates.
  'vertex-selection': 'vertex-selection', 'edge-selection': 'edge-selection', 'face-selection': 'face-selection', 'clear-selection': 'clear-selection',
} as const

export type IconName = keyof typeof FILES

export function Icon({ name, size = 16, className }: { name: IconName; size?: number; className?: string }) {
  return <img src={`./freecad-icons/${FILES[name]}.svg`} width={size} height={size} alt="" draggable={false}
    className={className ? `ico ${className}` : 'ico'} />
}
