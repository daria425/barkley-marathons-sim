export interface TerrainProfile {
  name: string;
  ground: string;
  trail: string;
  foliage: string;
  rock: string;
  width: number;
  curve: number;
  slope: number;
  trees: number;
  pine: number;
  grass: number;
  rocks: number;
  rockScale: number;
  brush: number;
  water: number;
  puddles: number;
  ridge: number;
}

const woodland: TerrainProfile = {
  name: "overgrown singletrack", ground: "#718263", trail: "#c8b38f", foliage: "#587652",
  rock: "#89887a", width: 1.6, curve: 0.65, slope: 0.015, trees: 0.7, pine: 0,
  grass: 1, rocks: 0.25, rockScale: 0.6, brush: 0.15, water: 0, puddles: 0, ridge: 0,
};

export const TERRAIN_PROFILES: Record<string, TerrainProfile> = {
  "gravel road, gentle climb": {
    ...woodland, name: "gravel road, gentle climb", ground: "#7f8867", trail: "#b2ac96",
    width: 4.5, curve: 0.2, slope: 0.07, trees: 0.45, grass: 0.35, rocks: 0.55, rockScale: 0.25,
  },
  "thick briars": {
    ...woodland, name: "thick briars", ground: "#5d6945", trail: "#8c805c", foliage: "#687046",
    width: 1.1, trees: 0.3, grass: 0.65, brush: 1, rocks: 0.1,
  },
  "creek crossing": {
    ...woodland, name: "creek crossing", ground: "#657f65", trail: "#a7a58a",
    width: 2.6, trees: 0.35, grass: 0.65, rocks: 0.8, rockScale: 0.85, water: 1,
  },
  "steep scree": {
    ...woodland, name: "steep scree", ground: "#85847c", trail: "#a8a395", foliage: "#737c61",
    width: 2, curve: 0.3, slope: 0.2, trees: 0.04, grass: 0.07, rocks: 1, rockScale: 1.3, ridge: 0.55,
  },
  "overgrown singletrack": woodland,
  "pine thicket": {
    ...woodland, name: "pine thicket", ground: "#615f44", trail: "#9d8768", foliage: "#315849",
    width: 1.8, trees: 1, pine: 1, grass: 0.2, rocks: 0.25, brush: 0.1,
  },
  "rocky ridge line": {
    ...woodland, name: "rocky ridge line", ground: "#838978", trail: "#b2af9a",
    width: 1.8, curve: 0.6, trees: 0.06, grass: 0.2, rocks: 0.85, rockScale: 1.8, ridge: 1,
  },
  "muddy switchbacks": {
    ...woodland, name: "muddy switchbacks", ground: "#697451", trail: "#75604a",
    width: 2.6, curve: 3.2, slope: 0.1, trees: 0.45, grass: 0.5, rocks: 0.2, puddles: 1,
  },
  "thick brush, no trail in sight": {
    ...woodland, name: "thick brush, no trail in sight", ground: "#546d48", trail: "#546d48",
    width: 0, trees: 0.65, grass: 1.2, rocks: 0.25, brush: 1.3, curve: 0,
  },
};

export function terrainProfile(label?: string): TerrainProfile {
  return label && Object.hasOwn(TERRAIN_PROFILES, label) ? TERRAIN_PROFILES[label] : woodland;
}

export function seeded(index: number, salt: number) {
  const n = Math.sin(index * 127.1 + salt * 311.7) * 43758.5453;
  return n - Math.floor(n);
}
