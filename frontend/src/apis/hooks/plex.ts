import {
  useMutation,
  useQuery,
  useQueryClient,
  UseQueryOptions,
} from "@tanstack/react-query";
import { QueryKeys } from "@/apis/queries/keys";
import api from "@/apis/raw";

export const usePlexAuthValidationQuery = () => {
  return useQuery({
    queryKey: [QueryKeys.Plex, "auth", "validate"],
    queryFn: async () => {
      try {
        const result = await api.plex.validateAuth();
        return result;
      } catch (error) {
        // Return a default value when API is not available
        return {
          valid: false,
          // eslint-disable-next-line camelcase
          auth_method: "oauth",
          error: "API unavailable",
        };
      }
    },
    staleTime: 1000 * 60 * 5,
    throwOnError: false,
    retry: 1,
  });
};

export const usePlexServersQuery = <TData = Plex.Server[]>(
  options?: Partial<
    UseQueryOptions<Plex.Server[], Error, TData, (string | boolean)[]>
  > & { enabled?: boolean },
) => {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: [QueryKeys.Plex, "servers"],
    queryFn: () => api.plex.servers(),
    enabled,
    staleTime: 1000 * 60 * 2,
    ...options,
  });
};

export const usePlexSelectedServerQuery = <TData = Plex.Server>(
  options?: Partial<
    UseQueryOptions<Plex.Server, Error, TData, (string | boolean)[]>
  > & { enabled?: boolean },
) => {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: [QueryKeys.Plex, "selectedServer"],
    queryFn: () => api.plex.selectedServer(),
    enabled,
    staleTime: 1000 * 60 * 5,
    ...options,
  });
};

export const usePlexPinMutation = () => {
  return useMutation({
    mutationFn: () => api.plex.createPin(),
  });
};

export const usePlexPinCheckQuery = (
  pinId: string | null,
  enabled: boolean,
  refetchInterval: number | false,
) => {
  return useQuery({
    queryKey: [QueryKeys.Plex, "pinCheck", pinId],
    queryFn: () => {
      if (!pinId) throw new Error("Pin ID is required");
      return api.plex.checkPin(pinId);
    },
    enabled: enabled && !!pinId,
    retry: false,
    refetchInterval: refetchInterval,
    refetchOnWindowFocus: false,
    staleTime: 0, // Always fresh for polling
  });
};

export const usePlexLogoutMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.plex.logout(),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex],
      });

      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.System],
      });
    },
  });
};

export const usePlexServerSelectionMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: {
      machineIdentifier: string;
      name: string;
      uri: string;
      local: boolean;
    }) =>
      api.plex.selectServer({
        machineIdentifier: params.machineIdentifier,
        name: params.name,
        uri: params.uri,
        local: params.local,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "selectedServer"],
      });
    },
  });
};

export const usePlexLibrariesQuery = <TData = Plex.Library[]>(
  options?: Partial<
    UseQueryOptions<Plex.Library[], Error, TData, (string | boolean)[]>
  > & { enabled?: boolean },
) => {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: [QueryKeys.Plex, "libraries"],
    queryFn: () => api.plex.libraries(),
    enabled,
    staleTime: 1000 * 60 * 5, // Cache for 5 minutes
    refetchOnWindowFocus: false, // Don't refetch on window focus
    ...options,
  });
};

export const usePlexWebhookCreateMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.plex.createWebhook(),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "webhooks"],
      });
    },
  });
};

export const usePlexWebhookListQuery = <TData = Plex.WebhookList>(
  options?: Partial<
    UseQueryOptions<Plex.WebhookList, Error, TData, (string | boolean)[]>
  > & { enabled?: boolean },
) => {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: [QueryKeys.Plex, "webhooks"],
    queryFn: () => api.plex.listWebhooks(),
    enabled,
    staleTime: 1000 * 60 * 2, // Cache for 2 minutes
    refetchOnWindowFocus: false,
    ...options,
  });
};

export const usePlexWebhookDeleteMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (webhookUrl: string) => api.plex.deleteWebhook(webhookUrl),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "webhooks"],
      });
    },
  });
};

// Sync Configuration Hooks
export const usePlexSyncSettingsQuery = <TData = Plex.SyncSettings>(
  options?: Partial<
    UseQueryOptions<Plex.SyncSettings, Error, TData, (string | boolean)[]>
  > & { enabled?: boolean },
) => {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: [QueryKeys.Plex, "sync", "settings"],
    queryFn: () => api.plex.getSyncSettings(),
    enabled,
    staleTime: 1000 * 60 * 2, // Cache for 2 minutes
    refetchOnWindowFocus: false,
    ...options,
  });
};

export const usePlexSyncSettingsMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (settings: Partial<Plex.SyncSettings>) =>
      api.plex.updateSyncSettings(settings),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "sync", "settings"],
      });
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "sync", "status"],
      });
    },
  });
};

export const usePlexSyncStatusQuery = <TData = Plex.SyncStatus>(
  options?: Partial<
    UseQueryOptions<Plex.SyncStatus, Error, TData, (string | boolean)[]>
  > & { enabled?: boolean; refetchInterval?: number },
) => {
  const enabled = options?.enabled ?? true;
  const refetchInterval = options?.refetchInterval ?? 30000; // 30 seconds default

  return useQuery({
    queryKey: [QueryKeys.Plex, "sync", "status"],
    queryFn: () => api.plex.getSyncStatus(),
    enabled,
    refetchInterval: refetchInterval,
    staleTime: 1000 * 15, // Consider data stale after 15 seconds
    refetchOnWindowFocus: true,
    ...options,
  });
};

export const usePlexSyncTriggerMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: {
      type: "full" | "incremental";
      library_id?: string;
    }) => api.plex.triggerSync(params),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "sync", "status"],
      });
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "sync", "history"],
      });
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "libraries", "management"],
      });
    },
  });
};

export const usePlexSyncHistoryQuery = <TData = Plex.SyncHistoryResponse>(
  params?: { page?: number; limit?: number },
  options?: Partial<
    UseQueryOptions<Plex.SyncHistoryResponse, Error, TData, (string | number)[]>
  > & { enabled?: boolean },
) => {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: [
      QueryKeys.Plex,
      "sync",
      "history",
      params?.page || 1,
      params?.limit || 25,
    ],
    queryFn: () => api.plex.getSyncHistory(params),
    enabled,
    staleTime: 1000 * 60 * 5, // Cache for 5 minutes
    refetchOnWindowFocus: false,
    ...options,
  });
};

export const usePlexLibraryManagementQuery = <TData = Plex.LibraryManagement[]>(
  options?: Partial<
    UseQueryOptions<
      Plex.LibraryManagement[],
      Error,
      TData,
      (string | boolean)[]
    >
  > & { enabled?: boolean },
) => {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: [QueryKeys.Plex, "libraries", "management"],
    queryFn: () => api.plex.getLibraryManagement(),
    enabled,
    staleTime: 1000 * 60 * 5, // Cache for 5 minutes
    refetchOnWindowFocus: false,
    ...options,
  });
};

export const usePlexLibrarySettingsMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: {
      libraryId: string;
      settings: Partial<Plex.LibrarySettings>;
    }) => api.plex.updateLibrarySettings(params.libraryId, params.settings),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "libraries", "management"],
      });
      void queryClient.invalidateQueries({
        queryKey: [QueryKeys.Plex, "sync", "status"],
      });
    },
  });
};
