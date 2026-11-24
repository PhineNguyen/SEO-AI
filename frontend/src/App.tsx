import React, { useState } from 'react';
import { AppBar, Box, Button, CssBaseline, ThemeProvider, Toolbar, Typography } from '@mui/material';
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom';
import { LoginPage } from './pages/LoginPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { ResearchWorkspacePage } from './pages/ResearchWorkspacePage';
import { appTheme } from './theme';

export const App: React.FC = () => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('seo_ai_token'));

  const handleLogout = () => {
    localStorage.removeItem('seo_ai_token');
    setToken(null);
  };

  return (
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <BrowserRouter>
        {token && (
          <AppBar position="static" elevation={1}>
            <Toolbar>
              <Typography
                variant="h6"
                component={Link}
                to="/"
                sx={{ flexGrow: 1, color: 'inherit', textDecoration: 'none', fontWeight: 700 }}
              >
                AI Keyword Research & Content Planning Agent
              </Typography>
              <Button color="inherit" onClick={handleLogout}>
                Sign Out
              </Button>
            </Toolbar>
          </AppBar>
        )}
        <Box minHeight="100vh" bgcolor="background.default">
          {!token ? (
            <LoginPage onAuthenticated={() => setToken(localStorage.getItem('seo_ai_token'))} />
          ) : (
            <Routes>
              <Route path="/" element={<ProjectsPage />} />
              <Route path="/runs/:runId" element={<ResearchWorkspacePage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          )}
        </Box>
      </BrowserRouter>
    </ThemeProvider>
  );
};

export default App;
