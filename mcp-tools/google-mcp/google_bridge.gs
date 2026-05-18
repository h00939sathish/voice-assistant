/**
 * Buddy Voice Assistant — Google Apps Script Bridge
 * 
 * Deploy as a Web App:
 *   Execute as: Me | Who has access: Anyone
 * 
 * Set Script Property:
 *   BUDDY_SECRET = your_random_secret_here
 * 
 * Buddy sends POST requests with JSON body:
 *   {
 *     "action": "gmail_search",
 *     "secret": "your_random_secret_here",
 *     "params": { "query": "from:boss" }
 *   }
 */

// ── Entry Point ─────────────────────────────────────────────────────

function doPost(e) {
  try {
    const payload = _parsePayload(e);
    _authorize(payload);
    const action = payload.action || '';
    const params = payload.params || {};

    const handlers = {
      'gmail_search':       () => gmailSearch(params),
      'gmail_read':         () => gmailRead(params),
      'gmail_send':         () => gmailSend(params),
      'gmail_list_unread':  () => gmailListUnread(params),
      'sheets_read':        () => sheetsRead(params),
      'sheets_write':       () => sheetsWrite(params),
      'sheets_append':      () => sheetsAppend(params),
      'docs_create':        () => docsCreate(params),
      'drive_search':       () => driveSearch(params),
      'calendar_list':      () => calendarList(params),
    };

    if (!handlers[action]) {
      return _json({ error: `Unknown action: ${action}`, available: Object.keys(handlers) });
    }

    const result = handlers[action]();
    return _json({ ok: true, action: action, data: result });

  } catch (err) {
    return _json({ ok: false, error: err.toString() });
  }
}

function doGet(e) {
  return _json({ status: 'Buddy Google Bridge is running', timestamp: new Date().toISOString() });
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function _parsePayload(e) {
  if (!e || !e.postData || !e.postData.contents) {
    throw new Error('Missing JSON request body');
  }
  return JSON.parse(e.postData.contents);
}

function _authorize(payload) {
  const secret = PropertiesService.getScriptProperties().getProperty('BUDDY_SECRET');
  if (!secret) {
    throw new Error('Bridge secret is not configured');
  }

  const reqSecret = String(payload.secret || '');
  if (reqSecret !== secret) {
    throw new Error('Unauthorized');
  }
}

function _requireString(value, fieldName) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`${fieldName} is required`);
  }
  return value.trim();
}

function _optionalString(value, fallback) {
  if (typeof value !== 'string') return fallback || '';
  return value;
}

function _boundedInt(value, fallback, maxValue) {
  const parsed = Number(value == null ? fallback : value);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return fallback;
  }
  return Math.min(Math.floor(parsed), maxValue);
}

function _getSheet(ss, sheetName) {
  const sheet = sheetName ? ss.getSheetByName(sheetName) : ss.getActiveSheet();
  if (!sheet) {
    throw new Error(`Sheet not found: ${sheetName}`);
  }
  return sheet;
}

function _validate2DValues(values) {
  if (!Array.isArray(values) || values.length === 0 || !values.every(Array.isArray)) {
    throw new Error('values must be a non-empty 2D array');
  }

  const width = values[0].length;
  if (width < 1) {
    throw new Error('values must contain at least one column');
  }

  values.forEach((row, index) => {
    if (row.length !== width) {
      throw new Error(`Row ${index + 1} has a different column count`);
    }
  });

  return values;
}

function _escapeDriveQueryLiteral(value) {
  return String(value || '')
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'");
}

function _latestMessage(thread) {
  const messages = thread.getMessages();
  return messages[messages.length - 1];
}

// ── Gmail ───────────────────────────────────────────────────────────

function gmailSearch(p) {
  const query = p.query || 'is:unread';
  const max = _boundedInt(p.max_results, 5, 20);
  const threads = GmailApp.search(query, 0, max);
  return threads.map(t => {
    const msg = _latestMessage(t);
    return {
      id: t.getId(),
      subject: msg.getSubject(),
      from: msg.getFrom(),
      date: msg.getDate().toISOString(),
      snippet: msg.getPlainBody().substring(0, 200),
      unread: t.isUnread(),
      message_count: t.getMessageCount(),
    };
  });
}

function gmailRead(p) {
  const thread = GmailApp.getThreadById(_requireString(p.thread_id, 'thread_id'));
  if (!thread) return { error: 'Thread not found' };
  const messages = thread.getMessages();
  return {
    id: thread.getId(),
    subject: messages[0].getSubject(),
    message_count: messages.length,
    messages: messages.map(m => ({
      from: m.getFrom(),
      to: m.getTo(),
      date: m.getDate().toISOString(),
      body: m.getPlainBody().substring(0, 3000),
    })),
  };
}

function gmailSend(p) {
  const to = _requireString(p.to, 'to');
  const subject = _optionalString(p.subject, '');
  const body = _optionalString(p.body, '');
  GmailApp.sendEmail(to, subject, body, {
    htmlBody: _optionalString(p.html_body, '') || undefined,
    cc: _optionalString(p.cc, '') || undefined,
    bcc: _optionalString(p.bcc, '') || undefined,
  });
  return { sent: true, to: to, subject: subject };
}

function gmailListUnread(p) {
  const max = _boundedInt(p.max_results, 10, 20);
  const threads = GmailApp.search('is:unread', 0, max);
  return {
    unread_count: GmailApp.getInboxUnreadCount(),
    threads: threads.map(t => {
      const msg = _latestMessage(t);
      return {
        id: t.getId(),
        subject: msg.getSubject(),
        from: msg.getFrom(),
        date: msg.getDate().toISOString(),
        snippet: msg.getPlainBody().substring(0, 150),
      };
    }),
  };
}

// ── Google Sheets ───────────────────────────────────────────────────

function sheetsRead(p) {
  const ss = SpreadsheetApp.openById(_requireString(p.spreadsheet_id, 'spreadsheet_id'));
  const sheet = _getSheet(ss, _optionalString(p.sheet_name, ''));
  const range = _optionalString(p.range, 'A1:Z100') || 'A1:Z100';
  const values = sheet.getRange(range).getValues();
  return {
    spreadsheet_id: p.spreadsheet_id,
    sheet_name: sheet.getName(),
    range: range,
    rows: values.length,
    data: values,
  };
}

function sheetsWrite(p) {
  const spreadsheetId = _requireString(p.spreadsheet_id, 'spreadsheet_id');
  const targetRange = _requireString(p.range, 'range');
  const values = _validate2DValues(p.values);
  const ss = SpreadsheetApp.openById(spreadsheetId);
  const sheet = _getSheet(ss, _optionalString(p.sheet_name, ''));
  const range = sheet.getRange(targetRange);

  if (range.getNumRows() !== values.length || range.getNumColumns() !== values[0].length) {
    throw new Error('values shape does not match the target range');
  }

  range.setValues(values);
  return { written: true, range: targetRange, rows: values.length };
}

function sheetsAppend(p) {
  const spreadsheetId = _requireString(p.spreadsheet_id, 'spreadsheet_id');
  if (!Array.isArray(p.row) || p.row.length === 0) {
    throw new Error('row must be a non-empty array');
  }
  const ss = SpreadsheetApp.openById(spreadsheetId);
  const sheet = _getSheet(ss, _optionalString(p.sheet_name, ''));
  sheet.appendRow(p.row);
  return { appended: true, row: p.row, sheet: sheet.getName() };
}

// ── Google Docs ─────────────────────────────────────────────────────

function docsCreate(p) {
  const doc = DocumentApp.create(_optionalString(p.title, 'Buddy Note') || 'Buddy Note');
  if (p.content) {
    doc.getBody().appendParagraph(p.content);
  }
  return {
    doc_id: doc.getId(),
    url: doc.getUrl(),
    title: doc.getName(),
  };
}

// ── Google Drive ────────────────────────────────────────────────────

function driveSearch(p) {
  const query = _escapeDriveQueryLiteral(_optionalString(p.query, ''));
  const type = _escapeDriveQueryLiteral(_optionalString(p.type, ''));
  const max = _boundedInt(p.max_results, 10, 30);
  let searchQuery = `title contains '${query}'`;
  if (type) searchQuery += ` and mimeType contains '${type}'`;

  const files = DriveApp.searchFiles(searchQuery);
  const results = [];
  let count = 0;
  while (files.hasNext() && count < max) {
    const f = files.next();
    results.push({
      id: f.getId(),
      name: f.getName(),
      url: f.getUrl(),
      type: f.getMimeType(),
      size: f.getSize(),
      updated: f.getLastUpdated().toISOString(),
    });
    count++;
  }
  return { query: query, count: results.length, files: results };
}

// ── Google Calendar ─────────────────────────────────────────────────

function calendarList(p) {
  const cal = CalendarApp.getDefaultCalendar();
  const now = new Date();
  const daysAhead = _boundedInt(p.days_ahead, 7, 365);
  const end = new Date(now.getTime() + daysAhead * 86400000);
  const events = cal.getEvents(now, end);
  const max = _boundedInt(p.max_results, 10, 30);

  return {
    calendar: cal.getName(),
    from: now.toISOString(),
    to: end.toISOString(),
    event_count: Math.min(events.length, max),
    events: events.slice(0, max).map(e => ({
      title: e.getTitle(),
      start: e.getStartTime().toISOString(),
      end: e.getEndTime().toISOString(),
      location: e.getLocation() || '',
      description: (e.getDescription() || '').substring(0, 200),
      all_day: e.isAllDayEvent(),
    })),
  };
}
