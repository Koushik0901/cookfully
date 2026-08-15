import { apiRequest } from "../recipes/api";
import type { JobAccepted } from "../recipes/types";
import type { components } from "../../app/api/generated/schema";

export type ReferenceDataStatus = components["schemas"]["ReferenceDataStatusResponse"];
export type InstallUnit = "foundation_sr_legacy" | "branded";

export const referenceDataApi = {
  status() {
    return apiRequest<ReferenceDataStatus>("/reference-data/status");
  },
  install(datasets: InstallUnit[]) {
    return apiRequest<JobAccepted>("/reference-data/install", {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({ datasets }),
    });
  },
};