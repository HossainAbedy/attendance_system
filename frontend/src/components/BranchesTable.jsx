// FILE: src/components/BranchesTable.jsx
import React, { useState, useEffect } from 'react';
import {
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  TableFooter,
  TablePagination,
  IconButton,
  Typography,
  Box,
  Button,
  Tooltip,
  Chip,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  TableContainer,
  Paper,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import DevicesIcon from '@mui/icons-material/DeviceHub';
import SyncIcon from '@mui/icons-material/Sync';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import { useSnackbar } from 'notistack';
import CircularProgress from '@mui/material/CircularProgress';

export default function BranchesTable({
  branches = [],
  onFetch,
  onShowDevices,
  onCreate,
  onUpdate,
  onDelete,
  rowsPerPageDefault = 30,
}) {
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState('add'); // 'add' | 'edit'
  const [formData, setFormData] = useState({ name: '', ip_range: '' });
  const [deleting, setDeleting] = useState({ open: false, id: null, name: '' });
  const [submitting, setSubmitting] = useState(false);
  const { enqueueSnackbar } = useSnackbar();

  // pagination
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(rowsPerPageDefault);

  // Keep per-branch busy state for fetch/poll
  const [busyIds, setBusyIds] = useState(new Set());

  useEffect(() => {
    // If branches shrink and page out of range, reset to last available page
    const maxPage = Math.max(0, Math.ceil(branches.length / rowsPerPage) - 1);
    if (page > maxPage) setPage(maxPage);
  }, [branches, page, rowsPerPage]);

  function openAdd() {
    setFormMode('add');
    setFormData({ name: '', ip_range: '' });
    setFormOpen(true);
  }

  function openEdit(branch) {
    setFormMode('edit');
    setFormData({ id: branch.id, name: branch.name, ip_range: branch.ip_range });
    setFormOpen(true);
  }

  async function submitForm() {
    setSubmitting(true);
    try {
      if (formMode === 'add') {
        if (!onCreate) throw new Error('Create handler missing');
        const res = await onCreate({ name: formData.name, ip_range: formData.ip_range });
        if (res?.success === false) throw new Error(res?.message || 'Create failed');
        setFormOpen(false);
        enqueueSnackbar('Branch created', { variant: 'success' });
      } else {
        if (!onUpdate) throw new Error('Update handler missing');
        const res = await onUpdate(formData.id, { name: formData.name, ip_range: formData.ip_range });
        if (res?.success === false) throw new Error(res?.message || 'Update failed');
        setFormOpen(false);
        enqueueSnackbar('Branch updated', { variant: 'success' });
      }
    } catch (err) {
      console.error(err);
      enqueueSnackbar(err.message || 'Operation failed', { variant: 'error' });
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmDelete() {
    setSubmitting(true);
    try {
      if (!onDelete) throw new Error('Delete handler missing');
      const res = await onDelete(deleting.id);
      if (res?.success === false) throw new Error(res?.message || 'Delete failed');
      setDeleting({ open: false, id: null, name: '' });
      enqueueSnackbar('Branch deleted', { variant: 'success' });
    } catch (err) {
      console.error(err);
      enqueueSnackbar(err.message || 'Failed to delete branch', { variant: 'error' });
    } finally {
      setSubmitting(false);
    }
  }

  const handleChangePage = (_event, newPage) => setPage(newPage);
  const handleChangeRowsPerPage = (event) => {
    const v = parseInt(event.target.value, 10);
    setRowsPerPage(v);
    setPage(0);
  };

  const paginated = branches.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  // busy helpers
  const setBusy = (id, val) =>
    setBusyIds((s) => {
      const copy = new Set(s);
      if (val) copy.add(id);
      else copy.delete(id);
      return copy;
    });

  const handleFetchClick = async (branchId) => {
    if (!onFetch) return;
    setBusy(branchId, true);
    try {
      await onFetch(branchId);
      enqueueSnackbar('Fetch enqueued', { variant: 'success' });
    } catch (err) {
      console.error(err);
      enqueueSnackbar('Failed to start fetch', { variant: 'error' });
    } finally {
      setBusy(branchId, false);
    }
  };

  const handleCopyId = async (id) => {
    try {
      await navigator.clipboard.writeText(String(id));
      enqueueSnackbar('Branch ID copied', { variant: 'info' });
    } catch {
      enqueueSnackbar('Copy failed', { variant: 'warning' });
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
      {/* header */}
      <Box sx={{ px: 2, py: 1.25, background: 'linear-gradient(90deg,#06b6d4 0%,#3b82f6 100%)' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box>
            <Typography variant="subtitle1" sx={{ color: '#fff', fontWeight: 700 }}>
              Branches
            </Typography>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.9)' }}>
              List of branches and quick actions
            </Typography>
          </Box>

          <Box>
            <Button
              startIcon={<AddIcon />}
              onClick={openAdd}
              size="small"
              variant="contained"
              sx={{
                background: 'linear-gradient(90deg,#10b981 0%,#06b6d4 100%)',
                color: 'white',
                fontWeight: 700,
                textTransform: 'none',
              }}
            >
              Add Branch
            </Button>
          </Box>
        </Box>
      </Box>

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 700 }}>Name</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>IP Range</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>Devices</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>Logs</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>Status</TableCell>
            <TableCell align="right" sx={{ fontWeight: 700 }}>Actions</TableCell>
          </TableRow>
        </TableHead>

        <TableBody>
          {paginated.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} align="center" sx={{ py: 6 }}>
                <Typography variant="body2" color="text.secondary">
                  No branches available.
                </Typography>
              </TableCell>
            </TableRow>
          ) : (
            paginated.map((b) => {
              const isBusy = busyIds.has(b.id);
              const online = Boolean(b.online);
              return (
                <TableRow
                  key={b.id}
                  hover
                  sx={{
                    '&:hover': { transform: 'translateY(-2px)', boxShadow: '0 8px 20px rgba(2,6,23,0.04)' },
                    transition: 'transform .12s ease, box-shadow .12s ease',
                  }}
                >
                  <TableCell>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{b.name}</Typography>
                      <Tooltip title="Copy Branch ID">
                        <IconButton size="small" onClick={() => handleCopyId(b.id)}>
                          <ContentCopyIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </TableCell>

                  <TableCell>
                    <Chip label={b.ip_range ?? '-'} size="small" sx={{ bgcolor: 'rgba(59,130,246,0.08)', color: 'primary.main' }} />
                  </TableCell>

                  <TableCell align="center">
                    <Chip label={b.device_count ?? 0} size="small" sx={{ bgcolor: 'rgba(16,185,129,0.08)', color: 'success.main' }} />
                  </TableCell>

                  <TableCell align="center">
                    <Chip label={b.log_count ?? 0} size="small" sx={{ bgcolor: 'rgba(14,165,233,0.06)', color: 'info.main' }} />
                  </TableCell>

                  <TableCell align="center">
                    <Chip
                      label={online ? 'Online' : 'Offline'}
                      size="small"
                      color={online ? 'success' : 'error'}
                      sx={{ fontWeight: 700 }}
                    />
                  </TableCell>

                  <TableCell align="right">
                    <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
                      <Tooltip title="Fetch (sync branch)">
                        <span>
                          <IconButton
                            size="small"
                            onClick={() => handleFetchClick(b.id)}
                            disabled={isBusy}
                            sx={{
                              '&:hover': { backgroundColor: isBusy ? 'transparent' : 'rgba(16,185,129,0.12)' },
                            }}
                          >
                            {isBusy ? <CircularProgress size={18} /> : <SyncIcon fontSize="small" sx={{ color: 'success.main' }} />}
                          </IconButton>
                        </span>
                      </Tooltip>

                      <Tooltip title="View devices">
                        <span>
                          <IconButton size="small" onClick={() => onShowDevices && onShowDevices(b.id)}>
                            <DevicesIcon fontSize="small" sx={{ color: 'primary.main' }} />
                          </IconButton>
                        </span>
                      </Tooltip>

                      <Tooltip title="Edit branch">
                        <span>
                          <IconButton size="small" onClick={() => openEdit(b)}>
                            <EditIcon fontSize="small" sx={{ color: 'warning.main' }} />
                          </IconButton>
                        </span>
                      </Tooltip>

                      <Tooltip title="Delete branch">
                        <span>
                          <IconButton
                            size="small"
                            onClick={() => setDeleting({ open: true, id: b.id, name: b.name })}
                            sx={{ color: 'error.main' }}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </Stack>
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>

        <TableFooter>
          <TableRow>
            <TableCell colSpan={6}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
                <Box>
                  <Button
                    size="small"
                    onClick={(e) => handleChangePage(e, Math.max(0, page - 1))}
                    disabled={page === 0}
                    sx={{ mr: 1 }}
                  >
                    Previous
                  </Button>
                  <Button
                    size="small"
                    onClick={(e) => handleChangePage(e, Math.min(Math.ceil(branches.length / rowsPerPage) - 1, page + 1))}
                    disabled={page >= Math.ceil(branches.length / rowsPerPage) - 1}
                  >
                    Next
                  </Button>
                </Box>

                <TablePagination
                  rowsPerPageOptions={[10, 20, 30, 50]}
                  count={branches.length}
                  rowsPerPage={rowsPerPage}
                  page={page}
                  onPageChange={handleChangePage}
                  onRowsPerPageChange={handleChangeRowsPerPage}
                  labelDisplayedRows={({ from, to, count }) => `${from}-${to} of ${count}`}
                />
              </Box>
            </TableCell>
          </TableRow>
        </TableFooter>
      </Table>

      {/* Branch Form Dialog */}
      <Dialog open={formOpen} onClose={() => setFormOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{formMode === 'add' ? 'Add Branch' : 'Edit Branch'}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField
              label="Name"
              value={formData.name}
              onChange={(e) => setFormData((s) => ({ ...s, name: e.target.value }))}
              fullWidth
            />
            <TextField
              label="IP Range"
              value={formData.ip_range}
              onChange={(e) => setFormData((s) => ({ ...s, ip_range: e.target.value }))}
              fullWidth
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFormOpen(false)} disabled={submitting}>Cancel</Button>
          <Button
            onClick={submitForm}
            disabled={submitting}
            variant="contained"
          >
            {formMode === 'add' ? 'Create' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Branch Dialog */}
      <Dialog open={deleting.open} onClose={() => setDeleting({ open: false, id: null, name: '' })}>
        <DialogTitle>Delete Branch</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete branch "{deleting.name}"? This will remove its devices/logs if cascade is enabled.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleting({ open: false, id: null, name: '' })}>Cancel</Button>
          <Button
            onClick={confirmDelete}
            color="error"
            variant="contained"
            disabled={submitting}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </TableContainer>
  );
}
