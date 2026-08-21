const FALLBACKS = {
  breakfast: "/media/recipe-fallbacks/breakfast.jpg",
  grain: "/media/recipe-fallbacks/grain-bowl.jpg",
  savory: "/media/recipe-fallbacks/savory-skillet.jpg",
  fresh: "/media/recipe-fallbacks/fresh-produce.jpg",
} as const;

type FallbackKind = keyof typeof FALLBACKS;

const KEYWORDS: Array<[FallbackKind, RegExp]> = [
  ["breakfast", /\b(oat|oats|yogurt|yoghurt|breakfast|porridge|granola|cereal|smoothie|pancake|waffle|toast|berry|berries|banana bread|muffin)\b/i],
  ["grain", /\b(rice|grain|bowl|quinoa|couscous|lentil|chickpea|bean|farro|barley|pilaf|burrito|risotto)\b/i],
  ["fresh", /\b(salad|greens?|vegetable|veggie|tomato|cucumber|radish|citrus|slaw|salsa|guacamole|coleslaw|pico)\b/i],
  ["savory", /\b(stir|fry|skillet|curry|stew|pasta|noodle|soup|chicken|beef|pork|fish|salmon|tofu|dinner|burger|patty|seitan|steak|roast|meatball|lasagna|mac|cheese|bbq|taco|wrap|sandwich|bacon|wing|meatloaf|stroganoff|piccata|cutlet)\b/i],
];

function recipeFallbackKind(title: string): FallbackKind {
  const match = KEYWORDS.find(([, pattern]) => pattern.test(title));
  if (match) return match[0];
  const hash = [...title].reduce((total, character) => ((total * 31) + character.charCodeAt(0)) >>> 0, 0);
  const kinds = Object.keys(FALLBACKS) as FallbackKind[];
  return kinds[hash % kinds.length];
}

export function RecipeFallbackArt({ title, className = "" }: { title: string; className?: string }) {
  const kind = recipeFallbackKind(title);
  return <img className={`recipe-fallback-art ${className}`} src={FALLBACKS[kind]} alt="" loading="lazy" decoding="async" draggable={false} data-fallback-kind={kind} />;
}
