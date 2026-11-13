// Generates the PWA icons as plain PNGs with no image dependency.
// Run once with `npm run icons`; the output in public/ is committed.
import { mkdirSync, writeFileSync } from "node:fs";
import { crc32, deflateSync } from "node:zlib";

const BG = [31, 42, 68];
const INK = [255, 255, 255];
// A pen squiggle in unit coordinates.
const LINE = [
  [0.22, 0.62], [0.36, 0.34], [0.48, 0.64], [0.6, 0.36], [0.78, 0.6],
];

function distToSegment(px, py, [ax, ay], [bx, by]) {
  const dx = bx - ax, dy = by - ay;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}

function chunk(type, data) {
  const body = Buffer.concat([Buffer.from(type), data]);
  const out = Buffer.alloc(body.length + 8);
  out.writeUInt32BE(data.length, 0);
  body.copy(out, 4);
  out.writeUInt32BE(crc32(body), body.length + 4);
  return out;
}

function png(size) {
  const raw = Buffer.alloc(size * (size * 3 + 1));
  for (let y = 0; y < size; y++) {
    const row = y * (size * 3 + 1);
    for (let x = 0; x < size; x++) {
      const u = (x + 0.5) / size, v = (y + 0.5) / size;
      let d = Infinity;
      for (let i = 0; i < LINE.length - 1; i++) d = Math.min(d, distToSegment(u, v, LINE[i], LINE[i + 1]));
      // Anti-aliased stroke edge, one pixel wide.
      const a = Math.max(0, Math.min(1, (0.045 - d) * size + 0.5));
      for (let c = 0; c < 3; c++) raw[row + 1 + x * 3 + c] = Math.round(BG[c] + (INK[c] - BG[c]) * a);
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr.set([8, 2, 0, 0, 0], 8); // 8-bit RGB
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

mkdirSync("public", { recursive: true });
for (const [name, size] of [["icon-192.png", 192], ["icon-512.png", 512], ["apple-touch-icon.png", 180]]) {
  writeFileSync(`public/${name}`, png(size));
}
