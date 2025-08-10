// FILE: src/components/TopBar.jsx
import React from 'react';
import { AppBar, Toolbar, Typography, Button } from '@mui/material';
import ListIcon from '@mui/icons-material/List';
import FactCheckIcon from '@mui/icons-material/FactCheck';

export default function TopBar({ onRefresh, onShowJobs }) {
  return (
    <AppBar position="static">
      <Toolbar>
        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          Attendance Dashboard
        </Typography>
        <Button color="inherit" startIcon={<ListIcon />} onClick={onRefresh}>
          Refresh
        </Button>
        <Button color="inherit" startIcon={<FactCheckIcon />} onClick={onShowJobs}>
          Jobs
        </Button>
      </Toolbar>
    </AppBar>
  );
}
