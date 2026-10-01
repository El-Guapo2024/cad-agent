// SPDX-License-Identifier: LGPL-2.1-or-later
// The 3D view's background (Preferences > Display > Colors, DlgSettingsViewColor), ported from
// FreeCAD main 3160daf1e2b6: View3DSettings.cpp picks a simple colour or SoFCBackgroundGradient
// (src/Gui/Inventor/SoFCBackgroundGradient.cpp), a linear or radial gradient drawn as triangles
// in clip space with a colour per corner and a dithering fragment shader. Here the same triangles
// and shader are a mesh drawn first in the scene, as the gradient node is in FreeCAD's.
import * as THREE from 'three'

export type BackgroundMode = 'simple' | 'linear' | 'radial'
/** View/Simple, Gradient, RadialGradient (one of the three), BackgroundColor, BackgroundColor2
 *  (top / central), BackgroundColor4 (middle / midway), BackgroundColor3 (bottom / end) and
 *  UseBackgroundColorMid. */
export type BackgroundPrefs = { mode: BackgroundMode; color: string; top: string; mid: string; bottom: string; useMid: boolean }
/** FreeCAD Light's [View] settings (Simple, BackgroundColor #F7F7F7); the gradient colours are
 *  the page's own (DlgSettingsViewColor.ui), which it shows and saves until they're changed. */
export const BACKGROUND_DEFAULTS: BackgroundPrefs = { mode: 'simple', color: '#f7f7f7', top: '#333365', mid: '#6f6f93', bottom: '#9797aa', useMid: false }

const SEGMENTS = 32 // SoFCBackgroundGradient::CircleSegments
type P = [number, number]

/** updateLinearGeometry / updateRadialGeometry: the triangles, in clip space, and their corners'
 *  colours. A quad of the linear gradient is the two triangles GL makes of it. */
export function gradientTriangles(p: BackgroundPrefs): { pos: P[]; col: string[] } {
  const pos: P[] = [], col: string[] = []
  const tri = (a: P, ca: string, b: P, cb: string, c: P, cc: string) => { pos.push(a, b, c); col.push(ca, cb, cc) }
  const quad = (v: P[], c: string[]) => { tri(v[0], c[0], v[1], c[1], v[2], c[2]); tri(v[0], c[0], v[2], c[2], v[3], c[3]) }
  const { top: from, mid, bottom: to } = p
  if (p.mode !== 'radial') {
    if (!p.useMid) quad([[-1, 1], [1, 1], [1, -1], [-1, -1]], [from, from, to, to])
    else {
      quad([[-1, 1], [1, 1], [1, 0], [-1, 0]], [from, from, mid, mid])
      quad([[-1, 0], [1, 0], [1, -1], [-1, -1]], [mid, mid, to, to])
    }
    return { pos, col }
  }
  const f = Math.fround, step = f((2 * f(Math.PI)) / SEGMENTS), sqrt2 = f(Math.SQRT2), sqrtHalf = f(Math.sqrt(0.5))
  const outer: P[] = [], inner: P[] = []
  for (let i = 0; i < SEGMENTS; i++) {
    const a = f(step * i)
    outer.push([f(sqrt2 * f(Math.cos(a))), f(sqrt2 * f(Math.sin(a)))])
    inner.push([f(f(0.3 * sqrt2) * f(Math.cos(a))), f(sqrtHalf * f(Math.sin(a)))])
  }
  // The fan from the centre to the inner circle (with a middle colour) or the outer one.
  for (let i = 0; i < SEGMENTS; i++) {
    const next = (i + 1) % SEGMENTS, ring = p.useMid ? inner : outer, c = p.useMid ? mid : to
    tri([0, 0], from, ring[i], c, ring[next], c)
  }
  // The ring from the inner circle to the outer.
  if (p.useMid) for (let i = 0; i < SEGMENTS; i++) {
    const next = (i + 1) % SEGMENTS
    tri(inner[i], mid, outer[i], to, outer[next], to)
    tri(inner[i], mid, outer[next], to, inner[next], mid)
  }
  return { pos, col }
}

/** #RRGGBB as GL takes an 8-bit colour: no colour management, as FreeCAD's fixed pipeline. */
const rgb = (hex: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as [number, number, number]

// SoFCBackgroundGradient's shaders: the vertex colour plus triangular noise of ±2/255.
const vertexShader = `
varying vec3 vColor;
void main() {
  gl_Position = vec4(position.xy, 0.0, 1.0);
  vColor = color;
}`
const fragmentShader = `
varying vec3 vColor;
vec3 permute(vec3 x) {
  return mod(((x * 34.0) + 1.0) * x, 289.0); }
float rand(vec2 co) {
  vec3 p = permute(permute(co.x + vec3(0.0, 1.0, 2.0)) + (co.y * 26.69));
  return fract((p.x + p.y + p.z) * 0.6180339887498949); }
void main() {
  float triNoise = rand(gl_FragCoord.xy) + rand(gl_FragCoord.yx) - 1.0;
  vec3 ditheredColor = vColor.rgb + vec3(triNoise * 2.0 / 255.0);
  gl_FragColor = vec4(ditheredColor, 1.0);
}`

/** The gradient as a mesh: drawn before everything (renderOrder), never depth-tested, picked,
 *  culled or clipped; its vertices are already in clip space. */
export function gradientMesh(p: BackgroundPrefs): THREE.Mesh {
  const { pos, col } = gradientTriangles(p)
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos.flatMap(([x, y]) => [x, y, 0]), 3))
  g.setAttribute('color', new THREE.Float32BufferAttribute(col.flatMap(rgb), 3))
  // SoShapeHints' UNKNOWN_SHAPE_TYPE: Coin draws both sides (the linear quads wind clockwise).
  const m = new THREE.Mesh(g, new THREE.ShaderMaterial({ vertexShader, fragmentShader, vertexColors: true, depthTest: false, depthWrite: false, side: THREE.DoubleSide }))
  m.renderOrder = -Infinity
  m.frustumCulled = false
  m.raycast = () => {}
  m.userData.cadHelper = true
  m.name = 'SoFCBackgroundGradient'
  return m
}
