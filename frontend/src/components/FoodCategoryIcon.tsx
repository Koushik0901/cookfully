/* eslint-disable react-refresh/only-export-components */
import type { ImgHTMLAttributes } from "react";

export type Category =
  | "leafy-greens"
  | "grains-rice"
  | "dairy-milk"
  | "fruit"
  | "vegetables"
  | "pantry-sauce"
  | "bread-bakery"
  | "protein-chicken"
  | "herbs-spices"
  | "beverages-drinks"
  | "seafood"
  | "eggs"
  | "snacks";

const CATEGORY_RULES: Array<[Category, RegExp]> = [
  [
    "vegetables",
    /\b(frozen vegetables?|tomato(?:es)?|carrot(?:s)?|potato(?:es)?|broccoli|cauliflower|celery|cucumber|zucchini|pepper(?:s)?|mushroom(?:s)?|eggplant|corn|peas|beans|cabbage|asparagus|radish|leek)\b/i,
  ],
  ["beverages-drinks", /\b(milkshake|smoothie|water|coffee|tea|soda|juice|wine|beer|drink|beverage)\b/i],
  ["eggs", /\beggs?\b/i],
  ["seafood", /\b(fish|salmon|shrimp|tuna|cod|seafood)\b/i],
  ["protein-chicken", /\b(chicken|beef|pork|turkey|tofu|meat|sausage|bacon)\b/i],
  ["dairy-milk", /\b(milk|cheese|yogurt|yoghurt|butter|cream|ghee|paneer)\b/i],
  ["leafy-greens", /\b(spinach|lettuce|kale|arugula|collard|chard|greens)\b/i],
  ["herbs-spices", /\b(herb|basil|cilantro|coriander|parsley|mint|oregano|rosemary|thyme|spice)\b/i],
  [
    "fruit",
    /\b(apples?|bananas?|berry|berries|strawberr(?:y|ies)|blueberr(?:y|ies)|raspberr(?:y|ies)|grapes?|lemons?|limes?|oranges?|avocados?|melons?|peach(?:es)?|pears?|fruit)\b/i,
  ],
  ["bread-bakery", /\b(bread|roll|bagel|croissant|bun|pita|dough|tortilla|bakery)\b/i],
  ["pantry-sauce", /\b(sauce|canned|can|oil|vinegar|condiment|honey|syrup|sugar|salt|lentil|chickpea|bean)\b/i],
  ["grains-rice", /\b(rice|pasta|flour|oat(?:s|meal)?|quinoa|barley|couscous|cereal|grain)\b/i],
  ["snacks", /\b(snack|chip|cracker|nut|nuts|granola|popcorn|pretzel)\b/i],
];

const ASSET_CATEGORIES: Record<Category, string> = {
  "leafy-greens": "leafy-greens",
  "grains-rice": "grains-rice",
  "dairy-milk": "dairy-milk",
  fruit: "fruit",
  vegetables: "vegetables",
  "pantry-sauce": "pantry-sauce",
  "bread-bakery": "bread-bakery",
  "protein-chicken": "protein-chicken",
  "herbs-spices": "herbs-spices",
  "beverages-drinks": "beverages-drinks",
  seafood: "seafood",
  eggs: "eggs",
  snacks: "snacks",
};

export function categoryFor(name: string): Category {
  const normalized = name.trim();
  for (const [category, rule] of CATEGORY_RULES) if (rule.test(normalized)) return category;
  return "pantry-sauce";
}

const SIZE_CLASS: Record<NonNullable<FoodCategoryIconProps["size"]>, string> = {
  compact: "grocery-icon--size-compact",
  row: "grocery-icon--size-row",
  tile: "grocery-icon--size-tile",
};

export type FoodCategoryIconProps = {
  name: string;
  size?: "compact" | "row" | "tile";
  className?: string;
};

export function FoodCategoryIcon({ name, size = "compact", className = "" }: FoodCategoryIconProps) {
  const category = categoryFor(name);
  const asset = ASSET_CATEGORIES[category];
  const attrs: ImgHTMLAttributes<HTMLImageElement> = {
    className: `grocery-icon grocery-icon--${category} ${SIZE_CLASS[size]} ${className}`.trim(),
    src: `/media/grocery-icons/${asset}-64.png`,
    srcSet: `/media/grocery-icons/${asset}-64.png 64w, /media/grocery-icons/${asset}.png 256w`,
    sizes: size === "tile" ? "48px" : size === "row" ? "40px" : "32px",
    alt: "",
    "aria-hidden": true,
  };
  return <img {...attrs} />;
}
