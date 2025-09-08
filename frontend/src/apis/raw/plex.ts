import BaseApi from "./base";

class NewPlexApi extends BaseApi {
  constructor() {
    super("/plex");
  }

  async createPin() {
    const response = await this.post<DataWrapper<Plex.Pin>>("/oauth/pin");

    return response.data;
  }

  async checkPin(pinId: string) {
    // TODO: Can this be replaced with params instead of passing a variable in the path?
    const response = await this.get<DataWrapper<Plex.PinCheckResult>>(
      `/oauth/pin/${pinId}/check`,
    );

    return response.data;
  }

  async logout() {
    await this.post(`/oauth/logout`);
  }

  async servers() {
    const response =
      await this.get<DataWrapper<Plex.Server[]>>(`/oauth/servers`);

    return response.data;
  }

  async selectServer(form: FormType.PlexSelectServer) {
    const response = await this.post<DataWrapper<Plex.Server>>(
      "/select-server",
      form,
    );

    return response.data;
  }
  async selectedServer() {
    const response = await this.get<DataWrapper<Plex.Server>>(`/select-server`);

    return response.data;
  }

  async validateAuth() {
    const response =
      await this.get<DataWrapper<Plex.ValidationResult>>(`/oauth/validate`);

    return response.data;
  }

  async libraries() {
    const response =
      await this.get<DataWrapper<Plex.Library[]>>(`/oauth/libraries`);

    return response.data;
  }

  async createWebhook() {
    const response =
      await this.post<DataWrapper<Plex.WebhookResult>>("/webhook/create");

    return response.data;
  }

  async listWebhooks() {
    const response =
      await this.get<DataWrapper<Plex.WebhookList>>("/webhook/list");

    return response.data;
  }

  async deleteWebhook(webhookUrl: string) {
    const response = await this.post<DataWrapper<Plex.WebhookResult>>(
      "/webhook/delete",
      // eslint-disable-next-line camelcase
      { webhook_url: webhookUrl },
    );

    return response.data;
  }

  // Sync Configuration APIs
  async getSyncSettings() {
    const response =
      await this.get<DataWrapper<Plex.SyncSettings>>("/sync/settings");
    return response.data;
  }

  async updateSyncSettings(settings: Partial<Plex.SyncSettings>) {
    const response = await this.post<DataWrapper<Plex.SyncSettings>>(
      "/sync/settings",
      settings,
    );
    return response.data;
  }

  async getSyncStatus() {
    const response =
      await this.get<DataWrapper<Plex.SyncStatus>>("/sync/status");
    return response.data;
  }

  async triggerSync(params: {
    type: "full" | "incremental";
    library_id?: string;
  }) {
    const response = await this.post<DataWrapper<Plex.SyncResult>>(
      "/sync/trigger",
      params,
    );
    return response.data;
  }

  async getSyncHistory(params?: { page?: number; limit?: number }) {
    const response = await this.get<DataWrapper<Plex.SyncHistoryResponse>>(
      "/sync/history",
      { params },
    );
    return response.data;
  }

  async getLibraryManagement() {
    const response = await this.get<DataWrapper<Plex.LibraryManagement[]>>(
      "/sync/libraries/manage",
    );
    return response.data;
  }

  async updateLibrarySettings(
    libraryId: string,
    settings: Partial<Plex.LibrarySettings>,
  ) {
    const response = await this.post<DataWrapper<Plex.LibrarySettings>>(
      `/sync/libraries/${libraryId}/settings`,
      settings,
    );
    return response.data;
  }
}

export default new NewPlexApi();
