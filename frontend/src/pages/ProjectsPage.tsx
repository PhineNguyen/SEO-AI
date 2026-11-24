import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid2 as Grid,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { Project, projectsApi, researchApi, ResearchRun } from '../services/api';

export const ProjectsPage: React.FC = () => {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [runsByProject, setRunsByProject] = useState<Record<string, ResearchRun[]>>({});
  const [openCreate, setOpenCreate] = useState(false);
  const [name, setName] = useState('');
  const [niche, setNiche] = useState('');
  const [country, setCountry] = useState('VN');
  const [language, setLanguage] = useState('vi');
  const [error, setError] = useState<string | null>(null);

  const loadProjects = async () => {
    try {
      const resp = await projectsApi.list();
      setProjects(resp.data);
      const map: Record<string, ResearchRun[]> = {};
      for (const p of resp.data) {
        const r = await researchApi.listRuns(p.id);
        map[p.id] = r.data;
      }
      setRunsByProject(map);
    } catch {
      setError('Failed to load projects. Check backend connection.');
    }
  };

  useEffect(() => {
    void loadProjects();
  }, []);

  const handleCreateProject = async () => {
    try {
      await projectsApi.create({
        name,
        niche,
        target_country: country,
        target_language: language,
      });
      setOpenCreate(false);
      setName('');
      setNiche('');
      await loadProjects();
    } catch {
      setError('Could not create project.');
    }
  };

  const handleNewRun = async (projectId: string) => {
    const runName = `Research Run ${new Date().toISOString().slice(0, 10)}`;
    const resp = await researchApi.createRun(projectId, runName, ['seo keyword']);
    navigate(`/runs/${resp.data.id}`);
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" fontWeight={700}>
          SEO Projects & Research Runs
        </Typography>
        <Button variant="contained" onClick={() => setOpenCreate(true)}>
          New Project
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Grid container spacing={3}>
        {projects.map((p) => (
          <Grid size={{ xs: 12, md: 6 }} key={p.id}>
            <Card variant="outlined">
              <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="h6" fontWeight={600}>
                    {p.name}
                  </Typography>
                  <Chip label={`${p.target_country} / ${p.target_language}`} size="small" />
                </Box>
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Niche: {p.niche}
                </Typography>
                <Stack spacing={1} mb={2}>
                  {(runsByProject[p.id] || []).map((run) => (
                    <Button
                      key={run.id}
                      variant="outlined"
                      size="small"
                      onClick={() => navigate(`/runs/${run.id}`)}
                      sx={{ justifyContent: 'space-between' }}
                    >
                      <span>{run.name}</span>
                      <Chip label={run.status} size="small" color="primary" />
                    </Button>
                  ))}
                </Stack>
                <Button variant="contained" size="small" onClick={() => handleNewRun(p.id)}>
                  Start New Research Run
                </Button>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Dialog open={openCreate} onClose={() => setOpenCreate(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create SEO Project</DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1}>
            <TextField label="Project Name" value={name} onChange={(e) => setName(e.target.value)} required />
            <TextField label="Niche / Industry" value={niche} onChange={(e) => setNiche(e.target.value)} required />
            <TextField label="Target Country (ISO-2)" value={country} onChange={(e) => setCountry(e.target.value)} />
            <TextField label="Target Language" value={language} onChange={(e) => setLanguage(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenCreate(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreateProject}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};
