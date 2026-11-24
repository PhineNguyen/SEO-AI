import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { useParams } from 'react-router-dom';
import {
  ContentBrief,
  KeywordCluster,
  KeywordItem,
  researchApi,
  WorkflowExecution,
} from '../services/api';

export const ResearchWorkspacePage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [tab, setTab] = useState(0);
  const [keywords, setKeywords] = useState<KeywordItem[]>([]);
  const [clusters, setClusters] = useState<KeywordCluster[]>([]);
  const [briefs, setBriefs] = useState<ContentBrief[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowExecution | null>(null);
  const [newKeyword, setNewKeyword] = useState('');
  const [sourceCode, setSourceCode] = useState('gkp_csv');
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const refreshAll = useCallback(async () => {
    if (!runId) return;
    const [kwRes, clRes, brRes, wfRes] = await Promise.all([
      researchApi.listKeywords(runId),
      researchApi.listClusters(runId),
      researchApi.listBriefs(runId),
      researchApi.listWorkflows(runId),
    ]);
    setKeywords(kwRes.data.items);
    setClusters(clRes.data);
    setBriefs(brRes.data);
    setWorkflow(wfRes.data[0] || null);
  }, [runId]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!runId || !e.target.files?.[0]) return;
    await researchApi.importFile(runId, sourceCode, e.target.files[0]);
    setStatusMsg('File imported successfully.');
    await refreshAll();
  };

  const handleExcelDownload = async () => {
    if (!runId) return;
    const resp = await researchApi.exportExcel(runId);
    const url = window.URL.createObjectURL(new Blob([resp.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `research_run_${runId}.xlsx`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    setStatusMsg('7-sheet Excel workbook downloaded.');
  };

  const keywordCols: GridColDef<KeywordItem>[] = [
    { field: 'original_keyword', headerName: 'Keyword', flex: 1.5 },
    { field: 'cleaning_status', headerName: 'Cleaning', width: 130 },
    { field: 'review_status', headerName: 'Review 1', width: 120 },
    {
      field: 'priority_score',
      headerName: 'Priority',
      width: 110,
      valueGetter: (_v, row) => row.priority_score ?? 'N/A',
    },
    { field: 'priority_tier', headerName: 'Tier', width: 100 },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 200,
      renderCell: (params) => (
        <Stack direction="row" spacing={1} alignItems="center" height="100%">
          <Button
            size="small"
            variant="outlined"
            color="success"
            onClick={async () => {
              await researchApi.reviewKeyword(params.row.id, 'APPROVED');
              await refreshAll();
            }}
          >
            Approve
          </Button>
          <Button
            size="small"
            variant="outlined"
            color="error"
            onClick={async () => {
              await researchApi.reviewKeyword(params.row.id, 'REJECTED');
              await refreshAll();
            }}
          >
            Reject
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Box>
          <Typography variant="h5" fontWeight={700}>
            Research Workspace
          </Typography>
          {workflow && (
            <Stack direction="row" spacing={1} mt={1} alignItems="center">
              <Chip label={`Workflow: ${workflow.status}`} color="primary" size="small" />
              {workflow.status.startsWith('WAITING_REVIEW') && (
                <Button
                  size="small"
                  variant="contained"
                  color="secondary"
                  onClick={async () => {
                    await researchApi.resumeWorkflow(workflow.id, 'APPROVE');
                    setStatusMsg(`Resumed workflow from ${workflow.status}.`);
                    await refreshAll();
                  }}
                >
                  Approve Gate & Resume
                </Button>
              )}
            </Stack>
          )}
        </Box>

        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            onClick={async () => {
              if (!runId) return;
              await researchApi.startWorkflow(runId);
              setStatusMsg('LangGraph workflow started (paused at Review 1).');
              await refreshAll();
            }}
          >
            Start HITL Workflow
          </Button>
          <Button variant="contained" onClick={handleExcelDownload}>
            Export Excel (7 Sheets)
          </Button>
        </Stack>
      </Box>

      {statusMsg && (
        <Alert severity="info" onClose={() => setStatusMsg(null)} sx={{ mb: 2 }}>
          {statusMsg}
        </Alert>
      )}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label={`Review 1: Keywords (${keywords.length})`} />
        <Tab label={`Review 2: Clusters (${clusters.length})`} />
        <Tab label={`Review 3: Content Briefs (${briefs.length})`} />
        <Tab label="Export & Data Sources" />
      </Tabs>

      {tab === 0 && (
        <Stack spacing={2}>
          <Stack direction="row" spacing={2} flexWrap="wrap">
            <TextField
              size="small"
              label="Add Keyword"
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
            />
            <Button
              variant="contained"
              onClick={async () => {
                if (!runId || !newKeyword.trim()) return;
                await researchApi.addKeyword(runId, newKeyword.trim());
                setNewKeyword('');
                await refreshAll();
              }}
            >
              Add
            </Button>
            <TextField
              select
              size="small"
              label="Import Source"
              value={sourceCode}
              onChange={(e) => setSourceCode(e.target.value)}
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="gkp_csv">Google Keyword Planner</MenuItem>
              <MenuItem value="spineditor_import">Spineditor CSV/XLSX</MenuItem>
              <MenuItem value="semrush_csv">Semrush CSV/XLSX</MenuItem>
            </TextField>
            <Button variant="outlined" component="label">
              Upload CSV/XLSX
              <input type="file" hidden accept=".csv,.tsv,.xlsx" onChange={handleFileUpload} />
            </Button>
            <Button
              variant="outlined"
              onClick={async () => {
                if (!runId) return;
                await researchApi.cleanKeywords(runId);
                setStatusMsg('Non-destructive cleaning completed.');
                await refreshAll();
              }}
            >
              Run Cleaning
            </Button>
            <Button
              variant="outlined"
              onClick={async () => {
                if (!runId) return;
                await researchApi.prioritize(runId);
                setStatusMsg('Prioritization scores updated.');
                await refreshAll();
              }}
            >
              Score Priority
            </Button>
          </Stack>

          <Box sx={{ height: 480, width: '100%', bgcolor: 'background.paper' }}>
            <DataGrid rows={keywords} columns={keywordCols} pageSizeOptions={[10, 25, 50]} />
          </Box>
        </Stack>
      )}

      {tab === 1 && (
        <Stack spacing={2}>
          <Box>
            <Button
              variant="contained"
              onClick={async () => {
                if (!runId) return;
                await researchApi.runClustering(runId);
                setStatusMsg('Hybrid clustering completed.');
                await refreshAll();
              }}
            >
              Run Hybrid Clustering
            </Button>
          </Box>
          {clusters.map((c) => (
            <Card key={c.id} variant="outlined">
              <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="h6">{c.cluster_name}</Typography>
                  <Stack direction="row" spacing={1}>
                    <Chip label={c.status} size="small" />
                    <Chip label={`${c.origin} v${c.version}`} size="small" variant="outlined" />
                    <Button
                      size="small"
                      variant="contained"
                      onClick={async () => {
                        await researchApi.approveCluster(c.id);
                        await refreshAll();
                      }}
                    >
                      Approve Cluster
                    </Button>
                  </Stack>
                </Box>
                <Typography variant="body2" color="text.secondary" mb={1}>
                  {c.clustering_reasoning}
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  {c.members.map((m) => (
                    <Chip
                      key={m.id}
                      label={`${m.original_keyword || m.keyword_id} (${m.role})`}
                      color={m.role === 'PRIMARY' ? 'primary' : 'default'}
                      size="small"
                    />
                  ))}
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}

      {tab === 2 && (
        <Stack spacing={2}>
          <Box>
            <Button
              variant="contained"
              onClick={async () => {
                if (!runId) return;
                await researchApi.generateBriefs(runId);
                setStatusMsg('Evidence-based content briefs generated.');
                await refreshAll();
              }}
            >
              Generate Content Briefs
            </Button>
          </Box>
          {briefs.map((b) => (
            <Card key={b.id} variant="outlined">
              <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="h6">{b.suggested_seo_title}</Typography>
                  <Stack direction="row" spacing={1}>
                    <Chip label={b.status} size="small" />
                    <Chip label={`${b.origin} v${b.version}`} size="small" variant="outlined" />
                    <Button
                      size="small"
                      variant="contained"
                      onClick={async () => {
                        await researchApi.approveBrief(b.id);
                        await refreshAll();
                      }}
                    >
                      Approve Brief
                    </Button>
                  </Stack>
                </Box>
                <Typography variant="body2" color="text.secondary" mb={1}>
                  <strong>H1:</strong> {b.h1} | <strong>Intent:</strong> {b.search_intent}
                </Typography>
                <Typography variant="body2" mb={1}>
                  <strong>Meta:</strong> {b.meta_description}
                </Typography>
                <Typography variant="subtitle2" mt={1}>
                  Outline Sections:
                </Typography>
                {b.sections.map((s) => (
                  <Typography key={s.id} variant="body2" sx={{ pl: s.heading_level === 3 ? 3 : 1 }}>
                    H{s.heading_level}: {s.heading_text}
                  </Typography>
                ))}
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}

      {tab === 3 && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Export Research Deliverables
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={2}>
              Download a 7-sheet Excel workbook (Overview, All Keywords, SERP Analysis, Search Intent, Keyword Clusters, Content Brief, Data Sources) or push to Google Sheets.
            </Typography>
            <Stack direction="row" spacing={2}>
              <Button variant="contained" onClick={handleExcelDownload}>
                Download .xlsx Workbook
              </Button>
              <Button
                variant="outlined"
                onClick={async () => {
                  if (!runId) return;
                  try {
                    await researchApi.exportGoogleSheets(runId);
                    setStatusMsg('Exported to Google Sheets.');
                  } catch {
                    setStatusMsg('Google Sheets OAuth is not connected yet.');
                  }
                }}
              >
                Export to Google Sheets
              </Button>
            </Stack>
          </CardContent>
        </Card>
      )}
    </Container>
  );
};
