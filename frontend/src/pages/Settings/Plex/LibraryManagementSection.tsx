import { useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Loader,
  NumberInput,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  faRefresh,
  faSync,
  faPlay,
  faStop,
  faCog,
  faExclamationTriangle,
  faCheck,
} from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  usePlexLibraryManagementQuery,
  usePlexLibrarySettingsMutation,
  usePlexSyncTriggerMutation,
} from "@/apis/hooks/plex";
import styles from "@/pages/Settings/Plex/LibraryManagementSection.module.scss";

const LibraryManagementSection = () => {
  const [expandedLibrary, setExpandedLibrary] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState<Record<string, boolean>>({});

  // Hooks for library management
  const {
    data: libraries = [],
    refetch: refetchLibraries,
    isLoading,
  } = usePlexLibraryManagementQuery();

  const { mutateAsync: updateLibrarySettings } =
    usePlexLibrarySettingsMutation();
  const { mutateAsync: triggerSync } = usePlexSyncTriggerMutation();

  // Handle library setting updates
  const handleLibrarySettingUpdate = async (
    libraryId: string,
    key: string,
    value: any,
  ) => {
    try {
      await updateLibrarySettings({
        libraryId,
        settings: { [key]: value },
      });
      await refetchLibraries();
    } catch (error) {
      console.error("Failed to update library setting:", error);
    }
  };

  // Handle library sync trigger
  const handleLibrarySync = async (libraryId: string) => {
    setIsSyncing((prev) => ({ ...prev, [libraryId]: true }));
    try {
      await triggerSync({ type: "incremental", library_id: libraryId } as any);
      await refetchLibraries();
    } catch (error) {
      console.error("Failed to trigger library sync:", error);
    } finally {
      setIsSyncing((prev) => ({ ...prev, [libraryId]: false }));
    }
  };

  // Handle bulk operations
  const handleBulkEnable = async (enable: boolean) => {
    const updates = libraries.map((library) =>
      updateLibrarySettings({
        libraryId: library.library_id,
        settings: { sync_enabled: enable },
      }),
    );

    try {
      await Promise.all(updates);
      await refetchLibraries();
    } catch (error) {
      console.error("Failed to update libraries:", error);
    }
  };

  const getStatusBadgeProps = (status: string, hasErrors: boolean) => {
    if (hasErrors) return { color: "red", label: "Error" };

    switch (status) {
      case "syncing":
        return { color: "blue", label: "Syncing" };
      case "idle":
        return { color: "green", label: "Ready" };
      case "error":
        return { color: "red", label: "Error" };
      default:
        return { color: "gray", label: "Unknown" };
    }
  };

  const formatLastSync = (lastSync?: string) => {
    if (!lastSync) return "Never";
    return new Date(lastSync).toLocaleString();
  };

  const priorityOptions = [
    { value: "1", label: "Highest" },
    { value: "2", label: "High" },
    { value: "3", label: "Normal" },
    { value: "4", label: "Low" },
    { value: "5", label: "Lowest" },
  ];

  if (isLoading) {
    return (
      <Paper withBorder radius="md" p="lg">
        <Group justify="center" p="xl">
          <Loader size="sm" />
          <Text>Loading library management...</Text>
        </Group>
      </Paper>
    );
  }

  const enabledLibraries = libraries.filter((lib) => lib.sync_enabled);
  const totalContent = libraries.reduce((acc, lib) => acc + lib.count, 0);
  const totalErrors = libraries.reduce((acc, lib) => acc + lib.error_count, 0);

  return (
    <Paper
      withBorder
      radius="md"
      p="lg"
      className={styles.libraryManagementSection}
    >
      <Stack gap="lg">
        {/* Header with bulk actions */}
        <Group justify="space-between" align="center">
          <Group align="center" gap="md">
            <Title order={4}>Library Management</Title>
            <Badge variant="light" color="blue">
              {enabledLibraries.length}/{libraries.length} enabled
            </Badge>
            {totalErrors > 0 && (
              <Badge variant="light" color="red">
                {totalErrors} errors
              </Badge>
            )}
          </Group>

          <Group gap="xs">
            <Button
              size="xs"
              variant="light"
              onClick={() => handleBulkEnable(true)}
              disabled={libraries.length === 0}
            >
              Enable All
            </Button>
            <Button
              size="xs"
              variant="light"
              color="gray"
              onClick={() => handleBulkEnable(false)}
              disabled={libraries.length === 0}
            >
              Disable All
            </Button>
            <ActionIcon
              variant="light"
              color="gray"
              onClick={() => refetchLibraries()}
              loading={isLoading}
              title="Refresh libraries"
            >
              <FontAwesomeIcon icon={faRefresh} size="sm" />
            </ActionIcon>
          </Group>
        </Group>

        {/* Summary stats */}
        {libraries.length > 0 && (
          <Group justify="space-around" className={styles.summaryStats}>
            <Stack gap={4} align="center">
              <Text size="xs" c="dimmed">
                Total Content
              </Text>
              <Text fw={600} size="lg">
                {totalContent.toLocaleString()}
              </Text>
            </Stack>
            <Stack gap={4} align="center">
              <Text size="xs" c="dimmed">
                Enabled Libraries
              </Text>
              <Text fw={600} size="lg">
                {enabledLibraries.length}
              </Text>
            </Stack>
            <Stack gap={4} align="center">
              <Text size="xs" c="dimmed">
                Sync Errors
              </Text>
              <Text fw={600} size="lg" c={totalErrors > 0 ? "red" : "gray"}>
                {totalErrors}
              </Text>
            </Stack>
          </Group>
        )}

        {/* Libraries table */}
        {libraries.length === 0 ? (
          <Alert color="blue" variant="light">
            No Plex libraries found. Make sure you're connected to a Plex server
            and have libraries configured.
          </Alert>
        ) : (
          <div className={styles.tableContainer}>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Library</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th>Items</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Last Sync</Table.Th>
                  <Table.Th>Priority</Table.Th>
                  <Table.Th>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {libraries.map((library) => {
                  const badgeProps = getStatusBadgeProps(
                    library.sync_status,
                    library.error_count > 0,
                  );
                  const isExpanded = expandedLibrary === library.library_id;

                  return (
                    <Table.Tr key={library.library_id}>
                      <Table.Td>
                        <Group gap="sm" align="center">
                          <Switch
                            size="sm"
                            checked={library.sync_enabled}
                            onChange={(event) =>
                              handleLibrarySettingUpdate(
                                library.library_id,
                                "sync_enabled",
                                event.currentTarget.checked,
                              )
                            }
                          />
                          <Stack gap={2}>
                            <Text fw={500} size="sm">
                              {library.name}
                            </Text>
                            <Text size="xs" c="dimmed">
                              {library.library_id}
                            </Text>
                          </Stack>
                        </Group>
                      </Table.Td>

                      <Table.Td>
                        <Badge variant="light" size="sm">
                          {library.type}
                        </Badge>
                      </Table.Td>

                      <Table.Td>
                        <Text fw={500}>{library.count.toLocaleString()}</Text>
                      </Table.Td>

                      <Table.Td>
                        <Group gap="xs">
                          <Badge
                            color={badgeProps.color}
                            variant="light"
                            size="sm"
                          >
                            {badgeProps.label}
                          </Badge>
                          {library.error_count > 0 && (
                            <Tooltip
                              label={`${library.error_count} sync errors`}
                            >
                              <FontAwesomeIcon
                                icon={faExclamationTriangle}
                                className={styles.errorIcon}
                              />
                            </Tooltip>
                          )}
                        </Group>
                      </Table.Td>

                      <Table.Td>
                        <Text size="sm" c="dimmed">
                          {formatLastSync(library.last_sync)}
                        </Text>
                      </Table.Td>

                      <Table.Td>
                        <Select
                          size="xs"
                          data={priorityOptions}
                          value={library.priority.toString()}
                          onChange={(value) =>
                            handleLibrarySettingUpdate(
                              library.library_id,
                              "priority",
                              parseInt(value || "3"),
                            )
                          }
                          disabled={!library.sync_enabled}
                          style={{ width: 100 }}
                        />
                      </Table.Td>

                      <Table.Td>
                        <Group gap="xs">
                          <Tooltip label="Sync this library">
                            <ActionIcon
                              size="sm"
                              variant="light"
                              color="blue"
                              onClick={() =>
                                handleLibrarySync(library.library_id)
                              }
                              loading={isSyncing[library.library_id]}
                              disabled={
                                !library.sync_enabled ||
                                library.sync_status === "syncing"
                              }
                            >
                              <FontAwesomeIcon icon={faPlay} size="xs" />
                            </ActionIcon>
                          </Tooltip>

                          <Tooltip label="Configure library settings">
                            <ActionIcon
                              size="sm"
                              variant="light"
                              color="gray"
                              onClick={() =>
                                setExpandedLibrary(
                                  isExpanded ? null : library.library_id,
                                )
                              }
                            >
                              <FontAwesomeIcon icon={faCog} size="xs" />
                            </ActionIcon>
                          </Tooltip>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </div>
        )}

        {/* Expanded library configuration */}
        {expandedLibrary && (
          <Card withBorder radius="sm" p="md" className={styles.expandedConfig}>
            {(() => {
              const library = libraries.find(
                (l) => l.library_id === expandedLibrary,
              );
              if (!library) return null;

              return (
                <Stack gap="md">
                  <Group justify="space-between" align="center">
                    <Text fw={600}>Settings for {library.name}</Text>
                    <ActionIcon
                      size="sm"
                      variant="subtle"
                      onClick={() => setExpandedLibrary(null)}
                    >
                      ×
                    </ActionIcon>
                  </Group>

                  <Group grow>
                    <Switch
                      label="Auto Subtitle Download"
                      description="Automatically download subtitles for new content"
                      checked={library.settings.auto_subtitle_download}
                      onChange={(event) =>
                        handleLibrarySettingUpdate(
                          library.library_id,
                          "auto_subtitle_download",
                          event.currentTarget.checked,
                        )
                      }
                      disabled={!library.sync_enabled}
                    />
                  </Group>

                  <Group grow>
                    <TextInput
                      label="Exclude Tags"
                      description="Comma-separated list of tags to exclude from sync"
                      value={library.settings.exclude_tags.join(", ")}
                      onChange={(event) =>
                        handleLibrarySettingUpdate(
                          library.library_id,
                          "exclude_tags",
                          event.currentTarget.value
                            .split(",")
                            .map((tag) => tag.trim())
                            .filter(Boolean),
                        )
                      }
                      disabled={!library.sync_enabled}
                      placeholder="tag1, tag2, tag3"
                    />
                  </Group>
                </Stack>
              );
            })()}
          </Card>
        )}

        {/* Configuration notes */}
        <Alert color="blue" variant="light">
          <Text fw={500} mb="xs">
            Library Management Notes:
          </Text>
          <Text size="sm">
            • Disabled libraries will not be synced or monitored for changes
          </Text>
          <Text size="sm">
            • Higher priority libraries (1-2) are synced first during bulk
            operations
          </Text>
          <Text size="sm">
            • Auto subtitle download requires language profiles to be configured
          </Text>
        </Alert>
      </Stack>
    </Paper>
  );
};

export default LibraryManagementSection;
