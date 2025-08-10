// FILE: src/components/JobsTable.jsx
import React from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
} from '@mui/material';
import dayjs from 'dayjs';

export default function JobsTable({ jobs = [] }) {
  return (
    <TableContainer component={Paper} sx={{ mt: 1 }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Job ID</TableCell>
            <TableCell>Type</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Started At</TableCell>
            <TableCell>Finished At</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {jobs.length ? (
            jobs.map((j) => (
              <TableRow key={j.id || j.job_id} hover>
                <TableCell>{j.id ?? j.job_id}</TableCell>
                <TableCell>{j.type ?? j.job_type ?? '-'}</TableCell>
                <TableCell>{j.status ?? j.state ?? '-'}</TableCell>
                <TableCell>{j.started_at ? dayjs(j.started_at).format('YYYY-MM-DD HH:mm') : '-'}</TableCell>
                <TableCell>{j.finished_at ? dayjs(j.finished_at).format('YYYY-MM-DD HH:mm') : '-'}</TableCell>
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={5} align="center">
                No jobs
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
