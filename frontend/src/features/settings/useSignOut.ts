import { useMutation, useQueryClient } from "@tanstack/react-query";

import { accountApi } from "./api";

export function useSignOut() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: accountApi.signOut,
    onSuccess: async () => {
      await queryClient.cancelQueries();
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== "owner-session",
      });
      queryClient.setQueryData(["owner-session"], false);
    },
  });
}
