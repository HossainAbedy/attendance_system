// FILE: src/components/DevicesTable.jsx
import React, { useState, useEffect } from 'react';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import {
  Table, TableHead, TableRow, TableCell, TableBody, TableFooter, TablePagination,
  IconButton, Typography, Box, Button, Tooltip, Chip, Stack, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, Paper, TableContainer
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import SyncIcon from '@mui/icons-material/Sync';
import PingIcon from '@mui/icons-material/Cloud';
import FileCopyIcon from '@mui/icons-material/FileCopy';
import { useSnackbar } from 'notistack';

export default function DevicesTable({
  devices = [],
  branchId = null,
  onFetch,     // optional: (deviceId) => Promise
  onPoll,      // optional: (deviceId) => Promise
  onCreate,    // optional: (branchId, payload) => Promise
  onUpdate,    // optional: (deviceId, payload) => Promise
  onDelete,    // optional: (deviceId) => Promise
  onBack,      // optional: () => void
}) {
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState('add'); // 'add' | 'edit'
  const [formData, setFormData] = useState({ name: '', ip_address: '', port: 4370, serial_no: '' });
  const [deleting, setDeleting] = useState({ open: false, id: null, name: '' });
  const [submitting, setSubmitting] = useState(false);
  const { enqueueSnackbar } = useSnackbar();

  // pagination
  const [page, setPage] = useState(0);
  const rowsPerPage = 30;

  useEffect(() => {
    if (page > 0 && page * rowsPerPage >= devices.length) setPage(0);
  }, [devices, page]);

  const openAdd = () => {
    setFormMode('add');
    setFormData({ name: '', ip_address: '', port: 4370, serial_no: '' });
    setFormOpen(true);
  };

  const openEdit = (d) => {
    setFormMode('edit');
    setFormData({
      id: d.id,
      name: d.name || '',
      ip_address: d.ip_address || '',
      port: d.port ?? 4370,
      serial_no: d.serial_no || ''
    });
    setFormOpen(true);
  };

  const submitForm = async () => {
    if (!formData.name.trim() || !formData.ip_address.trim()) {
      enqueueSnackbar('Name and IP are required', { variant: 'warning' });
      return;
    }
    setSubmitting(true);
    try {
      if (formMode === 'add') {
        if (!branchId) {
          enqueueSnackbar('Missing branch context', { variant: 'error' });
          setSubmitting(false);
          return;
        }
        const res = await onCreate?.(branchId, formData);
        if (res?.success ?? true) {
          setFormOpen(false);
          enqueueSnackbar('Device created', { variant: 'success' });
        } else {
          enqueueSnackbar('Failed to create device', { variant: 'error' });
        }
      } else {
        const res = await onUpdate?.(formData.id, formData);
        if (res?.success ?? true) {
          setFormOpen(false);
          enqueueSnackbar('Device updated', { variant: 'success' });
        } else {
          enqueueSnackbar('Failed to update device', { variant: 'error' });
        }
      }
    } catch (err) {
      console.error(err);
      enqueueSnackbar(err?.message || 'Request failed', { variant: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    setSubmitting(true);
    try {
      const res = await onDelete?.(deleting.id);
      if (res?.success ?? true) {
        setDeleting({ open: false, id: null, name: '' });
        enqueueSnackbar('Device deleted', { variant: 'success' });
      } else {
        enqueueSnackbar('Failed to delete device', { variant: 'error' });
      }
    } catch (err) {
      console.error(err);
      enqueueSnackbar('Error deleting device', { variant: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleChangePage = (_e, newPage) => setPage(newPage);

  const paginated = devices.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Paper sx={{ borderRadius: 2, boxShadow: '0 10px 30px rgba(2,6,23,0.06)', overflow: 'hidden' }}>
      {/* Header */}
      <Box sx={{ px: 2, py: 1, background: 'linear-gradient(90deg,#8e2de2 0%,#4a00e0 100%)', color: '#fff', display: 'flex', alignItems: 'center', gap: 2 }}>
        <Button onClick={onBack} startIcon={<ArrowBackIcon />} size="small" sx={{ color: '#fff', borderColor: 'rgba(255,255,255,0.08)' }} variant="outlined">Back</Button>
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            {branchId ? `Devices — Branch ${branchId}` : 'Devices'}
          </Typography>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.9)' }}>{devices.length} total</Typography>
        </Box>

        <Stack direction="row" spacing={1}>
          <Button startIcon={<AddIcon />} onClick={openAdd} variant="contained" size="small" sx={{ textTransform: 'none' }}>
            Add
          </Button>
        </Stack>
      </Box>

      {/* Body */}
      <Box sx={{ p: 2 }}>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell><Chip label="Name" sx={{ bgcolor: 'black', color: 'white' }} /></TableCell>
                <TableCell><Chip label="IP Address" sx={{ bgcolor: 'black', color: 'white' }} /></TableCell>
                <TableCell align="center"><Chip label="Port" sx={{ bgcolor: 'black', color: 'white' }} /></TableCell>
                <TableCell align="center"><Chip label="Serial" sx={{ bgcolor: 'black', color: 'white' }} /></TableCell>
                <TableCell align="right"><Chip label="Actions" sx={{ bgcolor: 'black', color: 'white' }} /></TableCell>
              </TableRow>
            </TableHead>

            <TableBody>
              {paginated.map(d => (
                <TableRow key={d.id} hover>
                  <TableCell>
                    <Chip label={d.name || '-'} size="small" sx={{ bgcolor: 'rgba(56,189,248,0.12)', color: 'info.main', fontWeight: 700 }} />
                  </TableCell>

                  <TableCell>
                    <Chip label={d.ip_address || '-'} size="small" sx={{ bgcolor: 'rgba(249,115,22,0.08)', color: 'warning.main' }} />
                  </TableCell>

                  <TableCell align="center">
                    <Chip label={d.port ?? 4370} size="small" sx={{ bgcolor: 'rgba(253,224,71,0.08)', color: 'warning.dark' }} />
                  </TableCell>

                  <TableCell align="center">
                    <Chip label={d.serial_no ?? '-'} size="small" sx={{ bgcolor: 'rgba(56,189,248,0.06)', color: 'text.primary' }} />
                  </TableCell>

                  <TableCell align="right">
                    <Stack direction="row" spacing={1} justifyContent="flex-end">
                      <Tooltip title="Fetch device (get logs)">
                        <IconButton
                          size="small"
                          onClick={async () => {
                            try {
                              if (!onFetch) return;
                              await onFetch(d.id); // device-level fetch
                              enqueueSnackbar('Fetch enqueued', { variant: 'success' });
                            } catch (err) {
                              console.error(err);
                              enqueueSnackbar('Fetch failed', { variant: 'error' });
                            }
                          }}
                          sx={{ color: 'green', '&:hover': { bgcolor: 'green', color: 'white' } }}
                        >
                          <SyncIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>

                      <Tooltip title="Ping device">
                        <IconButton
                          size="small"
                          onClick={async () => {
                            try {
                              if (!onPoll) return;
                              await onPoll(d.id);
                              enqueueSnackbar('Ping OK', { variant: 'success' });
                            } catch (err) {
                              console.error(err);
                              enqueueSnackbar('Ping failed', { variant: 'error' });
                            }
                          }}
                          sx={{ color: 'deepskyblue', '&:hover': { bgcolor: 'deepskyblue', color: 'white' } }}
                        >
                          <PingIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>

                      <Tooltip title="Edit device">
                        <IconButton size="small" onClick={() => openEdit(d)} sx={{ color: 'goldenrod', '&:hover': { bgcolor: 'orange', color: 'white' } }}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>

                      <Tooltip title="Delete device">
                        <IconButton
                          size="small"
                          onClick={() => setDeleting({ open: true, id: d.id, name: d.name })}
                          sx={{ color: 'red', '&:hover': { bgcolor: 'red', color: 'white' } }}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>

                      <Tooltip title="Copy IP">
                        <IconButton
                          size="small"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(d.ip_address || '');
                              enqueueSnackbar('IP copied', { variant: 'info' });
                            } catch {
                              enqueueSnackbar('Copy failed', { variant: 'error' });
                            }
                          }}
                          sx={{ color: 'grey.600' }}
                        >
                          <FileCopyIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>

            <TableFooter>
              <TableRow>
                <TableCell colSpan={5}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box>
                      <Button size="small" onClick={() => handleChangePage(null, Math.max(0, page - 1))} disabled={page === 0}>Previous</Button>
                      <Button size="small" onClick={() => handleChangePage(null, Math.min(Math.ceil(devices.length / rowsPerPage) - 1, page + 1))} disabled={page >= Math.ceil(devices.length / rowsPerPage) - 1} sx={{ ml: 1 }}>Next</Button>
                    </Box>

                    <TablePagination
                      rowsPerPageOptions={[rowsPerPage]}
                      count={devices.length}
                      rowsPerPage={rowsPerPage}
                      page={page}
                      onPageChange={handleChangePage}
                      onRowsPerPageChange={() => {}}
                      labelDisplayedRows={({ from, to, count }) => `${from}-${to} of ${count}`}
                      sx={{ '& .MuiTablePagination-toolbar': { px: 0 } }}
                    />
                  </Box>
                </TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </TableContainer>
      </Box>

      {/* Device Form Dialog */}
      <Dialog open={formOpen} onClose={() => setFormOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{formMode === 'add' ? 'Add Device' : 'Edit Device'}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField label="Name" value={formData.name} onChange={e => setFormData(s => ({ ...s, name: e.target.value }))} fullWidth />
            <TextField label="IP Address" value={formData.ip_address} onChange={e => setFormData(s => ({ ...s, ip_address: e.target.value }))} fullWidth />
            <TextField label="Port" value={String(formData.port)} onChange={e => setFormData(s => ({ ...s, port: Number(e.target.value) }))} fullWidth />
            <TextField label="Serial No" value={formData.serial_no} onChange={e => setFormData(s => ({ ...s, serial_no: e.target.value }))} fullWidth />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFormOpen(false)}>Cancel</Button>
          <Button
            onClick={async () => {
              try {
                await submitForm();
              } catch (err) {
                enqueueSnackbar('Operation failed', { variant: 'error' });
              }
            }}
            variant="contained"
            disabled={submitting}
          >
            {formMode === 'add' ? 'Create' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Device Dialog */}
      <Dialog open={deleting.open} onClose={() => setDeleting({ open: false, id: null, name: '' })}>
        <DialogTitle>Delete Device</DialogTitle>
        <DialogContent>
          <Typography>Are you sure you want to delete device "{deleting.name}"?</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleting({ open: false, id: null, name: '' })}>Cancel</Button>
          <Button
            onClick={async () => {
              try {
                await confirmDelete();
              } catch {
                enqueueSnackbar('Delete failed', { variant: 'error' });
              }
            }}
            color="error"
            variant="contained"
            disabled={submitting}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
