import { useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  Paper,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { faRefresh, faPlay, faStop } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  usePlexSyncSettingsQuery,
  usePlexSyncSettingsMutation,
  usePlexSyncStatusQuery,
  usePlexSyncTriggerMutation,
} from "@/apis/hooks/plex";
import { useFormActions } from "@/pages/Settings/utilities/FormValues";
import styles from "@/pages/Settings/Plex/SyncConfigSection.module.scss";

const SyncConfigSection = () => {
  const [isLoading, setIsLoading] = useState(false);

  // Hooks for sync configuration
  const { data: syncSettings, refetch: refetchSettings } =
    usePlexSyncSettingsQuery();
  const { data: syncStatus, refetch: refetchStatus } = usePlexSyncStatusQuery();
  const { mutateAsync: updateSettings } = usePlexSyncSettingsMutation();
  const { mutateAsync: triggerSync } = usePlexSyncTriggerMutation();

  const { setValue } = useFormActions();

  // Handle sync configuration updates
  const handleSettingUpdate = async (key: string, value: any) => {
    try {
      setIsLoading(true);
      await updateSettings({ [key]: value });
      setValue(value, key);
      await refetchSettings();
    } catch (error) {
      console.error("Failed to update sync setting:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // Handle manual sync trigger
  const handleManualSync = async (syncType: "full" | "incremental") => {
    try {
      setIsLoading(true);
      await triggerSync({ type: syncType });
      await refetchStatus();
    } catch (error) {
      console.error("Failed to trigger sync:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // Sync frequency options
  const syncFrequencyOptions = [
    { value: "0", label: "Disabled" },
    { value: "300", label: "Every 5 minutes" },
    { value: "600", label: "Every 10 minutes" },
    { value: "900", label: "Every 15 minutes" },
    { value: "1800", label: "Every 30 minutes" },
    { value: "3600", label: "Every hour" },
    { value: "7200", label: "Every 2 hours" },
    { value: "21600", label: "Every 6 hours" },
    { value: "43200", label: "Every 12 hours" },
    { value: "86400", label: "Every 24 hours" },
  ];

  // Conflict resolution strategy options
  const conflictResolutionOptions = [
    { value: "plex_wins", label: "Plex Wins (Recommended)" },
    { value: "database_wins", label: "Database Wins" },
    { value: "merge_metadata", label: "Merge Metadata" },
    { value: "manual_review", label: "Manual Review" },
  ];

  const isEnabled = syncSettings?.sync_enabled || false;
  const currentStatus = syncStatus?.status || "unknown";
  const lastSync = syncStatus?.last_sync
    ? new Date(syncStatus.last_sync).toLocaleString()
    : "Never";
  const healthScore = syncStatus?.health_score || 0;

  return (
    <Paper withBorder radius="md" p="lg" className={styles.syncConfigSection}>
      <Stack gap="lg">
        <Group justify="space-between" align="center">
          <Title order={4}>Sync Configuration</Title>
          <ActionIcon
            variant="light"
            color="gray"
            size="lg"
            onClick={() => {
              void refetchSettings();
              void refetchStatus();
            }}
            title="Refresh sync status"
          >
            <FontAwesomeIcon icon={faRefresh} size="sm" />
          </ActionIcon>
        </Group>

        {/* Sync Status */}
        <Stack gap="sm">
          <Text fw={500}>Current Status</Text>
          <Group gap="md">
            <Badge
              color={
                currentStatus === "syncing"
                  ? "blue"
                  : currentStatus === "healthy"
                    ? "green"
                    : "gray"
              }
              variant="filled"
            >
              {currentStatus.charAt(0).toUpperCase() + currentStatus.slice(1)}
            </Badge>
            <Text size="sm" c="dimmed">
              Last sync: {lastSync}
            </Text>
            {healthScore > 0 && (
              <Badge
                color={
                  healthScore >= 80
                    ? "green"
                    : healthScore >= 60
                      ? "yellow"
                      : "red"
                }
                variant="light"
              >
                Health: {healthScore}%
              </Badge>
            )}
          </Group>
        </Stack>

        {/* Manual Sync Controls */}
        <Stack gap="sm">
          <Text fw={500}>Manual Sync</Text>
          <Group gap="sm">
            <Button
              variant="light"
              color="blue"
              size="sm"
              leftSection={<FontAwesomeIcon icon={faPlay} size="xs" />}
              onClick={() => handleManualSync("incremental")}
              loading={isLoading}
              disabled={!isEnabled}
            >
              Incremental Sync
            </Button>
            <Button
              variant="light"
              color="orange"
              size="sm"
              leftSection={<FontAwesomeIcon icon={faRefresh} size="xs" />}
              onClick={() => handleManualSync("full")}
              loading={isLoading}
              disabled={!isEnabled}
            >
              Full Sync
            </Button>
          </Group>
        </Stack>

        {/* Sync Configuration */}
        <Stack gap="md">
          <Text fw={500}>Configuration</Text>

          {/* Enable/Disable Sync */}
          <Switch
            label="Enable Plex Synchronization"
            description="Automatically sync content from Plex server"
            checked={isEnabled}
            onChange={(event) =>
              handleSettingUpdate("sync_enabled", event.currentTarget.checked)
            }
            disabled={isLoading}
          />

          {/* Sync Frequency */}
          <Select
            label="Sync Frequency"
            description="How often to perform incremental sync"
            data={syncFrequencyOptions}
            value={syncSettings?.sync_frequency_seconds?.toString() || "3600"}
            onChange={(value) =>
              handleSettingUpdate(
                "sync_frequency_seconds",
                parseInt(value || "3600"),
              )
            }
            disabled={isLoading || !isEnabled}
          />

          {/* Conflict Resolution Strategy */}
          <Select
            label="Conflict Resolution"
            description="How to handle conflicts when the same item is updated both in Plex and Bazarr"
            data={conflictResolutionOptions}
            value={syncSettings?.conflict_resolution_strategy || "plex_wins"}
            onChange={(value) =>
              handleSettingUpdate("conflict_resolution_strategy", value)
            }
            disabled={isLoading || !isEnabled}
          />

          {/* Retry Configuration */}
          <Group grow>
            <TextInput
              label="Max Retries"
              description="Maximum retry attempts for failed operations"
              type="number"
              min={0}
              max={10}
              value={syncSettings?.max_retries?.toString() || "3"}
              onChange={(event) =>
                handleSettingUpdate(
                  "max_retries",
                  parseInt(event.currentTarget.value) || 3,
                )
              }
              disabled={isLoading || !isEnabled}
            />
            <TextInput
              label="Retry Delay (seconds)"
              description="Initial delay between retries"
              type="number"
              min={1}
              max={300}
              value={syncSettings?.retry_delay_seconds?.toString() || "60"}
              onChange={(event) =>
                handleSettingUpdate(
                  "retry_delay_seconds",
                  parseInt(event.currentTarget.value) || 60,
                )
              }
              disabled={isLoading || !isEnabled}
            />
          </Group>

          {/* Batch Size Configuration */}
          <Group grow>
            <TextInput
              label="Batch Size"
              description="Number of items to process in each sync batch"
              type="number"
              min={1}
              max={1000}
              value={syncSettings?.batch_size?.toString() || "50"}
              onChange={(event) =>
                handleSettingUpdate(
                  "batch_size",
                  parseInt(event.currentTarget.value) || 50,
                )
              }
              disabled={isLoading || !isEnabled}
            />
            <TextInput
              label="Cache TTL (seconds)"
              description="How long to cache sync results"
              type="number"
              min={60}
              max={86400}
              value={syncSettings?.cache_ttl_seconds?.toString() || "3600"}
              onChange={(event) =>
                handleSettingUpdate(
                  "cache_ttl_seconds",
                  parseInt(event.currentTarget.value) || 3600,
                )
              }
              disabled={isLoading || !isEnabled}
            />
          </Group>
        </Stack>

        {/* Health Information */}
        {syncStatus?.health_issues && syncStatus.health_issues.length > 0 && (
          <Alert color="yellow" variant="light">
            <Text fw={500} mb="xs">
              Health Issues Detected:
            </Text>
            {syncStatus.health_issues.map((issue: string, index: number) => (
              <Text key={index} size="sm">
                • {issue}
              </Text>
            ))}
          </Alert>
        )}

        {/* Configuration Notes */}
        {isEnabled && (
          <Alert color="blue" variant="light">
            <Text fw={500} mb="xs">
              Configuration Notes:
            </Text>
            <Text size="sm">
              • Incremental sync uses Plex's updatedAt timestamps to detect
              changes
            </Text>
            <Text size="sm">
              • "Plex Wins" strategy is recommended to keep Plex as the source
              of truth
            </Text>
            <Text size="sm">
              • Failed operations are automatically retried with exponential
              backoff
            </Text>
          </Alert>
        )}
      </Stack>
    </Paper>
  );
};

export default SyncConfigSection;
