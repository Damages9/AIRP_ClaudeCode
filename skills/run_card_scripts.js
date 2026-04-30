/**
 * run_card_scripts.js — Node.js vm 沙箱执行角色卡 tavern_helper 脚本
 *
 * 用法: node run_card_scripts.js <卡片文件夹路径>
 * 输出: 结构化 JSON 到 stdout（initvar + schema + injections）
 *
 * 安全: vm.Script.runInNewContext() 无 require/process/fs 权限
 *        超时 15 秒，卡片脚本只能访问注入的 mock 全局变量
 */

'use strict';

const vm = require('vm');
const fs = require('fs');
const path = require('path');
const z = require('zod');
const { extendZod, makeLodash, generateSchemaMeta, generateInitvar, generateScopeMeta, extractInjectionRulesFromScripts } = require('./mvu_shared.js');
extendZod(z);
const _ = makeLodash();

// ============================================================
// 读取卡片数据
// ============================================================
const cardFolder = process.argv[2];
if (!cardFolder) {
  console.error('用法: node run_card_scripts.js <卡片文件夹路径>');
  process.exit(1);
}

const cardDataPath = path.join(cardFolder, '.card_data.json');
if (!fs.existsSync(cardDataPath)) {
  console.error(`找不到 .card_data.json: ${cardDataPath}`);
  process.exit(1);
}

const cardData = JSON.parse(fs.readFileSync(cardDataPath, 'utf-8'));
const tavernHelper = cardData?.data?.extensions?.tavern_helper;
if (!tavernHelper || !tavernHelper.scripts) {
  // 无 tavern_helper 脚本 → 输出空结果，由 Python 端回退到 [initvar]
  console.log(JSON.stringify({ _no_scripts: true }));
  process.exit(0);
}

const scripts = tavernHelper.scripts.filter(s => s.enabled !== false);

// ============================================================
// 收集输出
// ============================================================
const output = {
  initvar: null,
  schema: null,
  injections: [],
};

// ============================================================
// 构建沙箱全局变量
// ============================================================

// --- mock registerMvuSchema: 捕获并合并所有 Zod schema ---
const capturedSchemas = [];
let capturedSchema = null;  // 向后兼容：保留最后一个
function registerMvuSchema(schema) {
  capturedSchemas.push(schema);
  capturedSchema = schema;
}

// --- mock injectPrompts: 捕获注入调用 ---
function injectPrompts(prompts, opts) {
  for (const p of prompts || []) {
    output.injections.push({
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

// --- mock eventOn: 记录事件 ---
const eventsRegistered = [];
function eventOn(eventName, callback) {
  eventsRegistered.push(eventName);
}

// --- mock Mvu: 返回空变量（导入时无运行时状态） ---
const Mvu = {
  events: {
    VARIABLE_UPDATE_ENDED: 'VARIABLE_UPDATE_ENDED',
  },
  getMvuData: function (opts) {
    // 导入阶段没有运行时变量，返回包含空 stat_data 的结构
    return { stat_data: {} };
  },
};

// --- mock waitGlobalInitialized: 立即 resolve ---
function waitGlobalInitialized(name) {
  return Promise.resolve();
}

// --- mock setTimeout (来自全局，但在 vm 中需要显式传入) ---
// 使用宿主 setTimeout

// --- mock $: DOM ready → 立即执行 ---
let $Callbacks = [];
function $(fn) {
  if (typeof fn === 'function') {
    $Callbacks.push(fn);
  }
}

// --- 模拟 tavern_events 全局对象 ---
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

// ============================================================
// 预处理脚本内容
// ============================================================
function preprocessScript(content) {
  let processed = content;

  // 移除 import 语句（我们已通过沙箱提供所有需要的全局变量）
  processed = processed.replace(/^import\s+.*?;?\s*$/gm, '// [removed import]');

  // .prefault(X) → .default(X)  （MagVarUpdate 自定义方法 → Zod 标准方法）
  processed = processed.replace(/\.prefault\(/g, '.default(');

  // export const/let/var → const/let/var（移除 ES module 导出）
  processed = processed.replace(/\bexport\s+(const|let|var|function|class|async\s+function)\b/g, '$1');

  // const Schema / const Variable / const schema → var（避免跨脚本重复声明）
  // 多个 tavern_helper 脚本各自声明同名的 const Schema / const Variable
  // 必须用 var（不是 let），因为 VM 中所有脚本共享全局作用域，let 不允许重复声明
  processed = processed.replace(/\bconst\s+(Schema|Variable|schema|variable)\b/g, 'var $1');

  // $() → 直接执行：$(() => { registerMvuSchema(Schema) }) → registerMvuSchema(Schema);
  // 必须在脚本内直接调用（而非延迟回调），否则 var Schema 会被后续脚本覆盖
  processed = processed.replace(
    /\$\(\(\)\s*=>\s*\{\s*registerMvuSchema\(([^)]+)\);?\s*\}\);?/g,
    'registerMvuSchema($1);'
  );

  return processed;
}

// ============================================================
// 执行脚本
// ============================================================
const sandbox = {
  // 真实 Zod 库
  z,
  // mock 函数
  registerMvuSchema,
  injectPrompts,
  eventOn,
  Mvu,
  waitGlobalInitialized,
  $,
  // 工具库
  _,
  // tavern events
  tavern_events,
  // 标准全局
  console: {
    log: (...args) => { /* 静默 */ },
    error: (...args) => { /* 静默 */ },
    warn: (...args) => { /* 静默 */ },
    info: (...args) => { /* 静默 */ },
    debug: (...args) => { /* 静默 */ },
  },
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: () => { /* noop */ },
  clearInterval: () => { /* noop */ },
  Promise: Promise,
  JSON: JSON,
  Object: Object,
  Array: Array,
  String: String,
  Number: Number,
  Boolean: Boolean,
  Math: Math,
  Date: Date,
  RegExp: RegExp,
  Error: Error,
  Map: Map,
  Set: Set,
  parseInt: parseInt,
  parseFloat: parseFloat,
  isNaN: isNaN,
  isFinite: isFinite,
  undefined: undefined,
  null: null,
  true: true,
  false: false,
  NaN: NaN,
  Infinity: Infinity,
};

const vmContext = vm.createContext(sandbox);

// 执行所有启用的脚本（名称无关，按内容特征分类执行）
const mvuScripts = [];
const schemaScripts = [];
const injectionScripts = [];
const otherScripts = [];

for (const script of scripts) {
  if (!script.content || !script.content.trim()) continue;
  const content = script.content;
  const name = script.name || '';
  if (name.includes('Zod') || name.includes('var_update') || content.includes('MagVarUpdate')) {
    mvuScripts.push(script);
  } else if (content.includes('registerMvuSchema')) {
    schemaScripts.push(script);
  } else if (content.includes('injectPrompts')) {
    injectionScripts.push(script);
  } else {
    otherScripts.push(script);
  }
}

// Execute in order: MVU runtime → Schema → Keywords → Others
const orderedScripts = [...mvuScripts, ...schemaScripts, ...injectionScripts, ...otherScripts];

for (const script of orderedScripts) {
  const name = script.name || 'unknown';
  if (!script.content || !script.content.trim()) continue;

  const processed = preprocessScript(script.content);

  try {
    const vmScript = new vm.Script(processed, {
      filename: `${name}.js`,
      timeout: 10000,
    });
    vmScript.runInContext(vmContext, { timeout: 10000 });
  } catch (err) {
    // 脚本执行失败不阻塞其他脚本
    if (schemaScripts.includes(script)) {
      console.error(`[run_card_scripts] Schema script "${name}" failed: ${err.message}`);
    }
  }
}

// 执行收集到的 $(callback) 回调
for (const cb of $Callbacks) {
  try {
    cb();
  } catch (err) {
    // 静默
  }
}

// ============================================================
// 从捕获的 Zod schema 提取结构化信息
// ============================================================
// --- Zod v3 内部结构导航辅助 ---
function unwrapDef(def) {
  // 剥掉 ZodDefault / ZodOptional / ZodNullable / ZodEffects 层，返回核心类型 def
  let d = def;
  while (d) {
    const tn = d.typeName;
    if (tn === 'ZodDefault' || tn === 'ZodOptional' || tn === 'ZodNullable') {
      d = d.innerType?._def;
    } else if (tn === 'ZodEffects') {
      d = d.schema?._def;
    } else {
      break;
    }
  }
  return d || {};
}

function isNullable(def) {
  let d = def;
  while (d) {
    if (d.typeName === 'ZodNullable') return true;
    if (d.typeName === 'ZodUnion') {
      if ((d.options || []).some(o => o._def?.typeName === 'ZodNull')) return true;
    }
    // 继续向里剥
    if (d.typeName === 'ZodDefault' || d.typeName === 'ZodOptional' || d.typeName === 'ZodEffects') {
      d = d.innerType?._def || d.schema?._def;
    } else {
      break;
    }
  }
  return false;
}

function zodTypeName(def) {
  const core = unwrapDef(def);
  const tn = core.typeName;
  if (tn === 'ZodString') return 'string';
  if (tn === 'ZodNumber') return 'number';
  if (tn === 'ZodBoolean') return 'boolean';
  if (tn === 'ZodEnum') return 'enum';
  if (tn === 'ZodObject' || tn === 'ZodRecord') return 'object';
  if (tn === 'ZodArray') return 'array';
  if (tn === 'ZodUnion') {
    // 取第一个非 null 类型
    const nonNull = (core.options || []).find(o => o._def?.typeName !== 'ZodNull');
    if (nonNull) return zodTypeName(nonNull._def);
    return 'any';
  }
  if (tn === 'ZodNull') return 'null';
  return 'any';
}

function getShape(field) {
  // 从任意 Zod 类型中提取 .shape（用于 ZodObject/ZodRecord）
  const coreDef = unwrapDef(field._def || {});
  if (coreDef.typeName === 'ZodObject') {
    return field.shape || {};
  }
  if (coreDef.typeName === 'ZodRecord') {
    return null; // Record 没有 .shape，用 .valueType
  }
  // 可能包裹了 ZodDefault/ZodEffects
  // 尝试直接取 .shape
  if (field.shape) return field.shape;
  // 尝试剥一层取 innerType.shape
  if (field._def?.innerType?.shape) return field._def.innerType.shape;
  return null;
}

function getRecordValueType(field) {
  const coreDef = unwrapDef(field._def || {});
  if (coreDef.typeName === 'ZodRecord') {
    return coreDef.valueType;
  }
  // 尝试直接取
  if (field._def?.innerType?._def?.valueType) return field._def.innerType._def.valueType;
  if (field._valueType) return field._valueType;
  return null;
}

function extractZodSchema(schema) {
  if (!schema) return null;

  const result = {
    fields: {},
    constraints: [],
    enums: {},
  };

  try {
    // 剥掉顶层 ZodDefault / ZodEffects，找到 ZodObject
    let objSchema = schema;
    while (objSchema) {
      const tn = objSchema._def?.typeName;
      if (tn === 'ZodDefault' || tn === 'ZodEffects') {
        objSchema = objSchema._def.innerType || objSchema._def.schema;
      } else if (tn === 'ZodObject') {
        break;
      } else {
        break;
      }
    }

    const shape = objSchema?.shape || null;
    if (shape) {
      extractShapeFields(shape, '', result);
    }

    // 提取约束
    extractConstraints(schema, '', result);
  } catch (err) {
    console.error(`[run_card_scripts] schema 提取失败: ${err.message}`);
  }

  return result;
}

function extractShapeFields(shape, prefix, result) {
  for (const [key, field] of Object.entries(shape)) {
    const fieldPath = prefix ? `${prefix}.${key}` : key;
    const def = field._def || {};

    // 记录字段类型（处理 ZodDefault/ZodNullable 包裹）
    extractFieldFromDef(fieldPath, def, result);

    // 剥掉外层包裹（ZodDefault / ZodNullable / ZodOptional / ZodEffects）
    // 找到内部的 ZodObject / ZodRecord 做递归
    let inner = field;
    let innerDef = def;
    while (innerDef) {
      const tn = innerDef.typeName;
      if (tn === 'ZodDefault' || tn === 'ZodNullable' || tn === 'ZodOptional') {
        inner = innerDef.innerType;
        innerDef = inner?._def;
      } else if (tn === 'ZodEffects') {
        // 检查 transform 约束
        extractTransformConstraint(fieldPath, innerDef, result);
        inner = innerDef.schema;
        innerDef = inner?._def;
      } else {
        break;
      }
    }

    // 递归处理嵌套 ZodObject
    if (innerDef?.typeName === 'ZodObject' && innerDef.shape) {
      try {
        extractShapeFields(innerDef.shape(), fieldPath, result);
      } catch (e) {
        try {
          extractShapeFields(innerDef.shape(), fieldPath, result);
        } catch (e2) { /* skip */ }
      }
    }

    // 递归处理 ZodRecord（如 互动对象: z.record(keyType, valueType)）
    if (innerDef?.typeName === 'ZodRecord') {
      // 提取 record key 枚举（如 z.enum(['主导','辅助','第三','劣势'])）
      if (innerDef.keyType) {
        const keyCore = unwrapDef(innerDef.keyType._def);
        if (keyCore.typeName === 'ZodEnum' && keyCore.values) {
          result.enums[`${fieldPath}._keys`] = keyCore.values;
        }
      }
      // 提取 record value 枚举（如 z.enum(['Ti','Te',...])）
      if (innerDef.valueType) {
        const valCore = unwrapDef(innerDef.valueType._def);
        if (valCore.typeName === 'ZodEnum' && valCore.values) {
          result.enums[`${fieldPath}._values`] = valCore.values;
        }
      }

      const valueType = innerDef.valueType;
      if (valueType) {
        // 剥 valueType 的包裹层
        let v = valueType;
        let vDef = v._def;
        while (vDef) {
          const vtn = vDef.typeName;
          if (vtn === 'ZodDefault' || vtn === 'ZodNullable' || vtn === 'ZodOptional') {
            v = vDef.innerType;
            vDef = v?._def;
          } else if (vtn === 'ZodEffects') {
            extractTransformConstraint(`${fieldPath}.*`, vDef, result);
            v = vDef.schema;
            vDef = v?._def;
          } else {
            break;
          }
        }
        if (vDef?.typeName === 'ZodObject' && vDef.shape) {
          try {
            extractShapeFields(vDef.shape(), `${fieldPath}.*`, result);
          } catch (e) {
            try {
              extractShapeFields(vDef.shape(), `${fieldPath}.*`, result);
            } catch (e2) { /* skip */ }
          }
        }
      }
    }
  }
}

function extractFieldFromDef(fieldPath, def, result) {
  const typeName = zodTypeName(def);

  if (typeName === 'enum' && def.values) {
    // 记录枚举值
    result.enums[fieldPath] = def.values;
    result.fields[fieldPath] = {
      type: 'enum',
      nullable: isNullable(def),
    };
  } else {
    result.fields[fieldPath] = {
      type: typeName,
      nullable: isNullable(def),
    };
  }
}

function extractTransformConstraint(fieldPath, def, result) {
  // 识别常见的约束模式
  // 如: _.fromPairs(_.entries(obj).slice(-5)) → max_entries: 5
  // 目前通过检查 effect 的 transform 函数体来识别
  if (def.effect?.transform) {
    const fnStr = def.effect.transform.toString();
    const sliceMatch = fnStr.match(/\.slice\((-?\d+)\)/);
    if (sliceMatch) {
      const n = Math.abs(parseInt(sliceMatch[1]));
      result.constraints.push({
        path: fieldPath,
        rule: 'max_entries',
        value: n,
      });
    }
  }
}

function extractConstraints(schema, prefix, result) {
  // 剥掉顶层包裹
  let s = schema;
  let sDef = s._def;
  while (sDef) {
    const tn = sDef.typeName;
    if (tn === 'ZodDefault' || tn === 'ZodNullable' || tn === 'ZodOptional') {
      s = sDef.innerType;
      sDef = s?._def;
    } else if (tn === 'ZodEffects') {
      s = sDef.schema;
      sDef = s?._def;
    } else {
      break;
    }
  }

  if (sDef?.typeName === 'ZodObject' && sDef.shape) {
    try {
      const shape = sDef.shape();
      for (const [key, field] of Object.entries(shape)) {
        const fieldPath = prefix ? `${prefix}.${key}` : key;
        extractConstraints(field, fieldPath, result);
      }
    } catch (e) { /* skip */ }
  }
}

// ============================================================
// 组装输出: 合并所有捕获的 schema
// ============================================================
let mergedSchema = capturedSchema;
if (capturedSchemas.length > 1) {
  // 多个 schema：合并为单一的顶层 ZodObject
  try {
    const mergedShape = {};
    for (const s of capturedSchemas) {
      let sDef = s?._def;
      let inner = s;
      // 剥掉包裹层（ZodDefault / ZodEffects）
      while (sDef) {
        const tn = sDef.typeName;
        if (tn === 'ZodDefault' || tn === 'ZodEffects') {
          inner = sDef.innerType || sDef.schema;
          sDef = inner?._def;
        } else {
          break;
        }
      }
      if (sDef?.typeName === 'ZodObject' && typeof sDef.shape === 'function') {
        const shape = sDef.shape();
        Object.assign(mergedShape, shape);
      }
    }
    if (Object.keys(mergedShape).length > 0) {
      mergedSchema = z.object(mergedShape);
    }
  } catch (e) {
    // 合并失败时回退到最后一个 schema
    console.error(`[run_card_scripts] Schema merge failed: ${e.message}, falling back to last`);
  }
}

const schemaInfo = extractZodSchema(mergedSchema);
const initvar = generateInitvar(mergedSchema);
output.schema = schemaInfo;
output.initvar = initvar;
output.scope = generateScopeMeta(initvar);
output.injections = extractInjectionRulesFromScripts(output.injections, scripts);

// 如果 initvar 为空但有 injection 数据，尝试从 schema 手动构建
if (!output.initvar && !output.schema) {
  // 完全无法提取 → 标记为失败
  output._parse_failed = true;
}

// 清理：移除注入中的原始内容（太长的文本），只保留结构化字段
output.injections = output.injections.map(inj => ({
  source_path: inj.source_path,
  split_pattern: inj.split_pattern,
  prefix: inj.prefix,
  inject_as: inj.inject_as || 'worldbook_trigger',
  trigger_on: inj.trigger_on || [],
}));

// 输出 JSON 到 stdout
process.stdout.write(JSON.stringify(output, null, 2));
