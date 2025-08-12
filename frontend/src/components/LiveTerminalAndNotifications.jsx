// src/components/LiveTerminalAndNotifications.jsx
import React, { useEffect, useRef, useState } from 'react';
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

/* ---------------- Shared socket manager (one socket per URL) ---------------- */
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

/* ---------------- Utilities ---------------- */
function safeStringify(obj, maxLen = 600) {
  try {
    const s = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 0);
    return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
  } catch {
    return String(obj);
  }
}

function stripAnsi(s = '') {
  // remove ANSI escape sequences (colors)
  return String(s).replace(/\x1b\[[0-9;]*m/g, '');
}

function pickTimestamp(payload) {
  return (
    payload?.timestamp ||
    payload?.time ||
    payload?.checktime ||
    payload?.createdAt ||
    new Date().toISOString()
  );
}

function pickDevice(payload, fallback) {
  return payload?.device_name || payload?.device_id || payload?.device || payload?.userid || fallback || 'unknown';
}

function pickLevel(payload) {
  const lvl = (payload?.level || payload?.status || payload?.status_level || '').toString().toUpperCase();
  if (!lvl) return 'INFO';
  return lvl;
}

function parseFromText(line) {
  const plain = stripAnsi(line).trim();
  let level = null;
  let device = null;

  const m = plain.match(/^\s*\[([A-Z0-9 _✅]+)\]\s*(.*)/i);
  if (m) {
    const token = m[1].toString().toUpperCase();
    if (token.includes('ERR') || token.includes('ERROR')) level = 'ERROR';
    else if (token.includes('WARN')) level = 'WARN';
    else if (token.includes('DEBUG')) level = 'DEBUG';
    else if (token.includes('ACCESS')) level = 'ACCESS';
    else if (token.includes('DISCONNECTED')) level = 'WARN';
    else if (token.includes('SCHEDULER')) level = 'INFO';
    else level = token.replace(/\s+/g, '_');

    const rest = m[2] || '';
    const devMatch = rest.match(/([A-Z0-9][A-Za-z0-9\s\-_]{4,50}?(?:Branch|Sub Branch|SUB Branch|SUB|Branch:|Lobby|Branch))/i);
    if (devMatch) device = devMatch[1].trim();
    else {
      const fallbackDev = rest.split(':')[0].split('-')[0].slice(0, 60).trim();
      if (fallbackDev.length > 2) device = fallbackDev;
    }

    return { level, device, plain };
  }

  return { level: null, device: null, plain };
}

function formatLine(eventName, payload) {
  const ts = pickTimestamp(payload);
  let rawMessage = '';

  if (typeof payload === 'string') rawMessage = payload;
  else if (payload && (payload.message || payload.msg || payload.msg_text)) rawMessage = payload.message || payload.msg || payload.msg_text;
  else rawMessage = safeStringify(payload, 1000);

  const parsed = parseFromText(rawMessage);
  const device = pickDevice(payload, parsed.device);
  const level = pickLevel(payload) || parsed.level || 'INFO';
  // store stripped message for display
  const stripped = stripAnsi(parsed.plain || rawMessage).trim();
  const text = `${ts} | ${eventName} | ${device} | ${level} | ${stripped}`;
  return { ts, device, level, text, rawMessage, stripped, parsed };
}

/* ---------------- TerminalConsole ---------------- */
function TerminalConsole({ socketUrl, terminalHeight = '420px', maxLines = DEFAULT_MAX_LINES }) {
  const [lines, setLines] = useState([]); // {text,eventName,payload,ts,level,device,rawMessage,open}
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [fullView, setFullView] = useState(false);
  const containerRef = useRef(null);
  const bottomRef = useRef(null);

  const pushLines = (newItems) => {
    setLines((prev) => {
      const next = [...prev, ...newItems];
      if (!fullView && next.length > maxLines) {
        return next.slice(next.length - maxLines);
      }
      return next;
    });
  };

  useEffect(() => {
    const socket = getSharedSocket(socketUrl);
    if (!socket) return;

    const enqueueEvent = (eventName, payload) => {
      const info = formatLine(eventName, payload);
      const raw = info.rawMessage ?? '';
      // split on newlines; keep non-empty pieces (but preserve lines like "[DEBUG] ..." even if preceded by newline)
      const pieces = String(raw).split(/\r\n|\n/).map((p) => stripAnsi(p).trim()).filter((p) => p.length > 0);

      if (pieces.length === 0) {
        // fallback: push the stripped text (useful for structured payloads)
        pushLines([{
          eventName,
          payload,
          text: info.text,
          ts: info.ts,
          level: info.level,
          device: info.device,
          rawMessage: info.rawMessage,
          open: false,
        }]);
      } else if (pieces.length === 1) {
        pushLines([{
          eventName,
          payload,
          text: info.text,
          ts: info.ts,
          level: info.level,
          device: info.device,
          rawMessage: info.rawMessage,
          open: false,
        }]);
      } else {
        // multi-line: create a header then each piece as its own line
        const items = [];
        items.push({
          eventName,
          payload,
          text: `${info.ts} | ${eventName} | ${info.device} | ${info.level} | (multi-line ${pieces.length} lines)`,
          ts: info.ts,
          level: info.level,
          device: info.device,
          rawMessage: info.rawMessage,
          open: false,
        });
        pieces.forEach((p) => {
          const parsed = parseFromText(p);
          items.push({
            eventName,
            payload,
            text: `${info.ts} | ${eventName} | ${parsed.device || info.device} | ${parsed.level || info.level} | ${p}`,
            ts: info.ts,
            level: parsed.level || info.level,
            device: parsed.device || info.device,
            rawMessage: p,
            open: false,
          });
        });
        pushLines(items);
      }
      // debug observe incoming event in browser console
      // eslint-disable-next-line no-console
      console.debug('[socket event recv]', eventName, payload);
    };

    // explicit listeners (guaranteed)
    const handleLog = (payload) => {
      enqueueEvent('log', payload);
    };
    const handleTerminalOutput = (payload) => {
      // payload may be { message: "..." } or string
      const p = payload && payload.message ? payload.message : payload;
      enqueueEvent('terminal_output', p);
    };
    // onAny fallback
    const onAnyHandler = (eventName, ...args) => {
      const payload = args.length === 1 ? args[0] : args;
      enqueueEvent(eventName, payload);
    };

    socket.on('log', handleLog);
    socket.on('terminal_output', handleTerminalOutput);
    if (socket.onAny) socket.onAny(onAnyHandler);

    // connection state notifications
    const onConnect = () => enqueueEvent('connect', { message: 'socket connected', timestamp: new Date().toISOString() });
    const onDisconnect = (reason) => enqueueEvent('disconnect', { message: `disconnected: ${reason}`, timestamp: new Date().toISOString() });
    const onConnectError = (err) => enqueueEvent('connect_error', { message: `connect_error: ${err?.message || String(err)}`, timestamp: new Date().toISOString() });

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('connect_error', onConnectError);

    return () => {
      socket.off('log', handleLog);
      socket.off('terminal_output', handleTerminalOutput);
      if (socket.offAny) socket.offAny(onAnyHandler);
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('connect_error', onConnectError);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [socketUrl, maxLines, paused, fullView]);

  // autoscroll
  useEffect(() => {
    if (!paused && containerRef.current) {
      const el = containerRef.current;
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
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

  const toggleOpen = (idx) => {
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, open: !l.open } : l)));
  };

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
    <Paper elevation={3} sx={{ p: 1, height: terminalHeight, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Box>
          <Typography variant="subtitle2">Terminal</Typography>
          <Typography variant="caption" color="text.secondary">Realtime logs (click a line to expand raw payload)</Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <TextField size="small" placeholder="search..." value={search} onChange={(e) => setSearch(e.target.value)} />
          <Select size="small" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <MenuItem value="ALL">ALL</MenuItem>
            <MenuItem value="DEBUG">DEBUG</MenuItem>
            <MenuItem value="INFO">INFO</MenuItem>
            <MenuItem value="NEW">NEW</MenuItem>
            <MenuItem value="ERROR">ERROR</MenuItem>
            <MenuItem value="WARN">WARN</MenuItem>
            <MenuItem value="ACCESS">ACCESS</MenuItem>
          </Select>

          <Button size="small" variant={fullView ? 'contained' : 'outlined'} onClick={() => setFullView((f) => !f)} title="Toggle Full View">
            {fullView ? 'Full' : 'Trimmed'}
          </Button>

          <IconButton onClick={() => setPaused((p) => !p)} color="primary" size="small">
            {paused ? <PlayArrowIcon /> : <PauseIcon />}
          </IconButton>

          <Tooltip title="Clear terminal">
            <IconButton onClick={clear} color="error" size="small"><ClearIcon /></IconButton>
          </Tooltip>

          <Tooltip title="Download logs">
            <IconButton onClick={download} color="success" size="small"><DownloadIcon /></IconButton>
          </Tooltip>
        </Box>
      </Box>

      <Box
        ref={containerRef}
        sx={{
          flex: 1,
          overflowY: 'auto',
          bgcolor: 'common.black',
          color: 'grey.100',
          fontFamily: 'monospace',
          p: 1,
          borderRadius: 1,
          lineHeight: '1.3',
          fontSize: '0.78rem',
        }}
      >
        {filtered.map((l, i) => (
          <Box key={i} sx={{ mb: 0.5 }}>
            <ListItem
              alignItems="flex-start"
              onClick={() => toggleOpen(i)}
              sx={{ cursor: 'pointer', py: 0.2, px: 0 }}
            >
              <ListItemText
                primary={
                  <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                    <Typography variant="caption" sx={{ color: 'grey.500' }}>
                      [{new Date(l.ts).toLocaleTimeString()}]
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>{l.eventName}</Typography>
                    <Typography variant="caption" sx={{ color: 'grey.400' }}>{l.device}</Typography>
                    <Typography variant="caption" sx={{ color: levelColor(l.level), fontWeight: 700 }}>{l.level}</Typography>
                    <Typography variant="body2" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '60ch' }}>
                      {l.text.split(' | ').slice(4).join(' | ')}
                    </Typography>
                  </Box>
                }
              />
            </ListItem>

            <Collapse in={!!l.open} timeout="auto" unmountOnExit>
              <Box sx={{ bgcolor: '#0b0b0b', p: 1, borderRadius: 1, color: 'grey.300', fontSize: '0.75rem' }}>
                <Typography variant="caption" sx={{ color: 'grey.500' }}>Raw payload:</Typography>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {typeof l.rawMessage === 'string' ? l.rawMessage : safeStringify(l.rawMessage, 4000)}
                </pre>
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

/* ---------------- NotificationsPanel (small & functional) ---------------- */
function NotificationsPanel({ socketUrl, notificationsHeight = '220px' }) {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [totalLogs, setTotalLogs] = useState(0);
  const [branchCounts, setBranchCounts] = useState({});

  useEffect(() => {
    const socket = getSharedSocket(socketUrl);
    if (!socket) return;

    const onAnyHandler = (eventName, ...args) => {
      const payload = args.length === 1 ? args[0] : args;
      if (eventName === 'new_log' || eventName === 'new_logs_batch' || eventName === 'access_log' || eventName === 'log' || eventName === 'terminal_output') {
        const id = `${eventName}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        const title = eventName === 'access_log' ? `Access: ${payload.userid || payload.device_id}` : `${eventName} — ${pickDevice(payload)}`;
        const time = pickTimestamp(payload);
        const note = { id, title, time, payload, read: false };
        setItems((prev) => [note, ...prev].slice(0, 300));
        setUnread((u) => u + 1);
        if (eventName === 'new_logs_batch') {
          const b = payload.branch_id ?? payload.device_id ?? 'unknown';
          const count = payload.count ?? (Array.isArray(payload.logs) ? payload.logs.length : 1);
          setBranchCounts((prev) => ({ ...(prev || {}), [b]: (prev?.[b] || 0) + count }));
          setTotalLogs((t) => t + count);
        } else {
          setTotalLogs((t) => t + 1);
          const b = payload.branch_id ?? payload.device_id ?? 'unknown';
          setBranchCounts((prev) => ({ ...(prev || {}), [b]: (prev?.[b] || 0) + 1 }));
        }
      }
    };

    if (socket.onAny) socket.onAny(onAnyHandler);
    return () => {
      if (socket.offAny) socket.offAny(onAnyHandler);
    };
  }, [socketUrl]);

  const markRead = (id) => {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, read: true } : it)));
    setUnread((prev) => Math.max(0, prev - 1));
  };
  const markAllRead = () => {
    setItems((prev) => prev.map((it) => ({ ...it, read: true })));
    setUnread(0);
  };
  const clearAll = () => {
    setItems([]);
    setUnread(0);
    setTotalLogs(0);
    setBranchCounts({});
  };

  return (
    <Paper elevation={3} sx={{ p: 1, height: notificationsHeight, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Box>
          <Typography variant="subtitle2">Notifications</Typography>
          <Typography variant="caption" color="text.secondary">Realtime activity & alerts</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Badge badgeContent={unread} color="error"><Box sx={{ width: 24 }} /></Badge>
          <Button size="small" onClick={markAllRead}>Mark all</Button>
          <Button size="small" color="error" onClick={clearAll}>Clear</Button>
        </Box>
      </Box>

      <Box sx={{ px: 1, pb: 1 }}>
        <Typography variant="body2">Total new logs: <strong>{totalLogs}</strong></Typography>
        <Box sx={{ mt: 0.5 }}>
          <Typography variant="caption" color="text.secondary">Per-branch:</Typography>
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {Object.keys(branchCounts).length === 0 && <li><Typography variant="caption" color="text.secondary">No data</Typography></li>}
            {Object.entries(branchCounts).map(([b, c]) => (
              <li key={b}><Typography variant="caption">{b}: {c}</Typography></li>
            ))}
          </Box>
        </Box>
      </Box>

      <Box sx={{ overflow: 'auto', flex: 1 }}>
        {items.length === 0 && <Typography variant="body2" color="text.secondary">No notifications yet</Typography>}
        <List dense disablePadding>
          {items.map((it) => (
            <React.Fragment key={it.id}>
              <ListItem alignItems="flex-start" secondaryAction={<Button size="small" onClick={() => markRead(it.id)}>Mark</Button>}>
                <ListItemText primary={it.title} secondary={new Date(it.time).toLocaleString()} primaryTypographyProps={{ noWrap: true }} />
              </ListItem>
              <Divider component="li" />
            </React.Fragment>
          ))}
        </List>
      </Box>
    </Paper>
  );
}

/* ---------------- Main exported widget ---------------- */
export default function LiveTerminalAndNotifications({
  socketUrl,
  containerWidth = '30%',
  notificationsHeight = '220px',
  terminalHeight = '420px',
  maxLines = DEFAULT_MAX_LINES,
}) {
  return (
    <Box sx={{ width: containerWidth, minWidth: '260px', display: 'flex', flexDirection: 'column', gap: 1, maxHeight: '92vh', overflow: 'hidden', p: 1 }}>
      <NotificationsPanel socketUrl={socketUrl} notificationsHeight={notificationsHeight} />
      <TerminalConsole socketUrl={socketUrl} terminalHeight={terminalHeight} maxLines={maxLines} />
    </Box>
  );
}
