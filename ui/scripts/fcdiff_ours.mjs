// fcdiff.py's other half: the same cases through our TypeScript ports (bundled by fcdiff.py).
import fs from 'node:fs'
const [bundle, inPath, outPath] = process.argv.slice(2)
const { quantity: Q, rotation: R, Quaternion } = await import(bundle)
const cases = JSON.parse(fs.readFileSync(inPath, 'utf8'))
const out = {}
const err = (e) => ({ error: e.message, kind: e.kind ?? null })

out.schemas = Q.SCHEMAS.map((s) => ({ num: s.num, name: s.name, description: s.description }))
out.parse = (cases.parse ?? []).map((t) => { try { const q = Q.parseQuantity(t); return { value: q.value, dims: q.dims } } catch (e) { return err(e) } })
out.user = (cases.user ?? []).map((c) => {
  let dims
  try { dims = Q.parseQuantity('1 ' + c.unit).dims } catch (e) { return err(e) }
  try { const r = Q.userString({ value: c.value, dims }, c.schema, c.decimals, c.denominator); return { dims, text: r.text, factor: r.factor, unit: r.unit } } catch (e) { return err(e) }
})
out.number = (cases.number ?? []).map((c) => Q.toNumber(c.value, c.format, c.precision))
const quat = (q) => [q.x, q.y, q.z, q.w]
const tryIt = (f) => { try { return f() } catch (e) { return err(e) } }
out.rotation = (cases.rotation ?? []).map((c) => {
  const q = new Quaternion(...c.q)
  const aa = tryIt(() => R.axisAngleOf(q))
  const res = { ypr: tryIt(() => R.yprOfQuat(q)), rawAxis: aa.axis, angle: aa.angle }
  for (const seq of cases.seqs) res[seq] = tryIt(() => R.eulerOf(q, seq))
  return res
})
out.ypr = (cases.ypr ?? []).map(([y, p, r]) => quat(R.quatOfYpr(y, p, r)))
out.euler = (cases.euler ?? []).map((c) => tryIt(() => quat(R.quatOfEuler(c.angles, c.seq))))
fs.writeFileSync(outPath, JSON.stringify(out))
