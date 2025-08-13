// FILE: src/components/JobsTable.jsx
import React, { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Box,
  Typography,
  Chip,
  IconButton,
  Tooltip,
  Stack,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import dayjs from 'dayjs';

function statusColor(status) {
  const s = String(status || '').toLowerCase();
  if (s === 'running' || s === 'queued' || s === 'in_progress') return 'primary';
  if (s === 'finished' || s === 'success' || s === 'done') return 'success';
  if (s === 'failed' || s === 'error') return 'error';
  return 'default';
}

export default function JobsTable({ jobs = [], onViewDetails = (job) => {} }) {
  const [copiedId, setCopiedId] = useState(null);

  const handleCopy = async (id) => {
    try {
      await navigator.clipboard.writeText(String(id));
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1500);
    } catch {
      // fallback: do nothing
    }
  };

  return (
    <TableContainer
      component={Paper}
      sx={{
        mt: 1,
        borderRadius: 3,
        boxShadow: '0 10px 30px rgba(2,6,23,0.06)',
        overflow: 'hidden',
      }}
    >
      {/* Gradient header */}
      <Box sx={{ px: 2, py: 1.25, background: 'linear-gradient(90deg,#0ea5a4 0%,#2563eb 100%)' }}>
        <Typography variant="subtitle1" sx={{ color: '#fff', fontWeight: 700 }}>
          Sync Jobs
        </Typography>
        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.85)' }}>
          Recent background sync jobs (click a row for details)
        </Typography>
      </Box>

      <Table size="small" sx={{ minWidth: 650 }}>
        <TableHead>
          <TableRow sx={{ background: 'transparent' }}>
            <TableCell sx={{ fontWeight: 700 }}>Job ID</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Type</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Started At</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Finished At</TableCell>
            <TableCell align="right" sx={{ fontWeight: 700 }}>Actions</TableCell>
          </TableRow>
        </TableHead>

        <TableBody>
          {jobs && jobs.length ? (
            jobs.map((j) => {
              const id = j.job_id ?? j.id;
              const type = j.type ?? j.job_type ?? '-';
              const status = j.status ?? j.state ?? '-';
              const started = j.started_at ? dayjs(j.started_at).format('YYYY-MM-DD HH:mm') : '-';
              const finished = j.finished_at ? dayjs(j.finished_at).format('YYYY-MM-DD HH:mm') : '-';
              const chipColor = statusColor(status);

              return (
                <TableRow
                  key={id}
                  hover
                  sx={{
                    '&:hover': { transform: 'translateY(-2px)', boxShadow: '0 8px 20px rgba(2,6,23,0.04)' },
                    transition: 'transform .12s ease, box-shadow .12s ease',
                    cursor: 'pointer',
                  }}
                  onClick={() => onViewDetails(j)}
                >
                  <TableCell sx={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 13 }}>
                        {String(id)}
                      </Typography>
                    </Stack>
                  </TableCell>

                  <TableCell>{type}</TableCell>

                  <TableCell>
                    <Chip label={String(status)} color={chipColor} size="small" />
                  </TableCell>

                  <TableCell sx={{ whiteSpace: 'nowrap' }}>{started}</TableCell>

                  <TableCell sx={{ whiteSpace: 'nowrap' }}>{finished}</TableCell>

                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
                      <Tooltip title={copiedId === id ? 'Copied!' : 'Copy Job ID'}>
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(id);
                          }}
                        >
                          <ContentCopyIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>

                      <Tooltip title="View details">
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            onViewDetails(j);
                          }}
                        >
                          <InfoOutlinedIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </TableCell>
                </TableRow>
              );
            })
          ) : (
            <TableRow>
              <TableCell colSpan={6} align="center" sx={{ py: 4 }}>
                <Typography variant="body2" color="text.secondary">
                  No jobs
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
