import { useQuery } from "@tanstack/react-query";

import { pantryApi } from "../pantry/api";
import { daysLeft } from "../pantry/expiry";

export function useExpiringPantry(threshold = 3, todayStr: string) {
  const q = useQuery({ queryKey: ["pantry-items"], queryFn: pantryApi.list });
  const expiring = (q.data ?? []).filter(
    (i) => i.expiresOn && daysLeft(i.expiresOn, todayStr) >= 0 && daysLeft(i.expiresOn, todayStr) <= threshold,
  );
  return { expiring, isLoading: q.isPending };
}
