// FILE: src/components/LogsViewer.jsx
import React, { useEffect, useState, useCallback } from "react";
import {
  Box,
  Typography,
  CircularProgress,
  IconButton,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Paper,
  TextField,
  TableFooter,
  TablePagination,
  Select,
  MenuItem,
  InputLabel,
  FormControl,
  Stack,
  Button,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { getLogs, getLogsByDevice } from "../api"; // ← new imports

function formatDate(iso) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

/**
 * Helper: convert datetime-local input (yyyy-MM-ddTHH:mm) to ISO string (UTC)
 * If value is empty, returns null.
 */
function dtLocalToISO(val) {
  if (!val) return null;
  // browser value like "2025-08-11T10:30"
  const dt = new Date(val);
  if (isNaN(dt.getTime())) return null;
  return dt.toISOString();
}

export default function LogsViewer({ branchId = null, deviceId = null, onBack = () => {} }) {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);

  const [page, setPage] = useState(0);
  const [perPage, setPerPage] = useState(25);
  const [total, setTotal] = useState(0);

  const [q, setQ] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [sortDir, setSortDir] = useState("desc");
  const [refreshKey, setRefreshKey] = useState(0);

  // NEW: per-column filters
  const [filters, setFilters] = useState({
    timestamp_from: "",
    timestamp_to: "",
    user_id: "",
    record_id: "",
    device: "",
    status: "",
  });

  const buildParams = useCallback(() => {
    const params = {
      page: page + 1, // backend 1-based
      per_page: perPage,
      sort_by: "timestamp",
      sort_dir: sortDir,
    };
    if (q && q.length) params.q = q;
    if (branchId) params.branch_id = branchId;
    if (deviceId) params.device_id = deviceId;

    // map filters -> params (convert datetimes)
    const tsFrom = dtLocalToISO(filters.timestamp_from);
    const tsTo = dtLocalToISO(filters.timestamp_to);
    if (tsFrom) params.timestamp_from = tsFrom;
    if (tsTo) params.timestamp_to = tsTo;

    if (filters.user_id) params.user_id = filters.user_id;
    if (filters.record_id) params.record_id = filters.record_id;
    if (filters.device) params.device = filters.device;
    if (filters.status) params.status = filters.status;

    return params;
  }, [page, perPage, q, sortDir, branchId, deviceId, filters]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const params = buildParams();
        const res = deviceId ? await getLogsByDevice(deviceId, params) : await getLogs(params);

        const fetchedItems = Array.isArray(res.data.items) ? res.data.items : [];
        setItems(fetchedItems);
        setTotal(typeof res.data.total === "number" ? res.data.total : fetchedItems.length);
      } catch (err) {
        setError(err.message || "Failed to load logs");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [deviceId, buildParams, refreshKey]);

  function handleSearchKeyDown(e) {
    if (e.key === "Enter") {
      setQ(searchInput.trim());
      setPage(0);
    }
  }

  function handleClearSearch() {
    setSearchInput("");
    setQ("");
    setPage(0);
    // clear filters too
    setFilters({
      timestamp_from: "",
      timestamp_to: "",
      user_id: "",
      record_id: "",
      device: "",
      status: "",
    });
  }

  function handleChangePage(_e, newPage) {
    setPage(newPage);
  }

  function handleChangeRowsPerPage(e) {
    const v = parseInt(e.target.value, 10);
    setPerPage(v);
    setPage(0);
  }

  function handleSortChange(e) {
    setSortDir(e.target.value);
    setPage(0);
  }

  function handleRefresh() {
    setRefreshKey((k) => k + 1);
  }

  // NEW: apply/clear filter handlers
  function handleFilterChange(field, value) {
    setFilters((f) => ({ ...f, [field]: value }));
  }

  function handleApplyFilters() {
    // When applying filters, push the q input as well (if present)
    setQ(searchInput.trim());
    setPage(0);
    setRefreshKey((k) => k + 1);
  }

  function handleClearFilters() {
    setFilters({
      timestamp_from: "",
      timestamp_to: "",
      user_id: "",
      record_id: "",
      device: "",
      status: "",
    });
    setPage(0);
    setRefreshKey((k) => k + 1);
  }

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <IconButton onClick={onBack} size="large" aria-label="back">
          <ArrowBackIcon />
        </IconButton>

        <Box sx={{ ml: 1, flex: 1 }}>
          <Typography variant="h6">
            {deviceId ? `Logs — Device ${deviceId}` : branchId ? `Logs — Branch ${branchId}` : "Logs"}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {loading ? "Loading..." : `${total} entries — page ${page + 1}`}
          </Typography>
        </Box>

        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            size="small"
            placeholder="Search (global q)"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            inputProps={{ "aria-label": "search logs" }}
          />

          <FormControl size="small" sx={{ minWidth: 90 }}>
            <InputLabel id="rows-label">Rows</InputLabel>
            <Select labelId="rows-label" value={perPage} label="Rows" onChange={handleChangeRowsPerPage}>
              <MenuItem value={10}>10</MenuItem>
              <MenuItem value={25}>25</MenuItem>
              <MenuItem value={50}>50</MenuItem>
              <MenuItem value={100}>100</MenuItem>
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel id="sort-label">Sort</InputLabel>
            <Select labelId="sort-label" value={sortDir} label="Sort" onChange={handleSortChange}>
              <MenuItem value="desc">Time ↓</MenuItem>
              <MenuItem value="asc">Time ↑</MenuItem>
            </Select>
          </FormControl>

          <Button variant="outlined" size="small" onClick={handleApplyFilters}>
            Apply Filters
          </Button>
          <Button variant="outlined" size="small" onClick={handleClearFilters}>
            Clear Filters
          </Button>
          <Button variant="contained" size="small" onClick={handleRefresh}>
            Refresh
          </Button>
        </Stack>
      </Box>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Box sx={{ p: 2 }}>
          <Typography color="error">Error loading logs: {error}</Typography>
        </Box>
      ) : items.length === 0 ? (
        <Box sx={{ p: 2 }}>
          <Typography>No logs available.</Typography>
        </Box>
      ) : (
        <>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Time</TableCell>
                <TableCell>User ID</TableCell>
                <TableCell>Record ID</TableCell>
                <TableCell>Device</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>

              {/* --- advanced filter row --- */}
              <TableRow>
                <TableCell>
                  <Stack direction="column" spacing={1}>
                    <TextField
                      size="small"
                      type="datetime-local"
                      label="From"
                      value={filters.timestamp_from}
                      onChange={(e) => handleFilterChange("timestamp_from", e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleApplyFilters()}
                      InputLabelProps={{ shrink: true }}
                    />
                    <TextField
                      size="small"
                      type="datetime-local"
                      label="To"
                      value={filters.timestamp_to}
                      onChange={(e) => handleFilterChange("timestamp_to", e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleApplyFilters()}
                      InputLabelProps={{ shrink: true }}
                    />
                  </Stack>
                </TableCell>

                <TableCell>
                  <TextField
                    size="small"
                    placeholder="User ID"
                    value={filters.user_id}
                    onChange={(e) => handleFilterChange("user_id", e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleApplyFilters()}
                  />
                </TableCell>

                <TableCell>
                  <TextField
                    size="small"
                    placeholder="Record ID"
                    value={filters.record_id}
                    onChange={(e) => handleFilterChange("record_id", e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleApplyFilters()}
                  />
                </TableCell>

                <TableCell>
                  <TextField
                    size="small"
                    placeholder="Device name / id"
                    value={filters.device}
                    onChange={(e) => handleFilterChange("device", e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleApplyFilters()}
                  />
                </TableCell>

                <TableCell>
                  <TextField
                    size="small"
                    placeholder="Status"
                    value={filters.status}
                    onChange={(e) => handleFilterChange("status", e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleApplyFilters()}
                  />
                </TableCell>
              </TableRow>
            </TableHead>

            <TableBody>
              {items.map((l) => {
                const ts = l.timestamp ?? l.ts ?? l.time;
                const user = l.user_id ?? l.user ?? "-";
                const record = l.record_id ?? l.record ?? "-";
                const deviceName = (l.device && (l.device.name ?? l.device.id)) || l.device_name || l.device_id || "-";
                const status = l.status ?? l.level ?? "-";

                return (
                  <TableRow key={l.id ?? `${ts}-${Math.random()}`}>
                    <TableCell style={{ whiteSpace: "nowrap" }}>{formatDate(ts)}</TableCell>
                    <TableCell>{user}</TableCell>
                    <TableCell>{record}</TableCell>
                    <TableCell>{deviceName}</TableCell>
                    <TableCell>{status}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>

            <TableFooter>
              <TableRow>
                <TablePagination
                  rowsPerPageOptions={[10, 25, 50, 100]}
                  colSpan={5}
                  count={total}
                  rowsPerPage={perPage}
                  page={page}
                  onPageChange={handleChangePage}
                  onRowsPerPageChange={handleChangeRowsPerPage}
                  labelDisplayedRows={({ from, to, count }) => `${from}-${to} of ${count}`}
                />
              </TableRow>
            </TableFooter>
          </Table>
        </>
      )}
    </Paper>
  );
}
