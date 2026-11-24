import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('seo_ai_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface Project {
  id: string;
  name: string;
  niche: string;
  target_country: string;
  target_language: string;
  target_audience?: string;
  status: string;
}

export interface ResearchRun {
  id: string;
  project_id: string;
  name: string;
  country_code: string;
  language_code: string;
  device: string;
  status: string;
  created_at: string;
}

export interface KeywordItem {
  id: string;
  original_keyword: string;
  normalized_keyword: string;
  cleaning_status: string;
  review_status: string;
  priority_score: number | null;
  priority_tier: string | null;
  priority_reasoning: string | null;
  metrics: Record<string, { value: number | null; data_status: string }>;
}

export interface ClusterMember {
  id: string;
  keyword_id: string;
  original_keyword?: string;
  role: string;
  similarity_score?: number | null;
}

export interface KeywordCluster {
  id: string;
  cluster_name: string;
  primary_keyword_id?: string | null;
  cluster_intent?: string | null;
  status: string;
  origin: string;
  version: number;
  clustering_reasoning: string;
  members: ClusterMember[];
}

export interface ContentBrief {
  id: string;
  cluster_id: string;
  version: number;
  origin: string;
  status: string;
  search_intent: string;
  suggested_seo_title: string;
  meta_description: string;
  h1: string;
  content_angle: string;
  sections: Array<{
    id: string;
    heading_level: number;
    heading_text: string;
    section_order: number;
    key_points: string[];
    target_keywords: string[];
  }>;
  faqs: Array<{
    id: string;
    question: string;
    answer_guidance: string;
    source_evidence: string;
  }>;
}

export interface WorkflowExecution {
  id: string;
  research_run_id: string;
  langgraph_thread_id: string;
  current_node: string | null;
  status: string;
  error_message: string | null;
}

export const authApi = {
  register: (email: string, password: string, full_name: string) =>
    apiClient.post('/auth/register', { email, password, full_name }),
  login: (email: string, password: string) =>
    apiClient.post<{ access_token: string }>('/auth/login', { email, password }),
  me: () => apiClient.get('/auth/me'),
};

export const projectsApi = {
  list: () => apiClient.get<Project[]>('/projects'),
  create: (payload: {
    name: string;
    niche: string;
    target_country: string;
    target_language: string;
    target_audience?: string;
  }) => apiClient.post<Project>('/projects', payload),
};

export const researchApi = {
  listRuns: (projectId: string) =>
    apiClient.get<ResearchRun[]>(`/projects/${projectId}/research-runs`),
  createRun: (projectId: string, name: string, seed_keywords: string[]) =>
    apiClient.post<ResearchRun>(`/projects/${projectId}/research-runs`, {
      name,
      seed_keywords: seed_keywords.map((seed_text) => ({ seed_text })),
    }),
  importFile: (runId: string, sourceCode: string, file: File) => {
    const form = new FormData();
    form.append('source_code', sourceCode);
    form.append('file', file);
    return apiClient.post(`/research-runs/${runId}/imports`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  cleanKeywords: (runId: string) => apiClient.post(`/research-runs/${runId}/clean`),
  listKeywords: (runId: string) =>
    apiClient.get<{ items: KeywordItem[]; total: number }>(`/research-runs/${runId}/keywords`),
  addKeyword: (runId: string, keyword: string) =>
    apiClient.post<KeywordItem>(`/research-runs/${runId}/keywords`, { keyword }),
  reviewKeyword: (keywordId: string, review_status: 'APPROVED' | 'REJECTED') =>
    apiClient.patch(`/keywords/${keywordId}/review`, { review_status }),
  runClustering: (runId: string) =>
    apiClient.post<KeywordCluster[]>(`/research-runs/${runId}/clusters/run`, {
      distance_threshold: 0.45,
    }),
  listClusters: (runId: string) =>
    apiClient.get<KeywordCluster[]>(`/research-runs/${runId}/clusters`),
  renameCluster: (clusterId: string, cluster_name: string) =>
    apiClient.patch<KeywordCluster>(`/clusters/${clusterId}/rename`, { cluster_name }),
  approveCluster: (clusterId: string) =>
    apiClient.post<KeywordCluster>(`/clusters/${clusterId}/approve`, {
      notes: 'Approved in UI',
    }),
  prioritize: (runId: string) => apiClient.post(`/research-runs/${runId}/prioritize`),
  generateBriefs: (runId: string) =>
    apiClient.post<ContentBrief[]>(`/research-runs/${runId}/briefs/generate`),
  listBriefs: (runId: string) =>
    apiClient.get<ContentBrief[]>(`/research-runs/${runId}/briefs`),
  editBrief: (
    briefId: string,
    payload: { suggested_seo_title?: string; meta_description?: string; h1?: string; content_angle?: string }
  ) => apiClient.patch<ContentBrief>(`/briefs/${briefId}`, payload),
  approveBrief: (briefId: string) =>
    apiClient.post<ContentBrief>(`/briefs/${briefId}/approve`, { feedback_notes: 'Approved in UI' }),
  startWorkflow: (runId: string) =>
    apiClient.post<WorkflowExecution>(`/research-runs/${runId}/workflow/start`, {
      use_async_worker: false,
    }),
  listWorkflows: (runId: string) =>
    apiClient.get<WorkflowExecution[]>(`/research-runs/${runId}/workflows`),
  resumeWorkflow: (executionId: string, decision: string) =>
    apiClient.post<WorkflowExecution>(`/workflows/${executionId}/resume`, {
      decision,
      use_async_worker: false,
    }),
  exportExcel: (runId: string) =>
    apiClient.post<Blob>(`/research-runs/${runId}/exports/excel`, {}, { responseType: 'blob' }),
  exportGoogleSheets: (runId: string) =>
    apiClient.post(`/research-runs/${runId}/exports/google-sheets`),
};
