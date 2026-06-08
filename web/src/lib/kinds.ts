// Presentation metadata per measurement kind. Bands and units come from the
// topology (crop bands + device unit); this only carries display label and the
// number of decimals to render. Unknown kinds fall back to a sane default.

export interface KindMeta {
  label: string;
  decimals: number;
}

const KINDS: Record<string, KindMeta> = {
  ph: { label: "pH", decimals: 2 },
  tds: { label: "TDS", decimals: 0 },
  ec: { label: "EC", decimals: 2 },
  temp: { label: "Water Temp", decimals: 1 },
  rh: { label: "Humidity", decimals: 0 },
  level: { label: "Level", decimals: 0 },
  co2: { label: "CO₂", decimals: 0 },
  par: { label: "PAR", decimals: 0 },
};

export function kindMeta(kind: string): KindMeta {
  return KINDS[kind] ?? { label: kind.toUpperCase(), decimals: 1 };
}
