// FreeCAD's corner coordinate system, ported from View3DInventorViewer::drawAxisCross and
// createAxisArrowGeometry at FreeCAD main 3160daf1e2b6 (LGPL-2.1-or-later). Three arrows in
// the AxisX/Y/ZColor turned as the camera is, drawn at the bottom right in a square that is
// CornerCoordSystemSize % of the view's shorter side, with X, Y and Z just past the tips.
// The letters are FreeCAD's CornerCrossLetters.h masks (21x27, first row at the bottom).
// Colours follow Preferences > Display > 3D View (AxisXColor/Y/Z, AxisLetterColor) live.
import * as THREE from 'three'
import type { AxisColors } from './store'

const LETTERS: Record<'X' | 'Y' | 'Z', string> = {
  X: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALH////QAwAAAAAAAAB3/////1kAAB70////agAAAAAAABrz////tAAAAAB1////7RMAAAAAAKX////zHQAAAAAE0v///5gAAAAAPP////9sAAAAAAAAOv7///0yAAACz////8YCAAAAAAAAAJv////FAQBo////+SoAAAAAAAAAABHq////XRLs////fwAAAAAAAAAAAABe////56H////VBgAAAAAAAAAAAAAAv/////////05AAAAAAAAAAAAAAAAKPn//////5IAAAAAAAAAAAAAAAAAAI3//////RYAAAAAAAAAAAAAAAAAA83//////4IAAAAAAAAAAAAAAAAAbP////////gkAAAAAAAAAAAAAAAX8P///8X///+1AAAAAAAAAAAAAACj////wg3p////TgAAAAAAAAAAAD7////+MwBp////3wkAAAAAAAAABNT///+hAAAD1v///4EAAAAAAAAAdf////UbAAAATf////cjAAAAAAAc8////4AAAAAAAL7///+0AAAAAACr////5QoAAAAAADL+////TQAAAEf/////XwAAAAAAAACj////3ggAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
  Y: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABc////2AAAAAAAAAAAAAAAAAAAAABc////2AAAAAAAAAAAAAAAAAAAAABc////2AAAAAAAAAAAAAAAAAAAAABc////2AAAAAAAAAAAAAAAAAAAAABc////2AAAAAAAAAAAAAAAAAAAAABc////2AAAAAAAAAAAAAAAAAAAAABc////2AAAAAAAAAAAAAAAAAAAAABc////2AAAAAAAAAAAAAAAAAAAAACi////9RYAAAAAAAAAAAAAAAAAACf8/////44AAAAAAAAAAAAAAAAAAKb///////cbAAAAAAAAAAAAAAAAK/3///////+VAAAAAAAAAAAAAAAAq/////n////5HwAAAAAAAAAAAAAv/v///2Tg////nQAAAAAAAAAAAACw////2gNl////+yQAAAAAAAAAADP/////XAAE3f///6QAAAAAAAAAALX////YAwAAYf////0qAAAAAAAAOP////9aAAAAA9r///+rAAAAAAAAuv///9cCAAAAAF3////+MAAAAAA8/////1gAAAAAAALX////sgAAAAC/////1QIAAAAAAABZ/////zYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
  Z: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAVP//////////////////jAAAAAAAVP//////////////////jAAAAAAATP//////////////////jAAAAAAAA8r////wdXR0dHR0dHR0PwAAAAAAAC76////ZAAAAAAAAAAAAAAAAAAAAACE////7xkAAAAAAAAAAAAAAAAAAAAH1////60AAAAAAAAAAAAAAAAAAAAAO/7///9SAAAAAAAAAAAAAAAAAAAAAJX////mEAAAAAAAAAAAAAAAAAAAAA3i////mwAAAAAAAAAAAAAAAAAAAABL/////0EAAAAAAAAAAAAAAAAAAAAApv///9wJAAAAAAAAAAAAAAAAAAAAFev///+KAAAAAAAAAAAAAAAAAAAAAFz////8MgAAAAAAAAAAAAAAAAAAAAC2////zwQAAAAAAAAAAAAAAAAAAAAe8////3gAAAAAAAAAAAAAAAAAAAAAbf////clAAAAAAAACXR0dHR0dHR0dvP////AAQAAAAAAFP//////////////////PwAAAAAAFP//////////////////SAAAAAAAFP//////////////////SAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
}
const LW = 21, LH = 27

/** ViewParams AxisXColor, AxisYColor, AxisZColor; FreeCAD Light's AxisLetterColor. Only the
 *  initial look (store.ts's AXIS_COLOR_DEFAULTS mirrors these); render() takes the live colours. */
export const AXIS_COLORS = { x: 0xcc3333, y: 0x33cc33, z: 0x3333cc, letter: 0x000000 }

/** createAxisArrowGeometry: a square shaft two thirds long, a cross of two fins for the tip. */
function arrowGeometry() {
  const s = 1 - 1 / 3, t = 0.02, h = 0.5 / 4
  const v: number[] = []
  const face = (...p: number[][]) => { for (let i = 1; i + 1 < p.length; i++) v.push(...p[0], ...p[i], ...p[i + 1]) }
  face([0, -t, t], [0, t, t], [s, t, t], [s, -t, t])
  face([0, -t, -t], [0, t, -t], [s, t, -t], [s, -t, -t])
  face([0, -t, t], [0, -t, -t], [s, -t, -t], [s, -t, t])
  face([0, t, t], [0, t, -t], [s, t, -t], [s, t, t])
  face([0, t, t], [0, t, -t], [0, -t, -t], [0, -t, t])
  face([1, 0, 0], [s, h, 0], [s, -h, 0])
  face([1, 0, 0], [s, 0, h], [s, 0, -h])
  face([s, h, 0], [s, 0, h], [s, -h, 0], [s, 0, -h])
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(v, 3))
  return g
}

function letterTexture(mask: string, color: number) {
  const a = atob(mask), c = new THREE.Color(color)
  const rgb = [c.r, c.g, c.b].map((x) => Math.round(x * 255))
  const data = new Uint8Array(LW * LH * 4)
  for (let i = 0; i < LW * LH; i++) data.set([rgb[0], rgb[1], rgb[2], a.charCodeAt(i)], i * 4)
  const tex = new THREE.DataTexture(data, LW, LH, THREE.RGBAFormat)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.magFilter = THREE.LinearFilter
  tex.minFilter = THREE.LinearMipmapLinearFilter
  tex.generateMipmaps = true
  tex.needsUpdate = true
  return tex
}

export class AxisCross {
  private axisScene = new THREE.Scene()
  private axisCamera = new THREE.PerspectiveCamera(45, 1, 0.1, 10) // heightAngle pi/4
  private group = new THREE.Group()
  private arrows: THREE.Mesh[] = []
  private letterScene = new THREE.Scene()
  private letterCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, -1, 1)
  private letters: THREE.Mesh[] = []
  private comb = new THREE.Matrix4()
  // '' never matches a real "#rrggbb" value, so the first render() always applies once.
  private lastColors: AxisColors = { x: '', y: '', z: '', letter: '' }

  constructor() {
    const geo = arrowGeometry()
    const arrow = (color: number) => new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, depthTest: false, depthWrite: false, toneMapped: false }))
    const [x, y, z] = [arrow(AXIS_COLORS.x), arrow(AXIS_COLORS.y), arrow(AXIS_COLORS.z)]
    y.rotation.set(0, 0, Math.PI / 2)
    z.rotation.set(0, -Math.PI / 2, 0)
    this.arrows = [x, y, z]
    this.group.add(x, y, z)
    this.axisScene.add(this.group)
    const quad = new THREE.PlaneGeometry(LW, LH).translate(LW / 2, LH / 2, 0)
    for (const k of ['X', 'Y', 'Z'] as const) {
      const m = new THREE.Mesh(quad, new THREE.MeshBasicMaterial({ map: letterTexture(LETTERS[k], AXIS_COLORS.letter), transparent: true, depthTest: false, depthWrite: false, toneMapped: false }))
      this.letters.push(m)
      this.letterScene.add(m)
    }
  }

  /** AxisXColor/AxisYColor/AxisZColor/AxisLetterColor, applied in place (arrow material colour,
   *  letter-texture RGB) only when a value actually changed since the last render(). */
  private applyColors(c: AxisColors) {
    if (c.x !== this.lastColors.x) (this.arrows[0].material as THREE.MeshBasicMaterial).color.set(c.x)
    if (c.y !== this.lastColors.y) (this.arrows[1].material as THREE.MeshBasicMaterial).color.set(c.y)
    if (c.z !== this.lastColors.z) (this.arrows[2].material as THREE.MeshBasicMaterial).color.set(c.z)
    if (c.letter !== this.lastColors.letter) {
      const col = new THREE.Color(c.letter)
      const rgb = [col.r, col.g, col.b].map((v) => Math.round(v * 255))
      for (const m of this.letters) {
        const tex = (m.material as THREE.MeshBasicMaterial).map as THREE.DataTexture
        const data = tex.image.data as Uint8Array
        for (let i = 0; i < LW * LH; i++) { data[i * 4] = rgb[0]; data[i * 4 + 1] = rgb[1]; data[i * 4 + 2] = rgb[2] }
        tex.needsUpdate = true
      }
    }
    this.lastColors = c
  }

  /** drawAxisCross: after the scene, in the corner square; `size` is CornerCoordSystemSize,
   *  `colors` the live AxisX/Y/ZColor + AxisLetterColor preferences. */
  render(r: THREE.WebGLRenderer, camera: THREE.Camera, size: number, colors: AxisColors) {
    this.applyColors(colors)
    const view = r.getSize(new THREE.Vector2())
    const px = Math.floor((size / 100) * Math.min(view.x, view.y))
    if (px <= 0) return
    // The model turned by the inverse of the camera's orientation, 3.5 in front of it.
    this.group.quaternion.copy(camera.quaternion).invert()
    this.group.position.set(0, 0, -3.5)
    this.group.updateMatrixWorld(true)
    this.axisCamera.updateMatrixWorld(true)
    this.comb.multiplyMatrices(this.axisCamera.projectionMatrix, this.group.matrixWorld)
    const project = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z).applyMatrix4(this.comb)
    const tips = [project(1, 0, 0), project(0, 1, 0), project(0, 0, 1)]
    // Farthest first, as FreeCAD sorts them (no depth test).
    const order = [0, 1, 2].sort((a, b) => tips[b].z - tips[a].z)
    order.forEach((i, k) => { this.arrows[i].renderOrder = k })
    // The letters: in the square's pixels, 7 % of it high (8 to 18 px), centred 1.15 past each tip.
    const h = Math.min(18, Math.max(8, px * 0.07)), scale = h / LH
    const cam = this.letterCamera
    cam.left = -px / 2; cam.right = px / 2; cam.top = px / 2; cam.bottom = -px / 2
    cam.updateProjectionMatrix()
    ;[[1, 0, 0], [0, 1, 0], [0, 0, 1]].forEach((a, i) => {
      const p = project(a[0] * 1.15, a[1] * 1.15, a[2] * 1.15)
      const m = this.letters[i]
      m.scale.set(scale, scale, 1)
      m.position.set(((1 + p.x) * px) / 2 - px / 2 - (LW * scale) / 2, ((1 + p.y) * px) / 2 - px / 2 - (LH * scale) / 2, 0)
    })
    const vp = r.getViewport(new THREE.Vector4())
    r.setViewport(view.x - px, 0, px, px)
    r.render(this.axisScene, this.axisCamera)
    r.render(this.letterScene, this.letterCamera)
    r.setViewport(vp)
  }

  dispose() {
    this.arrows[0]?.geometry.dispose()
    for (const m of [...this.arrows, ...this.letters]) {
      const mat = m.material as THREE.MeshBasicMaterial
      mat.map?.dispose()
      mat.dispose()
    }
    this.letters[0]?.geometry.dispose()
  }
}
