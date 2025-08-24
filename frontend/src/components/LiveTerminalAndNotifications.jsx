// src/components/LiveTerminalAndNotifications.jsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { AnsiUp } from 'ansi_up';
import { io } from 'socket.io-client';

// Material UI
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import DownloadIcon from '@mui/icons-material/Download';
import ClearIcon from '@mui/icons-material/ClearAll';
import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import Badge from '@mui/material/Badge';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Divider from '@mui/material/Divider';
import Collapse from '@mui/material/Collapse';
import Tooltip from '@mui/material/Tooltip';

const DEFAULT_MAX_LINES = 2000;
const ansiUp = new AnsiUp();

function getSharedSocket(url) {
  if (!window.__sharedSockets) window.__sharedSockets = {};
  const key = url || window.location.origin;
  if (!window.__sharedSockets[key]) {
    window.__sharedSockets[key] = io(key, {
      transports: ['websocket', 'polling'],
      autoConnect: true,
      reconnectionAttempts: 5,
      path: '/socket.io',
    });
  }
  return window.__sharedSockets[key];
}

function stripAnsi(s = '') {
  return String(s).replace(/\x1b\[[0-9;]*m/g, '');
}
function safeStringify(obj, maxLen = 800) {
  try {
    const s = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 0);
    return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
  } catch {
    return String(obj);
  }
}
function pickTimestamp(payload) {
  return payload?.timestamp || payload?.time || payload?.checktime || payload?.createdAt || new Date().toISOString();
}
function pickDevice(payload, fallback) {
  return payload?.device_name || payload?.device || payload?.userid || payload?.device_id || fallback || 'stdout';
}
function pickLevel(payload) {
  const lvl = (payload?.level || payload?.status || payload?.status_level || '').toString().toUpperCase();
  if (!lvl) return 'INFO';
  return lvl;
}
function parseSimpleTextLine(raw) {
  const plain = stripAnsi(raw).trim();
  const m = plain.match(/^\s*\[([^\]]+)\]\s*(.*)/);
  if (m) {
    const token = m[1].toUpperCase();
    const rest = m[2] || '';
    let level = 'INFO';
    if (token.includes('ERR') || token.includes('ERROR')) level = 'ERROR';
    else if (token.includes('WARN')) level = 'WARN';
    else if (token.includes('DEBUG')) level = 'DEBUG';
    else if (token.includes('ACCESS')) level = 'ACCESS';
    return { level, plain, rest };
  }
  return { level: null, plain, rest: '' };
}
function formatLine(eventName, payload) {
  const ts = pickTimestamp(payload);
  let rawMessage = '';

  if (typeof payload === 'string') rawMessage = payload;
  else if (payload && (payload.message || payload.msg || payload.msg_text)) rawMessage = payload.message || payload.msg || payload.msg_text;
  else rawMessage = safeStringify(payload, 1200);

  const parsed = parseSimpleTextLine(payload?.message || rawMessage);
  const device = pickDevice(payload, parsed?.rest || parsed?.device);
  const level = pickLevel(payload) || parsed.level || 'INFO';
  const stripped = stripAnsi(parsed.plain || rawMessage).trim();

  const text = `${ts} | ${eventName} | ${device} | ${level} | ${stripped}`;
  return { ts, device, level, text, rawMessage, stripped, parsed };
}

/* ---------------- TerminalConsole ---------------- */
function TerminalConsole({ socketUrl, terminalHeight = '420px', maxLines = DEFAULT_MAX_LINES }) {
  const [lines, setLines] = useState([]); // each item has id,text,ts,level,device,rawMessage,open,payload,eventName
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [fullView, setFullView] = useState(false);
  const containerRef = useRef(null);
  const bottomRef = useRef(null);

  // buffer -> flush interval
  const bufferRef = useRef([]);
  const flushRef = useRef(null);
  const pausedRef = useRef(paused);

  useEffect(() => { pausedRef.current = paused; }, [paused]);

  // push a batch of items into the state (kept stable)
  const pushBatch = useCallback((items) => {
    if (!items || items.length === 0) return;
    setLines((prev) => {
      const next = prev.concat(items);
      if (!fullView && next.length > maxLines) {
        return next.slice(next.length - maxLines);
      }
      return next;
    });
  }, [fullView, maxLines]);

  useEffect(() => {
    // flush buffer every 180ms to reduce re-renders
    flushRef.current = setInterval(() => {
      if (pausedRef.current) return; // don't flush while paused
      const buf = bufferRef.current;
      if (!buf || buf.length === 0) return;
      const out = buf.splice(0, buf.length);
      pushBatch(out);
    }, 180);
    return () => {
      clearInterval(flushRef.current);
      flushRef.current = null;
    };
  }, [pushBatch]);

  useEffect(() => {
    const socket = getSharedSocket(socketUrl);
    if (!socket) return undefined;

    const makeItem = (eventName, norm, rawAnsi = null) => {
      const info = formatLine(eventName, norm);
      const raw = info.rawMessage ?? (norm.ansi ?? norm.message ?? '');
      const pieces = String(raw).split(/\r\n|\n/).map((p) => stripAnsi(p).trim()).filter((p) => p.length > 0);

      const idBase = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      const items = [];

      if (pieces.length <= 1) {
        items.push({
          id: idBase + '_0',
          eventName,
          payload: norm,
          text: info.text,
          ts: info.ts,
          level: info.level,
          device: info.device,
          rawMessage: pieces[0] || norm,
          open: false,
        });
      } else {
        items.push({
          id: idBase + '_hdr',
          eventName,
          payload: norm,
          text: `${info.ts} | ${eventName} | ${info.device} | ${info.level} | (multi-line ${pieces.length} lines)`,
          ts: info.ts,
          level: info.level,
          device: info.device,
          rawMessage: norm,
          open: false,
        });
        pieces.forEach((p, idx) => {
          const parsed = parseSimpleTextLine(p);
          items.push({
            id: `${idBase}_${idx + 1}`,
            eventName,
            payload: norm,
            text: `${info.ts} | ${eventName} | ${parsed.device || info.device} | ${parsed.level || info.level} | ${p}`,
            ts: info.ts,
            level: parsed.level || info.level,
            device: parsed.device || info.device,
            rawMessage: p,
            open: false,
          });
        });
      }
      return items;
    };

    const enqueueEvent = (eventName, payload, rawAnsi = null) => {
      if (pausedRef.current) return; // skip accepting events while paused
      const norm = (typeof payload === 'string') ? { message: payload } : { ...(payload || {}) };
      if (rawAnsi) {
        norm.ansi = rawAnsi;
        norm.message = norm.message || stripAnsi(rawAnsi);
      }
      const items = makeItem(eventName, norm, rawAnsi);
      bufferRef.current.push(...items);
    };

    // named handlers
    const handleConsole = (payload) => {
      const rawAnsi = payload && (payload.ansi || payload.raw || null);
      enqueueEvent('console', payload, rawAnsi);
    };
    const handleLog = (payload) => enqueueEvent('log', payload);
    const handleTerminalOutput = (payload) => {
      const p = payload && payload.message ? payload.message : payload;
      enqueueEvent('terminal_output', p);
    };
    const handleAccessLog = (payload) => enqueueEvent('access_log', { message: `[ACCESS] USERID=${payload?.userid} CHECKTIME=${payload?.checktime}`, ...payload });
    const handleDeviceStatus = (payload) => enqueueEvent('device_status', payload);
    const handleNewLogsBatch = (payload) => enqueueEvent('new_logs_batch', { message: `New logs ${payload?.count ?? (payload?.logs?.length ?? 0)} from ${payload?.device_name || payload?.device_id}`, ...payload });
    const handleDbInsertTimes = (payload) => enqueueEvent('db_insert_times', { message: `Inserted ${payload?.new_count ?? 0} records (access ${payload?.access_insert_seconds}s, flask ${payload?.flask_insert_seconds}s)`, ...payload });

    // register
    socket.on('console', handleConsole);
    socket.on('log', handleLog);
    socket.on('terminal_output', handleTerminalOutput);
    socket.on('access_log', handleAccessLog);
    socket.on('device_status', handleDeviceStatus);
    socket.on('new_logs_batch', handleNewLogsBatch);
    socket.on('db_insert_times', handleDbInsertTimes);

    const explicit = new Set(['log', 'console', 'terminal_output', 'access_log', 'device_status', 'new_logs_batch', 'db_insert_times', 'connect', 'disconnect', 'connect_error']);

    const onAnyHandler = (eventName, ...args) => {
      if (explicit.has(eventName)) return;
      const payload = args.length === 1 ? args[0] : args;
      enqueueEvent(eventName, payload);
    };
    if (socket.onAny) socket.onAny(onAnyHandler);

    const onConnect = () => enqueueEvent('connect', { message: 'socket connected', timestamp: new Date().toISOString() });
    const onDisconnect = (reason) => enqueueEvent('disconnect', { message: `disconnected: ${reason}`, timestamp: new Date().toISOString() });
    const onConnectError = (err) => enqueueEvent('connect_error', { message: `connect_error: ${err?.message || String(err)}`, timestamp: new Date().toISOString() });

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('connect_error', onConnectError);

    return () => {
      try {
        socket.off('console', handleConsole);
        socket.off('log', handleLog);
        socket.off('terminal_output', handleTerminalOutput);
        socket.off('access_log', handleAccessLog);
        socket.off('device_status', handleDeviceStatus);
        socket.off('new_logs_batch', handleNewLogsBatch);
        socket.off('db_insert_times', handleDbInsertTimes);
        if (socket.offAny) socket.offAny(onAnyHandler);
        socket.off('connect', onConnect);
        socket.off('disconnect', onDisconnect);
        socket.off('connect_error', onConnectError);
      } catch (e) {
        // ignore cleanup errors
      }
    };
  }, [socketUrl, maxLines]);

  // auto-scroll logic
  useEffect(() => {
    if (!paused && containerRef.current) {
      const el = containerRef.current;
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      if (isNearBottom) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines, paused]);

  const clear = () => setLines([]);
  const download = () => {
    const content = lines.map((l) => l.text || safeStringify(l.rawMessage)).join('\n');
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'terminal_output.txt');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const toggleOpen = (id) => setLines((prev) => prev.map((l) => (l.id === id ? { ...l, open: !l.open } : l)));

  const filtered = lines.filter((l) => {
    if (filter !== 'ALL' && (l.level || '').toString().toUpperCase() !== filter) return false;
    if (search && !l.text.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  function levelColor(level) {
    const s = (level || '').toString().toUpperCase();
    if (s.includes('ERR') || s === 'ERROR') return 'error.main';
    if (s.includes('WARN') || s === 'WARNING' || s === 'DISCONNECTED') return 'warning.main';
    if (s === 'DEBUG') return 'text.secondary';
    if (s === 'ACCESS' || s === 'NEW') return 'primary.main';
    return 'success.main';
  }

  return (
    <Paper
      elevation={4}
      sx={{
        p: 1.5,
        height: terminalHeight,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        borderRadius: 2,
        background: 'linear-gradient(180deg, #1e1e1e 0%, #121212 100%)',
        boxShadow: '0 6px 18px rgba(0,0,0,0.4)',
      }}
    >
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, p: 1, borderRadius: 1, background: 'linear-gradient(90deg, #ff9a9e, #fad0c4)', boxShadow: '0 4px 12px rgba(255,154,158,0.3)', }}>
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, letterSpacing: 0.5, color: '#fff', textShadow: '0 2px 4px rgba(0,0,0,0.4)' }}>Terminal</Typography>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.85)', fontStyle: 'italic' }}>Realtime logs</Typography>
        </Box>

        {/* Controls */}
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <TextField size="small" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} sx={{ bgcolor: '#fff', borderRadius: 1, '& .MuiOutlinedInput-root': { fontSize: '0.8rem' } }} />
          <Select size="small" value={filter} onChange={(e) => setFilter(e.target.value)} sx={{ bgcolor: '#fff', borderRadius: 1, fontSize: '0.8rem' }}>
            {['ALL', 'DEBUG', 'INFO', 'NEW', 'ERROR', 'WARN', 'ACCESS'].map((opt) => (<MenuItem key={opt} value={opt}>{opt}</MenuItem>))}
          </Select>

          <Button size="small" variant={fullView ? 'contained' : 'outlined'} onClick={() => setFullView((f) => !f)} sx={{ textTransform: 'none', fontWeight: 600, borderRadius: 2, }}>{fullView ? 'Full' : 'Trimmed'}</Button>

          <IconButton onClick={() => setPaused((p) => !p)} size="small" sx={{ bgcolor: paused ? 'success.main' : 'primary.main', color: '#fff', '&:hover': { opacity: 0.85, bgcolor: paused ? 'success.dark' : 'primary.dark' } }}>
            {paused ? <PlayArrowIcon /> : <PauseIcon />}
          </IconButton>

          <Tooltip title="Clear terminal">
            <IconButton onClick={clear} size="small" sx={{ bgcolor: 'error.main', color: '#fff', '&:hover': { bgcolor: 'error.dark' } }}><ClearIcon /></IconButton>
          </Tooltip>
          <Tooltip title="Download logs">
            <IconButton onClick={download} size="small" sx={{ bgcolor: 'success.main', color: '#fff', '&:hover': { bgcolor: 'success.dark' } }}><DownloadIcon /></IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Log Body */}
      <Box ref={containerRef} sx={{ flex: 1, overflowY: 'auto', bgcolor: 'common.black', color: 'grey.100', fontFamily: 'monospace', p: 1.2, borderRadius: 1, lineHeight: 1.3, fontSize: '0.78rem', boxShadow: 'inset 0 0 10px rgba(0,0,0,0.6)', }}>
        {filtered.map((l) => (
          <Box key={l.id} sx={{ mb: 0.5 }}>
            <ListItem alignItems="flex-start" onClick={() => toggleOpen(l.id)} sx={{ cursor: 'pointer', py: 0.2, px: 0, borderRadius: 1, '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' } }}>
              <ListItemText primary={
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Typography variant="caption" sx={{ color: 'grey.500' }}>[{new Date(l.ts).toLocaleTimeString()}]</Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>{l.eventName}</Typography>
                  <Typography variant="caption" sx={{ color: 'grey.400' }}>{l.device}</Typography>
                  <Typography variant="caption" sx={{ color: levelColor(l.level), fontWeight: 700 }}>{l.level}</Typography>
                  <Box sx={{ maxWidth: '60ch', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.payload?.ansi ? (
                      <span dangerouslySetInnerHTML={{ __html: ansiUp.ansi_to_html(l.payload.ansi || '') }} />
                    ) : (
                      <Typography variant="body2">{l.text.split(' | ').slice(4).join(' | ')}</Typography>
                    )}
                  </Box>
                </Box>
              } />
            </ListItem>

            <Collapse in={!!l.open} timeout="auto" unmountOnExit>
              <Box sx={{ bgcolor: '#0b0b0b', p: 1, borderRadius: 1, color: 'grey.300', fontSize: '0.75rem' }}>
                <Typography variant="caption" sx={{ color: 'grey.500' }}>Raw payload:</Typography>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{typeof l.rawMessage === 'string' ? l.rawMessage : safeStringify(l.rawMessage, 4000)}</pre>
              </Box>
            </Collapse>
            <Divider />
          </Box>
        ))}
        <div ref={bottomRef} />
      </Box>
    </Paper>
  );
}

/* ---------------- NotificationsPanel ---------------- */
function NotificationsPanel({ socketUrl, notificationsHeight = '220px' }) {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [totalLogs, setTotalLogs] = useState(0);
  const [branchCounts, setBranchCounts] = useState({});
  const [lastBatchCount, setLastBatchCount] = useState(0);
  const [lastBatchDevice, setLastBatchDevice] = useState(null);
  const [lastDbInsert, setLastDbInsert] = useState(null);
  const [totalInsertedCount, setTotalInsertedCount] = useState(0);

  useEffect(() => {
    const socket = getSharedSocket(socketUrl);
    if (!socket) return undefined;

    const onAnyHandler = (eventName, ...args) => {
      const payload = args.length === 1 ? args[0] : args;

      // only certain events produce notifications
      if (['new_log', 'new_logs_batch', 'access_log', 'log', 'terminal_output', 'console', 'device_status', 'db_insert_times'].includes(eventName)) {
        const id = `${eventName}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        const title = eventName === 'access_log'
          ? `Access: ${payload.userid || payload.device_id || payload.device_name}`
          : eventName === 'db_insert_times'
          ? `DB Insert: ${payload?.new_count ?? 0} rows`
          : `${eventName} — ${pickDevice(payload)}`;
        const time = pickTimestamp(payload);
        const note = { id, title, time, payload, read: false };
        setItems((prev) => [note, ...prev].slice(0, 300));
        setUnread((u) => u + 1);

        if (eventName === 'new_logs_batch') {
          const b = payload.branch_id ?? payload.device_id ?? payload.device_name ?? 'unknown';
          const count = payload.count ?? (Array.isArray(payload.logs) ? payload.logs.length : 1);
          setBranchCounts((prev) => ({ ...(prev || {}), [b]: (prev?.[b] || 0) + count }));
          setTotalLogs((t) => t + count);
          setLastBatchCount(count);
          setLastBatchDevice(payload.device_name || payload.device_id || b);
        } else if (eventName === 'db_insert_times') {
          const newCount = payload?.new_count ?? 0;
          const accessSeconds = payload?.access_insert_seconds ?? payload?.access_seconds ?? payload?.access_insert_time ?? null;
          const flaskSeconds = payload?.flask_insert_seconds ?? payload?.flask_seconds ?? payload?.flask_insert_time ?? null;
          setLastDbInsert({
            new_count: newCount,
            access_seconds: accessSeconds,
            flask_seconds: flaskSeconds,
            ts: pickTimestamp(payload),
          });
          setTotalInsertedCount((prev) => prev + newCount);
        } else {
          // generic single event
          setTotalLogs((t) => t + 1);
          const b = payload.branch_id ?? payload.device_id ?? payload.device_name ?? 'unknown';
          setBranchCounts((prev) => ({ ...(prev || {}), [b]: (prev?.[b] || 0) + 1 }));
        }
      }
    };

    if (socket.onAny) socket.onAny(onAnyHandler);
    return () => {
      if (socket.offAny) socket.offAny(onAnyHandler);
    };
  }, [socketUrl]);

  const markRead = (id) => setItems((prev) => prev.map((it) => (it.id === id ? { ...it, read: true } : it)));
  const markAllRead = () => { setItems((prev) => prev.map((it) => ({ ...it, read: true }))); setUnread(0); };
  const clearAll = () => { setItems([]); setUnread(0); setTotalLogs(0); setBranchCounts({}); setLastBatchCount(0); setLastDbInsert(null); setTotalInsertedCount(0); };

  return (
    <Paper elevation={4} sx={{ p: 1.5, height: notificationsHeight, minHeight: 300, maxHeight: 500, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRadius: 2, background: 'linear-gradient(180deg, #1e1e1e 0%, #121212 100%)', boxShadow: '0 6px 18px rgba(0,0,0,0.4)', }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, p: 1, borderRadius: 1, background: 'linear-gradient(90deg, #f7971e, #ffd200)', boxShadow: '0 4px 12px rgba(255,210,0,0.3)', }}>
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, letterSpacing: 0.5, color: '#fff', textShadow: '0 2px 4px rgba(0,0,0,0.4)' }}>Notifications</Typography>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.85)', fontStyle: 'italic' }}>Realtime activity & alerts</Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Badge badgeContent={unread} color="error"><Box sx={{ width: 24 }} /></Badge>
          <Button size="small" onClick={markAllRead} sx={{ px: 1.5, borderRadius: 2, textTransform: 'none', fontWeight: 600, bgcolor: 'primary.main', color: '#fff', '&:hover': { bgcolor: 'primary.dark' }, }}>Mark all</Button>
          <Button size="small" color="error" onClick={clearAll} sx={{ px: 1.5, borderRadius: 2, textTransform: 'none', fontWeight: 600, bgcolor: 'error.main', color: '#fff', '&:hover': { bgcolor: 'error.dark' }, }}>Clear</Button>
        </Box>
      </Box>

      <Box sx={{ px: 1, pb: 1, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 1, mb: 1, }}>
        <Typography variant="body2" sx={{ color: '#fff' }}>Total logs seen: <strong>{totalLogs}</strong></Typography>
        <Typography variant="body2" sx={{ color: '#fff' }}>Total inserted (flask): <strong>{totalInsertedCount}</strong></Typography>
        <Box sx={{ mt: 0.5 }}>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.7)' }}>Per-branch:</Typography>
          <Box component="ul" sx={{ m: 0, pl: 2, color: '#ddd' }}>
            {Object.keys(branchCounts).length === 0 && (<li><Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.5)' }}>No data</Typography></li>)}
            {Object.entries(branchCounts).map(([b, c]) => (<li key={b}><Typography variant="caption" sx={{ color: '#fff' }}>{b}: {c}</Typography></li>))}
          </Box>
        </Box>

        <Box sx={{ mt: 1 }}>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.7)' }}>Last batch:</Typography>
          <Typography variant="body2" sx={{ color: '#fff' }}>{lastBatchCount} records from {lastBatchDevice ?? '—'}</Typography>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.6)' }}>Last DB insert: {lastDbInsert ? `${lastDbInsert.new_count} rows (access ${lastDbInsert.access_seconds}s, flask ${lastDbInsert.flask_seconds}s) @ ${new Date(lastDbInsert.ts).toLocaleTimeString()}` : '—'}</Typography>
        </Box>
      </Box>

      <Box sx={{ overflow: 'auto', flex: 1 }}>
        {items.length === 0 && (<Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.5)' }}>No notifications yet</Typography>)}
        <List dense disablePadding>
          {items.map((it) => (
            <React.Fragment key={it.id}>
              <ListItem alignItems="flex-start" sx={{ borderRadius: 1, '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' } }} secondaryAction={<Button size="small" onClick={() => markRead(it.id)} sx={{ px: 1.2, borderRadius: 2, textTransform: 'none', fontWeight: 600, bgcolor: 'success.main', color: '#fff', '&:hover': { bgcolor: 'success.dark' }, }}>Mark</Button>}>
                <ListItemText primary={it.title} secondary={new Date(it.time).toLocaleString()} primaryTypographyProps={{ noWrap: true, sx: { color: '#fff' } }} secondaryTypographyProps={{ sx: { color: 'rgba(255,255,255,0.6)' } }} />
              </ListItem>
              <Divider component="li" sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />
            </React.Fragment>
          ))}
        </List>
      </Box>
    </Paper>
  );
}

/* ---------------- Main exported widget ---------------- */
export default function LiveTerminalAndNotifications({ socketUrl, containerWidth = '100%', notificationsHeight = '220px', terminalHeight = '420px', maxLines = DEFAULT_MAX_LINES }) {
  return (
    <Box sx={{ width: containerWidth, minWidth: '260px', display: 'flex', flexDirection: 'column', gap: 1, maxHeight: '92vh', overflow: 'hidden', p: 1 }}>
      <TerminalConsole socketUrl={socketUrl} terminalHeight={terminalHeight} maxLines={maxLines} />
      <NotificationsPanel socketUrl={socketUrl} notificationsHeight={notificationsHeight} />
    </Box>
  );
}
