/**
 * mvu_shared.js — MVU 共享工具模块
 *
 * 被 run_card_scripts.js（导入时提取）和 mvu_server.js（运行时验证）共同引用。
 * 消除两份代码中的 Zod 扩展、lodash 工具、schema 遍历、initvar 生成、scope 元数据的重复。
 */

'use strict';

// ============================================================
// Zod 扩展（来自 mvu_zod.js 的额外 API）
// ============================================================
function extendZod(z) {
  if (!z.partialRecord) {
    z.partialRecord = function (keySchema, valueSchema) {
      let partialValue = valueSchema;
      if (valueSchema && typeof valueSchema.partial === 'function') {
        partialValue = valueSchema.partial();
      }
      return z.record(keySchema, partialValue);
    };
  }
}

// ============================================================
// lodash 风格工具
// ============================================================
function lodashGet(obj, pathStr, defaultValue) {
  if (!obj || !pathStr) return defaultValue;
  const keys = pathStr.split('.');
  let current = obj;
  for (const k of keys) {
    if (current == null || typeof current !== 'object') return defaultValue;
    current = current[k];
  }
  return current !== undefined ? current : defaultValue;
}

function lodashSet(obj, pathStr, value) {
  const keys = pathStr.split('.');
  let current = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i];
    if (!(k in current) || typeof current[k] !== 'object' || current[k] === null) {
      current[k] = {};
    }
    current = current[k];
  }
  current[keys[keys.length - 1]] = value;
  return obj;
}

function makeLodash() {
  return {
    get: lodashGet,
    set: lodashSet,
    entries: (obj) => Object.entries(obj || {}),
    fromPairs: (arr) => Object.fromEntries(arr || []),
    toPairs: (obj) => Object.entries(obj || {}),
    cloneDeep: (obj) => JSON.parse(JSON.stringify(obj || {})),
  };
}

// ============================================================
// Schema 遍历：Zod schema → 结构化元数据 {fields, enums, constraints}
// ============================================================
function generateSchemaMeta(schema) {
  if (!schema) return { fields: {}, constraints: [], enums: {} };
  const result = { fields: {}, constraints: [], enums: {} };

  function walk(shape, prefix) {
    for (const [key, field] of Object.entries(shape)) {
      const fieldPath = prefix ? `${prefix}.${key}` : key;
      let f = field;
      let nullable = false;

      while (f) {
        const tn = f._def?.typeName;
        if (tn === 'ZodNullable') { nullable = true; f = f._def.innerType; }
        else if (tn === 'ZodDefault') f = f._def.innerType;
        else if (tn === 'ZodOptional') f = f._def.innerType;
        else if (tn === 'ZodEffects') { f = f._def.schema; }
        else break;
      }

      if (!f) continue;
      const core = f._def || {};
      let typeName = 'any';
      if (core.typeName === 'ZodString') typeName = 'string';
      else if (core.typeName === 'ZodNumber') typeName = 'number';
      else if (core.typeName === 'ZodBoolean') typeName = 'boolean';
      else if (core.typeName === 'ZodObject') typeName = 'object';
      else if (core.typeName === 'ZodArray') typeName = 'array';
      else if (core.typeName === 'ZodRecord') typeName = 'object';
      else if (core.typeName === 'ZodEnum') { typeName = 'enum'; result.enums[fieldPath] = core.values; }

      result.fields[fieldPath] = { type: typeName, nullable };

      if (core.typeName === 'ZodObject') {
        const childShape = typeof core.shape === 'function' ? core.shape() : (core.shape || {});
        walk(childShape, fieldPath);
      }
      if (core.typeName === 'ZodRecord' && core.valueType) {
        let vt = core.valueType;
        while (vt) {
          const vtn = vt._def?.typeName;
          if (vtn === 'ZodDefault' || vtn === 'ZodNullable' || vtn === 'ZodOptional') vt = vt._def.innerType;
          else if (vtn === 'ZodEffects') vt = vt._def.schema;
          else break;
        }
        if (vt?._def?.typeName === 'ZodObject') {
          const childShape = typeof vt._def.shape === 'function' ? vt._def.shape() : (vt._def.shape || {});
          walk(childShape, `${fieldPath}.*`);
        }
      }
    }
  }

  let s = schema;
  while (s) {
    const tn = s._def?.typeName;
    if (tn === 'ZodDefault' || tn === 'ZodEffects') s = s._def.innerType || s._def.schema;
    else break;
  }

  const shape = typeof s?.shape === 'function' ? s.shape() : (s?.shape || {});
  walk(shape, '');
  return result;
}

// ============================================================
// Initvar 生成：从 Zod schema 递归提取默认值
// ============================================================
function fieldToDefault(field) {
  if (!field) return null;
  const def = field._def || {};

  if (def.typeName === 'ZodDefault') {
    // Get the explicit default value first
    let explicitDefault = undefined;
    try {
      explicitDefault = typeof def.defaultValue === 'function' ? def.defaultValue() : def.defaultValue;
    } catch (e) { /* fall through */ }

    // Recursively process the inner type for nested defaults
    const innerDefault = fieldToDefault(def.innerType);

    // Merge: explicit default takes priority, inner fills missing keys
    if (innerDefault !== null && typeof innerDefault === 'object' && !Array.isArray(innerDefault)) {
      if (explicitDefault !== null && typeof explicitDefault === 'object' && !Array.isArray(explicitDefault)) {
        return Object.assign({}, innerDefault, explicitDefault);
      }
      return innerDefault;
    }
    return explicitDefault !== undefined ? explicitDefault : innerDefault;
  }

  if (def.typeName === 'ZodEffects') return fieldToDefault(def.schema);
  if (def.typeName === 'ZodNullable') return fieldToDefault(def.innerType);
  if (def.typeName === 'ZodOptional') return fieldToDefault(def.innerType);

  if (def.typeName === 'ZodObject') {
    const obj = {};
    const shape = typeof def.shape === 'function' ? def.shape() : (def.shape || {});
    for (const [k, v] of Object.entries(shape)) obj[k] = fieldToDefault(v);
    return obj;
  }

  if (def.typeName === 'ZodRecord') return {};
  if (def.typeName === 'ZodArray') return [];
  if (def.typeName === 'ZodUnion') {
    const nonNull = (def.options || []).find(o => o._def?.typeName !== 'ZodNull');
    return nonNull ? fieldToDefault(nonNull) : null;
  }

  if (def.typeName === 'ZodString' || def.typeName === 'ZodNumber' ||
      def.typeName === 'ZodBoolean' || def.typeName === 'ZodEnum') {
    return null;
  }
  return null;
}

function generateInitvar(schema) {
  if (!schema) return null;

  let obj = schema;
  while (obj) {
    const tn = obj._def?.typeName;
    if (tn === 'ZodDefault' || tn === 'ZodEffects') {
      obj = obj._def.innerType || obj._def.schema;
    } else break;
  }

  const shape = typeof obj?.shape === 'function' ? obj.shape() : (obj?.shape || {});
  const result = {};
  for (const [key, field] of Object.entries(shape)) {
    result[key] = fieldToDefault(field);
  }
  return result;
}

// ============================================================
// Scope 元数据：启发式推断变量作用域（character/chat/session）
// ============================================================
function hasTimeChild(obj) {
  if (!obj || typeof obj !== 'object') return false;
  const timeKeys = ['时间', '日期', '年', '月', '日', '时', '分', '天气', '地点', '位置', '当前日期', '当前时段', '当前地点'];
  for (const k of Object.keys(obj)) {
    if (timeKeys.includes(k)) return true;
  }
  return false;
}

function generateScopeMeta(initvar) {
  const scope = {};
  if (!initvar) return scope;
  for (const key of Object.keys(initvar)) {
    if (key === '时间' || key === '日期' || key === '地点' || key === '天气') {
      scope[key] = 'chat';
    } else if (key === '世界设定' || key === '世界观' || key === '性癖' || key === '场景环境') {
      scope[key] = 'session';
    } else if (key === '世界' || key === '场景') {
      scope[key] = (initvar[key] && hasTimeChild(initvar[key])) ? 'chat' : 'session';
    } else {
      scope[key] = 'character';
    }
  }
  return scope;
}

// ============================================================
// 注入规则提取：从 injection script 源码中解析配置
// ============================================================
function extractInjectionRulesFromScripts(scripts) {
  for (const script of scripts) {
    const content = script.content || '';
    if (!content.includes('injectPrompts') && !content.includes('extractKinkKeywords')) continue;

    const getMatch = content.match(/_\.get\(\s*\w+\s*,\s*['"]([^'"]+)['"]\s*\)/);
    const sourcePath = getMatch ? getMatch[1] : null;

    const splitMatch = content.match(/\.split\(\s*(\/[^\/]+\/[gimsu]*)\s*\)/);
    const splitPattern = splitMatch ? splitMatch[1] : null;

    const prefixMatch = content.match(/startsWith\(['"]([^'"]+)['"]\)/);
    const prefix = prefixMatch ? prefixMatch[1] : null;

    const triggerOn = [];
    const eventRegex = /eventOn\(\s*tavern_events\.(\w+)\s*,/g;
    let em;
    while ((em = eventRegex.exec(content)) !== null) {
      triggerOn.push(em[1].toLowerCase());
    }
    if (content.includes('Mvu.events.VARIABLE_UPDATE_ENDED')) {
      triggerOn.push('variable_update');
    }

    return [{
      source_path: sourcePath || '世界设定.性癖',
      split_pattern: splitPattern ? String(splitPattern) : '[、,，\\n]',
      prefix: prefix || '性癖',
      inject_as: 'worldbook_trigger',
      trigger_on: triggerOn.length > 0 ? triggerOn : ['variable_update', 'generation_after_commands'],
    }];
  }
  return [];
}

// ============================================================
// 导出
// ============================================================
module.exports = {
  extendZod,
  makeLodash,
  lodashGet,
  lodashSet,
  generateSchemaMeta,
  generateInitvar,
  fieldToDefault,
  generateScopeMeta,
  hasTimeChild,
  extractInjectionRulesFromScripts,
};
