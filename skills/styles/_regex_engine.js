/**
 * _regex_engine.js — 酒馆兼容正则引擎
 *
 * 独立实现 SillyTavern getRegexedString() 核心逻辑。
 * 不依赖 ST 设置系统 / 角色系统，仅需要 regex scripts 数据。
 *
 * 对应 ST 源码: /public/scripts/extensions/regex/engine.js
 */

(function () {
  'use strict';

  /* ─── Placement 枚举 ─── */
  var REGEX_PLACEMENT = {
    MD_DISPLAY: 0,
    USER_INPUT: 1,
    AI_OUTPUT: 2,
    SLASH_COMMAND: 3,
    WORLD_INFO: 5,
    REASONING: 6
  };

  /* ─── LRU 正则缓存 ─── */
  var MAX_CACHE_SIZE = 1000;
  var _regexCache = new Map();
  var _cacheOrder = [];

  function getCachedRegex(pattern, flags) {
    var key = pattern + '\x00' + (flags || '');
    if (_regexCache.has(key)) {
      return _regexCache.get(key);
    }
    var re;
    try {
      re = new RegExp(pattern, flags || '');
    } catch (e) {
      return null;
    }
    if (_cacheOrder.length >= MAX_CACHE_SIZE) {
      var oldest = _cacheOrder.shift();
      _regexCache.delete(oldest);
    }
    _cacheOrder.push(key);
    _regexCache.set(key, re);
    return re;
  }

  /* ─── 内部脚本存储 ─── */
  var _scripts = [];

  /**
   * 标准化内部格式的脚本数据。
   * 从 REGEX_SCRIPTS 的简化格式:
   *   { name, find, replace, flags, markdownOnly }
   * 转换为引擎内部格式:
   *   { id, scriptName, findRegex, replaceString, flags, trimStrings,
   *     placement[], disabled, markdownOnly, promptOnly,
   *     runOnEdit, substituteRegex, minDepth, maxDepth }
   */
  function normalizeScript(raw, index) {
    return {
      id: raw.id || ('card_' + index),
      scriptName: raw.name || raw.scriptName || ('Script ' + index),
      findRegex: raw.find || raw.findRegex || '',
      replaceString: raw.replace || raw.replaceString || '',
      flags: raw.flags || '',
      trimStrings: raw.trimStrings || [],
      placement: raw.placement || [2],  // 默认仅 AI_OUTPUT，与 ST 行为一致
      disabled: !!raw.disabled,
      markdownOnly: !!raw.markdownOnly,
      promptOnly: !!raw.promptOnly,
      runOnEdit: !!raw.runOnEdit,
      substituteRegex: raw.substituteRegex || 0,
      minDepth: raw.minDepth != null ? raw.minDepth : null,
      maxDepth: raw.maxDepth != null ? raw.maxDepth : null
    };
  }

  /* ─── 公开 API ─── */

  /**
   * 注册脚本到引擎。
   * @param {Array} rawScripts - REGEX_SCRIPTS 数组（简化格式）
   */
  function registerRegexScripts(rawScripts) {
    if (!rawScripts || !rawScripts.length) {
      _scripts = [];
      return;
    }
    _scripts = rawScripts.map(function (s, i) {
      return normalizeScript(s, i);
    });
  }

  /**
   * 对字符串执行全部匹配的正则脚本。
   *
   * @param {string} rawString - 输入文本
   * @param {number} placement - REGEX_PLACEMENT 值
   * @param {Object} [opts]
   * @param {boolean} [opts.isMarkdown] - 是否用于显示端
   * @param {boolean} [opts.isPrompt]   - 是否用于提示词端
   * @param {boolean} [opts.isEdit]     - 是否编辑模式
   * @param {number} [opts.depth]       - 上下文深度
   * @returns {string} 转换后的文本
   */
  function getRegexedString(rawString, placement, opts) {
    if (typeof rawString !== 'string' || !rawString) return rawString;
    if (placement == null) return rawString;

    opts = opts || {};
    var isMarkdown = !!opts.isMarkdown;
    var isPrompt = !!opts.isPrompt;
    var isEdit = !!opts.isEdit;
    var depth = opts.depth;

    var result = rawString;

    for (var i = 0; i < _scripts.length; i++) {
      var script = _scripts[i];

      // --- 第 1 层: markdownOnly / promptOnly 匹配 ---
      // 和酒馆逻辑完全一致:
      //   markdownOnly=true  → 仅在 isMarkdown 时应用
      //   promptOnly=true    → 仅在 isPrompt 时应用
      //   两者都是 false     → 仅在两者都不是时应用（通用模式）
      //   两者都是 true      → 在 isMarkdown 或 isPrompt 时都应用
      if (script.markdownOnly && script.promptOnly) {
        if (!isMarkdown && !isPrompt) continue;
      } else if (script.markdownOnly) {
        if (!isMarkdown) continue;
      } else if (script.promptOnly) {
        if (!isPrompt) continue;
      } else {
        if (isMarkdown || isPrompt) continue;
      }

      // --- 第 2 层: onEdit 守卫 ---
      if (isEdit && !script.runOnEdit) continue;

      // --- 第 3 层: 深度过滤 ---
      if (depth != null) {
        if (script.minDepth != null && depth < script.minDepth) continue;
        if (script.maxDepth != null && depth > script.maxDepth) continue;
      }

      // --- 第 4 层: placement 匹配 ---
      if (script.placement.length && script.placement.indexOf(placement) === -1) continue;

      // --- 执行 ---
      result = runRegexScript(script, result);
    }

    return result;
  }

  /**
   * 对输入字符串执行单个脚本的查找/替换。
   */
  function runRegexScript(script, inputString) {
    if (!script.findRegex) return inputString;
    if (!inputString) return inputString;

    var re = getCachedRegex(script.findRegex, script.flags);
    if (!re) return inputString;

    var replaceStr = script.replaceString;
    var trimStrings = script.trimStrings || [];

    // 重置 lastIndex（全局正则跨调用共享状态）
    re.lastIndex = 0;

    var result = inputString.replace(re, function (match) {
      var replacement = replaceStr;

      // 处理 {{match}} → 整个匹配
      replacement = replacement.replace(/\{\{match\}\}/g, match);

      // 处理 $1, $2 ... → 捕获组
      for (var g = 1; g < arguments.length - 2; g++) {
        var groupValue = arguments[g];
        if (groupValue == null) groupValue = '';

        // 应用 trimStrings 到捕获组值
        if (trimStrings.length) {
          for (var t = 0; t < trimStrings.length; t++) {
            var trim = trimStrings[t];
            if (trim && groupValue.indexOf(trim) !== -1) {
              groupValue = groupValue.split(trim).join('');
            }
          }
        }

        replacement = replacement.split('$' + g).join(groupValue);
      }

      return replacement;
    });

    // 对最终结果应用 trimStrings 裁剪（匹配 ST 行为）
    if (trimStrings.length) {
      for (var t2 = 0; t2 < trimStrings.length; t2++) {
        var ts = trimStrings[t2];
        if (!ts) continue;
        while (result.indexOf(ts) === 0) {
          result = result.substring(ts.length);
        }
        while (result.length >= ts.length && result.lastIndexOf(ts) === result.length - ts.length) {
          result = result.substring(0, result.length - ts.length);
        }
      }
    }

    return result;
  }

  /* ─── 挂载到 window ─── */
  window.REGEX_PLACEMENT = REGEX_PLACEMENT;
  window.registerRegexScripts = registerRegexScripts;
  window.getRegexedString = getRegexedString;
  window.runRegexScript = runRegexScript;

})();
