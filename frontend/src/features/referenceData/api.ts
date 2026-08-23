import { apiRequest } from "../recipes/api";
import type { Job, JobAccepted } from "../recipes/types";

export type ReferenceDataRelease = {
  datasetType: string;
  releaseId: string;
  releasedOn: string;
  sourceUrl: string;
  license: string;
  reviewOverdue: boolean;
};

export type ReferenceDataStatus = {
  available: boolean;
  missing: string[];
  releases: ReferenceDataRelease[];
  requestedDatasets?: string[] | null;
  job?: Job | null;
};
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