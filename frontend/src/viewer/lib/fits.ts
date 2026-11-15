// Minimal FITS reader for the small 2-D images science writes.
// Reads every image HDU (primary + IMAGE extensions); tables are skipped.

const BLOCK = 2880; // FITS files are made of 2880-byte blocks
const CARD = 80; // one header line

export interface FitsImage {
  name: string; // EXTNAME, or "PRIMARY"
  width: number; // NAXIS1
  height: number; // NAXIS2
  header: Record<string, string | number | boolean>;
  data: Float64Array; // row 0 = bottom row (FITS order)
}

// "VALUE / comment" -> typed value.
function parseValue(raw: string): string | number | boolean {
  const text = raw.trim();
  if (text.startsWith("'")) {
    const end = text.indexOf("'", 1);
    return text.slice(1, end < 0 ? undefined : end).trim();
  }
  const value = text.split("/")[0].trim();
  if (value === "T") return true;
  if (value === "F") return false;
  const n = Number(value);
  return Number.isNaN(n) ? value : n;
}

// Reads one header starting at `offset`. Returns the cards and where the data starts.
function readHeader(bytes: Uint8Array, offset: number) {
  const header: Record<string, string | number | boolean> = {};
  let pos = offset;
  for (;;) {
    if (pos + CARD > bytes.length) throw new Error("FITS header has no END card");
    const card = String.fromCharCode(...bytes.subarray(pos, pos + CARD));
    pos += CARD;
    const key = card.slice(0, 8).trim();
    if (key === "END") break;
    if (card[8] === "=" && key) header[key] = parseValue(card.slice(10));
  }
  const dataStart = Math.ceil(pos / BLOCK) * BLOCK;
  return { header, dataStart };
}

// Reads all 2-D image HDUs from a FITS file.
export function readFits(buffer: ArrayBuffer): FitsImage[] {
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  const images: FitsImage[] = [];
  let offset = 0;

  while (offset + BLOCK <= bytes.length) {
    const { header, dataStart } = readHeader(bytes, offset);
    const bitpix = Number(header.BITPIX);
    const naxis = Number(header.NAXIS ?? 0);
    const dims = Array.from({ length: naxis }, (_, i) => Number(header[`NAXIS${i + 1}`]));
    const count = naxis ? dims.reduce((a, b) => a * b, 1) : 0;
    const bytesPer = Math.abs(bitpix) / 8;
    // Tables also have a heap after the main data.
    const dataSize = (count * bytesPer + Number(header.PCOUNT ?? 0)) * Number(header.GCOUNT ?? 1);

    const isImage = offset === 0 || header.XTENSION === "IMAGE";
    if (isImage && naxis >= 2 && count > 0) {
      const scale = Number(header.BSCALE ?? 1);
      const zero = Number(header.BZERO ?? 0);
      const blank = header.BLANK;
      const data = new Float64Array(count);
      for (let i = 0; i < count; i++) {
        const p = dataStart + i * bytesPer;
        let v: number;
        if (bitpix === -32) v = view.getFloat32(p, false);
        else if (bitpix === -64) v = view.getFloat64(p, false);
        else if (bitpix === 16) v = view.getInt16(p, false);
        else if (bitpix === 32) v = view.getInt32(p, false);
        else if (bitpix === 8) v = view.getUint8(p);
        else throw new Error(`Unsupported BITPIX ${bitpix}`);
        // Integer images can mark missing pixels with BLANK.
        data[i] = bitpix > 0 && v === blank ? NaN : v * scale + zero;
      }
      images.push({
        name: String(header.EXTNAME ?? (offset === 0 ? "PRIMARY" : `HDU${images.length}`)).toUpperCase(),
        width: dims[0],
        height: dims[1],
        header,
        data,
      });
    }

    offset = dataStart + Math.ceil(dataSize / BLOCK) * BLOCK;
  }
  return images;
}

// Value under a screen pixel. The PNGs are flipped so north is up,
// so screen row y is FITS row (height - 1 - y).
export function valueAt(img: FitsImage, x: number, y: number): number {
  if (x < 0 || y < 0 || x >= img.width || y >= img.height) return NaN;
  return img.data[(img.height - 1 - y) * img.width + x];
}
