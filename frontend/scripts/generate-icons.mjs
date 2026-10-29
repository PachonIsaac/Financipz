// Generates the PNG app icons in public/ with no external dependencies.
// Usage: node scripts/generate-icons.mjs
import { deflateSync } from 'node:zlib'
import { writeFileSync } from 'node:fs'

// Near black with the orange accent of the app.
const BG = [11, 11, 12]
const FG = [255, 138, 61]

function crc32(buf) {
  let c
  let crc = 0xffffffff
  for (let n = 0; n < buf.length; n++) {
    c = (crc ^ buf[n]) & 0xff
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    crc = (crc >>> 8) ^ c
  }
  return (crc ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}

// Three rising bars on a dark background, drawn in a 100x100 design space with rounded corners.
const BARS = [
  [24, 54, 14, 24],
  [43, 40, 14, 38],
  [62, 24, 14, 54],
]
const RADIUS = 3
// Each pixel is sampled on a grid, so the edges are smooth.
const SAMPLES = 3

function inside(u, v) {
  return BARS.some(([bx, by, bw, bh]) => {
    if (u < bx || u > bx + bw || v < by || v > by + bh) return false
    const cx = Math.min(Math.max(u, bx + RADIUS), bx + bw - RADIUS)
    const cy = Math.min(Math.max(v, by + RADIUS), by + bh - RADIUS)
    return (u - cx) ** 2 + (v - cy) ** 2 <= RADIUS ** 2
  })
}

function render(size) {
  const raw = Buffer.alloc((size * 3 + 1) * size)
  for (let y = 0; y < size; y++) {
    raw[y * (size * 3 + 1)] = 0
    for (let x = 0; x < size; x++) {
      let hits = 0
      for (let sy = 0; sy < SAMPLES; sy++) {
        for (let sx = 0; sx < SAMPLES; sx++) {
          if (inside(((x + (sx + 0.5) / SAMPLES) / size) * 100, ((y + (sy + 0.5) / SAMPLES) / size) * 100)) hits++
        }
      }
      const cover = hits / (SAMPLES * SAMPLES)
      const i = y * (size * 3 + 1) + 1 + x * 3
      for (let channel = 0; channel < 3; channel++) {
        raw[i + channel] = Math.round(BG[channel] + (FG[channel] - BG[channel]) * cover)
      }
    }
  }
  const header = Buffer.alloc(13)
  header.writeUInt32BE(size, 0)
  header.writeUInt32BE(size, 4)
  header[8] = 8
  header[9] = 2
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

writeFileSync('public/icon-192.png', render(192))
writeFileSync('public/icon-512.png', render(512))
writeFileSync('public/apple-touch-icon.png', render(180))
