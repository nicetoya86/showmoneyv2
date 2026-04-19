const fs = require('fs');
const path = require('path');

// Ensure logs directory exists
const logsDir = path.join(__dirname, '../logs');
if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir, { recursive: true });
}

class JsonLogger {
  constructor(service) {
    this.service = service;
    this.logFile = path.join(logsDir, `${service}_${this.getDateString()}.log`);
  }

  getDateString() {
    const d = new Date();
    return d.toISOString().split('T')[0];
  }

  // Generate request ID for a trading flow
  // Format: trading_YYYYMMDDHHMMSS_STOCKCODE
  generateRequestId(stockCode = '') {
    const now = new Date();
    const timestamp = now.toISOString().replace(/[-T:\.Z]/g, '').slice(0, 14);
    const code = stockCode ? `_${stockCode}` : '';
    return `trading_${timestamp}${code}`;
  }

  // Format log entry as JSON
  formatLog(level, message, data = {}, requestId = 'N/A') {
    return JSON.stringify({
      timestamp: new Date().toISOString(),
      level: level,
      service: this.service,
      request_id: requestId,
      message: message,
      ...(Object.keys(data).length > 0 && { data: data })
    });
  }

  // Write log to file and console
  writeLog(logEntry) {
    try {
      fs.appendFileSync(this.logFile, logEntry + '\n', 'utf8');
      console.log(logEntry);
    } catch (err) {
      console.error(`Failed to write log: ${err.message}`);
    }
  }

  // Log levels
  debug(message, data = {}, requestId = 'N/A') {
    const entry = this.formatLog('DEBUG', message, data, requestId);
    this.writeLog(entry);
  }

  info(message, data = {}, requestId = 'N/A') {
    const entry = this.formatLog('INFO', message, data, requestId);
    this.writeLog(entry);
  }

  warning(message, data = {}, requestId = 'N/A') {
    const entry = this.formatLog('WARNING', message, data, requestId);
    this.writeLog(entry);
  }

  error(message, data = {}, requestId = 'N/A') {
    const entry = this.formatLog('ERROR', message, data, requestId);
    this.writeLog(entry);
  }
}

module.exports = JsonLogger;
