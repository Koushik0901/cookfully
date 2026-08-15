import { apiRequest } from "../recipes/api";
import type { OnboardingAction, OnboardingState, ReferenceDataChoice } from "./types";

export const onboardingApi = {
  get() {
    return apiRequest<OnboardingState>("/owner/onboarding");
  },
  resolve(value: { state: "completed" | "dismissed"; firstAction?: OnboardingAction; referenceDataChoice?: ReferenceDataChoice; version: number }) {
    return apiRequest<OnboardingState>("/owner/onboarding", {
      method: "PUT",
      version: value.version,
      body: JSON.stringify({ ...value, referenceDataChoice: value.referenceDataChoice }),
    });
  },
};
