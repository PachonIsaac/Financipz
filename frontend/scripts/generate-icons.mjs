// Generates the PNG app icons in public/ with no external dependencies.
// Usage: node scripts/generate-icons.mjs
import { deflateSync } from 'node:zlib'
import { writeFileSync } from 'node:fs'

const BG = [11, 18, 32]
const FG = [52, 211, 153]

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

// Three rising bars on a dark background, drawn in a 100x100 design space.
const BARS = [
  [24, 54, 14, 24],
  [43, 40, 14, 38],
  [62, 24, 14, 54],
]

function render(size) {
  const raw = Buffer.alloc((size * 3 + 1) * size)
  for (let y = 0; y < size; y++) {
    raw[y * (size * 3 + 1)] = 0
    for (let x = 0; x < size; x++) {
      const u = ((x + 0.5) / size) * 100
      const v = ((y + 0.5) / size) * 100
      const inBar = BARS.some(([bx, by, bw, bh]) => u >= bx && u < bx + bw && v >= by && v < by + bh)
      const color = inBar ? FG : BG
      const i = y * (size * 3 + 1) + 1 + x * 3
      raw[i] = color[0]
      raw[i + 1] = color[1]
      raw[i + 2] = color[2]
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
