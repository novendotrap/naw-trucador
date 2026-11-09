/** Temas / eventos — espejo liviano de core/theme_tags.py para filtrar en UI. */

export const THEMES = [
  {
    id: "halloween",
    label: "Halloween",
    emoji: "🎃",
    keywords: [
      "halloween", "hallo", "fantasma", "vamp", "zombie", "bruj", "calabaza",
      "murcielago", "esqueleto", "momia", "terror", "dracula", "franken",
    ],
  },
  {
    id: "navidad",
    label: "Navidad",
    emoji: "🎄",
    keywords: [
      "navidad", "christmas", "xmas", "noel", "reno", "elfo", "snow", "nieve",
      "invierno", "ginger", "regalo", "santa",
    ],
  },
  {
    id: "pascua",
    label: "Pascua",
    emoji: "🐣",
    keywords: ["pascua", "pascuas", "conejo", "huevo", "easter"],
  },
  {
    id: "sanvalentin",
    label: "San Valentín",
    emoji: "💕",
    keywords: ["sanval", "sanvalentin", "valent", "amor", "corazon", "heart", "cupido"],
  },
  {
    id: "piratas",
    label: "Piratas",
    emoji: "🏴‍☠️",
    keywords: ["pirata", "piratas", "barco", "tesoro", "corsario"],
  },
  {
    id: "espacial",
    label: "Espacial",
    emoji: "🚀",
    keywords: ["espacial", "space", "alien", "ovni", "astronaut", "planeta", "galaxia"],
  },
  {
    id: "mundial",
    label: "Deportes",
    emoji: "⚽",
    keywords: ["mundial", "futbol", "football", "copa", "gol", "deporte", "olimpi", "basket"],
  },
  {
    id: "playa",
    label: "Verano",
    emoji: "🏖️",
    keywords: ["playa", "verano", "summer", "bikini", "surf", "tropical", "piscina"],
  },
  {
    id: "fiesta",
    label: "Fiestas",
    emoji: "🎉",
    keywords: ["fiesta", "cumple", "aniversario", "party", "disco", "baile"],
  },
  {
    id: "egipto",
    label: "Egipto",
    emoji: "🏺",
    keywords: ["egipto", "egypt", "faraon", "piramide", "cleopatra"],
  },
  {
    id: "anime",
    label: "Anime",
    emoji: "✨",
    keywords: ["anime", "manga", "otaku", "kawaii", "neko", "sakura"],
  },
  {
    id: "fantasia",
    label: "Fantasía",
    emoji: "🪄",
    keywords: [
      "fantasia", "mago", "hada", "dragon", "unicornio", "castillo", "princesa",
      "caballero", "medieval", "varita",
    ],
  },
];

function norm(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9._\-/áéíóúñü]/gi, "");
}

export function themeById(id) {
  return THEMES.find((t) => t.id === id) || null;
}

export function textMatchesTheme(text, theme) {
  if (!theme) return true;
  const hay = norm(text);
  return theme.keywords.some((kw) => hay.includes(norm(kw)));
}

export function packMatchesTheme(pack, themeId) {
  const theme = themeById(themeId);
  if (!theme) return true;
  return textMatchesTheme(pack, theme);
}

export function itemMatchesTheme(pack, itemName, themeId) {
  const theme = themeById(themeId);
  if (!theme) return true;
  if (textMatchesTheme(pack, theme)) return true;
  return textMatchesTheme(itemName, theme);
}
