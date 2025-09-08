import { Stack } from "@mantine/core";
import { usePlexAuthValidationQuery } from "@/apis/hooks/plex";
import AuthSection from "./AuthSection";
import ServerSection from "./ServerSection";
import SyncConfigSection from "./SyncConfigSection";
import LibraryManagementSection from "./LibraryManagementSection";

export const PlexSettings = () => {
  const { data: authData } = usePlexAuthValidationQuery();

  const isAuthenticated = Boolean(
    authData?.valid && authData?.auth_method === "oauth",
  );

  return (
    <Stack gap="lg">
      <AuthSection />
      <ServerSection />
      {isAuthenticated && (
        <>
          <SyncConfigSection />
          <LibraryManagementSection />
        </>
      )}
    </Stack>
  );
};

export default PlexSettings;
