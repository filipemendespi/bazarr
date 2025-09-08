interface Badge {
  episodes: number;
  movies: number;
  providers: number;
  status: number;
  sonarr_signalr: string;
  radarr_signalr: string;
  announcements: number;
}

declare namespace Language {
  type CodeType = string;
  interface Server {
    code2: CodeType;
    code3: CodeType;
    name: string;
    enabled: boolean;
  }

  interface Info {
    code2: CodeType;
    name: string;
    hi?: boolean;
    forced?: boolean;
  }

  interface ProfileItem {
    id: number;
    audio_exclude: PythonBoolean;
    audio_only_include: PythonBoolean;
    forced: PythonBoolean;
    hi: PythonBoolean;
    language: CodeType;
  }

  interface Profile {
    name: string;
    profileId: number;
    cutoff: number | null;
    items: ProfileItem[];
    mustContain: string[];
    mustNotContain: string[];
    originalFormat: boolean | null;
    tag: string | undefined;
  }
}

interface Subtitle {
  code2: Language.CodeType;
  name: string;
  forced: boolean;
  hi: boolean;
  path: string | null | undefined; // TODO: FIX ME!!!!!!
}

interface AudioTrack {
  stream: string;
  name: string;
  language: string;
}

interface SubtitleTrack {
  stream: string;
  name: string;
  language: string;
  forced: boolean;
  hearing_impaired: boolean;
}

interface ExternalSubtitle {
  name: string;
  path: string;
  language: string;
  forced: boolean;
  hearing_impaired: boolean;
}

interface PathType {
  path: string;
}

interface SubtitlePathType {
  subtitles_path: string;
}

interface MonitoredType {
  monitored: boolean;
}

interface SubtitleType {
  subtitles: Subtitle[];
}

interface MissingSubtitleType {
  missing_subtitles: Subtitle[];
}

interface SceneNameType {
  sceneName?: string;
}

interface TagType {
  tags: string[];
}

interface SeriesIdType {
  sonarrSeriesId: number;
}

type EpisodeIdType = SeriesIdType & {
  sonarrEpisodeId: number;
};

interface EpisodeTitleType {
  seriesTitle: string;
  episodeTitle: string;
}

interface MovieIdType {
  radarrId: number;
}

interface TitleType {
  title: string;
}

interface AudioLanguageType {
  audio_language: Language.Info[];
}

interface ItemHistoryType {
  language: Language.Info;
  provider: string;
}

declare namespace Item {
  type Base = PathType &
    TitleType &
    TagType &
    MonitoredType &
    AudioLanguageType & {
      profileId: number | null;
      fanart: string;
      overview: string;
      imdbId: string;
      alternativeTitles: string[];
      poster: string;
      year: string;
    };

  type Series = Base &
    SeriesIdType & {
      episodeFileCount: number;
      episodeMissingCount: number;
      ended: boolean;
      lastAired: string;
      seriesType: SonarrSeriesType;
      tvdbId: number;
    };

  type Movie = Base &
    MovieIdType &
    SubtitleType &
    MissingSubtitleType &
    SceneNameType;

  type Episode = PathType &
    TitleType &
    MonitoredType &
    EpisodeIdType &
    SubtitleType &
    MissingSubtitleType &
    SceneNameType &
    AudioLanguageType & {
      season: number;
      episode: number;
    };

  type RefTracks = {
    audio_tracks: AudioTrack[];
    embedded_subtitles_tracks: SubtitleTrack[];
    external_subtitles_tracks: ExternalSubtitle[];
  };
}

declare namespace Wanted {
  type Base = MonitoredType &
    TagType &
    SceneNameType & {
      hearing_impaired: boolean;
      missing_subtitles: Subtitle[];
    };

  type Episode = Base &
    EpisodeIdType &
    EpisodeTitleType & {
      episode_number: string;
      seriesType: SonarrSeriesType;
    };

  type Movie = Base & MovieIdType & TitleType;
}

declare namespace Blacklist {
  type Base = ItemHistoryType & {
    parsed_timestamp: string;
    timestamp: string;
    subs_id: string;
  };

  type Movie = Base & MovieIdType & TitleType;

  type Episode = Base &
    EpisodeTitleType &
    SeriesIdType & {
      episode_number: string;
    };
}

declare namespace History {
  type Base = SubtitlePathType &
    TagType &
    MonitoredType &
    Partial<ItemHistoryType> & {
      action: number;
      blacklisted: boolean;
      score?: string;
      subs_id?: string;
      parsed_timestamp: string;
      timestamp: string;
      description: string;
      upgradable: boolean;
      matches: string[];
      dont_matches: string[];
    };

  type Movie = History.Base & MovieIdType & TitleType;

  type Episode = History.Base &
    EpisodeIdType &
    EpisodeTitleType & {
      episode_number: string;
    };

  type StatItem = {
    count: number;
    date: string;
  };

  type Stat = {
    movies: StatItem[];
    series: StatItem[];
  };

  type TimeFrameOptions = "week" | "month" | "trimester" | "year";
  type ActionOptions = 1 | 2 | 3;
}

declare namespace Parameter {
  interface Range {
    start: number;
    length: number;
  }
}

declare namespace Plex {
  interface Pin {
    pinId: string;
    code: string;
    clientId: string;
    authUrl: string;
  }

  interface ValidationResult {
    valid: boolean;
    auth_method?: string;
    username?: string;
    email?: string;
    error?: string;
    code?: string;
  }

  interface PinCheckResult {
    authenticated: boolean;
    username?: string;
    email?: string;
    error?: string;
  }

  interface ServerConnection {
    uri: string;
    protocol: string;
    address: string;
    port: number;
    local: boolean;
    available?: boolean;
    latency?: number;
  }

  interface Server {
    name: string;
    machineIdentifier: string;
    connections: ServerConnection[];
    version: string;
    platform: string;
    device: string;
    bestConnection?: ServerConnection | null;
  }

  interface Library {
    key: string;
    title: string;
    type: string;
    count: number;
    agent: string;
    scanner: string;
    language: string;
    uuid: string;
    updatedAt: number;
    createdAt: number;
  }

  interface WebhookResult {
    success: boolean;
    message: string;
    webhook_url?: string;
    total_webhooks?: number;
  }

  interface WebhookInfo {
    url: string;
  }

  interface WebhookList {
    webhooks: WebhookInfo[];
    count: number;
  }

  // Sync Configuration Types
  interface SyncSettings {
    sync_enabled: boolean;
    sync_frequency_seconds: number;
    conflict_resolution_strategy:
      | "plex_wins"
      | "database_wins"
      | "merge_metadata"
      | "manual_review";
    max_retries: number;
    retry_delay_seconds: number;
    batch_size: number;
    cache_ttl_seconds: number;
    webhook_enabled: boolean;
    full_sync_on_startup: boolean;
    incremental_sync_enabled: boolean;
    health_check_enabled: boolean;
  }

  interface SyncStatus {
    status: "idle" | "syncing" | "healthy" | "error" | "warning" | "unknown";
    last_sync?: string;
    next_sync?: string;
    sync_in_progress: boolean;
    current_operation?: string;
    progress_percentage?: number;
    health_score: number;
    health_issues: string[];
    total_movies: number;
    total_shows: number;
    total_episodes: number;
    sync_errors: number;
    cache_hit_rate: number;
  }

  interface SyncResult {
    success: boolean;
    message: string;
    sync_id?: string;
    started_at: string;
    estimated_duration?: number;
  }

  interface SyncHistoryItem {
    id: string;
    sync_type: "full" | "incremental";
    started_at: string;
    completed_at?: string;
    status: "running" | "completed" | "failed" | "cancelled";
    items_processed: number;
    items_added: number;
    items_updated: number;
    items_removed: number;
    errors: number;
    duration_seconds?: number;
    error_message?: string;
  }

  interface SyncHistoryResponse {
    items: SyncHistoryItem[];
    total: number;
    page: number;
    limit: number;
    has_next: boolean;
    has_prev: boolean;
  }

  interface LibrarySettings {
    library_id: string;
    sync_enabled: boolean;
    priority: number;
    auto_subtitle_download: boolean;
    language_profiles: string[];
    exclude_tags: string[];
    last_sync?: string;
  }

  interface LibraryManagement {
    library_id: string;
    name: string;
    type: string;
    count: number;
    sync_enabled: boolean;
    last_sync?: string;
    sync_status: "idle" | "syncing" | "error";
    error_count: number;
    priority: number;
    settings: LibrarySettings;
  }
}

interface SearchResultType {
  matches: string[];
  dont_matches: string[];
  language: string;
  forced: PythonBoolean;
  hearing_impaired: PythonBoolean;
  orig_score: number;
  provider: string;
  release_info: string[];
  score: number;
  score_without_hash: number;
  subtitle: unknown;
  uploader?: string;
  url?: string;
  original_format: PythonBoolean;
}

interface ReleaseInfo {
  current: boolean;
  date: string;
  name: string;
  prerelease: boolean;
  body: string[];
}

interface SubtitleInfo {
  filename: string;
  episode: number;
  season: number;
}

type ItemSearchResult = Partial<SeriesIdType> &
  Partial<MovieIdType> & {
    title: string;
    year: string;
    poster: string;
  };

type BackendError = {
  code: number;
  message: string;
};
