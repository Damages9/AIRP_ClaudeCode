/**
 * mvu_server.js — 常驻 MVU 引擎，直接执行角色卡脚本（和酒馆助手一样）
 *
 * 用法: node mvu_server.js --card=<卡片文件夹> [--port=8766]
 *
 * 与 run_card_scripts.js 的区别：
 *   - run_card_scripts: 导入时一次性提取 → JSON
 *   - mvu_server:     常驻进程，真实 Zod 验证，实时注入，零提取
 */

'use strict';

const http = require('http');
const vm = require('vm');
const fs = require('fs');
const path = require('path');
const z = require('zod');
const { extendZod, makeLodash, generateSchemaMeta, generateInitvar, generateScopeMeta, extractInjectionRulesFromScripts } = require('./mvu_shared.js');
extendZod(z);

// ============================================================
// CLI args
// ============================================================
let cardFolder = null;
let port = 8766;
for (const arg of process.argv) {
  if (arg.startsWith('--card=')) cardFolder = arg.slice(7);
  if (arg.startsWith('--port=')) port = parseInt(arg.slice(7), 10);
}
if (!cardFolder) {
  console.error('用法: node mvu_server.js --card=<卡片文件夹> [--port=8766]');
  process.exit(1);
}

// ============================================================
// lodash 工具（来自 mvu_shared）
// ============================================================
const _ = makeLodash();

// ============================================================
// 执行卡片脚本，捕获真实 Zod schema 和注入函数
// ============================================================
let capturedSchema = null;       // 真实 Zod schema 对象
let injectionUpdateFn = null;   // updateKinkInjection() 函数引用
let injectionRules = [];        // 结构化注入规则
let scriptErrors = [];

function loadCard(cardDir) {
  capturedSchema = null;
  injectionUpdateFn = null;
  injectionRules = [];
  scriptErrors = [];

  const cardDataPath = path.join(cardDir, '.card_data.json');
  if (!fs.existsSync(cardDataPath)) {
    return { ok: false, error: `.card_data.json 不存在: ${cardDataPath}` };
  }

  let cardData;
  try {
    cardData = JSON.parse(fs.readFileSync(cardDataPath, 'utf-8'));
  } catch (err) {
    return { ok: false, error: `.card_data.json 解析失败: ${err.message}` };
  }
  const tavernHelper = cardData?.data?.extensions?.tavern_helper;
  if (!tavernHelper || !tavernHelper.scripts) {
    return { ok: true, no_scripts: true, message: '卡片无 tavern_helper 脚本' };
  }

  const scripts = tavernHelper.scripts.filter(s => s.enabled !== false);

  // --- Mock: registerMvuSchema ---
  function registerMvuSchema(schema) {
    capturedSchema = schema;
  }

  // --- Mock: injectPrompts ---
  function injectPrompts(prompts, opts) {
    injectionRules = [];
    for (const p of prompts || []) {
      injectionRules.push({
        id: p.id || '',
        position: p.position || 'none',
        depth: typeof p.depth === 'number' ? p.depth : 0,
        role: p.role || 'system',
        content: p.content || '',
        should_scan: !!p.should_scan,
        once: opts?.once || false,
      });
    }
    return { uninject: () => {} };
  }

  // --- Mock: eventOn ---
  const eventHandlers = {};
  function eventOn(eventName, callback) {
    if (!eventHandlers[eventName]) eventHandlers[eventName] = [];
    eventHandlers[eventName].push(callback);
  }

  // --- Mock: Mvu ---
  let mockStatData = {};
  const Mvu = {
    events: { VARIABLE_UPDATE_ENDED: 'VARIABLE_UPDATE_ENDED' },
    getMvuData: function () { return { stat_data: mockStatData }; },
  };

  // --- Mock: waitGlobalInitialized ---
  function waitGlobalInitialized() { return Promise.resolve(); }

  // --- Mock: $ ---
  let $Callbacks = [];
  function $(fn) { if (typeof fn === 'function') $Callbacks.push(fn); }

  // --- tavern_events ---
  const tavern_events = {
    CHAT_CHANGED: 'CHAT_CHANGED',
    GENERATION_AFTER_COMMANDS: 'GENERATION_AFTER_COMMANDS',
    MESSAGE_RECEIVED: 'MESSAGE_RECEIVED',
    GENERATION_ENDED: 'GENERATION_ENDED',
    APP_READY: 'APP_READY',
    GENERATION_STARTED: 'GENERATION_STARTED',
    STREAM_TOKEN_RECEIVED_FULLY: 'STREAM_TOKEN_RECEIVED_FULLY',
    STREAM_TOKEN_RECEIVED_INCREMENTALLY: 'STREAM_TOKEN_RECEIVED_INCREMENTALLY',
  };

  const sandbox = {
    z,
    registerMvuSchema,
    injectPrompts,
    eventOn,
    Mvu,
    waitGlobalInitialized,
    $,
    _,
    tavern_events,
    console: { log: () => {}, error: () => {}, warn: () => {}, info: () => {}, debug: () => {} },
    setTimeout,
    clearTimeout,
    setInterval: () => {},
    clearInterval: () => {},
    Promise, JSON, Object, Array, String, Number, Boolean,
    Math, Date, RegExp, Error, Map, Set,
    parseInt, parseFloat, isNaN, isFinite,
  };

  const vmContext = vm.createContext(sandbox);

  // Preprocess: remove imports, .prefault()→.default(), remove export
  function preprocess(content) {
    let out = content;
    out = out.replace(/^import\s+.*?;?\s*$/gm, '// [removed import]');
    out = out.replace(/\.prefault\(/g, '.default(');
    out = out.replace(/\bexport\s+(const|let|var|function|class|async\s+function)\b/g, '$1');
    return out;
  }

  // Classify and execute scripts
  const mvuScripts = [], schemaScripts = [], injectionScripts = [], otherScripts = [];
  for (const script of scripts) {
    if (!script.content || !script.content.trim()) continue;
    const c = script.content;
    const n = script.name || '';
    if (n.includes('Zod') || n.includes('var_update') || c.includes('MagVarUpdate')) {
      mvuScripts.push(script);
    } else if (c.includes('registerMvuSchema')) {
      schemaScripts.push(script);
    } else if (c.includes('injectPrompts')) {
      injectionScripts.push(script);
    } else {
      otherScripts.push(script);
    }
  }

  const ordered = [...mvuScripts, ...schemaScripts, ...injectionScripts, ...otherScripts];

  for (const script of ordered) {
    const name = script.name || 'unknown';
    const processed = preprocess(script.content);
    try {
      const vmScript = new vm.Script(processed, { filename: `${name}.js`, timeout: 10000 });
      vmScript.runInContext(vmContext, { timeout: 10000 });
    } catch (err) {
      scriptErrors.push({ script: name, error: err.message });
    }
  }

  // Execute $(callback) callbacks
  for (const cb of $Callbacks) {
    try { cb(); } catch (err) { /* silent */ }
  }

  // Store injection update function for later calls
  // The keyword script defines updateKinkInjection() in the sandbox
  if (vmContext.updateKinkInjection) {
    injectionUpdateFn = vmContext.updateKinkInjection;
  }

  // Extract injection rules from keyword script (structural config)
  if (injectionUpdateFn || injectionScripts.length > 0) {
    injectionRules = extractInjectionRulesFromScripts(scripts);
  }

  return {
    ok: true,
    has_schema: !!capturedSchema,
    has_injection: !!injectionUpdateFn,
    scripts_executed: ordered.length,
    errors: scriptErrors,
  };
}

// ============================================================
// HTTP Server
// ============================================================
const server = http.createServer((req, res) => {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  // CORS for local dev
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end('{}');
    return;
  }

  // --- GET /status ---
  if (req.method === 'GET' && req.url === '/status') {
    res.writeHead(200);
    res.end(JSON.stringify({
      loaded: !!capturedSchema,
      has_injection: !!injectionUpdateFn,
      errors: scriptErrors,
    }));
    return;
  }

  // --- POST /reload ---
  if (req.method === 'POST' && req.url === '/reload') {
    const result = loadCard(cardFolder);
    res.writeHead(result.ok ? 200 : 400);
    res.end(JSON.stringify(result));
    return;
  }

  // --- POST /validate ---
  if (req.method === 'POST' && req.url === '/validate') {
    let chunks = [];
    req.on('data', chunk => chunks.push(chunk));
    req.on('end', () => {
      try {
        const body = Buffer.concat(chunks).toString('utf-8');
        const { path, value } = JSON.parse(body);
        const field = resolveSchemaPath(capturedSchema, path);
        const result = field ? field.safeParse(value) : { success: false, error: { issues: [{ message: `path not found: ${path}` }] } };
        const out = result.success ? { ok: true } : { ok: false, error: result.error.issues.map(i => i.message).join('; ') };
        res.writeHead(200);
        res.end(JSON.stringify(out));
      } catch (e) {
        res.writeHead(400);
        res.end(JSON.stringify({ ok: false, error: e.message }));
      }
    });
    return;
  }

  // --- POST /validate_all ---
  if (req.method === 'POST' && req.url === '/validate_all') {
    let chunks = [];
    req.on('data', chunk => chunks.push(chunk));
    req.on('end', () => {
      try {
        const body = Buffer.concat(chunks).toString('utf-8');
        const { commands } = JSON.parse(body);
        const results = [];
        for (const cmd of (commands || [])) {
          const r = validateValue(capturedSchema, cmd.path, cmd.value);
          results.push({ ...cmd, ...r });
        }
        res.writeHead(200);
        res.end(JSON.stringify({ results }));
      } catch (e) {
        res.writeHead(400);
        res.end(JSON.stringify({ ok: false, error: e.message }));
      }
    });
    return;
  }

  // --- POST /initvar ---
  if (req.method === 'POST' && req.url === '/initvar') {
    const initvar = generateInitvar(capturedSchema);
    const scope = generateScopeMeta(initvar);
    const schemaMeta = generateSchemaMeta(capturedSchema);
    res.writeHead(200);
    res.end(JSON.stringify({ initvar, scope, schema: schemaMeta }));
    return;
  }

  // --- POST /inject ---
  if (req.method === 'POST' && req.url === '/inject') {
    let injectChunks = [];
    req.on('data', chunk => injectChunks.push(chunk));
    req.on('end', () => {
      try {
        const body = Buffer.concat(injectChunks).toString('utf-8');
        const { stat_data } = JSON.parse(body);
        let keywords = [];

        if (injectionRules.length > 0) {
          const rule = injectionRules[0];
          const sourceVal = _.get(stat_data, rule.source_path);
          if (sourceVal && typeof sourceVal === 'string' && sourceVal.trim()) {
            // Parse split pattern
            let splitRe = rule.split_pattern;
            if (splitRe.startsWith('/') && splitRe.lastIndexOf('/') > 0) {
              splitRe = splitRe.slice(1, splitRe.lastIndexOf('/'));
            }
            let parts = [];
            try {
              parts = sourceVal.split(new RegExp(splitRe));
            } catch (e) {
              parts = sourceVal.replace(/、/g, ',').replace(/，/g, ',').split(',');
            }
            keywords = parts.map(k => k.trim()).filter(k => k.length > 0)
              .map(k => (rule.prefix && !k.startsWith(rule.prefix)) ? rule.prefix + k : k);
          }
        }

        res.writeHead(200);
        res.end(JSON.stringify({ keywords }));
      } catch (e) {
        res.writeHead(400);
        res.end(JSON.stringify({ ok: false, error: e.message }));
      }
    });
    return;
  }

  // --- POST /schema ---
  if (req.method === 'POST' && req.url === '/schema') {
    const schemaMeta = generateSchemaMeta(capturedSchema);
    const initvar = generateInitvar(capturedSchema);
    const scope = generateScopeMeta(initvar);
    res.writeHead(200);
    res.end(JSON.stringify({ ...schemaMeta, scope, initvar }));
    return;
  }

  // --- 404 ---
  res.writeHead(404);
  res.end(JSON.stringify({ error: 'not found' }));
});

// ============================================================
// 启动
// ============================================================
const loadResult = loadCard(cardFolder);
if (!loadResult.ok) {
  console.error(`[mvu_server] 加载失败: ${loadResult.error}`);
} else if (loadResult.no_scripts) {
  console.log(`[mvu_server] ${loadResult.message}，在 :${port} 以空引擎运行`);
} else {
  console.log(`[mvu_server] Schema=${!!capturedSchema} Injection=${!!injectionUpdateFn} Scripts=${loadResult.scripts_executed} Errors=${scriptErrors.length}`);
}

server.listen(port, '127.0.0.1', () => {
  console.log(`[mvu_server] 监听 http://127.0.0.1:${port}`);
});

// 优雅退出
process.on('SIGTERM', () => { server.close(); process.exit(0); });
process.on('SIGINT', () => { server.close(); process.exit(0); });
