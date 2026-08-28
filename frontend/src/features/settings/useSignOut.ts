import { useMutation, useQueryClient } from "@tanstack/react-query";

import { accountApi } from "./api";
import { clearOfflineResponses } from "../../app/offlineCache";
import { markSessionKnown } from "../../app/pwa";

export function useSignOut() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: accountApi.signOut,
    onSuccess: async () => {
      markSessionKnown(false);
      await clearOfflineResponses();
      await queryClient.cancelQueries();
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== "owner-session",
      });
      queryClient.setQueryData(["owner-session"], false);
    },
  });
}
