// Preferences > Display > Light Sources: View3DSettings.cpp (OnChange EnableHeadlight …
// AmbientLightIntensity), View3DInventorViewer.cpp's three-point lighting (headlight, backlight,
// fill light, SoEnvironment) and DlgSettingsLightSources.cpp at FreeCAD main 3160daf1e2b6.
// The three lights are directional and follow the camera, as Coin's are: a direction is in the
// camera's own frame (x right, y up, z towards the viewer) and turns with the view.
import * as THREE from 'three'

export type Vec = [number, number, number]
export type Light = { on: boolean; color: string; dir: Vec; intensity: number }
export type LightPrefs = { head: Light; back: Light; fill: Light; ambient: { color: string; intensity: number } }

// View3DSettings.h defaultHeadLightDirection / defaultBackLightDirection / defaultFillLightDirection;
// View3DSettings.cpp's GetUnsigned/GetInt fallbacks (0xFFFFFFFF/90, 0xF5F5EEFF/60, 0xE6FAFFFF/40,
// AmbientLightColor 0xFFFFFFFF/20); EnableHeadlight/Backlight/FillLight default true.
export const LIGHT_DEFAULTS: LightPrefs = {
  head: { on: true, color: '#ffffff', dir: [0.6841049, -0.12062616, -0.7193398], intensity: 90 },
  back: { on: true, color: '#f5f5ee', dir: [-0.7544065, -0.63302225, -0.17364818], intensity: 60 },
  fill: { on: true, color: '#e6faff', dir: [-0.6403416, 0.7631294, 0.087155744], intensity: 40 },
  ambient: { color: '#ffffff', intensity: 20 },
}

const rad = (d: number) => (d * Math.PI) / 180, deg = (r: number) => (r * 180) / Math.PI
/** DlgSettingsLightSources::azimuthElevationToDirection. */
export function azimuthElevationToDirection(azimuth: number, elevation: number): Vec {
  const a = rad(azimuth), e = rad(elevation)
  const v = new THREE.Vector3(Math.sin(a) * Math.cos(e), Math.cos(a) * Math.cos(e), Math.sin(e)).normalize()
  return [v.x, v.y, v.z]
}
/** DlgSettingsLightSources::directionToAzimuthElevation. */
export function directionToAzimuthElevation([x, y, z]: Vec): [number, number] {
  return [deg(Math.atan2(x, y)), deg(Math.atan2(z, Math.sqrt(y * y + x * x)))]
}

/** Coin's lights are fixed-function Lambert: colour × intensity × cos. three's physically based
 *  lights divide the diffuse term by π, so π × FreeCAD's fraction gives the same shading
 *  (three-cad-viewer's own scaleLight does the same). */
const toThree = (percent: number) => (Math.PI * percent) / 100

/** The viewer's lights: SoDirectionalLight ×3 and SoEnvironment's ambient. */
export class LightRig {
  readonly head = new THREE.DirectionalLight()
  readonly back = new THREE.DirectionalLight()
  readonly fill = new THREE.DirectionalLight()
  readonly ambient = new THREE.AmbientLight()
  private dirs: Record<'head' | 'back' | 'fill', THREE.Vector3> = { head: new THREE.Vector3(), back: new THREE.Vector3(), fill: new THREE.Vector3() }
  private q = new THREE.Quaternion()

  constructor(scene: THREE.Object3D, prefs: LightPrefs) {
    for (const l of [this.head, this.back, this.fill, this.ambient]) { l.name = 'cad-light'; scene.add(l) }
    this.apply(prefs)
  }
  apply(p: LightPrefs) {
    for (const k of ['head', 'back', 'fill'] as const) {
      const l = this[k], s = p[k]
      l.visible = s.on // setHeadlightEnabled / setBacklightEnabled / setFillLightEnabled
      l.color.set(s.color)
      l.intensity = toThree(s.intensity)
      this.dirs[k].set(...s.dir).normalize()
    }
    this.ambient.color.set(p.ambient.color)
    this.ambient.intensity = toThree(p.ambient.intensity)
  }
  /** Turns the lights with the camera; call before each render. A DirectionalLight shines from
   *  its position towards its target (the origin), so it sits opposite its direction. */
  follow(camera: THREE.Camera) {
    camera.getWorldQuaternion(this.q)
    for (const k of ['head', 'back', 'fill'] as const) { this[k].position.copy(this.dirs[k]).applyQuaternion(this.q).negate(); this[k].updateMatrixWorld() }
  }
  dispose() { for (const l of [this.head, this.back, this.fill, this.ambient]) { l.removeFromParent(); l.dispose() } }
}
