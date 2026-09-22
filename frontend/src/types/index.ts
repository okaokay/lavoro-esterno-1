// Shared domain types used across api/, hooks/ and routes/.
// Kept intentionally close to the backend Pydantic schemas so the two stay easy to reconcile.

// Matches the Postgres enum `user_role` in the backend exactly
// (backend/app/models/users.py) — "operator" here previously read "analyst",
// a naming mismatch that silently broke any frontend logic keyed on role.
export type UserRole = "admin" | "operator" | "viewer";

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  mfaEnabled: boolean;
  status: "active" | "suspended" | "invited";
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
}

// Login can succeed outright, require a second factor, or (for roles where
// 2FA is mandatory) require completing 2FA enrollment before anything else
// works — the caller discriminates on `status` to decide which step to show.
export type LoginResult =
  | { status: "authenticated"; tokens: AuthTokens; user: User; newBackupCodes?: string[] }
  | { status: "mfa_required"; mfaToken: string }
  | { status: "mfa_setup_required"; tokens: AuthTokens; user: User };

export type SourceStatus = "healthy" | "degraded" | "offline";
export type SourcePriority = "high" | "medium" | "low";
export type ScrapeFetchMode = "http" | "dynamic" | "stealth";
export type ScrapeSelectorType = "css" | "xpath";
export type AutomaticScrapingState = "waiting" | "pending" | "running" | "paused" | "disabled";
export type ScrapeIntervalUnit = "minutes" | "hours" | "days";

export interface Source {
  id: string;
  code: string;
  name: string;
  country: string;
  countryCode: string | null;
  status: SourceStatus;
  enabled: boolean;
  // Priorità reale della fonte (bug corretto: prima l'API non la
  // esponeva affatto, la colonna "Priority" della tabella fabbricava
  // un'etichetta High/Medium/Low da errorRate — mostrava il tasso di
  // errore travestito da priorità).
  priority: SourcePriority;
  lastRunAt: string | null;
  itemsLast24h: number;
  errorRate: number;
  consecutiveFailures: number;
  hasScrapeConfig: boolean;
  proxyPoolId: string | null;
  proxyPoolStatus: "direct" | "configured" | "healthy" | "disabled" | "unavailable";
  automaticScrapingEnabled: boolean;
  scrapeIntervalMinutes: number | null;
  nextScrapeAt: string | null;
  lastScheduledAt: string | null;
  lastCompletedScrapeAt: string | null;
  lastScheduleSkipReason: string | null;
  scheduleRevision: number;
  automaticScrapingState: AutomaticScrapingState;
}

export type ScrapeFieldExtractionMode = "value" | "keyValue" | "posterVideo" | "items";

export interface ScrapeItemFieldConfig {
  selector: string;
  selectorType?: ScrapeSelectorType;
  attribute: "text" | "href" | "src";
  sanitizeWithAi?: boolean;
}

export interface ScrapeFieldPaginationConfig {
  nextSelector: string;
  nextSelectorType?: ScrapeSelectorType;
  maxPages: number;
  maxItems: number;
}

export interface ScrapeFieldConfig {
  selector?: string | null;
  selectorType?: ScrapeSelectorType;
  attribute: string;
  multiple: boolean;
  extractionMode?: ScrapeFieldExtractionMode;
  containerSelector?: string | null;
  containerSelectorType?: ScrapeSelectorType;
  keySelector?: string | null;
  keySelectorType?: ScrapeSelectorType;
  keyAttribute?: string;
  valueSelector?: string | null;
  valueSelectorType?: ScrapeSelectorType;
  valueAttribute?: string;
  posterSelector?: string | null;
  posterSelectorType?: ScrapeSelectorType;
  posterAttribute?: string;
  videoSelector?: string | null;
  videoSelectorType?: ScrapeSelectorType;
  videoAttribute?: string;
  itemFields?: Record<string, ScrapeItemFieldConfig>;
  pagination?: ScrapeFieldPaginationConfig | null;
  sanitizeWithAi?: boolean;
}

export interface ScrapeConfig {
  startUrls: string[];
  adLinkSelector: string;
  adLinkSelectorType?: ScrapeSelectorType;
  nextPageSelector: string | null;
  nextPageSelectorType?: ScrapeSelectorType;
  maxPages: number;
  maxAdsPerRun: number;
  maxPagesEnabled?: boolean;
  maxAdsPerRunEnabled?: boolean;
  rateLimitSeconds: number;
  fetchMode?: ScrapeFetchMode;
  renderJs: boolean;
  userAgent?: string | null;
  solveCloudflare?: boolean;
  blockWebrtc?: boolean;
  hideCanvas?: boolean;
  realChrome?: boolean;
  blockAds?: boolean;
  waitSelector?: string | null;
  waitSelectorType?: ScrapeSelectorType;
  waitMs?: number | null;
  fields: Record<string, ScrapeFieldConfig>;
}

export interface SourceTransferItem {
  name: string;
  slug: string;
  baseUrl: string;
  priority: SourcePriority;
  countryCode?: string | null;
  scrapeConfig: ScrapeConfig | null;
  proxyPoolName: string | null;
  watermarkRemoval: WatermarkRemovalConfig;
}

export interface SourceTransferDocument {
  format: "lavoro-esterno-sources";
  version: 1;
  exportedAt: string;
  sources: SourceTransferItem[];
}

export interface SourceImportPreviewEntry {
  index: number;
  slug: string | null;
  name: string | null;
  status: "new" | "conflict" | "invalid";
  proxyPoolStatus: "none" | "resolved" | "missing";
  proxyPoolName: string | null;
  errors: string[];
  warnings: string[];
}

export interface SourceImportPreviewResult {
  valid: boolean;
  format: string | null;
  version: number | null;
  entries: SourceImportPreviewEntry[];
  globalErrors: string[];
}

export interface SourceImportResult {
  created: number;
  updated: number;
  skipped: number;
  warnings: string[];
}

export interface RobotsCheckResult {
  allowed: boolean;
  robotsTxtFound: boolean;
  checkedUrl: string;
}

export interface TestConfigResult {
  adUrlsFound: number;
  sampleUrl: string | null;
  extractedFields: Record<string, unknown> | null;
  warnings: string[];
  error: string | null;
  errorCode: ScrapeFailureCode | null;
  httpStatus: number | null;
  recommendedActions: string[];
  pagesVisited: number;
  configuredMaxPages: number;
  paginationMode: "none" | "href" | "click";
  paginationStopReason: string;
  uniqueAdsFound: number;
  fieldPagination: Record<string, FieldPaginationDiagnostic>;
}

export interface FieldPaginationDiagnostic {
  pagesVisited: number;
  itemsCollected: number;
  paginationMode: "none" | "href" | "click";
  stopReason: string;
  complete: boolean;
}

export type ScrapeFailureCode =
  | "anti_bot_blocked"
  | "proxy_pool_exhausted"
  | "robots_disallowed"
  | "fetch_failed"
  | "field_pagination_incomplete"
  | "content_sanitization_failed"
  | "content_sanitization_configuration"
  | "content_sanitization_timeout"
  | "content_sanitization_unavailable"
  | "content_sanitization_http_error"
  | "content_sanitization_invalid_response"
  | "content_sanitization_incomplete_response"
  | "content_sanitization_empty_output"
  | "content_sanitization_invalid_changed"
  | "content_sanitization_unchanged_mismatch"
  | "content_sanitization_numbers_changed";

export type ProxyScheme = "http" | "https" | "socks4" | "socks5";

export interface ProxyEndpoint {
  id: string;
  name: string;
  scheme: ProxyScheme;
  host: string;
  port: number;
  enabled: boolean;
  credentialConfigured: boolean;
  health: "healthy" | "cooldown" | "disabled";
  consecutiveFailures: number;
  cooldownUntil: string | null;
  lastUsedAt: string | null;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
}

export interface ProxyPool {
  id: string;
  name: string;
  enabled: boolean;
  proxyIds: string[];
  healthyCount: number;
  totalCount: number;
}

export interface ProxyTestResult {
  success: boolean;
  latencyMs: number;
  statusCategory: string;
  message: string;
}

export interface ProxyFeed {
  id: string;
  name: string;
  url: string;
  scheme: ProxyScheme;
  poolId: string;
  enabled: boolean;
  syncIntervalMinutes: number;
  headerNames: string[];
  lastSyncedAt: string | null;
  nextSyncAt: string | null;
  lastSyncStatus: string | null;
  lastSyncMessage: string | null;
  lastImportedCount: number;
}

export type ScrapingRunStatus = "queued" | "running" | "completed" | "failed" | "rate_limited";

export interface ScrapingActivity {
  id: string;
  sourceId: string;
  sourceName: string;
  sourceCode: string;
  status: ScrapingRunStatus;
  startedAt: string | null;
  durationSeconds: number | null;
  items: number | null;
  errors: number | null;
}

export interface DashboardKpis {
  totalRecords: number;
  totalRecordsDeltaPct: number;
  activeSources: number;
  activeSourcesHealthyPct: number;
  newRecordsToday: number;
  scrapingErrors: number;
  scrapingErrorsDelta: number;
  activeExports: number;
  rangeStart: string;
  rangeEnd: string;
  newRecordsInRange: number;
  newRecordsDeltaPct: number;
}

export interface DashboardRangeParams {
  start: string;
  end: string;
}

export interface SourceHealthBreakdown {
  healthy: number;
  rateLimited: number;
  error: number;
  total: number;
}

export type ActivityActor = "system" | "admin" | "scraper" | "ai";

export interface ActivityEvent {
  id: string;
  actor: ActivityActor;
  actorLabel: string;
  message: string;
  occurredAt: string;
}

export interface RecordSearchResult {
  id: string;
  phone: string;
  phoneVisibility: "clear" | "masked";
  canonicalTitle: string;
  sourcesCount: number;
  occurrencesCount: number;
  firstSeenAt: string;
  lastSeenAt: string;
  status: "verified" | "unverified" | "flagged";
}

export interface RecordSearchFilters {
  phone?: string;
  source?: string;
  status?: string;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}

export interface RecordSearchResponse {
  results: RecordSearchResult[];
  total: number;
  page: number;
  pageSize: number;
}

export interface RecordOverview {
  id: string;
  phone: string;
  phoneVisibility: "clear" | "masked";
  canonicalTitle: string;
  canonicalDescription: string;
  confidenceScore: number;
  sourcesCount: number;
  occurrencesCount: number;
  firstSeenAt: string;
  lastSeenAt: string;
  status: "verified" | "unverified" | "flagged";
  tags: string[];
  /** Snapshot canonico mantenuto per retrocompatibilita. */
  customFields: CustomFields;
  /** Valori valorizzati raccolti da tutte le occorrenze, con provenienza. */
  customFieldGroups: CustomFieldGroup[];
  contentRevision: number;
}

export type CustomFieldObject = Record<string, string>;
export type CustomFieldValue = string | string[] | CustomFieldObject | CustomFieldObject[] | null;
export type CustomFields = Record<string, CustomFieldValue>;

export interface CustomFieldSourceValue {
  value: CustomFieldValue;
  sourceId: string;
  sourceName: string;
  sourceCode: string;
  advertisementId: string;
  isCanonical: boolean;
}

export interface CustomFieldGroup {
  name: string;
  values: CustomFieldSourceValue[];
}

export interface RecordOccurrence {
  id: string;
  sourceName: string;
  sourceCode: string;
  title: string;
  url: string;
  scrapedAt: string;
  isCanonical: boolean;
  matchConfidence: number;
  customFields: CustomFields;
  revision: number;
  lastChangedAt: string;
  hasUpdates: boolean;
  listingPageNumber: number | null;
}

export interface RecordOccurrenceDetail extends RecordOccurrence {
  countryCode: string | null;
  description: string;
  phone: string;
  phoneVisibility: "clear" | "masked";
  status: string;
  firstSeenAt: string;
  lastSeenAt: string;
  media: RecordMedia[];
}

export interface IngestionSettings {
  publishBatchSize: number;
  revision: number;
  sanitizationProvider: "ollama";
  sanitizationModel: string;
}

export interface WebhookEndpoint {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  allSources: boolean;
  sourceIds: string[];
  phonePolicy: "clear" | "masked" | "excluded";
  secretConfigured: boolean;
  revision: number;
  createdAt: string;
  updatedAt: string;
}

export interface AdvertisementVersion {
  id: string;
  advertisementId: string;
  revision: number;
  scrapeRunId: string | null;
  changedFields: string[];
  snapshot: {
    title?: string | null;
    description?: string | null;
    customFields?: CustomFields;
    mediaHashes?: string[];
  };
  createdAt: string;
}

export type MediaSensitivity = "safe" | "explicit";

export interface RecordMedia {
  id: string;
  url: string;
  thumbnailUrl: string;
  type: "image" | "video";
  sensitivity: MediaSensitivity;
  sourceName: string;
  addedAt: string;
  classification: "safe" | "explicit" | "unclassified";
  classificationConfidence: number | null;
  safetySignals: {
    explicitContent?: boolean;
    explicitScore?: number;
    faceVisible?: boolean;
    faceScore?: number;
    watermarkPresent?: boolean;
    possibleMinorReview?: boolean;
  };
  reviewStatus: "not_required" | "required" | "reviewed";
  processingStatus: "pending" | "processing" | "ready" | "failed";
  displayUrl: string;
  originalUrl: string;
}

export interface WatermarkRemovalConfig {
  enabled: boolean;
  authorizationReference: string | null;
  regions: { x: number; y: number; width: number; height: number }[];
}

export interface RecordHistoryEvent {
  id: string;
  actor: ActivityActor;
  actorLabel: string;
  action: string;
  detail: string;
  occurredAt: string;
}

export interface RecordAiSummary {
  generatedAt: string | null;
  executiveSynthesis: string;
  unverifiedClaims: string[];
  forumChatter: string[];
  sourcesUsed: { name: string; url: string }[];
  provider: string;
  model: string;
  recordContentRevision: number;
  isStale: boolean;
}

// A single entry in the full version history (GET /records/{id}/ai-summary/versions),
// as opposed to RecordAiSummary which is only ever the latest one.
export interface RecordAiSummaryVersion extends RecordAiSummary {
  version: number;
}

export interface SummaryGenerationJob {
  id: string;
  recordId: string;
  status: "pending" | "processing" | "completed" | "failed";
  provider: string;
  model: string;
  providerConfigRevision: number | null;
  resultVersion: number | null;
  cacheHit: boolean;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  recordContentRevision: number;
}

export type AIProviderName =
  "ollama" | "openai" | "anthropic" | "google" | "groq" | "mistral" | "openrouter" | "custom_openai";

export interface AIProviderConfig {
  provider: AIProviderName;
  displayName: string;
  model: string;
  enabled: boolean;
  active: boolean;
  baseUrl: string | null;
  credentialConfigured: boolean;
  options: Record<string, string>;
  revision: number;
  lastTestedAt: string | null;
  lastTestSuccess: boolean | null;
}

export interface AISettings {
  activeProvider: AIProviderName;
  promptVersion: string;
  userDailyRequestLimit: number;
  providerRequestsPerMinute: number;
  globalDailyTokenBudget: number;
  revision: number;
  providers: AIProviderConfig[];
}

export interface AIModelCatalog {
  provider: AIProviderName;
  models: string[];
  cached: boolean;
}

export interface AIProviderTestResult {
  provider: AIProviderName;
  success: boolean;
  latencyMs: number;
  message: string;
}

export interface ScrapeError {
  id: string;
  url: string;
  errorMessage: string;
  errorCode: ScrapeFailureCode | null;
  createdAt: string;
}

export type ScrapeRunStatus = "pending" | "running" | "completed" | "failed";

export interface ScrapeRun {
  id: string;
  startedAt: string | null;
  finishedAt: string | null;
  queuedAt: string;
  triggerType: "manual" | "scheduled";
  scheduledFor: string | null;
  status: ScrapeRunStatus;
  itemsFound: number;
  itemsNew: number;
  itemsUpdated: number;
  itemsUnchanged: number;
  errorsCount: number;
  pagesVisited: number;
  paginationMode: "none" | "href" | "click";
  paginationStopReason: string | null;
  proxyAttemptsCount: number;
  proxyRotationsCount: number;
  proxyStopReason: string | null;
  errors: ScrapeError[];
}

export type ExportType = "text_only" | "complete_media" | "safe_complete";
export type ExportStatus = "pending" | "ready" | "processing" | "failed";

export interface ExportFilters {
  phone?: string;
  source?: string;
  status?: "verified" | "unverified" | "flagged";
  dateFrom?: string;
  dateTo?: string;
}

export interface ExportJob {
  id: string;
  type: ExportType;
  status: ExportStatus;
  progressPct: number;
  requestedBy: string;
  requestedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  expiresAt: string | null;
  recordCount: number;
  estimatedUncompressedBytes: number;
  archiveSizeBytes: number | null;
  phoneVisibility: "clear" | "masked";
  errorMessage: string | null;
  downloadUrl: string | null;
}

export interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  status: "active" | "suspended" | "invited";
  mfaEnabled: boolean;
  lastLoginAt: string | null;
  canViewClearPhone: boolean;
}

export interface ErasureRequest {
  id: string;
  recordId: string | null;
  status: "draft" | "pending" | "processing" | "completed" | "failed";
  reason: string;
  authorizationReference: string;
  impact: Record<string, number>;
  result: Record<string, unknown> | null;
  errorMessage: string | null;
  createdAt: string;
  confirmedAt: string | null;
  completedAt: string | null;
}

export interface SourcePriorityJob {
  id: string;
  sourceId: string;
  previousPriority: SourcePriority;
  requestedPriority: SourcePriority;
  status: "pending" | "processing" | "completed" | "failed" | "superseded";
  recordsTotal: number;
  recordsProcessed: number;
  canonicalsChanged: number;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
}

export interface SourcePriorityConfig {
  sourceId: string;
  name: string;
  code: string;
  status: SourceStatus;
  priority: SourcePriority;
  affectedRecords: number;
  latestJob: SourcePriorityJob | null;
}

export interface ClassifierSettings {
  modelName: string;
  modelVersion: string;
  safeThreshold: number;
  explicitThreshold: number;
  revision: number;
  stats: {
    classifications: Record<string, number>;
    processing: Record<string, number>;
    reviews: Record<string, number>;
  };
}

export interface OperationalNotification {
  id: string;
  kind: string;
  severity: "info" | "warning" | "error";
  title: string;
  message: string;
  link: string | null;
  isRead: boolean;
  createdAt: string;
}

export interface NotificationList {
  items: OperationalNotification[];
  unreadCount: number;
}

export interface SystemComponent {
  name: string;
  status: "healthy" | "degraded" | "unavailable";
  latencyMs: number | null;
  message: string | null;
}

export interface SystemStatus {
  status: "healthy" | "degraded" | "unavailable";
  checkedAt: string;
  components: SystemComponent[];
}

export interface Paginated<T> {
  results: T[];
  total: number;
  page: number;
  pageSize: number;
}
