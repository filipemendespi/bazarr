import { useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Progress,
  Stack,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  faRefresh,
  faPlay,
  faCog,
  faExclamationTriangle,
} from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  usePlexAuthValidationQuery,
  usePlexSyncStatusQuery,
  usePlexSyncTriggerMutation,
} from "@/apis/hooks/plex";
import { Link } from "react-router-dom";
import styles from "@/pages/Dashboard/PlexSyncWidget.module.scss";

const PlexSyncWidget = () => {
  const [isTriggering, setIsTriggering] = useState(false);

  // Check if Plex is authenticated
  const { data: authData } = usePlexAuthValidationQuery();
  const isAuthenticated = Boolean(
    authData?.valid && authData?.auth_method === "oauth",
  );

  // Get sync status with live updates
  const {
    data: syncStatus,
    refetch: refetchStatus,
    isLoading: statusLoading,
  } = usePlexSyncStatusQuery({
    enabled: isAuthenticated,
    refetchInterval: 30000, // Refetch every 30 seconds
  });

  const { mutateAsync: triggerSync } = usePlexSyncTriggerMutation();

  // Don't render if not authenticated
  if (!isAuthenticated) {
    return null;
  }

  const handleQuickSync = async () => {
    setIsTriggering(true);
    try {
      await triggerSync({ type: "incremental" });
      await refetchStatus();
    } catch (error) {
      console.error("Failed to trigger quick sync:", error);
    } finally {
      setIsTriggering(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "syncing":
        return "blue";
      case "healthy":
        return "green";
      case "error":
        return "red";
      case "warning":
        return "yellow";
      default:
        return "gray";
    }
  };

  const getHealthColor = (score: number) => {
    if (score >= 80) return "green";
    if (score >= 60) return "yellow";
    return "red";
  };

  const formatLastSync = (lastSync?: string) => {
    if (!lastSync) return "Never";

    const date = new Date(lastSync);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  if (statusLoading && !syncStatus) {
    return (
      <Card withBorder padding="lg" className={styles.plexSyncWidget}>
        <Group justify="center" p="xl">
          <Loader size="sm" />
          <Text>Loading Plex sync status...</Text>
        </Group>
      </Card>
    );
  }

  const status = syncStatus?.status || "unknown";
  const healthScore = syncStatus?.health_score || 0;
  const hasIssues =
    syncStatus?.health_issues && syncStatus.health_issues.length > 0;
  const totalContent =
    (syncStatus?.total_movies || 0) +
    (syncStatus?.total_shows || 0) +
    (syncStatus?.total_episodes || 0);

  return (
    <Card withBorder padding="lg" className={styles.plexSyncWidget}>
      <Stack gap="md">
        {/* Header */}
        <Group justify="space-between" align="flex-start">
          <Group align="center" gap="sm">
            <Title order={4}>Plex Sync</Title>
            <Badge
              color={getStatusColor(status)}
              variant="filled"
              size="sm"
              className={styles.statusBadge}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </Badge>
            {hasIssues && (
              <Tooltip
                label={`${syncStatus?.health_issues?.length || 0} health issues detected`}
              >
                <FontAwesomeIcon
                  icon={faExclamationTriangle}
                  className={styles.warningIcon}
                />
              </Tooltip>
            )}
          </Group>

          <Group gap="xs">
            <Tooltip label="Refresh status">
              <ActionIcon
                variant="subtle"
                color="gray"
                size="sm"
                onClick={() => refetchStatus()}
                loading={statusLoading}
              >
                <FontAwesomeIcon icon={faRefresh} size="xs" />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Plex settings">
              <ActionIcon
                variant="subtle"
                color="gray"
                size="sm"
                component={Link}
                to="/settings/plex"
              >
                <FontAwesomeIcon icon={faCog} size="xs" />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>

        {/* Sync Progress */}
        {status === "syncing" &&
          syncStatus?.progress_percentage !== undefined && (
            <Stack gap="xs">
              <Group justify="space-between">
                <Text size="sm">
                  {syncStatus?.current_operation || "Syncing..."}
                </Text>
                <Text size="sm" c="dimmed">
                  {Math.round(syncStatus.progress_percentage)}%
                </Text>
              </Group>
              <Progress
                value={syncStatus.progress_percentage}
                color="blue"
                size="sm"
              />
            </Stack>
          )}

        {/* Stats */}
        <Group justify="space-between">
          <Stack gap="xs" className={styles.statGroup}>
            <Text size="xs" c="dimmed">
              Content
            </Text>
            <Text fw={600} size="lg">
              {totalContent.toLocaleString()}
            </Text>
            <Text size="xs" c="dimmed">
              {syncStatus?.total_movies || 0}M • {syncStatus?.total_shows || 0}S
              • {syncStatus?.total_episodes || 0}E
            </Text>
          </Stack>

          <Stack gap="xs" className={styles.statGroup}>
            <Text size="xs" c="dimmed">
              Health
            </Text>
            <Group gap="xs" align="center">
              <Text fw={600} size="lg" c={getHealthColor(healthScore)}>
                {healthScore}%
              </Text>
              {hasIssues && (
                <Badge color="yellow" size="xs" variant="dot">
                  {syncStatus?.health_issues?.length || 0}
                </Badge>
              )}
            </Group>
          </Stack>

          <Stack gap="xs" className={styles.statGroup}>
            <Text size="xs" c="dimmed">
              Errors
            </Text>
            <Text
              fw={600}
              size="lg"
              c={syncStatus?.sync_errors ? "red" : "gray"}
            >
              {syncStatus?.sync_errors || 0}
            </Text>
          </Stack>
        </Group>

        {/* Last Sync & Actions */}
        <Group justify="space-between" align="center">
          <Stack gap={4}>
            <Text size="xs" c="dimmed">
              Last sync
            </Text>
            <Text size="sm" fw={500}>
              {formatLastSync(syncStatus?.last_sync)}
            </Text>
          </Stack>

          <Button
            size="xs"
            variant="light"
            leftSection={<FontAwesomeIcon icon={faPlay} size="xs" />}
            onClick={handleQuickSync}
            loading={isTriggering || status === "syncing"}
            disabled={status === "syncing"}
          >
            Quick Sync
          </Button>
        </Group>

        {/* Health Issues Alert */}
        {hasIssues && (
          <Card withBorder radius="sm" p="xs" className={styles.issuesCard}>
            <Text size="xs" fw={500} c="orange" mb={4}>
              Recent Issues:
            </Text>
            {syncStatus?.health_issues?.slice(0, 2).map((issue, index) => (
              <Text key={index} size="xs" c="dimmed">
                • {issue}
              </Text>
            ))}
            {(syncStatus?.health_issues?.length || 0) > 2 && (
              <Text size="xs" c="dimmed">
                • +{(syncStatus?.health_issues?.length || 0) - 2} more issues
              </Text>
            )}
          </Card>
        )}
      </Stack>
    </Card>
  );
};

export default PlexSyncWidget;
