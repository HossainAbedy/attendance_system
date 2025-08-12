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
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import DevicesIcon from '@mui/icons-material/DeviceHub';
import SyncIcon from '@mui/icons-material/Sync';

export default function BranchesTable({ branches = [], onFetch, onShowDevices, onCreate, onUpdate, onDelete }) {
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState('add'); // 'add' | 'edit'
  const [formData, setFormData] = useState({ name: '', ip_range: '' });
  const [deleting, setDeleting] = useState({ open: false, id: null, name: '' });
  const [submitting, setSubmitting] = useState(false);

  // pagination
  const [page, setPage] = useState(0);
  const rowsPerPage = 30;

  useEffect(() => {
    // if branches shrink and current page is out of range, reset to 0
    if (page > 0 && page * rowsPerPage >= branches.length) {
      setPage(0);
    }
  }, [branches, page]);

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
        const res = await onCreate({ name: formData.name, ip_range: formData.ip_range });
        if (res?.success) setFormOpen(false);
        else alert('Failed to create branch');
      } else {
        const res = await onUpdate(formData.id, { name: formData.name, ip_range: formData.ip_range });
        if (res?.success) setFormOpen(false);
        else alert('Failed to update branch');
      }
    } catch (err) {
      console.error(err);
      alert('Error performing request');
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmDelete() {
    setSubmitting(true);
    try {
      const res = await onDelete(deleting.id);
      if (res?.success) setDeleting({ open: false, id: null, name: '' });
      else alert('Failed to delete branch');
    } catch (err) {
      console.error(err);
      alert('Error deleting branch');
    } finally {
      setSubmitting(false);
    }
  }

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const paginated = branches.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
        <Typography variant="h6" gutterBottom>
          Branches
        </Typography>
        <Button startIcon={<AddIcon />} onClick={openAdd} size="small">
          Add Branch
        </Button>
      </Box>

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell align="left">
              <Chip
                label="Name"
                size="medium"
                sx={{ backgroundColor: 'black', color: 'white' }}
              />
            </TableCell>
            <TableCell align="right">
              <Chip
                label="IP Range"
                size="medium"
                sx={{ backgroundColor: 'black', color: 'white' }}
              />
            </TableCell>
            <TableCell align="center">
              <Chip
                label="Devices"
                size="medium"
                sx={{ backgroundColor: 'black', color: 'white' }}
              />
            </TableCell>
            <TableCell align="center">
              <Chip
                label="Logs"
                size="medium"
                sx={{ backgroundColor: 'black', color: 'white' }}
              />
            </TableCell>
            <TableCell align="center">
              <Chip
                label="Status"
                size="medium"
                sx={{ backgroundColor: 'black', color: 'white' }}
              />
            </TableCell>
            <TableCell align="right">
              <Chip
                label="Actions"
                size="medium"
                sx={{ backgroundColor: 'black', color: 'white' }}
              />
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {paginated.map((b) => (
            <TableRow key={b.id} hover>
              <TableCell>
                <Chip
                  label={b.name}
                  size="small"
                  sx={{ backgroundColor: 'deepskyblue', color: 'black' }}
                />
              </TableCell>
              <TableCell align="right">
                <Chip
                  label={b.ip_range}
                  size="small"
                  sx={{ backgroundColor: 'orange', color: 'black' }}
                />
              </TableCell>
              <TableCell align="center">
                <Chip
                  label={b.device_count ?? 0}
                  size="small"
                  sx={{ backgroundColor: 'yellow', color: 'black' }}
                />
              </TableCell>

              <TableCell align="center">
                <Chip
                  label={b.log_count ?? 0}
                  size="small"
                  sx={{ backgroundColor: 'cyan', color: 'black' }}
                />
              </TableCell>

              <TableCell align="center">
                {b.online ? (
                  <Chip label="Online" size="small" sx={{ backgroundColor: 'green', color: 'black' }} />
                ) : (
                  <Chip label="Offline" size="small" sx={{ backgroundColor: 'red', color: 'black' }} />
                )}
              </TableCell>
              <TableCell align="right">
                <Stack direction="row" spacing={1} justifyContent="flex-end">
                  <Tooltip title="Fetch">
                    <IconButton size="small" onClick={() => onFetch && onFetch(b.id)}
                      sx={{
                        color: 'green',
                        '&:hover': {
                          backgroundColor: 'green',
                          color: 'white'
                        },
                      }}>
                      <SyncIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Devices">
                    <IconButton size="small" onClick={() => onShowDevices && onShowDevices(b.id)}
                      sx={{
                        color: 'deepskyblue',
                        '&:hover': {
                          backgroundColor: 'deepskyblue',
                          color: 'white'
                        },
                      }}>
                      <DevicesIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Edit">
                    <IconButton size="small" onClick={() => openEdit(b)}
                      sx={{
                        color: 'yellow',
                        '&:hover': {
                          backgroundColor: 'orange',
                          color: 'white'
                        },
                      }}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Delete">
                    <IconButton size="small" color="error" onClick={() => setDeleting({ open: true, id: b.id, name: b.name })}
                      sx={{
                        color: 'red',
                        '&:hover': {
                          backgroundColor: 'red',
                          color: 'white'
                        },
                      }}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>

        <TableFooter>
          <TableRow>
            <TableCell colSpan={6}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Button
                    size="small"
                    onClick={(e) => handleChangePage(e, Math.max(0, page - 1))}
                    disabled={page === 0}
                  >
                    Previous
                  </Button>
                  <Button
                    size="small"
                    onClick={(e) => handleChangePage(e, Math.min(Math.ceil(branches.length / rowsPerPage) - 1, page + 1))}
                    disabled={page >= Math.ceil(branches.length / rowsPerPage) - 1}
                    sx={{ ml: 1 }}
                  >
                    Next
                  </Button>
              </Box>
                  <TablePagination
                    rowsPerPageOptions={[30]} //data per page
                    count={branches.length}
                    rowsPerPage={rowsPerPage}
                    page={page}
                    onPageChange={handleChangePage}
                    onRowsPerPageChange={() => {}}
                    labelDisplayedRows={({ from, to, count }) => `${from}-${to} of ${count}`}
                  />
              </Box>
            </TableCell>
          </TableRow>
        </TableFooter>
      </Table>

      {/* Form dialog */}
      <Dialog open={formOpen} onClose={() => setFormOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{formMode === 'add' ? 'Add Branch' : 'Edit Branch'}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField label="Name" value={formData.name} onChange={(e) => setFormData((s) => ({ ...s, name: e.target.value }))} fullWidth />
            <TextField label="IP Range" value={formData.ip_range} onChange={(e) => setFormData((s) => ({ ...s, ip_range: e.target.value }))} fullWidth />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFormOpen(false)}>Cancel</Button>
          <Button onClick={submitForm} disabled={submitting} variant="contained">
            {formMode === 'add' ? 'Create' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={deleting.open} onClose={() => setDeleting({ open: false, id: null, name: '' })}>
        <DialogTitle>Delete Branch</DialogTitle>
        <DialogContent>
          <Typography>Are you sure you want to delete branch "{deleting.name}"? This will remove its devices/logs if cascade is enabled.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleting({ open: false, id: null, name: '' })}>Cancel</Button>
          <Button onClick={confirmDelete} color="error" variant="contained" disabled={submitting}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
