/** Parse GPS strings like "48.4558756N, 19.2321186E" into { lat, lng }. */
export function parseGps(text) {
  if (!text) return null
  const m = text.match(/(-?\d+(?:\.\d+)?)\s*([NS])\s*,\s*(-?\d+(?:\.\d+)?)\s*([EW])/i)
  if (!m) return null
  let lat = parseFloat(m[1])
  let lng = parseFloat(m[3])
  if (/s/i.test(m[2])) lat = -lat
  if (/w/i.test(m[4])) lng = -lng
  if (Number.isNaN(lat) || Number.isNaN(lng)) return null
  return { lat, lng }
}
