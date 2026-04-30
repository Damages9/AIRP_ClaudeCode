/* _st_shims.js — SillyTavern / MVU API compatibility shims.
   Loaded once in index.html.  Makes card-author beautify scripts
   run unchanged by providing the globals they expect.

   IMPORTANT: Load AFTER jQuery / lodash CDN scripts so we can
   detect whether the real libraries are present and avoid
   overwriting them.

   Covers:
     getAllVariables()        → reads window.MVU_VARIABLES
     _ (lodash fallback)     → extended if real lodash not loaded
     $ (jQuery)              → real jQuery via CDN; shim only as fallback
     getvar() / getwi()      → MVU / worldbook accessors
     waitGlobalInitialized() → resolves immediately
     eventOn / eventEmit     → custom event bus with ST event aliases
     Mvu namespace           → Mvu.events.*
     errorCatched()          → try/catch wrapper
*/

(function () {
  'use strict';

  /* ─── jQuery bridge ───
     If real jQuery is loaded (CDN), we keep it untouched.
     Only install the MiniJQ subset when jQuery is missing. */
  var _hasRealJQuery = (typeof window.jQuery !== 'undefined');

  if (!_hasRealJQuery) {
    /* ─── jQuery subset ─── */
    (function () {
      function MiniJQ(selectorOrEl, context) {
        var els = [];

        if (selectorOrEl == null) {
          els = [];
        } else if (typeof selectorOrEl === 'function') {
          var self = new MiniJQ(document);
          self.ready(selectorOrEl);
          return self;
        } else if (selectorOrEl instanceof MiniJQ) {
          return selectorOrEl;
        } else if (typeof selectorOrEl === 'string') {
          var root = context ? (context instanceof MiniJQ ? context[0] : context) : document;
          try {
            var nodeList = root.querySelectorAll(selectorOrEl);
            for (var i = 0; i < nodeList.length; i++) els.push(nodeList[i]);
          } catch (_) { /* bad selector */ }
        } else if (selectorOrEl && (selectorOrEl.nodeType === 1 || selectorOrEl.nodeType === 9)) {
          els = [selectorOrEl];
        } else if (selectorOrEl && selectorOrEl.length !== undefined && typeof selectorOrEl !== 'string') {
          for (var j = 0; j < selectorOrEl.length; j++) {
            if (selectorOrEl[j] && selectorOrEl[j].nodeType) els.push(selectorOrEl[j]);
          }
        }

        this.length = els.length;
        for (var k = 0; k < els.length; k++) this[k] = els[k];
      }

      MiniJQ.prototype = {
        ready: function (fn) {
          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
          } else { fn(); }
          return this;
        },
        find: function (sel) { return new MiniJQ(sel, this[0]); },
        closest: function (sel) {
          return this[0] && this[0].closest ? new MiniJQ(this[0].closest(sel)) : new MiniJQ();
        },
        parent: function () { return this[0] ? new MiniJQ(this[0].parentNode) : new MiniJQ(); },
        text: function (val) {
          if (arguments.length === 0) return this[0] ? this[0].textContent : '';
          for (var i = 0; i < this.length; i++) this[i].textContent = val;
          return this;
        },
        html: function (val) {
          if (arguments.length === 0) return this[0] ? this[0].innerHTML : '';
          for (var i = 0; i < this.length; i++) this[i].innerHTML = val;
          return this;
        },
        val: function (val) {
          if (arguments.length === 0) return this[0] ? (this[0].value || '') : '';
          for (var i = 0; i < this.length; i++) this[i].value = val;
          return this;
        },
        css: function (prop, val) {
          for (var i = 0; i < this.length; i++) this[i].style.setProperty(prop, val);
          return this;
        },
        on: function (event, selector, fn) {
          if (arguments.length === 2 && typeof selector === 'function') { fn = selector; selector = null; }
          for (var i = 0; i < this.length; i++) {
            var el = this[i];
            if (selector) {
              el.addEventListener(event, function (e) {
                var target = e.target.closest(selector);
                if (target && el.contains(target)) fn.call(target, e);
              });
            } else {
              el.addEventListener(event, fn);
            }
          }
          return this;
        },
        addClass: function (names) {
          var cls = names.split(/\s+/);
          for (var i = 0; i < this.length; i++) {
            for (var j = 0; j < cls.length; j++) this[i].classList.add(cls[j]);
          }
          return this;
        },
        removeClass: function (names) {
          var cls = names.split(/\s+/);
          for (var i = 0; i < this.length; i++) {
            for (var j = 0; j < cls.length; j++) this[i].classList.remove(cls[j]);
          }
          return this;
        },
        toggleClass: function (name) {
          for (var i = 0; i < this.length; i++) this[i].classList.toggle(name);
          return this;
        },
        hasClass: function (name) {
          return this[0] ? this[0].classList.contains(name) : false;
        }
      };

      window.$ = function (sel, ctx) { return new MiniJQ(sel, ctx); };
    })();
  }
  /* else: real jQuery is loaded, keep it. */

  /* ─── lodash bridge ───
     If real lodash (with _.cloneDeep) is loaded, keep it.
     Otherwise provide a minimal fallback with the most-used methods. */
  var _hasRealLodash = (typeof window._ !== 'undefined' && typeof window._.cloneDeep === 'function');

  if (!_hasRealLodash) {
    window._ = {
      get: function (obj, path, fallback) {
        if (!obj || typeof obj !== 'object') return fallback;
        var keys = String(path).split('.');
        var cur = obj;
        for (var i = 0; i < keys.length; i++) {
          if (cur == null || typeof cur !== 'object') return fallback;
          cur = cur[keys[i]];
        }
        return cur !== undefined ? cur : fallback;
      },
      set: function (obj, path, value) {
        if (!obj || typeof obj !== 'object') return obj;
        var keys = String(path).split('.');
        var cur = obj;
        for (var i = 0; i < keys.length - 1; i++) {
          var k = keys[i];
          if (!(k in cur) || typeof cur[k] !== 'object' || cur[k] === null) cur[k] = {};
          cur = cur[k];
        }
        cur[keys[keys.length - 1]] = value;
        return obj;
      },
      cloneDeep: function (obj) { return JSON.parse(JSON.stringify(obj)); },
      defaults: function (obj) {
        for (var i = 1; i < arguments.length; i++) {
          var src = arguments[i];
          if (!src) continue;
          for (var k in src) {
            if (Object.prototype.hasOwnProperty.call(src, k) && obj[k] === undefined) {
              obj[k] = src[k];
            }
          }
        }
        return obj;
      },
      merge: function (obj) {
        for (var i = 1; i < arguments.length; i++) {
          var src = arguments[i];
          if (!src) continue;
          for (var k in src) {
            if (!Object.prototype.hasOwnProperty.call(src, k)) continue;
            if (typeof src[k] === 'object' && src[k] !== null && !Array.isArray(src[k]) &&
                typeof obj[k] === 'object' && obj[k] !== null && !Array.isArray(obj[k])) {
              window._.merge(obj[k], src[k]);
            } else {
              obj[k] = window._.cloneDeep(src[k]);
            }
          }
        }
        return obj;
      },
      isEqual: function (a, b) { return JSON.stringify(a) === JSON.stringify(b); },
      each: function (collection, iteratee) {
        if (!collection) return collection;
        if (Array.isArray(collection)) {
          for (var i = 0; i < collection.length; i++) iteratee(collection[i], i, collection);
        } else {
          for (var k in collection) {
            if (Object.prototype.hasOwnProperty.call(collection, k)) iteratee(collection[k], k, collection);
          }
        }
        return collection;
      },
      maxBy: function (arr, fn) {
        if (!arr || !arr.length) return undefined;
        var best = arr[0], bestVal = fn(arr[0]);
        for (var i = 1; i < arr.length; i++) { var v = fn(arr[i]); if (v > bestVal) { best = arr[i]; bestVal = v; } }
        return best;
      },
      minBy: function (arr, fn) {
        if (!arr || !arr.length) return undefined;
        var best = arr[0], bestVal = fn(arr[0]);
        for (var i = 1; i < arr.length; i++) { var v = fn(arr[i]); if (v < bestVal) { best = arr[i]; bestVal = v; } }
        return best;
      },
      isEmpty: function (v) { return !v || (Array.isArray(v) ? v.length === 0 : Object.keys(v).length === 0); },
      isNumber: function (v) { return typeof v === 'number' && !isNaN(v); },
      isString: function (v) { return typeof v === 'string'; },
      isArray: Array.isArray,
      isObject: function (v) { return v !== null && typeof v === 'object'; },
      keys: Object.keys,
      values: function (v) { return Object.keys(v).map(function (k) { return v[k]; }); },
      entries: function (v) { return Object.keys(v).map(function (k) { return [k, v[k]]; }); },
      template: function (str) {
        return function (data) {
          return str.replace(/\{\{(\w+)\}\}/g, function (_, key) {
            return data && data[key] !== undefined ? data[key] : '';
          });
        };
      }
    };
  }

  /* ─── GetAllVariables ─── */
  window._deepReplaceUser = function (obj, name) {
    if (typeof obj === 'string') return obj.split('{{user}}').join(name);
    if (Array.isArray(obj)) {
      var arr = [];
      for (var i = 0; i < obj.length; i++) arr[i] = window._deepReplaceUser(obj[i], name);
      return arr;
    }
    if (obj && typeof obj === 'object') {
      var result = {};
      for (var key in obj) {
        if (Object.prototype.hasOwnProperty.call(obj, key)) result[key] = window._deepReplaceUser(obj[key], name);
      }
      return result;
    }
    return obj;
  };

  window.getAllVariables = function () {
    var vars = window.MVU_VARIABLES || {};
    var name = (typeof window.userName === 'function') ? window.userName() : '';
    // Wrap in stat_data if not already present (compat with both
    // SillyTavern-style {stat_data: {...}} and flat MVU_VARIABLES)
    if (!vars.stat_data) {
      vars = { stat_data: vars };
    }
    if (!name || name === '{{user}}') return vars;
    return window._deepReplaceUser(vars, name);
  };

  /* ─── SillyTavern context stub ───
     Card scripts in the regex pipeline (e.g. init_terminal radar
     chart) may probe window.SillyTavern.getContext() to check
     whether they are running inside SillyTavern.  Provide a stub
     that reports "not in ST" so the fallback code paths are taken. */
  window.SillyTavern = window.SillyTavern || {
    getContext: function () { return null; }
  };

  /* ─── getvar / getwi (MVU / worldbook accessors) ─── */
  window.getvar = function (key, options) {
    var vars = window.getAllVariables();
    var sd = vars.stat_data || vars;
    var val = window._.get(sd, key);
    return val !== undefined ? val : (options && options.defaults !== undefined ? options.defaults : undefined);
  };

  window.getwi = function (worldinfo, title) {
    // In our system, worldbook entries are fetched server-side via Grep.
    // This client-side stub signals the function exists but returns empty.
    return '';
  };

  /* ─── waitGlobalInitialized ─── */
  window.waitGlobalInitialized = function (_name) {
    return Promise.resolve();
  };

  /* ─── eventOn / eventEmit (pub-sub with ST event aliases) ─── */
  (function () {
    var listeners = {};

    // Map ST event names to our internal names
    var EVENT_ALIASES = {
      'message_received': ['MESSAGE_RECEIVED'],
      'char_message_rendered': ['CHARACTER_MESSAGE_RENDERED'],
      'user_message_rendered': ['USER_MESSAGE_RENDERED'],
      'generation_end': ['GENERATION_ENDED'],
      'app_ready': ['APP_READY'],
      'mag_variable_update_ended': ['VARIABLE_UPDATE_ENDED'],
      'mag_variable_update_started': ['VARIABLE_UPDATE_STARTED'],
      'mag_variable_initialized': ['VARIABLE_INITIALIZED']
    };

    window.eventOn = function (event, fn) {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(fn);
      // Also register on aliases
      var aliases = EVENT_ALIASES[event];
      if (aliases) {
        for (var a = 0; a < aliases.length; a++) {
          if (!listeners[aliases[a]]) listeners[aliases[a]] = [];
          listeners[aliases[a]].push(fn);
        }
      }
      return { stop: function () { window.eventRemoveListener(event, fn); } };
    };

    window.eventEmit = function (event) {
      var args = Array.prototype.slice.call(arguments, 1);
      var fns = listeners[event] || [];
      for (var i = 0; i < fns.length; i++) {
        try { fns[i].apply(null, args); } catch (e) { console.error('[eventEmit]', event, e); }
      }
      // Also emit on aliases
      var aliases = EVENT_ALIASES[event];
      if (aliases) {
        for (var a = 0; a < aliases.length; a++) {
          var aliasFns = listeners[aliases[a]] || [];
          for (var j = 0; j < aliasFns.length; j++) {
            try { aliasFns[j].apply(null, args); } catch (e) { console.error('[eventEmit]', aliases[a], e); }
          }
        }
      }
    };

    window.eventRemoveListener = function (event, fn) {
      var arr = listeners[event];
      if (!arr) return;
      var idx = arr.indexOf(fn);
      if (idx >= 0) arr.splice(idx, 1);
    };
  })();

  /* ─── Mvu namespace ─── */
  window.Mvu = {
    events: {
      VARIABLE_UPDATE_ENDED: 'mag_variable_update_ended',
      VARIABLE_UPDATE_STARTED: 'mag_variable_update_started',
      VARIABLE_INITIALIZED: 'mag_variable_initialized'
    }
  };

  /* ─── errorCatched ─── */
  window.errorCatched = function (fn) {
    return function () {
      try {
        var result = fn.apply(this, arguments);
        if (result && typeof result.catch === 'function') {
          result.catch(function (e) { console.error('[beautify-panel]', e); });
        }
      } catch (e) {
        console.error('[beautify-panel]', e);
      }
    };
  };

})();
