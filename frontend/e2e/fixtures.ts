export const firstTimeOwner = {
  onboarding: { state: "pending", version: 1 },
  preferences: { timezone: "America/Vancouver", weekStartsOn: 1, version: 1 },
};

export function recipePhotoFixture(overrides: Record<string, unknown> = {}) {
  return {
    imageUrl: "/api/v1/media/fixture-photo",
    imageSrcSet: null,
    thumbnailCrop: { x: "0.000000", y: "0.000000", width: "1.000000", height: "1.000000" },
    ...overrides,
  };
}

export const organizationFixture = {
  favorite: true,
  collections: [{ id: "fixture-collection", name: "Weeknight favourites", position: 0, version: 1 }],
  mealRoles: ["dinner"],
};

export const twoStopGroceryFixture = {
  stops: [
    { id: "fixture-stop-market", name: "Market", position: 0, version: 1 },
    { id: "fixture-stop-pantry", name: "Pantry shop", position: 1, version: 1 },
  ],
};
