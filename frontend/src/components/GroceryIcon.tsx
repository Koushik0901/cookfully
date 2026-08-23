type Category = "produce"|"dairy"|"bakery"|"meat"|"pantry"|"frozen"|"beverage"|"household"|"other";
const MAP: Array<[Category, RegExp]> = [
  ["dairy", /\b(milk|cheese|yogurt|yoghurt|butter|cream|ghee|paneer)\b/i],
  ["produce", /\b(tomato|lettuce|apple|banana|spinach|onion|potato|herb|berry|berries|carrot|cucumber|avocado|kale|pepper|garlic|ginger|lemon|lime|corn)\b/i],
  ["bakery", /\b(bread|roll|bagel|croissant|bun|pita|dough|tortilla)\b/i],
  ["meat", /\b(chicken|beef|pork|fish|salmon|turkey|mutton|sausage|bacon|egg)\b/i],
  ["pantry", /\b(rice|pasta|oil|flour|sugar|salt|spice|lentil|chickpea|oat|quinoa|honey|vinegar|soy)\b/i],
  ["frozen", /\b(frozen|ice)\b/i],
  ["beverage", /\b(water|juice|wine|coffee|tea|soda|milkshake|smoothie)\b/i],
  ["household", /\b(paper|soap|detergent|foil|wrap)\b/i],
];
export function categoryFor(name: string): Category {
  const n = name.trim().toLowerCase();
  if (!n) return "other";
  for (const [cat, re] of MAP) if (re.test(n)) return cat;
  return "other";
}
import Produce from "../../public/media/grocery-icons/produce.svg?react";
import Dairy from "../../public/media/grocery-icons/dairy.svg?react";
import Bakery from "../../public/media/grocery-icons/bakery.svg?react";
import Meat from "../../public/media/grocery-icons/meat.svg?react";
import Pantry from "../../public/media/grocery-icons/pantry.svg?react";
import Frozen from "../../public/media/grocery-icons/frozen.svg?react";
import Beverage from "../../public/media/grocery-icons/beverage.svg?react";
import Household from "../../public/media/grocery-icons/household.svg?react";
import Other from "../../public/media/grocery-icons/other.svg?react";
const ICONS: Record<Category, React.ComponentType<React.SVGProps<SVGSVGElement>>> = { produce: Produce, dairy: Dairy, bakery: Bakery, meat: Meat, pantry: Pantry, frozen: Frozen, beverage: Beverage, household: Household, other: Other };
export function GroceryIcon({ name, className = "" }: { name: string; className?: string }) {
  const cat = categoryFor(name);
  const Icon = ICONS[cat];
  return <Icon className={`grocery-icon grocery-icon--${cat} ${className}`.trim()} aria-hidden="true" />;
}
