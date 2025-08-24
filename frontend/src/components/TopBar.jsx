// FILE: src/components/TopBar.jsx
import React from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  Box,
  Stack,
  Tooltip,
  CircularProgress,
  IconButton,
} from '@mui/material';
import ListIcon from '@mui/icons-material/List';
import FactCheckIcon from '@mui/icons-material/FactCheck';
import RefreshIcon from '@mui/icons-material/Refresh';
import AccountCircle from '@mui/icons-material/AccountCircle';

/**
 * TopBar
 * Props:
 *  - onRefresh: fn
 *  - onShowJobs: fn
 *  - isRefreshing?: boolean
 *  - isLoadingJobs?: boolean
 *  - userName?: string (optional)
 */
export default function TopBar({ onRefresh, onShowJobs, isRefreshing = false, isLoadingJobs = false, userName = '' }) {
  return (
    <AppBar position="static" elevation={6} sx={{ background: 'linear-gradient(90deg,#0f172a 0%,#0ea5a4 100%)' }}>
      <Toolbar sx={{ minHeight: 64 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', flexGrow: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 700, letterSpacing: 0.2 }}>
            Attendance Dashboard
          </Typography>

          {/* optional subtitle */}
          {userName ? (
            <Typography variant="body2" sx={{ ml: 2, color: 'rgba(255,255,255,0.8)' }}>
              {userName}
            </Typography>
          ) : null}
        </Box>

        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="Refresh data">
            <span>
              <Button
                onClick={onRefresh}
                startIcon={isRefreshing ? <CircularProgress size={18} color="inherit" /> : <RefreshIcon />}
                sx={{
                  textTransform: 'none',
                  color: 'common.white',
                  borderRadius: 2,
                  px: 2,
                  py: 0.8,
                  fontWeight: 600,
                  background: 'linear-gradient(90deg,#06b6d4 0%,#3b82f6 100%)',
                  boxShadow: '0 8px 20px rgba(3,105,161,0.12)',
                  '&:hover': { boxShadow: '0 12px 30px rgba(3,105,161,0.16)' },
                }}
              >
                Refresh
              </Button>
            </span>
          </Tooltip>

          <Tooltip title="View Jobs">
            <span>
              <Button
                onClick={onShowJobs}
                startIcon={isLoadingJobs ? <CircularProgress size={18} color="inherit" /> : <ListIcon />}
                sx={{
                  textTransform: 'none',
                  color: 'primary.main',
                  borderRadius: 2,
                  px: 2,
                  py: 0.8,
                  fontWeight: 600,
                  background: 'linear-gradient(90deg,#ffffff 0%,#f1f5f9 100%)',
                  boxShadow: '0 6px 16px rgba(2,6,23,0.06)',
                  '&:hover': { boxShadow: '0 10px 26px rgba(2,6,23,0.08)' },
                }}
              >
                Jobs
              </Button>
            </span>
          </Tooltip>

          {/* small profile icon — optional, purely decorative */}
          <IconButton sx={{ ml: 1, color: 'rgba(255,255,255,0.9)' }} aria-label="profile">
            <AccountCircle />
          </IconButton>
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
