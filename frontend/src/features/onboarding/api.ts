import { apiRequest } from "../recipes/api";
import type { OnboardingAction, OnboardingState } from "./types";

export const onboardingApi = {
  get() {
    return apiRequest<OnboardingState>("/owner/onboarding");
  },
  resolve(value: { state: "completed" | "dismissed"; firstAction?: OnboardingAction; version: number }) {
    return apiRequest<OnboardingState>("/owner/onboarding", {
      method: "PUT",
      version: value.version,
      body: JSON.stringify(value),
    });
  },
};
