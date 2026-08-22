import type { components } from "../app/api/generated/schema";

type Micronutrients = components["schemas"]["Micronutrients"];

function unavailable(unit: "g" | "mg" | "ug", usdaNutrientId: number) {
  return {
    value: null,
    unit,
    explicitZero: false,
    coverageRatio: "0",
    source: "unavailable" as const,
    mappingVersion: "usda-fdc-2026-04-v1",
    usdaNutrientId,
  };
}

export const unavailableMicronutrients: Micronutrients = {
  dietaryFiberG: unavailable("g", 1079),
  sodiumMg: unavailable("mg", 1093),
  potassiumMg: unavailable("mg", 1092),
  calciumMg: unavailable("mg", 1087),
  ironMg: unavailable("mg", 1089),
  magnesiumMg: unavailable("mg", 1090),
  vitaminCMg: unavailable("mg", 1162),
  vitaminDUg: unavailable("ug", 1114),
  vitaminB12Ug: unavailable("ug", 1178),
};
